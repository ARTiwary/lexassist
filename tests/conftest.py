"""Shared pytest fixtures.

The application defaults to calling the real Groq API (USE_LIVE_LLM=true).
Tests must not depend on network access, an API key, or Groq's uptime/
quota, so we override the `get_llm` FastAPI dependency for the entire
test session to always return the deterministic MockLLMClient --
regardless of the USE_LIVE_LLM setting or environment. This exercises the
full request/response pipeline (routing, guardrails, retrieval,
formatting) without ever making a real network call.
"""
from backend.llm_client import MockLLMClient
from backend.main import app, get_llm

app.dependency_overrides[get_llm] = lambda: MockLLMClient()
