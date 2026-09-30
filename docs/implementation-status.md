# CardLens AI implementation status

Audit performed against the repository tree and source on 30 September 2026. The last confirmed green CI run at the start of this continuation passed backend tests and the frontend production build. This document reflects the subsequent changes; check the latest Actions run for final verification.

## IMPLEMENTED

- Existing React + TypeScript + Vite responsive dashboard and editable in-memory profile retained.
- FastAPI validation, deterministic eligibility filtering, configurable weighted CardLens Score with six API breakdown factors, illustrative per-category reward estimate, deterministic ranking, generated why/why-not explanations, profile completeness, and confidence estimate with explanation.
- Top-two personalized compare API/UI.
- What-If accepts category spending, income, credit score, and annual-fee preference changes; responds with before/after rankings, moved cards, and deterministic explanation. UI now exposes multiple spend sliders and highlights movements.
- SQLAlchemy schema for requested user, profile, card, benefit, card document, recommendation, explanation, conversation, and simulation tables; Alembic initial migration enables pgvector.
- Idempotent demo-card seed script. Docker Compose has PostgreSQL/pgvector, API, and frontend services. CI runs migration and seed against PostgreSQL.
- pgvector retrieval endpoint and JSONL ingestion script with source/version/verification metadata. Empty retrieval returns an explicit insufficient-evidence answer.
- Replaceable LLM, embedding, STT, and TTS protocols and optional OpenAI-compatible adapter. LLM can call deterministic profile/recommendation/card/compare/value/simulation/RAG tools. Without credentials, deterministic fallbacks remain.
- Optional voice transcription and speech endpoints with bounded uploads, supported language codes (English/Hindi/Telugu), and friendly failure response.
- Advisor panel with text chat, bounded client-side message context, optional microphone input/speech output, language selector for voice, and source links.
- API request IDs, per-IP in-process rate windows, redacted structured request metadata logs, readiness checks, and environment-based CORS.
- Backend tests cover scoring, explanations, compare, What-If, LLM tool routing, voice fallback, empty RAG, pgvector retrieval and model schema. CI builds the frontend and runs database migration/seed/tests.
- README, architecture, deployment, testing, implementation status, and interview notes.

## PARTIALLY IMPLEMENTED

- PostgreSQL tables, migration, and seeding work; app profiles/recommendations/conversations/simulation history are not yet durably connected to authenticated user sessions. The ranking still uses the in-memory card constants as its authoritative demo catalog.
- RAG ingestion/retrieval path is implemented and tested with a fake embedding vector in CI. No issuer-verified documents are bundled, and real external embedding/LLM API calls are not exercised in CI.
- LLM adapter/tool flow is implemented and tool routing is tested with a fake provider. Live model quality, timeouts against a provider, retry behavior, citations rendered by a live model, and Hindi/Telugu answer quality are not verified.
- Voice API and UI paths exist. Live STT/TTS, real device/browser permission behavior, and multilingual speech accuracy are not verified.
- Confidence is a deterministic heuristic from profile completeness and score separation; it is not calibrated against user outcomes.
- Rate limiting is in-process by remote address and must be replaced by a shared store before multi-instance deployment.
- Error fallback and request metadata are implemented; production alerting/metrics, distributed caching, and Docker image smoke testing remain.
- Reward optimizer uses illustrative category rates minus annual fee; caps, exclusions, joining fees, redemption, and conditional benefits are absent.
- Model evaluation is not available because no labeled recommendation dataset exists; no ML performance claims are made.

## MISSING

- Authentication, profile consent and retention controls, secure user self-service, and complete persistence flows.
- Issuer-verified real card catalog with change monitoring and a production document set.
- Persistent conversation read/write integration and true cross-session memory.
- Multilingual Advisor output validated end-to-end in English, Hindi, and Telugu; browser microphone/speaker accessibility testing.
- Shared/distributed rate limiting and cache infrastructure, production observability/alerting, CI lint/type-check rules, and verified production deployment.
- Wider frontend accessibility/interaction tests and real-device end-to-end demo testing.

Synthetic catalog terms and example source URLs must not be presented as real financial information.
