# LexAssist

**Understand, compare, and prepare — before you sign.**

LexAssist is a GenAI-powered assistant that helps non-lawyers make sense of
legal documents: leases, employment offers, NDAs, freelance contracts,
terms of service. It simplifies dense text, flags risky clauses, compares
documents side by side, answers questions grounded in the actual document
text, and prepares users to get the most out of a real consultation with a
licensed attorney.

**It provides information and preparation — never a substitute for
professional legal advice.** That boundary is enforced in the code, not
just in a disclaimer (see [Guardrails](#guardrails)).

---

## Table of Contents
- [Problem Statement Alignment](#problem-statement-alignment)
- [Features](#features)
- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Guardrails](#guardrails)
- [Security](#security)
- [Testing](#testing)
- [Accessibility](#accessibility)
- [Project Structure](#project-structure)
- [Design Trade-offs & Roadmap](#design-trade-offs--roadmap)

---

## Problem Statement Alignment

| Use case from the brief | How LexAssist addresses it |
|---|---|
| Simplifying complex legal documents | `POST /api/documents` returns a plain-language summary plus per-clause text, upon upload |
| Comparing contracts, agreements, or policies | `POST /api/compare` diffs two uploaded documents and explains practical differences |
| Highlighting important clauses, obligations, risks | `GET /api/documents/{id}/risks` flags clauses with severity + explanation |
| Answering questions based on provided documents | `POST /api/ask` performs retrieval-grounded Q&A, always citing the source clause(s) |
| Helping users understand options/next steps | Escalation notices point to attorneys/legal aid for high-stakes questions |
| Generating summaries, checklists, actionable outputs | `GET /api/documents/{id}/checklist` produces a "before you sign" list |
| Preparing questions for a legal professional | The same checklist endpoint generates a "questions for a lawyer" list |
| Information/assistance, not advice replacement | See [Guardrails](#guardrails) — enforced with rule-based classifiers and reframing logic |

---

## Features

- **Upload & parse**: `.pdf`, `.docx`, `.txt` documents are parsed and
  segmented into clauses (numbered-section detection with paragraph
  fallback).
- **Plain-language summary**: generated on upload.
- **Grounded Q&A**: TF-IDF retrieval finds the most relevant clause(s) for
  a question; the LLM is instructed to answer *only* from that text and
  say so explicitly when the document doesn't cover the question.
- **Risk highlighting**: per-clause severity assessment (low/medium/high)
  with a plain-language explanation.
- **Document comparison**: highlights meaningful differences between two
  documents (e.g., termination rights, liability, notice periods).
- **Checklists**: a "before you sign" list and a "questions for a lawyer"
  list, generated from the specific uploaded document.
- **Guardrails**: advice-seeking questions are detected and reframed;
  high-stakes topics (eviction, immigration, criminal matters, lawsuits)
  trigger an explicit referral to a licensed professional or legal aid.

---

## Architecture

```
Browser (frontend/) ── fetch() ──▶ FastAPI app (backend/main.py)
                                        │
                     ┌──────────────────┼───────────────────┐
                     ▼                  ▼                    ▼
          document_parser.py     retrieval.py          guardrails.py
          (PDF/DOCX/TXT →        (TF-IDF clause         (advice /
           clauses)                index + query)        escalation
                     │                  │                 detection)
                     └──────────┬───────┘
                                ▼
                          llm_client.py
                (Groq API by default, or a
                 deterministic mock client for
                 offline dev/tests)
```

- **No external vector database**: clause counts in typical legal
  documents (tens to low hundreds) don't need one. A local TF-IDF index
  (`scikit-learn`) gives fast, deterministic, fully-offline grounding for
  retrieval — swappable for an embeddings-based store later without
  changing the calling code.
- **Real LLM by default, via Groq**: `USE_LIVE_LLM=true` is the default,
  so the app calls the real model through [Groq](https://console.groq.com)
  (an OpenAI-compatible, low-latency inference API) as soon as
  `GROQ_API_KEY` is set. A deterministic `MockLLMClient` is also included
  for local development without a key (`USE_LIVE_LLM=false`) and is what
  the automated test suite injects via a FastAPI dependency override
  (`tests/conftest.py`) — so tests stay fast, free, and independent of
  network access or API quota regardless of this setting.
- **In-memory document store**: appropriate for a demo. A production
  deployment would swap this for encrypted, access-controlled storage
  scoped to an authenticated session (see [Roadmap](#design-trade-offs--roadmap)).

---

## Quick Start

### Backend
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env and set GROQ_API_KEY (get a free key at https://console.groq.com/keys)
# .env is loaded automatically at startup via python-dotenv -- no need to
# export variables manually.

uvicorn backend.main:app --reload --port 8000
```

The API is now running at `http://localhost:8000`, calling the real Groq
model by default. Visit `http://localhost:8000/docs` for interactive
OpenAPI docs.

If you don't have a Groq key yet, set `USE_LIVE_LLM=false` in `.env` to
run against the deterministic offline mock instead.

### Frontend
The frontend is dependency-free static HTML/CSS/JS — no build step.
```bash
cd frontend
python -m http.server 5173
```
Open `http://localhost:5173`. Try uploading `sample_docs/sample_lease.txt`.

### LLM provider: Groq
```bash
# in .env
USE_LIVE_LLM=true
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b   # or another model from console.groq.com/docs/models
```
Restart the backend after editing `.env`. Without a key set,
`USE_LIVE_LLM=true` raises a clear configuration error at startup rather
than silently failing or leaking a confusing stack trace.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check |
| POST | `/api/documents` | Upload a document (`multipart/form-data`, field `file`) |
| GET | `/api/documents/{id}` | Retrieve a previously parsed document |
| POST | `/api/ask` | `{document_id, question, user_role?}` → grounded answer |
| POST | `/api/compare` | `{document_id_a, document_id_b}` → key differences |
| GET | `/api/documents/{id}/risks` | Per-clause risk report |
| GET | `/api/documents/{id}/checklist` | Pre-sign checklist + lawyer questions |

Full interactive schema: `/docs` (Swagger UI) once the server is running.

---

## Guardrails

LexAssist enforces the "information, not advice" boundary in code
(`backend/guardrails.py`), not only in UI copy:

1. **Advice-seeking detection** — questions like *"Should I sign this?"*
   or *"Am I going to win?"* are detected and the response is prefixed
   with a clear reframing notice before still surfacing the relevant
   document text.
2. **High-stakes escalation** — questions touching eviction, immigration,
   criminal matters, custody, bankruptcy, or lawsuits trigger a
   proactive, explicit referral to a licensed attorney or legal aid,
   regardless of how the question is phrased.
3. **Mandatory grounding** — every `/api/ask` response is generated from
   retrieved clause text and returns the `cited_clause_ids` used, so a
   user can verify the answer against their own document. If no clause is
   relevant, the system says so instead of guessing from general
   knowledge.

These are implemented as transparent, testable, rule-based classifiers
(see `tests/test_guardrails.py`) rather than opaque model calls, so
behavior is auditable and doesn't depend on network availability.

---

## Security

- **Explicit file-type allow-list** (`.pdf`, `.docx`, `.txt`) — rejects
  everything else with `415 Unsupported Media Type`.
- **Upload size limit** (default 10 MB, configurable) — rejects oversized
  files with `413` before they're processed in memory.
- **No secrets in source** — the Groq API key is read only from the
  environment (`backend/config.py`); `.env` is git-ignored and
  `.env.example` contains no real values.
- **Explicit CORS allow-list** — configurable via `ALLOWED_ORIGINS`,
  rather than a wildcard.
- **Input validation everywhere** — all request bodies are Pydantic
  models with length limits (e.g., `question` capped at 1000 chars),
  which FastAPI validates before any handler code runs.
- **Sanitized error responses** — unexpected exceptions are caught and
  converted to a generic message (`backend/security.py:sanitize_error_message`)
  so stack traces, file paths, or document content never leak into an
  API error response.
- **Basic rate limiting** — an in-memory fixed-window limiter
  (`RATE_LIMIT_PER_MINUTE`) protects against naive abuse; the code notes
  where to swap in a distributed limiter (e.g., Redis) for production.
- **No arbitrary file paths** — uploads are processed entirely in memory
  and never written to disk with a user-controlled filename.

---

## Testing

34 automated tests, all passing, covering parsing, retrieval, guardrails,
and the full API surface (including error paths):

```bash
pip install -r requirements.txt
pytest tests/ -v
```

| File | Focus |
|---|---|
| `tests/test_document_parser.py` | Clause segmentation (numbered sections, paragraph fallback, edge cases) |
| `tests/test_retrieval.py` | TF-IDF relevance ranking, empty-input handling |
| `tests/test_guardrails.py` | Advice-detection and escalation-detection accuracy |
| `tests/test_api.py` | End-to-end API behavior: uploads (including rejected file type/size), Q&A (including advice-reframing and escalation), compare, risk report, checklist, 404/422 error paths |

The test suite runs entirely offline: `tests/conftest.py` overrides the
`get_llm` FastAPI dependency with the deterministic `MockLLMClient` for
the whole session, regardless of the `USE_LIVE_LLM` setting. Tests
require no Groq API key and incur no cost or flakiness from network
calls, while still exercising the complete request/response flow
(routing, guardrails, retrieval, formatting) that the real model would go
through.

---

## Accessibility

- Semantic HTML landmarks (`header`, `main`, `footer`, `section`) with
  proper heading hierarchy.
- A skip-to-content link for keyboard users.
- All form inputs have associated `<label>` elements; the file size limit
  is exposed via `aria-describedby`.
- Dynamic regions (`answer-output`, `risk-output`, `checklist-output`,
  upload status) use `aria-live` / `role="status"` so screen readers
  announce new content automatically.
- Visible focus outlines (`:focus-visible`) for keyboard navigation,
  distinct from default browser styling.
- Color is never the sole indicator of meaning: risk severity is
  communicated through both a color-coded border *and* text
  (`(high)` / `(medium)` / `(low)`) in the label itself.
- Sufficient color contrast between text and background (dark navy on
  white/light gray, WCAG AA-oriented palette).

---

## Project Structure

```
lexassist/
├── backend/
│   ├── main.py            # FastAPI app & routes
│   ├── config.py          # env-driven settings
│   ├── models.py          # Pydantic request/response schemas
│   ├── document_parser.py # PDF/DOCX/TXT → clauses
│   ├── retrieval.py       # TF-IDF clause retrieval
│   ├── guardrails.py      # advice/escalation classifiers
│   ├── llm_client.py      # Groq API wrapper + offline mock
│   └── security.py        # upload validation, rate limiting
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── tests/                 # 34 pytest tests
├── sample_docs/
│   └── sample_lease.txt
├── requirements.txt
├── .env.example
└── README.md
```

---

## Design Trade-offs & Roadmap

Deliberate scope choices for a hackathon-sized submission, and what a
production version would add next:

- **In-memory storage → persistent, encrypted, per-user storage** with
  authentication, so documents survive restarts and are isolated per
  account.
- **TF-IDF retrieval → embeddings-based vector search** for better
  semantic matching on paraphrased questions, once clause volume or
  accuracy requirements grow.
- **Free-text compare output → JSON-schema-constrained generation**
  parsed into fully structured `CompareDifference` items (the schema
  already supports this; the current implementation wraps the raw model
  output in one item for simplicity).
- **Rule-based guardrails → hybrid rule + LLM classifier** for higher
  recall on advice-seeking/high-stakes detection, using the current rules
  as an always-available fallback.
- **Single-process rate limiter → distributed limiter** (e.g., Redis) for
  multi-instance deployments.
- Multi-language document support; e-signature platform integration for
  pre-signing risk checks; warm-handoff partnerships with legal aid
  organizations for flagged high-stakes cases.

---

## Disclaimer

LexAssist provides legal information and document-comprehension
assistance. It does not provide legal advice, does not create an
attorney-client relationship, and is not a substitute for consultation
with a licensed attorney regarding your specific situation.
