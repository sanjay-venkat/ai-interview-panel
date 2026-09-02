import io

from docx import Document
from fastapi import HTTPException
from pypdf import PdfReader

MAX_RESUME_BYTES = 8 * 1024 * 1024  # 8MB — plenty for a resume, caps parse time/memory
MAX_RESUME_CHARS = 6000  # keeps the resume block bounded inside every panelist's prompt


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_resume_text(filename: str, data: bytes) -> str:
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(400, f"Resume file too large (max {MAX_RESUME_BYTES // 1024 // 1024}MB)")

    lower = filename.lower()
    try:
        if lower.endswith(".pdf"):
            text = _extract_pdf(data)
        elif lower.endswith(".docx"):
            text = _extract_docx(data)
        else:
            raise HTTPException(400, "Unsupported file type — upload a .pdf or .docx")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not read resume file: {e}")

    text = text.strip()
    if not text:
        raise HTTPException(400, "No extractable text found in that file (is it a scanned image?)")
    return text[:MAX_RESUME_CHARS]
