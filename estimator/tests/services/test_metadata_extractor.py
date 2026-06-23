import pytest
from unittest.mock import patch

from app.models.session import ProjectMetadata
from app.services.metadata_extractor import extract_project_metadata


def test_extract_project_metadata_updates_fields():
    """Should extract project facts from conversation turn."""
    user_msg = "I need an estimate for a mobile banking app called FinPay"
    assistant_msg = "For a mobile banking app with standard features, assuming a team of 3-4 developers..."
    current = ProjectMetadata()

    # Mock LLM to return structured metadata
    mock_llm_response = {
        "estimation": """{
            "project_name": "FinPay",
            "assumed_team_size": 4,
            "mentioned_technologies": ["React Native", "Node.js"],
            "agreed_scope": "mobile banking app with standard features"
        }"""
    }

    with patch("app.services.metadata_extractor._invoke_llm", return_value=mock_llm_response):
        updated = extract_project_metadata(user_msg, assistant_msg, current)

    assert updated.project_name == "FinPay"
    assert updated.assumed_team_size == 4
    assert "React Native" in updated.mentioned_technologies
    assert "mobile banking app" in updated.agreed_scope


def test_extract_project_metadata_falls_back_on_error():
    """Should return current metadata if LLM call or parsing fails."""
    current = ProjectMetadata(
        project_name="ExistingProject",
        assumed_team_size=5,
        mentioned_technologies=["Python"],
        agreed_scope="existing scope",
    )

    # Mock LLM to raise exception
    with patch("app.services.metadata_extractor._invoke_llm", side_effect=Exception("API error")):
        updated = extract_project_metadata("user msg", "assistant msg", current)

    # Should preserve current metadata
    assert updated.project_name == "ExistingProject"
    assert updated.assumed_team_size == 5
    assert updated.mentioned_technologies == ["Python"]
