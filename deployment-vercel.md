# Deploy CardLens AI on Vercel

This repository is configured as a Vercel **Services** project: the Vite frontend is built from `frontend/`, and the FastAPI service is built from `backend/`. Both are served on one deployment domain. The root `vercel.json` routes `/api/*` to FastAPI and all other paths to the frontend. The browser API base is same-origin in production.

> **Vercel feature status:** Services is currently in beta. In Vercel project settings, select **Services** as the project framework before deploying. If Services is unavailable for your account, this configuration cannot be deployed as one project until access is enabled.

## Prerequisites

- GitHub access to this repository and a Vercel account.
- Node.js 20+ and Python 3.11+ for local builds and database setup.
- A managed PostgreSQL database whose server supports the `vector` extension. Use the provider's pooled connection URL for the app when available.
- Vercel CLI 48.1.8 or newer for the FastAPI runtime.
- Optional server-side AI credentials for LLM, embeddings/RAG, and voice. The deterministic demo works without them.

The included card catalog and benefit values are **synthetic demo data**, not current issuer terms.

## 1. Create PostgreSQL and enable pgvector

Create a production database with your PostgreSQL provider. Confirm that the provider supports pgvector, then run:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

Use the provider's pooled URL for the deployed app if it offers one. Keep the direct/admin URL for schema migration if the provider recommends it. Do not use the local example URL in production.

## 2. Apply schema migrations and seed demo data

From the repository root, set the database URL in your shell and run the existing migration and idempotent seed script. Use a secure shell secret prompt or your provider's password manager; do not paste credentials into source files or commit them.

PowerShell:

```powershell
$env:DATABASE_URL = Read-Host "Production PostgreSQL URL"
python -m pip install -r backend/requirements.txt
python -m alembic -c backend/alembic.ini upgrade head
python scripts/seed_database.py
Remove-Item Env:DATABASE_URL
```

macOS/Linux:

```bash
read -s DATABASE_URL
export DATABASE_URL
python -m pip install -r backend/requirements.txt
python -m alembic -c backend/alembic.ini upgrade head
python scripts/seed_database.py
unset DATABASE_URL
```

Migrations update the current schema; they do not reset or drop the production database. Review backups and your provider's migration guidance before applying schema changes. The seed script is idempotent and inserts explicitly labeled synthetic demo cards.

## 3. Import the GitHub repository into Vercel

1. In Vercel, choose **Add New → Project**, then import `REDDIPALLIPHANIKOUSHIK/CardLens_AI`.
2. Set the project framework to **Services** in Build and Deployment settings.
3. Keep the project root at the repository root (`.`). Do not set it to `frontend/`; the root `vercel.json` defines the separate frontend and API service roots.
4. Use the repository's `vercel.json` defaults. Do not set one shared build command or output directory for the whole project; the two services are built separately.
5. Add the environment variables below to the intended Vercel environments.
6. Deploy a Preview first, verify the health/readiness endpoints and app flows, then promote/deploy to Production.

The service rewrites preserve the incoming URL path, so FastAPI receives `/api/health`, `/api/recommend`, and the other existing `/api/*` routes unchanged.

## 4. Configure environment variables

Set these in Vercel **Project → Settings → Environment Variables**. Keep database and provider credentials server-side; never put them in `VITE_*` values.

