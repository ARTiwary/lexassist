"""Security helpers.

These are intentionally simple and dependency-free so they are easy to
audit. In a production deployment, upload scanning (e.g., antivirus),
authenticated storage, and a proper distributed rate limiter (Redis) would
replace the in-memory versions here.
"""
from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, UploadFile, status

from .config import settings


class UnsupportedFileType(HTTPException):
    def __init__(self, extension: str):
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{extension}'. "
                f"Allowed types: {', '.join(settings.allowed_extensions)}"
            ),
        )


class FileTooLarge(HTTPException):
    def __init__(self, size: int):
        super().__init__(
            status_code=413,
            detail=(
                f"File is {size} bytes, which exceeds the "
                f"{settings.max_upload_bytes} byte limit."
            ),
        )


def validate_extension(filename: str) -> str:
    """Validate the file extension against an explicit allow-list.

    Raises UnsupportedFileType if the extension is not permitted.
    Returns the lower-cased extension on success.
    """
    _, ext = os.path.splitext(filename.lower())
    if ext not in settings.allowed_extensions:
        raise UnsupportedFileType(ext or "(none)")
    return ext


def validate_upload_size(content: bytes) -> None:
    """Reject uploads above the configured size limit.

    Guards against resource-exhaustion (memory/CPU) from oversized files,
    since documents are processed in memory rather than streamed to disk.
    """
    if len(content) > settings.max_upload_bytes:
        raise FileTooLarge(len(content))


async def read_and_validate_upload(upload: UploadFile) -> bytes:
    """Validate filename/extension and size, then return the file bytes."""
    if not upload.filename:
        raise HTTPException(status_code=400, detail="Uploaded file is missing a filename.")
    validate_extension(upload.filename)
    content = await upload.read()
    validate_upload_size(content)
    return content


def sanitize_error_message(exc: Exception) -> str:
    """Return a safe, generic error message.

    Prevents leaking stack traces, file paths, or internal details to
    clients, which could otherwise aid an attacker or expose sensitive
    document content in logs returned to the caller.
    """
    return "An internal error occurred while processing the request."


class InMemoryRateLimiter:
    """A minimal fixed-window rate limiter, keyed by client identifier.

    Not suitable for a multi-process production deployment (state is not
    shared across workers) -- included here to demonstrate the control
    and to keep the demo dependency-free. Swap for a Redis-backed limiter
    in production.
    """

    def __init__(self, limit_per_minute: int) -> None:
        self.limit_per_minute = limit_per_minute
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, client_key: str) -> bool:
        now = time.monotonic()
        window_start = now - 60
        hits = self._hits[client_key]
        while hits and hits[0] < window_start:
            hits.popleft()
        if len(hits) >= self.limit_per_minute:
            return False
        hits.append(now)
        return True


rate_limiter = InMemoryRateLimiter(settings.rate_limit_per_minute)
