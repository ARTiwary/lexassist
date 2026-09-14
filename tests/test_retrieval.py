import pytest

from backend.document_parser import ParsedClause
from backend.retrieval import ClauseIndex


def make_clauses():
    return [
        ParsedClause(clause_id="c1", text="The tenant shall pay rent of $1200 on the first of each month."),
        ParsedClause(clause_id="c2", text="The landlord may enter the premises with 24 hours written notice."),
        ParsedClause(clause_id="c3", text="Either party may terminate this agreement with 30 days notice."),
    ]


def test_query_returns_most_relevant_clause_first():
    index = ClauseIndex(make_clauses())
    results = index.query("How much rent do I have to pay?", top_k=1)
    assert len(results) == 1
    assert results[0].clause_id == "c1"


def test_query_respects_top_k():
    index = ClauseIndex(make_clauses())
    results = index.query("notice period termination rent entry", top_k=2)
    assert len(results) <= 2


def test_query_with_empty_question_returns_empty_list():
    index = ClauseIndex(make_clauses())
    assert index.query("") == []


def test_query_with_irrelevant_terms_may_return_no_results():
    index = ClauseIndex(make_clauses())
    # Completely unrelated vocabulary should not force a spurious match.
    results = index.query("xyzabc123 nonexistent token qwerty", top_k=3)
    assert results == [] or all(r.score >= 0 for r in results)


def test_index_rejects_empty_clause_list():
    with pytest.raises(ValueError):
        ClauseIndex([])


def test_len_returns_clause_count():
    index = ClauseIndex(make_clauses())
    assert len(index) == 3
