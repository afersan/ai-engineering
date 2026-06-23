from app.prompts.loader import render_estimation_prompt
from app.schemas.estimation import EstimationRequest, ProjectType, DetailLevel, OutputFormat
from app.models.session import ProjectMetadata


def test_render_prompt_with_project_metadata():
    """System prompt should include project metadata section when provided."""
    request = EstimationRequest(
        description="Add payment features",
        project_type=ProjectType.WEB_SAAS,
        detail_level=DetailLevel.MEDIUM,
        output_format=OutputFormat.PHASES_TABLE,
    )

    metadata = ProjectMetadata(
        project_name="FinPay",
        assumed_team_size=4,
        mentioned_technologies=["React", "Node.js"],
        agreed_scope="mobile banking app with standard features",
    )

    system_prompt, user_prompt = render_estimation_prompt(request, project_metadata=metadata)

    assert "FinPay" in system_prompt
    assert "4" in system_prompt or "four" in system_prompt.lower()
    assert "React" in system_prompt
    assert "Node.js" in system_prompt
    assert "banking app" in system_prompt


def test_render_prompt_without_metadata():
    """System prompt should work without project metadata (first turn)."""
    request = EstimationRequest(
        description="Build a comprehensive CRM system",
        project_type=ProjectType.INTERNAL_TOOL,
        detail_level=DetailLevel.SUMMARY,
        output_format=OutputFormat.NARRATIVE,
    )

    system_prompt, user_prompt = render_estimation_prompt(request, project_metadata=None)

    # Should render successfully without metadata section
    assert len(system_prompt) > 0
    assert "You are" in system_prompt
