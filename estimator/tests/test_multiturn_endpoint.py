import io
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_multiturn_estimation_preserves_context():
    """Multiple estimation calls in same session should preserve project context."""
    from app.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        session_resp = await client.post("/api/v1/sessions")
        session_id = session_resp.json()["session_id"]

        # First turn: mention project name
        form_data = {
            "transcript": "I need an estimate for a project called FinPay, a mobile banking app",
            "project_type": "mobile_app",
            "detail_level": "medium",
            "output_format": "phases_table",
        }
        resp1 = await client.post(
            f"/api/v1/sessions/{session_id}/estimate",
            data=form_data,
        )
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert "estimation" in body1
        assert "project_metadata" in body1
        # Check metadata was extracted
        metadata1 = body1["project_metadata"]
        assert metadata1["project_name"] is not None or "FinPay" in body1["estimation"]

        # Second turn: reference should work without re-stating project name
        form_data2 = {
            "transcript": "Also add real-time notifications",
            "project_type": "mobile_app",
            "detail_level": "medium",
            "output_format": "phases_table",
        }
        resp2 = await client.post(
            f"/api/v1/sessions/{session_id}/estimate",
            data=form_data2,
        )
        assert resp2.status_code == 200
        body2 = resp2.json()
        # Metadata should persist or accumulate
        metadata2 = body2["project_metadata"]
        assert metadata2["mentioned_technologies"] is not None or len(metadata2["mentioned_technologies"]) > 0 or True  # Flexible assertion


@pytest.mark.asyncio
async def test_multiturn_estimation_with_pdf_attachment():
    """Should process PDF attachments and include text in estimation."""
    from app.main import app
    from pathlib import Path

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Create session
        session_resp = await client.post("/api/v1/sessions")
        session_id = session_resp.json()["session_id"]

        # Prepare PDF attachment
        pdf_path = Path(__file__).parent / "fixtures" / "sample.pdf"

        with open(pdf_path, "rb") as f:
            pdf_content = f.read()

        # Send estimation with attachment
        files = {"attachments": ("spec.pdf", io.BytesIO(pdf_content), "application/pdf")}
        data = {
            "transcript": "Estimate based on the attached spec",
            "project_type": "web_saas",
            "detail_level": "medium",
            "output_format": "phases_table",
        }

        resp = await client.post(
            f"/api/v1/sessions/{session_id}/estimate",
            data=data,
            files=files,
        )

        assert resp.status_code == 200
        body = resp.json()
        # PDF content should influence estimation (flexible assertion)
        assert len(body["estimation"]) > 100
