# Deployment and local run

CardLens is a small demo stack: PostgreSQL with pgvector, one FastAPI API, and a static React build served by Nginx. The included card catalog and terms are synthetic. This Compose file is suitable for a local or interview demo; use managed PostgreSQL, TLS, private networking, a secrets manager, backups, and a deployment-specific CORS/API URL before sharing it publicly.

## Prerequisites

- Docker Engine/Desktop with Docker Compose v2
- For optional AI: provider API keys. Ranking, comparison, simulation, and deterministic chat fallback work without them.
- For public deployment: a PostgreSQL/pgvector database, a public API URL, a public frontend origin, and a strong database password.

## Configure

Copy the example environment file and edit it:

```sh
cp .env.example .env
```

On PowerShell, use `Copy-Item .env.example .env`. `POSTGRES_PASSWORD=cardlens-dev-only` is only a local demo default; replace it before exposing the stack. Configure `FRONTEND_ORIGINS` with the exact frontend origin(s), and set `VITE_API_BASE_URL` to the API base URL without a trailing slash. For a production API process, set `APP_ENV=production`, provide `DATABASE_URL`, and use explicit HTTPS frontend origins; the API refuses production startup with missing database/CORS settings or wildcard/non-HTTPS CORS origins. The frontend value is baked into its static build, so rebuild after changing it. Optional `LLM_API_KEY`, `EMBEDDING_API_KEY`, and `VOICE_API_KEY` enable the advisor, RAG embeddings, and voice services; blank keys disable those features gracefully.

## Build, migrate, seed, start

Run from the repository root:

```sh
docker compose up -d db
docker compose build
docker compose run --rm api alembic -c backend/alembic.ini upgrade head
docker compose run --rm api python scripts/seed_database.py
docker compose up -d
```

Open the dashboard at http://localhost:5173 and API documentation at http://localhost:8000/docs. The API container includes the migration and seed files. The seeded offers are synthetic demo data.

To view service status/logs, run `docker compose ps` and `docker compose logs -f api frontend`. Stop services with `docker compose down`; this keeps the local database volume. Add `-v` only when you intentionally want to erase the local database.

## Health checks

- `GET /health` (also available at `/api/health`) is a liveness check and does not call the LLM or require PostgreSQL.
- `GET /ready` (also available at `/api/ready`) checks the configured database connection. With no `DATABASE_URL`, it reports the deterministic demo fallback as ready.
- Docker health checks use these endpoints. Compose waits for PostgreSQL before starting the API.

## Local development without Docker

API:

```sh
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
```

Frontend in a second terminal:

```sh
cd frontend
npm install
npm run dev
```

Set `VITE_API_BASE_URL` when the API is not at `http://localhost:8000`. For PostgreSQL, configure `DATABASE_URL`, then run the same Alembic migration and `python scripts/seed_database.py`.

## RAG documents

RAG is inactive until verified source documents are ingested. Each JSONL line must include `card_id`, `card_name`, an HTTPS `source`, `document_version`, ISO `last_verified`, and `text`. After setting `DATABASE_URL` and an embedding key/model, run:

```sh
python scripts/ingest_documents.py path/to/documents.jsonl
```

Only issuer primary-source material should be marked verified. Without a matching indexed document, the Advisor says it lacks verified information; the synthetic sample URL is not evidence.

## Troubleshooting

- Database unavailable: check `docker compose logs db`, `DATABASE_URL`, and the database health status; rerun migration after the database is healthy.
- Seed command missing: rebuild the API image with `docker compose build api`; the image must include `scripts/`.
- Browser cannot reach the API: check `VITE_API_BASE_URL` in the frontend build and include the browser's exact origin in `FRONTEND_ORIGINS`; then rebuild/restart.
- Advisor/voice unavailable: core deterministic recommendation features remain usable without AI credentials. Check provider credentials and network access; do not put provider keys in frontend variables.
- Card terms not returned: ingest verified issuer documents and configure embedding access. RAG intentionally fails closed when evidence is missing.
