# CardLens AI implementation status

Verification: the pull request's GitHub Actions runs PostgreSQL migration/seed, backend tests, the frontend production build, Docker builds, and the Compose smoke test. Check the current PR checks for the result on its latest commit.

## IMPLEMENTED

- Existing React + TypeScript + Vite app retained. Added a responsive public landing page, protected account flows, six-step resumable onboarding, profile editor, personalized dashboard, card explorer/details/saved cards, account settings, activity, and logout UI.
- FastAPI validation, deterministic eligibility filtering, configurable weighted CardLens Score with six API breakdown factors, illustrative per-category reward estimate, deterministic ranking, generated why/why-not explanations, profile completeness, and confidence estimate with explanation.
- Deterministic personalized compare supports user-selected pairs and trios as well as the top ranked pair.
- What-If accepts all spending categories, income, credit score, annual-fee preference, and reward preference changes; it returns before/after rankings, moved cards, and a deterministic explanation.
- SQLAlchemy schema for users, profiles, card catalog/benefits/documents, recommendations, conversations and simulations; account migration adds email/password hashes and revocable sessions, and a further migration adds saved cards. Alembic enables pgvector.
- Idempotent demo-card seed script. Docker Compose has PostgreSQL/pgvector, API, and frontend services. CI runs migration and seed against PostgreSQL.
- pgvector retrieval endpoint and JSONL ingestion script with source/version/verification metadata. Empty retrieval returns an explicit insufficient-evidence answer.
- Replaceable LLM, embedding, STT, and TTS protocols and optional OpenAI-compatible adapter. LLM can call deterministic profile/recommendation/card/compare/value/simulation/RAG tools. Without credentials, deterministic fallbacks remain.
- Optional voice transcription and speech endpoints with bounded uploads; English, Hindi, Telugu, and Tamil are accepted, with browser speech fallback where the browser provides a matching locale.
- Advisor panel with text chat, bounded client-side context, optional microphone input/speech output, locale and speech-speed selectors, and source links; account-scoped conversation archives can be reopened, renamed, individually deleted, or cleared.
- Optional natural-language profile extraction with validated AI JSON, one retry, deterministic local fallback, unknown fields left unset, and editable user review before recommendations.
- API request IDs, per-IP in-process rate windows, redacted structured request metadata logs, readiness checks, and environment-based CORS. Production mode fails fast without DATABASE_URL and explicit HTTPS FRONTEND_ORIGINS, and rejects wildcard CORS.
- Backend tests cover scoring, explanations, compare, What-If, LLM tool routing, voice fallback, empty RAG, pgvector retrieval and model schema. CI builds the frontend and runs database migration/seed/tests.
- README, architecture, deployment, testing, implementation status, and interview notes.

## PARTIALLY IMPLEMENTED

- Email/password authentication uses scrypt password hashes and opaque database-backed HTTP-only sessions; password change and password-confirmed account deletion are implemented. Profiles, recommendation snapshots, comparison/What-If history, Advisor conversations, saved cards, and voice language preference are account-owned in PostgreSQL. Profiles and rankings restore on sign-in. Multiple conversation archives/search, explicit profile consent, retention schedules, and consent audit history are not implemented. The ranking still uses the in-memory synthetic card constants as its authoritative catalog.
- RAG ingestion/retrieval path is implemented and tested with a fake embedding vector in CI. No issuer-verified documents are bundled, and real external embedding/LLM API calls are not exercised in CI.
- LLM adapter/tool flow is implemented and tool routing is tested with a fake provider. Live model quality, timeouts against a provider, retry behavior, citations rendered by a live model, and Hindi/Telugu answer quality are not verified. Natural-language profile extraction is optional and never required for demo recommendations.
- Voice API and UI paths exist. Live STT/TTS, real device/browser permission behavior, and multilingual speech accuracy are not verified.
- Confidence is a deterministic heuristic from profile completeness and score separation; it is not calibrated against user outcomes.
- Rate limiting is in-process by remote address and must be replaced by a shared store before multi-instance deployment.
- Error fallback and request metadata are implemented; the production-like Compose demo now passes CI smoke checks. Production alerting/metrics and distributed caching remain.
- Reward optimizer uses illustrative category rates minus annual fee; caps, exclusions, joining fees, redemption, and conditional benefits are absent.
- Model evaluation is not available because no labeled recommendation dataset exists; no ML performance claims are made.

## MISSING

- Full public marketing/landing experience, account recovery/password change, account deletion, profile consent/retention controls, and a complete account settings area.
- Issuer-verified real card catalog with change monitoring and a production document set.
- Conversation archive/search and more complete cross-session Advisor memory.
- End-to-end multilingual Advisor/voice validation (including generated answer quality); browser microphone/speaker accessibility testing.
- Shared/distributed rate limiting and cache infrastructure, production observability/alerting, CI lint/type-check rules, and verified production deployment.
- Wider frontend accessibility/interaction tests and real-device end-to-end demo testing. The new authentication flow is covered by API integration tests; no browser E2E suite is configured.
- External deployment to a managed host/database has not been performed or verified.

Synthetic catalog terms and example source URLs must not be presented as real financial information.
