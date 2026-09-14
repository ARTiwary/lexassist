from backend.document_parser import extract_text_from_txt, segment_into_clauses


def test_extract_text_from_txt_decodes_utf8():
    content = "Hello, this is a lease.".encode("utf-8")
    assert extract_text_from_txt(content) == "Hello, this is a lease."


def test_segment_into_clauses_numbered_sections():
    text = (
        "1. Rent. Tenant shall pay $1000 per month.\n"
        "2. Term. This lease lasts 12 months.\n"
        "3. Termination. Either party may terminate with 30 days notice.\n"
    )
    clauses = segment_into_clauses(text)
    assert len(clauses) == 3
    assert "Rent" in clauses[0].text
    assert "Term." in clauses[1].text
    assert "Termination" in clauses[2].text


def test_segment_into_clauses_falls_back_to_paragraphs():
    text = "This is paragraph one about payment.\n\nThis is paragraph two about liability."
    clauses = segment_into_clauses(text)
    assert len(clauses) == 2
    assert "payment" in clauses[0].text
    assert "liability" in clauses[1].text


def test_segment_into_clauses_never_returns_empty_for_nonempty_input():
    text = "Just one unstructured blob of legal text with no clear breaks."
    clauses = segment_into_clauses(text)
    assert len(clauses) >= 1


def test_segment_into_clauses_handles_empty_input():
    clauses = segment_into_clauses("")
    assert clauses == []


def test_each_clause_has_a_unique_id():
    text = "1. First clause.\n2. Second clause.\n3. Third clause.\n"
    clauses = segment_into_clauses(text)
    ids = [c.clause_id for c in clauses]
    assert len(ids) == len(set(ids))
