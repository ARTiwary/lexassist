"""Parse uploaded documents into plain text and segment into clauses.

Supports .txt, .docx, and .pdf. Clause segmentation uses a lightweight,
dependency-free heuristic: it looks for common legal-document numbering
patterns (e.g., "1.", "1.1", "Section 2", "Article III") and falls back to
paragraph-based splitting when no such pattern is detected. This keeps the
pipeline fast, deterministic, and easy to unit test -- an LLM-based
segmenter could replace this for higher accuracy on messier documents.
"""
from __future__ import annotations

import io
import re
import uuid
from dataclasses import dataclass
from typing import List, Optional

NUMBERED_CLAUSE_RE = re.compile(
    r"""^\s*
    (
        \d+(\.\d+)*\.?          # 1.  1.1  2.3.4
        |Section\s+\d+          # Section 3
        |Article\s+[IVXLC]+     # Article IV
        |Article\s+\d+          # Article 4
        |\([a-zA-Z]\)           # (a)
    )
    \s*[-.:)]?\s+
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class ParsedClause:
    clause_id: str
    text: str
    section_title: Optional[str] = None


def extract_text_from_txt(content: bytes) -> str:
    return content.decode("utf-8", errors="replace")


def extract_text_from_docx(content: bytes) -> str:
    from docx import Document  # local import: keeps optional dependency lazy

    doc = Document(io.BytesIO(content))
    return "\n".join(p.text for p in doc.paragraphs)


def extract_text_from_pdf(content: bytes) -> str:
    import pdfplumber  # local import: keeps optional dependency lazy

    text_parts: List[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


EXTRACTORS = {
    ".txt": extract_text_from_txt,
    ".docx": extract_text_from_docx,
    ".pdf": extract_text_from_pdf,
}


def extract_text(content: bytes, extension: str) -> str:
    """Dispatch to the correct extractor for the given file extension.

    Raises ValueError for unsupported extensions (callers should validate
    the extension via backend.security.validate_extension beforehand).
    """
    extractor = EXTRACTORS.get(extension.lower())
    if extractor is None:
        raise ValueError(f"No extractor registered for extension '{extension}'")
    return extractor(content)


def segment_into_clauses(raw_text: str) -> List[ParsedClause]:
    """Split raw document text into clause-sized chunks.

    Strategy:
    1. Split on lines that look like a numbered clause/section marker.
    2. If fewer than 2 such markers are found (i.e. the document doesn't
       follow a numbered structure), fall back to splitting on blank-line
       separated paragraphs.
    3. Drop empty/whitespace-only fragments.
    """
    lines = raw_text.splitlines()
    marker_indices = [i for i, line in enumerate(lines) if NUMBERED_CLAUSE_RE.match(line)]

    clauses: List[ParsedClause] = []

    if len(marker_indices) >= 2:
        boundaries = marker_indices + [len(lines)]
        for start, end in zip(boundaries[:-1], boundaries[1:]):
            chunk = "\n".join(lines[start:end]).strip()
            if chunk:
                clauses.append(ParsedClause(clause_id=str(uuid.uuid4()), text=chunk))
    else:
        paragraphs = re.split(r"\n\s*\n", raw_text)
        for para in paragraphs:
            cleaned = para.strip()
            if cleaned:
                clauses.append(ParsedClause(clause_id=str(uuid.uuid4()), text=cleaned))

    if not clauses:
        # Guarantee at least one clause so downstream code has something
        # to work with, rather than failing on a near-empty document.
        cleaned_all = raw_text.strip()
        if cleaned_all:
            clauses.append(ParsedClause(clause_id=str(uuid.uuid4()), text=cleaned_all))

    return clauses


def parse_document(content: bytes, extension: str) -> List[ParsedClause]:
    """Full pipeline: extract text, then segment into clauses."""
    raw_text = extract_text(content, extension)
    return segment_into_clauses(raw_text)
