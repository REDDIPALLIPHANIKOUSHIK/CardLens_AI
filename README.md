# CardLens AI

**A smarter way to explore credit cards based on how you actually spend.**

CardLens AI is a full-stack fintech project I built to make credit-card discovery easier to understand.

Instead of showing a long list of cards and asking users to figure everything out themselves, CardLens takes a user's spending habits and preferences, checks the available demo-card criteria, and produces a clear ranked set of matches.

The idea is simple:

> **Tell CardLens how you spend. It helps you understand which card profiles fit you best—and why.**

---

## ✨ What CardLens AI does

CardLens is designed as a personalized decision-support experience.

A signed-in user can:

- create and maintain a personal spending profile
- enter monthly spending by category
- include income, credit score, annual-fee preference, and reward preference
- generate personalized card recommendations
- understand why a card received its score
- see estimated rewards and estimated net annual value
- save cards for later
- compare two or three cards side by side
- run **What-If** scenarios without changing the saved profile
- ask the **CardLens AI Advisor** questions about their results
- use multilingual voice features where the browser/provider supports them
- keep profile and activity data tied to their account

The core recommendation system is deterministic, so the same inputs can be traced back to the same calculations.

---

## 🧠 How the recommendation works

One of the main design decisions in this project was to keep the actual ranking logic deterministic instead of asking an LLM to decide which card should win.

The flow is roughly:

```text
User profile
    ↓
Eligibility checks
    ↓
Spending + preference analysis
    ↓
Six-factor suitability scoring
    ↓
Reward/value estimation
    ↓
Ranked recommendations
    ↓
Explanations + trade-offs
```

The current score considers factors such as:

- spending match
- reward value
- reward preference
- eligibility
- annual-fee fit
- benefits

The API also returns the score breakdown and explanations so the recommendation is easier to inspect.

### Suitability vs. estimated value

These are intentionally different numbers.

**CardLens Score** tells you how well a card fits the profile.

**Estimated Net Annual Value** is an estimate of yearly rewards after the listed annual fee.

That means the highest-ranked card does not necessarily have the highest estimated monetary value. The UI makes this distinction visible instead of treating the two metrics as the same thing.

---

## 💡 What-If

The What-If feature is one of the parts I wanted to make more practical.

A user can change values such as:

- travel spending
- dining
- shopping
- fuel
- grocery
- utilities
- income
- credit score
- annual-fee preference
- reward preference

CardLens then runs the same recommendation logic against that temporary scenario.

For example:

```text
Current profile
Travel = ₹5,000/month
        ↓
What-If scenario
Travel = ₹30,000/month
        ↓
Recalculate recommendations
        ↓
Show rank/score changes
```

The scenario is separate from the saved profile, so experimenting should not silently overwrite the user's actual data.

---

## 🤖 CardLens AI Advisor

The Advisor sits on top of the recommendation system rather than replacing it.

It can explain things like:

- Why did this card rank first?
- Why did another card rank lower?
- What happens if I spend more on travel?
- How do these two cards compare?
- What does this score mean?

When configured, the project can also use retrieval and language-model providers for supported questions. The design keeps the numeric recommendation logic outside the LLM.

Voice functionality supports English, Hindi, Telugu, and Tamil through browser/provider capabilities, with text fallback when voice is unavailable.

---

## 🏗️ Architecture

```text
React + TypeScript + Vite
            │
            │ same-origin /api requests
            ▼
FastAPI + Pydantic
            │
            ├── deterministic eligibility + recommendation engine
            │
            ├── SQLAlchemy + Alembic
            │          │
            │          └── PostgreSQL / pgvector
            │
            └── optional AI / embeddings / speech providers
```

### Main responsibilities

**Frontend**
- product UI
- profile editing
- recommendations
- What-If
- comparison
- saved cards
- Advisor
- voice controls

**Backend**
- authentication and sessions
- profile persistence
- recommendation calculations
- simulations
- comparison
- favorites
- Advisor endpoints
- readiness/health checks

**Database**
- accounts
- profiles
- saved-card relationships
- activity/history
- settings
- conversation data

---

## 🛠️ Tech stack

| Layer | Technology |
| --- | --- |
| Frontend | React, TypeScript, Vite |
| UI / icons | CSS, Lucide React |
| Charts | Recharts |
| API | FastAPI, Pydantic |
| Database | PostgreSQL |
| ORM / migrations | SQLAlchemy, Alembic |
| Vector search | pgvector |
| AI | Optional LLM + embedding adapters |
| Voice | Browser speech + optional server providers |
| Deployment | Vercel, Docker, GitHub Actions |

---

## 🚀 Run it locally

### Requirements

- Python 3.11+
- Node.js 20+
- PostgreSQL
- PostgreSQL `vector` extension for the full persistence/RAG setup

