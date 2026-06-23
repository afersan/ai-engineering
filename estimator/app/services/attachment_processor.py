"""File attachment processing with local text extraction.

This implementation uses local libraries (pypdf, python-docx) rather than
sending files to multimodal LLM APIs. Advantages:
- Provider-agnostic (works with any LLM)
- Prepares foundation for RAG chunking in Module 3
- Full control over text extraction and preprocessing

Trade-off: Requires more code than direct multimodal API upload.
"""
from __future__ import annotations

import io
from typing import BinaryIO

import structlog
from pypdf import PdfReader
from docx import Document
from fastapi import UploadFile

log = structlog.get_logger()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


class AttachmentProcessingError(Exception):
    """Raised when file processing fails."""


def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract all text from PDF bytes."""
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        text_parts = []
        for page_num, page in enumerate(reader.pages, start=1):
            text = page.extract_text()
            if text.strip():
                text_parts.append(f"[Page {page_num}]\n{text}")
        return "\n\n".join(text_parts)
    except Exception as exc:
        log.error("pdf_extraction_failed", error=str(exc))
        raise AttachmentProcessingError(f"PDF extraction failed: {exc}") from exc


def extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract all text from Word document bytes."""
    try:
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs)
    except Exception as exc:
        log.error("docx_extraction_failed", error=str(exc))
        raise AttachmentProcessingError(f"Word extraction failed: {exc}") from exc


async def process_attachments(files: list[UploadFile]) -> str:
    """Process all attachments and return concatenated text with separators.

    Returns empty string if no files provided.
    Raises AttachmentProcessingError if any file fails processing.
    """
    if not files:
        return ""

    parts = []
    for upload_file in files:
        filename = upload_file.filename or "unknown"
        content_type = upload_file.content_type or ""

        log.info("processing_attachment", filename=filename, content_type=content_type)

        file_bytes = await upload_file.read()

        if len(file_bytes) > MAX_FILE_SIZE:
            raise AttachmentProcessingError(
                f"File {filename} exceeds 10MB limit"
            )

        # Determine extractor based on content type
        if content_type == "application/pdf" or filename.endswith(".pdf"):
            text = extract_text_from_pdf(file_bytes)
        elif content_type in (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/msword",
        ) or filename.endswith((".docx", ".doc")):
            text = extract_text_from_docx(file_bytes)
        else:
            raise AttachmentProcessingError(
                f"Unsupported file type: {filename} ({content_type})"
            )

        parts.append(f"--- Attachment: {filename} ---\n{text}")

    return "\n\n".join(parts)
