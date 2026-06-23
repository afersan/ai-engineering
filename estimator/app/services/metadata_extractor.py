"""Project metadata extraction from conversation turns.

Uses a dedicated LLM call with structured output to extract project facts.
Alternative approach: regex/heuristic parsing (faster, cheaper, less robust).

This LLM-based approach is chosen for:
- Robustness to varied user phrasing
- Structured JSON output validation
- Educational value (shows secondary LLM calls pattern)

Trade-off: Adds one LLM call per conversation turn.
"""
from __future__ import annotations

import json

import structlog

from app.models.session import ProjectMetadata
from app.services.llm_service import _invoke_llm

log = structlog.get_logger()

EXTRACTION_SYSTEM_PROMPT = """You are a metadata extraction assistant.

Given a conversation turn about a software project, extract factual information into JSON.

Return ONLY valid JSON with this structure:
{
  "project_name": "string or null",
  "assumed_team_size": number or null,
  "mentioned_technologies": ["string"],
  "agreed_scope": "string summarizing what was agreed"
}

Rules:
- project_name: Extract if user mentions a specific name
- assumed_team_size: Extract only if explicitly mentioned
- mentioned_technologies: List any tech stacks, frameworks, languages mentioned
- agreed_scope: Brief summary of confirmed features/requirements

If no new information, preserve current values. Return empty strings/arrays if nothing found.
"""


def extract_project_metadata(
    user_message: str,
    assistant_response: str,
    current_metadata: ProjectMetadata,
) -> ProjectMetadata:
    """Extract project metadata from a conversation turn using LLM.

    Returns updated ProjectMetadata. Falls back to current_metadata if extraction fails.
    """
    user_prompt = f"""Current metadata:
{current_metadata.model_dump_json(indent=2)}

New conversation turn:
User: {user_message}
Assistant: {assistant_response}

Extract updated metadata as JSON:"""

    try:
        result = _invoke_llm(
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            user_message=user_prompt,
            max_tokens=500,
        )

        # Parse JSON from LLM response
        extracted_json = result["estimation"].strip()
        if extracted_json.startswith("```json"):
            extracted_json = extracted_json.split("```json")[1].split("```")[0].strip()

        extracted = json.loads(extracted_json)

        # Merge with current metadata
        return ProjectMetadata(
            project_name=extracted.get("project_name") or current_metadata.project_name,
            assumed_team_size=extracted.get("assumed_team_size") or current_metadata.assumed_team_size,
            mentioned_technologies=(
                current_metadata.mentioned_technologies + extracted.get("mentioned_technologies", [])
            ),
            agreed_scope=extracted.get("agreed_scope") or current_metadata.agreed_scope,
        )

    except Exception as exc:
        log.warning("metadata_extraction_failed", error=str(exc))
        # Fall back to current metadata on any failure
        return current_metadata
