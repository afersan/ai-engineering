"""Interfaz conversacional Streamlit para el estimador de software."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator

import httpx
import streamlit as st
from dotenv import load_dotenv

from app.context.examples import ESTIMATION_EXAMPLES
from app.services.llm_service import build_system_prompt

load_dotenv()

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
STREAM_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/api/v1/estimate/stream"

st.set_page_config(
    page_title="Estimador de Software",
    page_icon="📊",
    layout="wide",
)


def _init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "last_meta" not in st.session_state:
        st.session_state.last_meta = None


def _stream_from_api(transcription: str) -> Iterator[str]:
    """Consume SSE from FastAPI and yield text chunks; stores meta in session_state."""
    with httpx.Client(timeout=120.0) as client:
        with client.stream(
            "POST",
            STREAM_ENDPOINT,
            json={"transcription": transcription},
            headers={"Accept": "text/event-stream"},
        ) as response:
            response.raise_for_status()
            event_type = "message"
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    raw = line[5:].strip()
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        data = raw
                    if event_type == "meta":
                        st.session_state.last_meta = data if isinstance(data, dict) else json.loads(data)
                    elif event_type == "error":
                        raise RuntimeError(str(data))
                    else:
                        yield str(data)
                    event_type = "message"


def _render_sidebar() -> None:
    with st.sidebar:
        st.header("Contexto CAG")
        st.subheader("System prompt")
        st.text_area(
            "Prompt activo",
            value=build_system_prompt(),
            height=200,
            disabled=True,
            label_visibility="collapsed",
        )

        st.subheader("Ejemplos de referencia")
        for idx, example in enumerate(ESTIMATION_EXAMPLES, start=1):
            with st.expander(f"Ejemplo {idx}"):
                st.markdown(example["estimation"])

        st.divider()
        st.subheader("Última llamada")
        meta = st.session_state.get("last_meta")
        if meta:
            st.metric("Modelo", meta.get("model", "—"))
            usage = meta.get("usage", {})
            st.metric("Tokens entrada", usage.get("input_tokens", 0))
            st.metric("Tokens salida", usage.get("output_tokens", 0))
            latency = meta.get("latency_ms")
            st.metric("Latencia (ms)", f"{latency:.1f}" if latency is not None else "—")
            st.caption(
                f"Cache: {'sí' if meta.get('cache_hit') else 'no'} · "
                f"Fallback: {'sí' if meta.get('fallback_used') else 'no'}"
            )
        else:
            st.info("Envía una transcripción para ver métricas.")


def main() -> None:
    _init_session_state()
    _render_sidebar()

    st.title("Estimador de Software con IA")
    st.caption(
        "Pega una transcripción de reunión y obtén una estimación detallada en streaming."
    )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Pega la transcripción de la reunión..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            try:
                response_text = st.write_stream(_stream_from_api(prompt))
            except httpx.HTTPError as exc:
                st.error(f"Error al conectar con la API: {exc}")
                return
            except RuntimeError as exc:
                st.error(str(exc))
                return

        st.session_state.messages.append({"role": "assistant", "content": response_text})


if __name__ == "__main__":
    main()
