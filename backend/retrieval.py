"""Clause-level retrieval used to ground LLM answers in the source document.

Rather than depending on an external vector database and an embeddings
API call for every query (added cost, latency, and an external network
dependency), retrieval here uses scikit-learn's TF-IDF vectorizer with
cosine similarity. This is fast, fully local, deterministic, and easy to
unit test -- appropriate for the clause counts found in typical legal
documents (tens to low hundreds of clauses). It can be swapped for a
proper embedding-based vector store without changing the public
interface (`ClauseIndex.query`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .document_parser import ParsedClause


@dataclass
class RetrievedClause:
    clause_id: str
    text: str
    score: float


class ClauseIndex:
    """An in-memory, per-document TF-IDF index over clauses."""

    def __init__(self, clauses: Sequence[ParsedClause]) -> None:
        if not clauses:
            raise ValueError("Cannot build an index over zero clauses.")
        self._clauses: List[ParsedClause] = list(clauses)
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._matrix = self._vectorizer.fit_transform([c.text for c in self._clauses])

    def query(self, question: str, top_k: int = 3) -> List[RetrievedClause]:
        """Return the top_k clauses most relevant to the question."""
        if not question.strip():
            return []
        query_vec = self._vectorizer.transform([question])
        similarities = cosine_similarity(query_vec, self._matrix)[0]
        ranked_indices = similarities.argsort()[::-1][:top_k]
        return [
            RetrievedClause(
                clause_id=self._clauses[i].clause_id,
                text=self._clauses[i].text,
                score=float(similarities[i]),
            )
            for i in ranked_indices
            if similarities[i] > 0
        ]

    def __len__(self) -> int:
        return len(self._clauses)
