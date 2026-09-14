from backend.guardrails import escalation_notice_for, is_advice_seeking, needs_escalation


def test_is_advice_seeking_detects_should_i():
    assert is_advice_seeking("Should I sign this contract?") is True


def test_is_advice_seeking_detects_win_question():
    assert is_advice_seeking("Am I going to win this case?") is True


def test_is_advice_seeking_false_for_factual_question():
    assert is_advice_seeking("What is the notice period in this lease?") is False


def test_needs_escalation_detects_eviction():
    assert needs_escalation("I just got an eviction notice, what does this clause mean?") is True


def test_needs_escalation_detects_immigration():
    assert needs_escalation("Does this affect my visa or immigration status?") is True


def test_needs_escalation_false_for_routine_question():
    assert needs_escalation("What is my monthly rent under this lease?") is False


def test_escalation_notice_for_returns_none_when_not_needed():
    assert escalation_notice_for("What is my monthly rent?") is None


def test_escalation_notice_for_returns_text_when_needed():
    notice = escalation_notice_for("Can I be sued for breaking this lease early?")
    assert notice is not None
    assert "attorney" in notice.lower() or "legal aid" in notice.lower()
