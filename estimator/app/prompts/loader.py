from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas.estimation import EstimationRequest

if TYPE_CHECKING:
    from app.models.session import ProjectMetadata

PROMPTS_DIR = Path(__file__).parent

_env = Environment(
    loader=FileSystemLoader(PROMPTS_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=False,
    undefined=StrictUndefined,
)


def render_estimation_prompt(
    request: EstimationRequest,
    version: str = "v1",
    project_metadata: "ProjectMetadata | None" = None,
) -> tuple[str, str]:
    """Render system and user prompts for the given estimation request.

    Args:
        request: Typed estimation parameters
        version: Prompt template version (default "v1")
        project_metadata: Optional project context from session
    """

    system_template = _env.get_template(f"estimation/{version}/system.j2")
    user_template = _env.get_template(f"estimation/{version}/user.j2")

    context = {
        "project_type": request.project_type.value,
        "detail_level": request.detail_level.value,
        "output_format": request.output_format.value,
        "description": request.description,
        "project_metadata": project_metadata,
    }

    return system_template.render(**context), user_template.render(**context)
