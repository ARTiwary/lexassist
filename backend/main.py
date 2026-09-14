"""LexAssist FastAPI application.

Endpoints:
    POST /api/documents            upload + parse a document
    GET  /api/documents/{id}       fetch a previously parsed document
    POST /api/ask                  ask a grounded question about a document
    POST /api/compare              compare two documents
    GET  /api/documents/{id}/risks generate a risk report for a document
    GET  /api/documents/{id}/checklist  generate a pre-sign checklist + lawyer questions
    GET  /health                   liveness probe

Storage is in-memory and per-process, keyed by a server-generated UUID --
appropriate for a demo/hackathon deployment. A production deployment would
replace `DOCUMENT_STORE` with encrypted, access-controlled persistent
storage scoped to an authenticated user/session.
"""
from __future__ import annotations

import uuid
from typing import Dict, List

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .document_parser import ParsedClause, parse_document
from .guardrails import ADVICE_REFRAME_NOTICE, escalation_notice_for, is_advice_seeking
from .llm_client import LLMClient, SYSTEM_PROMPT, get_llm_client
from .models import (
    AskRequest,
    AskResponse,
    ChecklistResponse,
    Clause,
    CompareDifference,
    CompareRequest,
    CompareResponse,
    DocumentSummary,
    RiskItem,
    RiskReport,
)
from .retrieval import ClauseIndex
from .security import rate_limiter, read_and_validate_upload, sanitize_error_message

