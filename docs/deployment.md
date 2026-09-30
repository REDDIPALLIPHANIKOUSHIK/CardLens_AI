# Local deployment

## Full Docker demo (PostgreSQL + pgvector)

Requires Docker Compose. The Compose credentials are development-only; replace them and use a secret manager before any shared deployment.

```sh
docker compose up -d db
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose run --rm api python scripts/seed_database.py
docker compose up --build
```

Open the Vite dashboard at http://localhost:5173 and the API docs at http://localhost:8000/docs. The seeded card offers are synthetic demo data.

## API without PostgreSQL

```sh
python -m venv .venv
# Activate the environment for your shell.
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Without DATABASE_URL, the deterministic in-memory demo stays available. To use persistence and RAG, set DATABASE_URL to PostgreSQL with pgvector enabled, then run the Alembic migration and the demo seed script.

## Optional AI and voice

Set LLM_API_KEY and LLM_MODEL to enable the optional OpenAI-compatible advisor adapter. Set EMBEDDING_API_KEY and EMBEDDING_MODEL for RAG indexing/search. VOICE_API_KEY, VOICE_STT_MODEL, and VOICE_TTS_MODEL enable transcription and speech synthesis. No key is needed for ranking, comparison, reward estimates, deterministic chat fallbacks, or What-If calculations.

RAG needs explicitly sourced JSONL documents; ingestion requires source, version, and last-verified date. Never use the demo source URLs as verified issuer terms. Check each issuer's current primary terms before importing a document as verified.