| Variable | Required | Value |
| --- | --- | --- |
| `APP_ENV` | Yes | `production` |
| `DATABASE_URL` | Yes | Secret PostgreSQL connection URL (prefer the provider's pooled app URL) |
| `FRONTEND_ORIGINS` | Yes | Exact HTTPS Vercel deployment origin, e.g. `https://your-project.vercel.app`; add the production custom domain if used |
| `DATABASE_POOL_SIZE` | Recommended | `1` |
| `DATABASE_MAX_OVERFLOW` | Recommended | `0` |
| `VITE_API_BASE_URL` | No | Leave unset for same-origin `/api/...` calls |
| `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_MODEL` | Optional | Existing backend AI provider configuration |
| `EMBEDDING_API_KEY`, `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL` | Optional | Existing embedding/RAG configuration |
| `VOICE_API_KEY`, `VOICE_STT_MODEL`, `VOICE_TTS_MODEL`, `VOICE_BASE_URL`, `VOICE_NAME` | Optional | Existing voice configuration |

Production startup validates that `DATABASE_URL` is present and `FRONTEND_ORIGINS` contains explicit HTTPS origins without wildcards. Set the final Vercel domain(s) before promoting to production. Same-origin requests do not need cross-origin access, but the current production guard still requires the explicit origin variable.

For optional keys, see `.env.example` for names and defaults. Vercel preview deployments use different URLs; include the specific preview origin if cross-origin access is needed for a preview. Do not use a wildcard in production.

## 5. Deploy with Vercel CLI

Install/use a current CLI (FastAPI requires 48.1.8 or newer):

```bash
npm install --global vercel
vercel --version
vercel login
vercel link
```

Link the project to the GitHub-imported Vercel project. Add secrets interactively; Vercel prompts for the value so it need not be placed in shell history:

```bash
vercel env add DATABASE_URL production
vercel env add APP_ENV production
vercel env add FRONTEND_ORIGINS production
vercel env add DATABASE_POOL_SIZE production
vercel env add DATABASE_MAX_OVERFLOW production
```

Repeat `vercel env add VARIABLE preview` for preview-only values when needed. Add optional provider keys the same way. Leave `VITE_API_BASE_URL` unset for the shared-domain setup.

Build locally with the Vercel project settings and deployment environment:

```bash
vercel pull
vercel build
```

Deploy a preview, then production:

```bash
vercel deploy --prebuilt
vercel deploy --prebuilt --prod
```

You can also deploy through the connected GitHub project: pushes create deployments according to the configured Vercel Git settings. Do not commit `.vercel/` project metadata or any secrets.

## 6. Verify deployment

After deployment, replace `<deployment-host>` below with the deployment domain:

```text
https://<deployment-host>/api/health
https://<deployment-host>/api/ready
```

`/api/health` is the simple liveness check and does not require an LLM. `/api/ready` checks database connectivity and should report PostgreSQL when production `DATABASE_URL` is configured. Then use the app to verify recommendations, compare, what-if simulation, chat, and optional RAG/voice behavior. A green Vercel build alone does not verify credentials, live database connectivity, provider quotas, or all interactive flows.

For a local full-stack Vercel emulation, use `vercel dev` from the repository root after linking and pulling environment variables.

## Troubleshooting

- **Project does not build as multiple services:** confirm Services is selected as the Vercel project framework and that root `vercel.json` is present. Services is in beta and access/availability may vary.
- **API returns 404:** inspect the `/api/(.*)` rewrite and ensure the service receives the original `/api/... ` path. Keep the root project linked; do not configure the frontend folder as the project root.
- **FastAPI import/dependency error:** ensure the API service root is `backend/`, its entrypoint is `app.main:app`, and `backend/requirements.txt` includes the runtime dependencies. Check Vercel function logs.
- **Production startup error:** set `APP_ENV=production`, `DATABASE_URL`, and the exact HTTPS `FRONTEND_ORIGINS`.
- **Readiness reports database unavailable:** verify the connection URL, provider network/access rules, TLS requirements, pgvector availability, and applied migrations. Keep pool defaults small for serverless concurrency.
- **Function bundle too large:** inspect the deployment bundle; the API service excludes tests, fixtures, and migration files from its function bundle. Vercel Functions have a bundle-size limit.
- **RAG has no verified answer:** configure embeddings, enable pgvector, and ingest verified source documents. The built-in card catalog remains synthetic and is not evidence of real issuer terms.
- **Localhost API requests in production:** leave `VITE_API_BASE_URL` unset. The frontend defaults to same-origin in production and localhost only in Vite development mode.
