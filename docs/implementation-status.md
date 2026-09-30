# CardLens AI implementation status

Audit performed against the repository tree and source on 30 September 2026. The pre-change GitHub Actions run passed both the backend unittest suite and frontend production build.

## IMPLEMENTED

- React + TypeScript + Vite dashboard with responsive styling.
- Editable in-memory demo profile with income, score, fee preference, reward preference, and six spending categories.
- FastAPI with Pydantic profile validation and health/readiness endpoints.
- Synthetic card catalog explicitly labeled as demo data.
- Deterministic eligibility filtering and ranking; the LLM does not make decisions.
- Estimated rewards and net annual value from monthly spend and demo reward rates.
- Deterministic travel what-if endpoint and UI.
- Top-two personalized comparison API and UI.
- Basic recommendation reasons and limitations.
- Initial Docker API image, compose file, architecture notes, backend tests, and GitHub Actions backend/frontend CI.
- Works without AI credentials.

## PARTIALLY IMPLEMENTED

- CardLens Score: backend score exists; breakdown and score methodology need to be exposed and explained to the user.
- Reward optimizer: uncapped illustrative reward rates and annual fees only; no validated caps, exclusions, redemption rules, or conditional benefits.
- Explainability: basic why strings exist, but comparisons against alternatives and rank-specific why-not reasons need improving.
- What-if: travel-only UI change; API can merge category changes, but income/fee changes and rank movement explanation are not surfaced.
- Profile insight: derives the largest entered category and reward preference; no historical profile or calibrated financial analysis.
- Confidence: basic profile-completeness signal exists; a useful confidence measure and explanation are still needed.
- Chat: /api/chat is a deterministic safe fallback response, not a contextual tool-using assistant.
- Deployment: API Docker setup exists; database-backed production configuration, frontend deployment config, and end-to-end container verification remain.

## MISSING

- PostgreSQL persistence, SQLAlchemy models, Alembic migrations, and reproducible DB seed.
- pgvector extension, embeddings, issuer-document ingestion, retrieval, citation metadata, and RAG-grounded factual answers.
- Replaceable LLM, embedding, speech-to-text, and text-to-speech provider interfaces.
- Real tool-calling AI Advisor with session memory.
- Voice capture/transcription/speech output and English/Hindi/Telugu language selection.
- Persistent users/profiles/recommendations/conversations/simulations.
- Per-route rate limiting, bounded external-service timeouts/retries, request IDs, structured redacted logs, and production error envelopes.
- Expanded tests for score components, why-not, confidence, comparison edge cases, RAG, chatbot tools, voice fallback, DB migrations/failure, and multilingual behavior.
- Interview-preparation and full deployment/testing documentation.
- Real credit-card dataset: no issuer-verified production offers are included; the available catalog must remain labeled synthetic.
- Labeled recommendation outcomes and model evaluation: no ML accuracy or recommendation quality claims are supported.
