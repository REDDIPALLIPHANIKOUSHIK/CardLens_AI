# Testing CardLens AI

## Automated checks

CI runs on pushes and pull requests:

- Backend suite (pytest): `pytest -q backend/tests`
- PostgreSQL/pgvector migrations and seed: `alembic -c backend/alembic.ini upgrade head`, then `python scripts/seed_database.py`
- Frontend TypeScript check and production build: `cd frontend && npm install && npm run build`
- Production Docker image builds for API and Nginx-served frontend.

The backend suite covers deterministic recommendations, score/explanations, compare, What-If, profile validation/extraction, chat tools and fallback, RAG empty/retrieval behavior, database readiness failure, and relational schema. CI PostgreSQL retrieval tests use a fake embedding vector, so they need no paid AI key.

There is no standalone frontend unit-test or browser end-to-end suite configured yet. A passing TypeScript/Vite build does not verify actual browser interactions, microphone permissions, or screen-reader behavior.

## Local commands

```sh
pip install -r backend/requirements-dev.txt
pytest -q backend/tests
cd frontend
npm install
npm run build
cd ..
docker build -f backend/Dockerfile -t cardlens-api:local .
docker build -t cardlens-web:local ./frontend
```

For a database-backed test run, start PostgreSQL with pgvector, set `DATABASE_URL`, apply the migration, seed, then run pytest. For a production-like app smoke test, use the full Compose steps in [deployment.md](deployment.md). Live LLM/STT/TTS requests, issuer documents, external deployment, and real-device voice are not part of CI.
