"""
Centralized application configuration.

All configurable values are read from environment variables so that no
secrets or environment-specific values are hardcoded in source code.
See .env.example for the full list of supported variables.

`.env` is loaded automatically via python-dotenv so that running
`uvicorn backend.main:app` picks up values from a local `.env` file
without requiring the user to export variables manually in their shell.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()  # loads variables from a .env file in the current working directory, if present


def _get_bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # LLM provider configuration (Groq -- OpenAI-compatible chat completions API)
    groq_api_key: str = field(default_factory=lambda: os.getenv("GROQ_API_KEY", ""))
    groq_model: str = field(
        default_factory=lambda: os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    )

    # Upload limits (security: prevent resource-exhaustion / abuse)
    max_upload_bytes: int = field(default_factory=lambda: _get_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024))
    allowed_extensions: tuple = (".pdf", ".docx", ".txt")

    # CORS: explicit allow-list rather than wildcard, configurable per deployment.
    # Includes both localhost and 127.0.0.1 variants by default since
    # browsers treat them as different origins even on the same machine.
    allowed_origins: tuple = field(
        default_factory=lambda: tuple(
            o.strip()
            for o in os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,"
                "http://localhost:8000,http://127.0.0.1:8000",
            ).split(",")
        )
    )

    # Feature flags. Defaults to True: the app calls the real Groq API by
    # default. Set USE_LIVE_LLM=false to fall back to the deterministic
    # offline mock (useful for local development without an API key).
    # The test suite does NOT rely on this flag -- it injects a mock LLM
    # client directly via a FastAPI dependency override, so tests stay
    # fast/free/offline regardless of this setting.
    use_live_llm: bool = field(default_factory=lambda: _get_bool("USE_LIVE_LLM", True))

    # Simple in-memory rate limiting (requests per minute per client)
    rate_limit_per_minute: int = field(default_factory=lambda: _get_int("RATE_LIMIT_PER_MINUTE", 30))


settings = Settings()
