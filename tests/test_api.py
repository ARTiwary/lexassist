import io

import pytest
from fastapi.testclient import TestClient

from backend.main import DOCUMENT_STORE, app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_store():
    """Ensure each test starts with a clean in-memory document store."""
    DOCUMENT_STORE.clear()
    yield
    DOCUMENT_STORE.clear()


SAMPLE_LEASE = (
    "1. Rent. Tenant shall pay $1200 per month on the first of each month.\n"
    "2. Term. This lease begins January 1 and lasts 12 months.\n"
    "3. Termination. Either party may terminate this lease with 30 days written notice.\n"
    "4. Liability. Tenant is liable for all damages beyond normal wear and tear.\n"
)


def upload_sample_document(filename: str = "lease.txt") -> str:
    response = client.post(
        "/api/documents",
        files={"file": (filename, io.BytesIO(SAMPLE_LEASE.encode("utf-8")), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return response.json()["document_id"]


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_document_returns_clauses_and_summary():
    response = client.post(
        "/api/documents",
        files={"file": ("lease.txt", io.BytesIO(SAMPLE_LEASE.encode("utf-8")), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["clause_count"] == 4
    assert body["filename"] == "lease.txt"
    assert len(body["plain_summary"]) > 0
    assert len(body["clauses"]) == 4


def test_upload_rejects_disallowed_extension():
    response = client.post(
        "/api/documents",
        files={"file": ("malware.exe", io.BytesIO(b"binary content"), "application/octet-stream")},
    )
    assert response.status_code == 415


def test_upload_rejects_oversized_file(monkeypatch):
    import dataclasses

    import backend.security as security_module

    tiny_settings = dataclasses.replace(security_module.settings, max_upload_bytes=10)
    monkeypatch.setattr(security_module, "settings", tiny_settings)
    response = client.post(
        "/api/documents",
        files={"file": ("lease.txt", io.BytesIO(SAMPLE_LEASE.encode("utf-8")), "text/plain")},
    )
    assert response.status_code == 413


def test_get_document_after_upload():
    document_id = upload_sample_document()
    response = client.get(f"/api/documents/{document_id}")
    assert response.status_code == 200
    assert response.json()["document_id"] == document_id


def test_get_document_not_found_returns_404():
    response = client.get("/api/documents/does-not-exist")
    assert response.status_code == 404


def test_ask_question_returns_grounded_answer_with_citation():
    document_id = upload_sample_document()
    response = client.post(
        "/api/ask",
        json={"document_id": document_id, "question": "How much is the monthly rent?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["cited_clause_ids"]) > 0
    assert body["is_advice_request"] is False


def test_ask_advice_seeking_question_is_flagged_and_reframed():
    document_id = upload_sample_document()
    response = client.post(
        "/api/ask",
        json={"document_id": document_id, "question": "Should I sign this lease?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_advice_request"] is True
    assert "advice" in body["answer"].lower() or "attorney" in body["answer"].lower()


def test_ask_high_stakes_question_triggers_escalation_notice():
    document_id = upload_sample_document()
    response = client.post(
        "/api/ask",
        json={
            "document_id": document_id,
            "question": "I got an eviction notice, does this clause protect me?",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["escalation_notice"] is not None


def test_ask_on_unknown_document_returns_404():
    response = client.post(
        "/api/ask", json={"document_id": "nonexistent", "question": "What is the rent?"}
    )
    assert response.status_code == 404


def test_ask_rejects_empty_question():
    document_id = upload_sample_document()
    response = client.post("/api/ask", json={"document_id": document_id, "question": ""})
    assert response.status_code == 422  # pydantic validation error


def test_compare_documents_returns_differences():
    doc_a = upload_sample_document("lease_a.txt")
    doc_b = upload_sample_document("lease_b.txt")
    response = client.post(
        "/api/compare", json={"document_id_a": doc_a, "document_id_b": doc_b}
    )
    assert response.status_code == 200
    assert len(response.json()["differences"]) >= 1


def test_risk_report_returns_valid_structure():
    document_id = upload_sample_document()
    response = client.get(f"/api/documents/{document_id}/risks")
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == document_id
    for item in body["items"]:
        assert item["severity"] in {"low", "medium", "high"}


def test_checklist_returns_two_lists():
    document_id = upload_sample_document()
    response = client.get(f"/api/documents/{document_id}/checklist")
    assert response.status_code == 200
    body = response.json()
    assert len(body["checklist"]) >= 1
    assert len(body["questions_for_a_lawyer"]) >= 1
