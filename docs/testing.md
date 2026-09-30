# Testing CardLens AI

CI runs on pushes and pull requests.

- Backend unit/API tests: `python -m unittest discover -s backend/tests -v`
- PostgreSQL migration and seed check: `alembic -c backend/alembic.ini upgrade head`, then `python scripts/seed_database.py`
- Frontend production build: `cd frontend && npm install && npm run build`
- PostgreSQL/pgvector retrieval test runs with the CI PostgreSQL service and a fake embedding vector, so it does not require a paid embedding API.
- LLM tool routing and AI/voice-unavailable behavior are tested with fakes or absent credentials.

A live OpenAI-compatible model, live voice provider, real issuer documents, deployment target, and browser microphone permissions are not required in CI and are not claimed as verified. The database-backed migration/seed path is exercised in CI; the Docker image itself is not built by the current workflow.
