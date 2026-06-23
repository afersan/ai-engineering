"""Streamlit product UI for the estimator.

Streamlit acts as an HTTP client of the FastAPI service: it POSTs to
``/api/v1/estimate`` with a typed ``EstimationRequest`` JSON body.
The endpoint URL is read from ``ESTIMATOR_API_BASE_URL`` (loaded from
the same ``.env`` as the API).
"""

from __future__ import annotations

import os

import httpx
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

API_BASE_URL = os.getenv("ESTIMATOR_API_BASE_URL", "http://localhost:8000")
ESTIMATE_ENDPOINT = f"{API_BASE_URL.rstrip('/')}/api/v1/estimate"

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

st.set_page_config(page_title="Software Estimator", page_icon="📊")
st.title("Software Estimator")
st.caption(
    "Describe your project with structured parameters. The FastAPI service "
    "renders a versioned Jinja2 prompt and returns the estimation."
)

with st.form("estimation_form"):
    description = st.text_area(
        "Project description",
        placeholder="Describe scope, integrations, deadlines, and constraints…",
        height=200,
    )
    project_type_label = st.selectbox("Project type", list(PROJECT_TYPE_OPTIONS.keys()))
    detail_level_label = st.selectbox("Detail level", list(DETAIL_LEVEL_OPTIONS.keys()))
    output_format_label = st.selectbox("Output format", list(OUTPUT_FORMAT_OPTIONS.keys()))
    submitted = st.form_submit_button("Estimate", type="primary")

if submitted:
    if len(description.strip()) < 20:
        st.error("Description must be at least 20 characters.")
    else:
        payload = {
            "description": description.strip(),
            "project_type": PROJECT_TYPE_OPTIONS[project_type_label],
            "detail_level": DETAIL_LEVEL_OPTIONS[detail_level_label],
            "output_format": OUTPUT_FORMAT_OPTIONS[output_format_label],
        }
        with st.spinner("Generating estimation…"):
            try:
                response = httpx.post(
                    ESTIMATE_ENDPOINT,
                    json=payload,
                    timeout=httpx.Timeout(120.0, connect=10.0),
                )
            except httpx.HTTPError as exc:
                st.error(f"Could not reach the API: {exc}")
            else:
                if response.status_code == 422:
                    st.error(f"Validation error: {response.json()}")
                elif response.status_code >= 400:
                    st.error(f"API error ({response.status_code}): {response.text}")
                else:
                    body = response.json()
                    st.markdown(body["text"])
                    st.caption(f"Prompt version: {body['prompt_version']}")
