# CardLens AI

**See the card that's right for you.**

CardLens AI is a fintech decision-support demo that ranks credit cards from a structured spending profile. Eligibility, rewards, suitability scores, and what-if simulations are deterministic; an optional language model is presentation-only and never decides card ranking.

## Current implementation

This repository is initialized with a small local-first foundation. Included card offers are **synthetic demo data**, not current financial product terms. No approval guarantee is made. The API remains usable without AI credentials.

## Run locally

Requirements: Python 3.11+ and Node.js 20+.

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

The API is available at http://localhost:8000; interactive docs at `/docs`. In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` if the API is not at `http://localhost:8000`.

## Core behavior

- Eligibility filters known minimum income and credit score requirements. Missing data is treated as unknown, never invented.
- Eligible cards are ranked with configurable deterministic weights, spending similarity, user preference, fee fit, and estimated net annual value.
- Annual value is an estimate based on demo reward rates and declared monthly spending. Real issuer caps, exclusions, and current terms are not represented.
- `POST /api/simulate` reruns the same engine after a profile change.
- `POST /api/chat` gives deterministic explanations. Card-specific facts that are not in the local demo catalog are not asserted.

## Safety and limitations

CardLens provides informational recommendations, not financial advice or an issuer decision. Actual approval and terms are determined by the card issuer. This demo does not collect payment credentials, CVV, passwords, or bank account numbers. Demo catalog values must be replaced by verified issuer-sourced terms before public use. No labeled user-choice dataset is included, so this version does not claim predictive ML performance.

## Stack

React, TypeScript, Vite, FastAPI, Pydantic, and a deterministic hybrid ranking baseline. See `docs/architecture.md` for the system boundary and extension path.

## PostgreSQL and pgvector

For the full local stack, follow [docs/deployment.md](docs/deployment.md). PostgreSQL migrations live in `backend/migrations`; the initial migration enables pgvector and creates the relational tables. `scripts/seed_database.py` loads only explicitly synthetic demo offers. With `DATABASE_URL` unset, the API continues to use its deterministic demo catalog.

## Score, What-If, Advisor, and RAG

The CardLens Score endpoint includes six weighted factors, category reward estimates, recommendation reasons, rank-relative explanations, profile completeness, and a measurable confidence estimate with a reason. What-If accepts category spend, income, score, and fee-preference changes and returns rank movements. The Advisor uses deterministic calculations and, when configured, optional LLM tool calls; factual issuer questions use pgvector retrieval and return source metadata. Empty or unavailable RAG fails closed. Optional transcription and speech endpoints degrade to a text fallback.

To ingest source material, create JSONL with the required metadata and verified primary-source text, then run `python scripts/ingest_documents.py path/to/documents.jsonl`. The embedding adapter requires a configured embedding key. Do not label synthetic examples as verified issuer documents.

## Current limitations

- The demo offer catalog is synthetic and is not an up-to-date list of real credit cards.
- Reward caps, exclusions, joining fees, redemption limitations, and benefit conditions are not modeled for the synthetic catalog.
- PostgreSQL schema and seeding are exercised in CI, but profile, recommendation, and conversation writes are not yet wired to authenticated user workflows. The session/profile tables are groundwork, not proof of durable user persistence.
- The demo has no authentication, profile consent/retention controls, production distributed rate limiter, or production deployment verification. Do not enter real sensitive financial data.
- No recommendation outcome dataset is available, so there are no model-performance claims.

See [implementation status](docs/implementation-status.md), [architecture](docs/architecture.md), [testing](docs/testing.md), [deployment](docs/deployment.md), and [interview notes](docs/interview-preparation.md).
