from enum import Enum

from pydantic import BaseModel, Field

# Transcripción del usuario en el formulario multiturno.
MAX_TRANSCRIPT_LENGTH = 50_000

# Transcripción + texto extraído de adjuntos (hasta ~10 MB).
MAX_DESCRIPTION_LENGTH = 100_000


class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"


class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"


class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"


class EstimationRequest(BaseModel):
    description: str = Field(min_length=20, max_length=MAX_DESCRIPTION_LENGTH)
    project_type: ProjectType
    detail_level: DetailLevel
    output_format: OutputFormat


class EstimationResponse(BaseModel):
    text: str
    prompt_version: str
