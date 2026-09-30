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