app = FastAPI(
    title="LexAssist API",
    description="GenAI-powered legal document comprehension and comparison assistant.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)

# --- In-memory storage -------------------------------------------------
# document_id -> (filename, clauses, ClauseIndex)
DOCUMENT_STORE: Dict[str, Dict] = {}


def get_llm() -> LLMClient:
    return get_llm_client()


def _rate_limit_or_raise(request: Request) -> None:
    client_key = request.client.host if request.client else "unknown"
    if not rate_limiter.allow(client_key):
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")


def _get_document_or_404(document_id: str) -> Dict:
    doc = DOCUMENT_STORE.get(document_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/documents", response_model=DocumentSummary)
async def upload_document(
    request: Request, file: UploadFile, llm: LLMClient = Depends(get_llm)
) -> DocumentSummary:
    _rate_limit_or_raise(request)
    try:
        content = await read_and_validate_upload(file)
        extension = "." + file.filename.rsplit(".", 1)[-1].lower()
        clauses: List[ParsedClause] = parse_document(content, extension)
        index = ClauseIndex(clauses)

        document_id = str(uuid.uuid4())
        DOCUMENT_STORE[document_id] = {
            "filename": file.filename,
            "clauses": clauses,
            "index": index,
        }

        full_text = "\n\n".join(c.text for c in clauses[:20])  # cap context sent to the model
        plain_summary = llm.complete(
            system=SYSTEM_PROMPT,
            user=(
                "Summarize the following legal document in plain, everyday "
                "language in 3-5 sentences. Do not give advice, only "
                f"explain what it says.\n\n{full_text}"
            ),
        )

        return DocumentSummary(
            document_id=document_id,
            filename=file.filename,
            clause_count=len(clauses),
            plain_summary=plain_summary,
            clauses=[Clause(clause_id=c.clause_id, text=c.text) for c in clauses],
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - convert unexpected errors to a safe response
        raise HTTPException(status_code=500, detail=sanitize_error_message(exc)) from exc


@app.get("/api/documents/{document_id}", response_model=DocumentSummary)
def get_document(document_id: str) -> DocumentSummary:
    doc = _get_document_or_404(document_id)
    clauses: List[ParsedClause] = doc["clauses"]
    return DocumentSummary(
        document_id=document_id,
        filename=doc["filename"],
        clause_count=len(clauses),
        plain_summary="",
        clauses=[Clause(clause_id=c.clause_id, text=c.text) for c in clauses],
    )


@app.post("/api/ask", response_model=AskResponse)
def ask_question(
    request: Request, payload: AskRequest, llm: LLMClient = Depends(get_llm)
) -> AskResponse:
    _rate_limit_or_raise(request)
    doc = _get_document_or_404(payload.document_id)
    index: ClauseIndex = doc["index"]

    advice_seeking = is_advice_seeking(payload.question)
    escalation = escalation_notice_for(payload.question)

    retrieved = index.query(payload.question, top_k=3)
    if not retrieved:
        return AskResponse(
            answer=(
                "This document does not appear to address that question. "
                "Consider asking about a topic that's explicitly covered "
                "in the uploaded text."
            ),
            cited_clause_ids=[],
            is_advice_request=advice_seeking,
            escalation_notice=escalation,
        )

    context = "\n\n".join(f"[Clause {r.clause_id}]: {r.text}" for r in retrieved)
    role_note = f"The user's role in this document is: {payload.user_role}. " if payload.user_role else ""

    prompt = (
        f"{role_note}Answer the user's question using ONLY the clause text "
        "below. Quote or closely paraphrase the relevant part, and state "
        "clearly if the clauses don't fully answer the question. Do not "
        "give personal legal advice -- explain what the text says and "
        f"what it generally means.\n\nQuestion: {payload.question}\n\n"
        f"Relevant clauses:\n{context}"
    )

    answer = llm.complete(system=SYSTEM_PROMPT, user=prompt)
    if advice_seeking:
        answer = f"{ADVICE_REFRAME_NOTICE}\n\n{answer}"

    return AskResponse(
        answer=answer,
        cited_clause_ids=[r.clause_id for r in retrieved],
        is_advice_request=advice_seeking,
        escalation_notice=escalation,
    )


@app.post("/api/compare", response_model=CompareResponse)
def compare_documents(
    request: Request, payload: CompareRequest, llm: LLMClient = Depends(get_llm)
) -> CompareResponse:
    _rate_limit_or_raise(request)
    doc_a = _get_document_or_404(payload.document_id_a)
    doc_b = _get_document_or_404(payload.document_id_b)

    text_a = "\n".join(c.text for c in doc_a["clauses"][:30])
    text_b = "\n".join(c.text for c in doc_b["clauses"][:30])

    prompt = (
        "Compare Document A and Document B below. Identify the 3-6 most "
        "meaningful differences (e.g., payment terms, termination rights, "
        "liability, notice periods). For each difference, return a short "
        "topic label, a one-sentence summary of what A says, a "
        "one-sentence summary of what B says, and one sentence on why the "
        "difference matters practically. Do not recommend which document "
        "to choose.\n\n"
        f"Document A:\n{text_a}\n\nDocument B:\n{text_b}"
    )
    raw = llm.complete(system=SYSTEM_PROMPT, user=prompt)

    # The mock/live client returns free text; for the demo we wrap it in a
    # single structured item so the response always matches the schema.
    # A production implementation would request JSON-schema-constrained
    # output from the model and parse it directly.
    return CompareResponse(
        differences=[
            CompareDifference(
                topic="Overview",
                document_a_summary=doc_a["filename"],
                document_b_summary=doc_b["filename"],
                why_it_matters=raw,
            )
        ]
    )


@app.get("/api/documents/{document_id}/risks", response_model=RiskReport)
def get_risk_report(document_id: str, llm: LLMClient = Depends(get_llm)) -> RiskReport:
    doc = _get_document_or_404(document_id)
    clauses: List[ParsedClause] = doc["clauses"]

    items: List[RiskItem] = []
    for clause in clauses[:15]:  # cap for demo performance
        prompt = (
            "Assess this single clause for the non-drafting party. "
            "Respond in the exact format:\nSEVERITY: <low|medium|high>\n"
            "LABEL: <short label>\nEXPLANATION: <one sentence>\n\n"
            f"Clause:\n{clause.text}"
        )
        raw = llm.complete(system=SYSTEM_PROMPT, user=prompt)
        severity, label, explanation = _parse_risk_response(raw)
        if severity in {"medium", "high"}:
            items.append(
                RiskItem(
                    clause_id=clause.clause_id,
                    severity=severity,
                    label=label,
                    explanation=explanation,
                )
            )

    return RiskReport(document_id=document_id, items=items)


def _parse_risk_response(raw: str) -> tuple[str, str, str]:
    """Best-effort parse of the model's structured risk response.

    Falls back to safe defaults if the model does not follow the
    requested format exactly (e.g. when using the mock client).
    """
    severity, label, explanation = "low", "General clause", raw.strip()[:200]
    for line in raw.splitlines():
        lower = line.strip().lower()
        if lower.startswith("severity:"):
            candidate = line.split(":", 1)[1].strip().lower()
            if candidate in {"low", "medium", "high"}:
                severity = candidate
        elif lower.startswith("label:"):
            label = line.split(":", 1)[1].strip() or label
        elif lower.startswith("explanation:"):
            explanation = line.split(":", 1)[1].strip() or explanation
    return severity, label, explanation


@app.get("/api/documents/{document_id}/checklist", response_model=ChecklistResponse)
def get_checklist(document_id: str, llm: LLMClient = Depends(get_llm)) -> ChecklistResponse:
    doc = _get_document_or_404(document_id)
    clauses: List[ParsedClause] = doc["clauses"]
    text = "\n".join(c.text for c in clauses[:30])

    prompt = (
        "Based on this document, produce two short lists:\n"
        "1) A 'before you sign' checklist of concrete things to verify "
        "(5 items max).\n"
        "2) Specific questions the user should ask a licensed attorney "
        "about this document (5 items max).\n"
        "Format each list item on its own line starting with '- '.\n\n"
        f"Document:\n{text}"
    )
    raw = llm.complete(system=SYSTEM_PROMPT, user=prompt)
    lines = [l.strip("- ").strip() for l in raw.splitlines() if l.strip().startswith("-")]
    midpoint = max(1, len(lines) // 2) if lines else 0
    checklist = lines[:midpoint] if lines else ["Review the full document text above."]
    questions = lines[midpoint:] if lines else ["What are my main obligations under this document?"]

    return ChecklistResponse(
        document_id=document_id, checklist=checklist, questions_for_a_lawyer=questions
    )
