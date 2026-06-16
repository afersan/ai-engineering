from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    OutputFormat,
    ProjectType,
)

ASSUMPTIONS_PHRASE = "list the assumptions you made"


def _make_request(
    *,
    description: str = "Mobile app with login, chat and push notifications.",
    project_type: ProjectType = ProjectType.MOBILE_APP,
    detail_level: DetailLevel = DetailLevel.DETAILED,
    output_format: OutputFormat = OutputFormat.PHASES_TABLE,
) -> EstimationRequest:
    return EstimationRequest(
        description=description,
        project_type=project_type,
        detail_level=detail_level,
        output_format=output_format,
    )


def test_render_includes_description() -> None:
    description = "Mobile app with login, chat and push notifications."
    request = _make_request(description=description)
    _system, user = render_estimation_prompt(request)

    assert "<project_description>" in user
    assert description in user


PHASES_TABLE_INSTRUCTION = "one row per project phase"
NARRATIVE_INSTRUCTION = "flowing prose estimate"


def test_output_format_phases_table_vs_narrative() -> None:
    phases_request = _make_request(output_format=OutputFormat.PHASES_TABLE)
    narrative_request = _make_request(output_format=OutputFormat.NARRATIVE)

    phases_system, _ = render_estimation_prompt(phases_request)
    narrative_system, _ = render_estimation_prompt(narrative_request)

    assert PHASES_TABLE_INSTRUCTION in phases_system
    assert PHASES_TABLE_INSTRUCTION not in narrative_system
    assert NARRATIVE_INSTRUCTION in narrative_system


def test_detail_level_detailed_vs_summary() -> None:
    detailed_request = _make_request(detail_level=DetailLevel.DETAILED)
    summary_request = _make_request(detail_level=DetailLevel.SUMMARY)

    detailed_system, _ = render_estimation_prompt(detailed_request)
    summary_system, _ = render_estimation_prompt(summary_request)

    assert ASSUMPTIONS_PHRASE in detailed_system
    assert ASSUMPTIONS_PHRASE not in summary_system