### 1. Clone and configure

```powershell
git clone https://github.com/REDDIPALLIPHANIKOUSHIK/CardLens_AI.git
cd CardLens_AI

Copy-Item .env.example .env
```

Create a Python environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements-dev.txt
```

Set a valid local `DATABASE_URL` in your environment.

### 2. Apply migrations

```powershell
python -m alembic -c backend/alembic.ini upgrade head
python scripts/seed_database.py
```

The seed script loads the project's clearly labelled illustrative catalog.

### 3. Start the backend

```powershell
python -m uvicorn backend.app.main:app --reload
```

API:

`http://localhost:8000`

Swagger/OpenAPI:

`http://localhost:8000/docs`

### 4. Start the frontend

```powershell
cd frontend
npm install
npm run dev
```

Open:

`http://localhost:5173`

For the single-domain Vercel deployment, leave `VITE_API_BASE_URL` unset so the browser uses same-origin `/api/...` requests.

---

## 🔌 Useful API routes

| Route | Purpose |
| --- | --- |
| `POST /api/auth/signup` | Create an account |
| `POST /api/auth/login` | Start a session |
| `POST /api/auth/logout` | End the session |
| `GET /api/profile` | Load the signed-in profile |
| `PUT /api/profile` | Save the signed-in profile |
| `POST /api/recommend` | Generate recommendations |
| `POST /api/simulate` | Run a temporary What-If scenario |
| `POST /api/compare` | Compare two or three cards |
| `GET/POST/DELETE /api/favorites...` | Manage saved cards |
| `POST /api/chat` | Ask the CardLens Advisor |
| `GET /api/health` | API health check |
| `GET /api/ready` | Database/readiness check |

---

## 🔐 Security and privacy

CardLens uses server-side sessions and account-scoped data.

A few principles are important in the project:

- passwords are handled on the backend
- session cookies are HTTP-only
- user data is scoped to the authenticated account
- provider/API secrets stay on the backend
- secrets should never be placed in `VITE_*` frontend variables
- the application does not need card numbers, CVVs, bank passwords, or bank-login credentials

For a public deployment, users should only enter the profile information the application actually needs.

---

## 📊 About the card data

This project currently uses **synthetic illustrative card data**.

That is deliberate.

The demo is meant to show the product experience and engineering approach, not to pretend that the included reward rates and benefits are current issuer terms.

Because of that, the project does **not** claim:

- current card offers
- guaranteed approval
- current issuer eligibility
- production financial advice
- real-world recommendation accuracy

For a production version, the next step would be to replace the demo catalog with verified issuer-sourced data and model real-world constraints such as caps, exclusions, redemption rules, fees, and term changes.

---

## ✅ Testing and verification

Run backend tests:

```bash
python -m pytest -q backend/tests
```

Build the frontend:

```bash
npm --prefix frontend install
npm --prefix frontend run build
```

The repository also includes Docker/GitHub Actions workflows for production-like verification.

Keep in mind that a successful build only proves the code builds; deployed environment variables, database connectivity, third-party quotas, and browser-specific voice support still need to be checked in the target environment.

---

## 🎯 Why I built it this way

The interesting part of CardLens for me is not just the UI.

It is the separation between:

**calculation → explanation → interaction**

The recommendation engine owns the numeric decision.

The UI makes the result understandable.

The Advisor helps the user ask questions about the result.

And What-If lets the user experiment with their own assumptions.

That separation makes the project easier to test, reason about, and improve.

---

## 🔭 What I would build next

There are several natural next steps for turning the prototype into a production-grade product:

- verified, continuously maintained issuer catalog
- consent and data-retention controls
- broader accessibility and browser-level interaction tests
- distributed rate limiting and stronger observability
- email-based account recovery
- evaluation data for measuring recommendation quality
- deeper provider validation for LLM, RAG, transcription, and speech

These are intentionally future improvements rather than things the current demo pretends to already have.

---

## ⚠️ Important limitations

CardLens AI is an informational decision-support project, not an issuer decision or financial-advice service.

Please treat the included card catalog and calculations as **illustrative examples**.

Actual approval, eligibility, rewards, fees, benefits, and terms depend on the relevant issuer and current product conditions.

Do not enter bank passwords, payment-card numbers, CVVs, or other highly sensitive financial information.

---

## 📌 Project links

**GitHub:**  
https://github.com/REDDIPALLIPHANIKOUSHIK/CardLens_AI

**Live demo:**  
https://cardlensai.vercel.app/

---

## 👋 A note from the builder

I built CardLens AI as an end-to-end project to explore what a useful, transparent recommendation product could look like—not just a page that outputs a score.

The goal was to make the result something a person can actually question:

**Why this card?**

**Why not the other one?**

**What changes if my spending changes?**

That is the experience CardLens is trying to build.
