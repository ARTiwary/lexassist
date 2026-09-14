"""Guardrails that enforce the 'information, not advice' boundary.

This module implements two lightweight, rule-based classifiers:

1. `is_advice_seeking` -- detects when a user's question has moved from
   "explain what this document says" to "tell me what I personally should
   do", which the product intentionally declines to answer directly.
2. `needs_escalation` -- detects high-stakes situations (eviction,
   immigration, criminal matters, restraining orders, large financial
   exposure) that should be paired with a proactive nudge toward a
   licensed professional or legal aid, regardless of how the question is
   phrased.

Both are implemented as transparent keyword/pattern heuristics rather than
an opaque model call so that behavior is auditable, testable, and doesn't
depend on network availability. In a production system these could be
layered with an LLM-based classifier for higher recall, using this
rule-based layer as a fast, always-available fallback.
"""
from __future__ import annotations

import re
from typing import Optional

_ADVICE_PATTERNS = [
    r"\bshould i\b",
    r"\bwhat would you do\b",
    r"\bam i (going to|gonna) win\b",
    r"\bwill i win\b",
    r"\bis it worth (suing|it)\b",
    r"\bwhat should i do\b",
    r"\bdo you think i should\b",
    r"\bwhat's my best (move|option|strategy)\b",
    r"\bwhat is my best (move|option|strategy)\b",
]

_HIGH_STAKES_PATTERNS = [
    r"\beviction\b",
    r"\brestraining order\b",
    r"\bcriminal (charge|charges|case)\b",
    r"\barrest(ed)?\b",
    r"\bimmigration\b",
    r"\bdeportation\b",
    r"\bvisa (denial|denied|revoked)\b",
    r"\bcustody\b",
    r"\bbankrupt(cy)?\b",
    r"\blawsuit\b",
    r"\bsued\b",
    r"\bsue (me|him|her|them)\b",
]

_ADVICE_RE = re.compile("|".join(_ADVICE_PATTERNS), re.IGNORECASE)
_HIGH_STAKES_RE = re.compile("|".join(_HIGH_STAKES_PATTERNS), re.IGNORECASE)

ESCALATION_NOTICE = (
    "This question touches on a high-stakes legal matter. LexAssist can help you "
    "understand the relevant document text, but for guidance specific to your "
    "situation, please consult a licensed attorney or a local legal aid "
    "organization."
)

ADVICE_REFRAME_NOTICE = (
    "LexAssist explains what a document says and what clauses typically mean -- "
    "it doesn't recommend what you personally should do. Here's the relevant "
    "text and context; consider bringing this to a licensed attorney for advice "
    "tailored to your situation."
)


def is_advice_seeking(question: str) -> bool:
    """Return True if the question asks for personalized legal advice."""
    return bool(_ADVICE_RE.search(question))


def needs_escalation(question: str) -> bool:
    """Return True if the question involves a high-stakes legal matter."""
    return bool(_HIGH_STAKES_RE.search(question))


def escalation_notice_for(question: str) -> Optional[str]:
    """Return an escalation notice string if warranted, else None."""
    if needs_escalation(question):
        return ESCALATION_NOTICE
    return None
