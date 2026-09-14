"""Pydantic schemas for request/response validation.

Using explicit schemas (rather than raw dicts) gives us input validation
for free, which is both a code-quality and a security control (rejects
malformed / oversized / wrong-typed input before it reaches business logic).
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class Clause(BaseModel):
    clause_id: str
    text: str
    section_title: Optional[str] = None


class DocumentSummary(BaseModel):
    document_id: str
    filename: str
    clause_count: int
    plain_summary: str
    clauses: List[Clause]


class RiskItem(BaseModel):
    clause_id: str
    severity: str = Field(description="one of: low, medium, high")
    label: str
    explanation: str

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        allowed = {"low", "medium", "high"}
        if v.lower() not in allowed:
            raise ValueError(f"severity must be one of {allowed}")
        return v.lower()


class RiskReport(BaseModel):
    document_id: str
    items: List[RiskItem]


class AskRequest(BaseModel):
    document_id: str
    question: str = Field(min_length=1, max_length=1000)
    user_role: Optional[str] = Field(default=None, max_length=100)


class AskResponse(BaseModel):
    answer: str
    cited_clause_ids: List[str]
    is_advice_request: bool
    escalation_notice: Optional[str] = None


class CompareRequest(BaseModel):
    document_id_a: str
    document_id_b: str


class CompareDifference(BaseModel):
    topic: str
    document_a_summary: str
    document_b_summary: str
    why_it_matters: str


class CompareResponse(BaseModel):
    differences: List[CompareDifference]


class ChecklistResponse(BaseModel):
    document_id: str
    checklist: List[str]
    questions_for_a_lawyer: List[str]
