"""Wrapper around the Groq API used for all generative tasks.

Groq (console.groq.com) exposes an OpenAI-compatible chat completions API
and is used here as the LLM provider for cost-effective, low-latency
inference.

Design notes:
- The API key is read only from the environment (see config.py) and is
  never logged or returned to the client.
- `get_llm_client()` returns a real `GroqLLMClient` by default
  (`USE_LIVE_LLM=true`). A `MockLLMClient` is available for local
  development without an API key (`USE_LIVE_LLM=false`) and is what the
  automated test suite injects via a FastAPI dependency override --
  keeping tests fast, free, and independent of network access / API
  quota regardless of this setting.
- All prompts instruct the model to ground its answer in the supplied
  clause text and to explicitly say when the document does not address a
  question, rather than filling gaps from general legal knowledge.
"""
from __future__ import annotations

from typing import List, Protocol

from .config import settings

SYSTEM_PROMPT = (
    "You are a legal-document comprehension assistant. You explain what a "
    "document says in plain language. You NEVER give personalized legal "
    "advice or tell the user what they should do -- you explain the text "
    "and general meaning of clauses only. Always ground your answer in the "
    "clause text provided; if the provided text does not address the "
    "question, say so explicitly rather than guessing. Keep answers "
    "concise and cite which clause(s) you used."
)


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class MockLLMClient:
    """Deterministic offline stand-in used for tests and local dev.

    Produces a plausible, clearly-labeled placeholder response derived
    from the input, so the rest of the pipeline (formatting, guardrails,
    citation wiring) can be fully exercised without a network call.
    """

    def complete(self, system: str, user: str) -> str:
        snippet = user.strip().splitlines()[0][:160] if user.strip() else ""
        return (
            "[MOCK RESPONSE -- set USE_LIVE_LLM=true and GROQ_API_KEY "
            f"to call the real model]\nBased on the provided text: {snippet}"
        )


class GroqLLMClient:
    """Live client backed by the Groq chat completions API."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ValueError(
                "GROQ_API_KEY is not set. Get a free key at "
                "https://console.groq.com/keys and set it in your "
                "environment or .env file, or set USE_LIVE_LLM=false to "
                "use the offline mock client instead."
            )
        import groq  # local import: keeps the dependency optional for mock-only usage

        self._client = groq.Groq(api_key=api_key)
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


def get_llm_client() -> LLMClient:
    """Factory that returns the appropriate client based on configuration."""
    if settings.use_live_llm:
        return GroqLLMClient(settings.groq_api_key, settings.groq_model)
    return MockLLMClient()
