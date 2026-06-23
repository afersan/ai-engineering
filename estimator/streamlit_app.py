# estimator/streamlit_app.py
"""Streamlit UI with conversational session support.

New features:
- Session creation and persistence in st.session_state
- File attachment upload (PDF, Word docs)
- Project metadata display panel
- Multi-turn conversation history display
- "New Conversation" button to reset session
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx
import streamlit as st
from dotenv import load_dotenv

from app.schemas.estimation import MAX_DESCRIPTION_LENGTH, MAX_TRANSCRIPT_LENGTH

load_dotenv()

API_BASE_URL = os.getenv("ESTIMATOR_API_BASE_URL", "http://localhost:8000")
SESSIONS_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/api/v1/sessions"

PROJECT_TYPE_OPTIONS = {
    "Mobile app": "mobile_app",
    "Web SaaS": "web_saas",
    "Internal tool": "internal_tool",
    "Data pipeline": "data_pipeline",
}

DETAIL_LEVEL_OPTIONS = {
    "Summary": "summary",
    "Medium": "medium",
    "Detailed": "detailed",
}

OUTPUT_FORMAT_OPTIONS = {
    "Phases table": "phases_table",
    "Line items": "line_items",
    "Narrative": "narrative",
}


def format_validation_error(response: httpx.Response) -> str:
    """Convierte errores 422 de FastAPI en mensajes legibles."""
    try:
        payload = response.json()
    except ValueError:
        return response.text

    detail = payload.get("detail")
    if isinstance(detail, str):
        return detail

    if isinstance(detail, list):
        messages = []
        for item in detail:
            field = ".".join(str(part) for part in item.get("loc", []) if part != "body")
            msg = item.get("msg", "Error de validación")
            if field == "transcript" and "at most" in msg:
                messages.append(
                    f"La transcripción supera el límite de {MAX_TRANSCRIPT_LENGTH:,} caracteres "
                    f"(actual: {len(item.get('input', '')):,}). "
                    "Acorta el texto o mueve detalle a un adjunto PDF/Word."
                )
            elif field:
                messages.append(f"{field}: {msg}")
            else:
                messages.append(msg)
        return " ".join(messages)

    return str(payload)

st.set_page_config(page_title="Software Estimator (Session 05)", page_icon="💬", layout="wide")


def create_new_session() -> str:
    """Call API to create new session and return session_id."""
    try:
        response = httpx.post(SESSIONS_ENDPOINT, timeout=10.0)
        response.raise_for_status()
        return response.json()["session_id"]
    except httpx.HTTPError as exc:
        st.error(f"Failed to create session: {exc}")
        return None


# Initialize session state
if "session_id" not in st.session_state:
    st.session_state.session_id = create_new_session()
    st.session_state.conversation_history = []
    st.session_state.project_metadata = {}

st.title("💬 Software Estimator (Conversational)")
st.caption(
    "Multi-turn estimation with file attachments and project memory. "
    f"Session: `{st.session_state.session_id[:8]}...`"
)

# Sidebar: Project metadata display
with st.sidebar:
    st.subheader("📋 Project Context")

    if st.button("🔄 New Conversation", type="secondary"):
        st.session_state.session_id = create_new_session()
        st.session_state.conversation_history = []
        st.session_state.project_metadata = {}
        st.rerun()

    metadata = st.session_state.project_metadata
    if metadata:
        if metadata.get("project_name"):
            st.write(f"**Project:** {metadata['project_name']}")
        if metadata.get("assumed_team_size"):
            st.write(f"**Team size:** {metadata['assumed_team_size']}")
        if metadata.get("mentioned_technologies"):
            st.write(f"**Tech stack:** {', '.join(metadata['mentioned_technologies'])}")
        if metadata.get("agreed_scope"):
            st.write(f"**Scope:** {metadata['agreed_scope']}")
    else:
        st.info("No project context yet. Submit your first estimation to start.")

# Main form
with st.form("estimation_form"):
    transcript = st.text_area(
        "Describe your request",
        placeholder="Add a login feature with OAuth...",
        height=150,
        help=f"Máximo {MAX_TRANSCRIPT_LENGTH:,} caracteres. Para textos largos, adjunta un PDF o Word.",
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        project_type_label = st.selectbox("Project type", list(PROJECT_TYPE_OPTIONS.keys()))
    with col2:
        detail_level_label = st.selectbox("Detail level", list(DETAIL_LEVEL_OPTIONS.keys()))
    with col3:
        output_format_label = st.selectbox("Output format", list(OUTPUT_FORMAT_OPTIONS.keys()))

    uploaded_files = st.file_uploader(
        "Attach documents (optional)",
        type=["pdf", "docx", "doc"],
        accept_multiple_files=True,
    )

    submitted = st.form_submit_button("📤 Send", type="primary")

if submitted:
    cleaned_transcript = transcript.strip()
    if len(cleaned_transcript) < 20:
        st.error("La petición debe tener al menos 20 caracteres.")
    elif len(cleaned_transcript) > MAX_TRANSCRIPT_LENGTH:
        st.error(
            f"La transcripción tiene {len(cleaned_transcript):,} caracteres. "
            f"El máximo permitido es {MAX_TRANSCRIPT_LENGTH:,}. "
            "Acorta el texto o adjunta un documento con el detalle."
        )
    else:
        estimate_url = f"{SESSIONS_ENDPOINT}/{st.session_state.session_id}/estimate"

        # Prepare form data
        form_data = {
            "transcript": cleaned_transcript,
            "project_type": PROJECT_TYPE_OPTIONS[project_type_label],
            "detail_level": DETAIL_LEVEL_OPTIONS[detail_level_label],
            "output_format": OUTPUT_FORMAT_OPTIONS[output_format_label],
        }

        # Prepare files for multipart upload
        files = []
        if uploaded_files:
            for uploaded_file in uploaded_files:
                files.append(
                    ("attachments", (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type))
                )

        with st.spinner("Generating estimation..."):
            try:
                response = httpx.post(
                    estimate_url,
                    data=form_data,
                    files=files if files else None,
                    timeout=httpx.Timeout(120.0, connect=10.0),
                )
            except httpx.HTTPError as exc:
                st.error(f"Could not reach the API: {exc}")
            else:
                if response.status_code == 404:
                    st.error("Session expired. Click 'New Conversation' to start fresh.")
                elif response.status_code == 422:
                    st.error(f"Error de validación: {format_validation_error(response)}")
                elif response.status_code >= 400:
                    st.error(f"API error ({response.status_code}): {response.text}")
                else:
                    body = response.json()

                    # Update session state
                    st.session_state.conversation_history.append({
                        "turn": body["turn_number"],
                        "user": transcript,
                        "assistant": body["estimation"],
                        "attachments": [f.name for f in uploaded_files] if uploaded_files else [],
                    })
                    st.session_state.project_metadata = body["project_metadata"]

                    st.rerun()

# Display conversation history
if st.session_state.conversation_history:
    st.subheader("💬 Conversation")

    for turn_data in st.session_state.conversation_history:
        with st.container():
            st.markdown(f"**Turn {turn_data['turn']}**")

            # User message
            with st.chat_message("user"):
                st.write(turn_data["user"])
                if turn_data["attachments"]:
                    st.caption(f"📎 Attachments: {', '.join(turn_data['attachments'])}")

            # Assistant response
            with st.chat_message("assistant"):
                st.markdown(turn_data["assistant"])

            st.divider()
