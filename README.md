# CardLens AI

**Personalized credit-card recommendations, explained in plain language.**

CardLens AI is a full-stack fintech application that helps a user explore credit-card options using the way they actually spend.

Instead of giving a generic list of cards, CardLens builds a spending profile, checks basic eligibility, calculates a transparent suitability score, estimates annual value, and explains why each card appears where it does.

The project combines a deterministic recommendation engine with account persistence, What-If simulation, card comparison, saved cards, an AI Advisor, retrieval-augmented generation, and multilingual voice support.

> **Important:** the current card catalog is synthetic and illustrative. It is included to demonstrate the product and engineering workflow, not to represent current issuer offers or financial advice.

---

## ✨ What the application does

CardLens is built around one simple journey:

**Profile → Analyze → Recommend → Explain → Explore**

A signed-in user can:

- create an account and maintain a personal profile
- enter income, credit score, fee preference, reward preference, and monthly spending
- describe spending in natural language and extract structured profile fields
- generate personalized card recommendations
- inspect the suitability score and its individual factors
- see estimated rewards and estimated net annual value
- understand why a card fits and why another card may rank lower
- save cards to their account
- compare two or three cards
- run temporary What-If scenarios
- view recommendation, comparison, simulation, and Advisor activity
- ask the CardLens Advisor questions about recommendations
- use English, Hindi, Telugu, or Tamil voice interactions where browser/provider support is available
- manage account settings, password, profile reset, conversation history, and account deletion

---

## 🧩 Main features and how they are implemented

### 1. Account authentication

CardLens uses a real account-based flow rather than a frontend-only login.

The backend provides:

- account creation
- login/logout
- session restoration
- protected API access
- password changes
- account deletion

Passwords are stored as scrypt-derived hashes. Login creates a server-side session whose token is stored through an HTTP-only cookie.

The authenticated user is resolved on the backend for protected operations, so profile, saved-card, comparison, history, and conversation data remain account-scoped.

---

### 2. Personalized spending profile

The profile is the main input to the recommendation engine.

A user can provide:

- monthly income
- credit score
- age
- maximum annual fee
- reward preference
- shopping spend
- dining spend
- fuel spend
- travel spend
- grocery spend
- utilities spend

The profile can be edited and saved through the backend, then loaded again after refresh or a new session.

There is also a natural-language profile input. For example:

> “I spend ₹15,000 online, ₹8,000 on dining, ₹5,000 on travel and I prefer cashback.”

The application can turn this description into structured fields through the profile-extraction endpoint. If an AI provider is not configured, the project has a local extraction fallback.

---

### 3. Deterministic recommendation engine

The core recommendation calculation is handled by Python on the server.

The flow is:

```text
User profile
    ↓
Pydantic validation
    ↓
Eligibility filtering
    ↓
Six-factor suitability scoring
    ↓
Reward estimation
    ↓
Net annual value calculation
    ↓
Ranked recommendations
    ↓
Reasons + trade-offs + score breakdown
```

The current suitability model combines six weighted factors:

| Factor | Purpose |
| --- | --- |
| Spending Match | Measures how closely the card rewards align with the user's spending |
| Reward Value | Estimates the reward contribution from the user's declared spend |
| Preference Match | Checks alignment with cashback, travel, fuel, or flexible rewards |
| Eligibility | Considers known income and credit-score requirements |
| Fee Fit | Measures how well the annual fee fits the user's preference |
| Benefits | Accounts for supported benefits such as lounge access |

The score is a **suitability score**, not an approval probability.

Missing income or credit-score information is kept unknown rather than invented.

---

## 💰 Suitability score vs. annual value

CardLens intentionally keeps these concepts separate.

**Suitability Score**

Measures how well the card fits the user's overall profile.

**Estimated Net Annual Value**

Estimates yearly rewards using the illustrative catalog and subtracts the listed annual fee.

Because they measure different things, the card with the highest suitability score does not necessarily have the highest estimated annual value.

The interface exposes this distinction and provides the score breakdown so the result is easier to understand.

---

## 🔄 What-If simulation

The What-If feature uses the same recommendation engine with temporary changes.

A user can experiment with:

- shopping
- dining
- fuel
- travel
- grocery
- utilities
- income
- credit score
- annual-fee preference
- reward preference

The backend recalculates recommendations for the scenario and returns the differences between the original and simulated profiles.

For example:

```text
Saved profile
Travel = ₹5,000/month

        ↓ What-If

Scenario
Travel = ₹30,000/month

        ↓

Recalculate the same scoring pipeline

        ↓

Show rank movement, score movement and explanation
```

The saved profile is not silently overwritten by a simulation.

---

## ❤️ Saved cards

Users can save cards to their account for later.

Saved-card relationships are stored in PostgreSQL with a unique user/card constraint so the same card cannot be saved repeatedly for the same account.

The UI keeps saved state consistent across:

- recommendations
- card explorer
- saved cards
- comparison

Save and remove actions are performed through authenticated API calls.

---

## ⚖️ Card comparison

CardLens supports side-by-side comparison of two or three cards.

The comparison endpoint calculates the selected cards using the same profile context and returns fields such as:

- suitability score
- annual fee
- estimated rewards
- estimated net annual value
- reward type
- recommendation context

The frontend presents the cards as a focused comparison view instead of forcing the user to mentally compare separate recommendation cards.

---

## 🤖 AI Advisor

The CardLens Advisor is an explanation layer around the application's deterministic calculations.

It can answer questions such as:

- Why did this card rank first?
- Why did another card rank lower?
- What happens if I spend more on travel?
- How do my top two cards compare?
- What does my CardLens score mean?

The application first uses deterministic tools for supported recommendation, comparison, and What-If questions.

An optional LLM provider can then be used for richer natural-language responses.

This keeps the actual numeric ranking outside the language model.

---

## 📚 RAG and grounded card knowledge

CardLens includes a retrieval-augmented generation pipeline for card knowledge.

The project can:

1. accept source documents in JSONL format
2. validate source metadata
3. split documents into overlapping chunks
4. generate embeddings
5. store embeddings in PostgreSQL using pgvector
6. search the vector index using cosine similarity
7. pass retrieved evidence to the Advisor
8. return source metadata with grounded answers

The retrieval layer is implemented in `backend/app/rag.py`, while document ingestion is handled by `scripts/ingest_documents.py`.

The system is deliberately conservative:

**No evidence → no invented answer.**

When indexed verified material is unavailable or retrieval is insufficient, the Advisor returns an insufficient-evidence response instead of pretending that unsupported card facts are verified.

Synthetic demo data is never presented as verified issuer evidence.

---

## 🎙️ Multilingual voice

CardLens supports voice interaction for:

- English — `en-IN`
- Hindi — `hi-IN`
- Telugu — `te-IN`
- Tamil — `ta-IN`

The voice layer has separate speech-to-text and text-to-speech paths.

### Speech input

The browser microphone is captured with the Web Media APIs and a `MediaRecorder`.

Where available, browser speech recognition is also used as a fallback.

### Speech output

The backend can use an optional text-to-speech provider.

If that is unavailable, the application falls back to browser `SpeechSynthesis`.

The UI also provides a **Stop** control for active speech so playback can be cancelled instead of continuing until the response finishes.

Voice language and playback speed can be stored in the user's settings.

---

## 🏗️ System architecture

The application follows a layered architecture so calculation logic, persistence, AI features, and presentation stay separate.

```text
┌─────────────────────────────────────────────────────────┐
│                    React Web App                        │
│                                                         │
│ Profile │ Recommendations │ What-If │ Compare │ Advisor │
│ Explorer │ Saved Cards │ Settings │ Voice Controls      │
└───────────────────────┬─────────────────────────────────┘
                        │
                        │ REST API over HTTP / JSON
                        ▼
┌─────────────────────────────────────────────────────────┐
│                FastAPI Application                      │
│                                                         │
│ Authentication & Sessions                               │
│ Profile APIs                                            │
│ Recommendation APIs                                     │
│ Simulation / Compare / Favorites / History              │
│ Advisor / Voice / Health / Readiness                    │
└───────────────┬───────────────────────┬────────────────┘
                │                       │
                │                       │
                ▼                       ▼
┌──────────────────────────┐   ┌─────────────────────────┐
│ Recommendation Layer     │   │ AI / RAG Layer          │
│                          │   │                         │
│ Eligibility             │   │ Optional LLM            │
│ Six-factor scoring      │   │ Embeddings              │
│ Reward estimation       │   │ pgvector retrieval      │
│ Explanations            │   │ Grounded responses      │
│ What-If simulation      │   │ STT / TTS               │
└──────────────┬───────────┘   └────────────┬────────────┘
               │                            │
               └──────────────┬─────────────┘
                              ▼
                 ┌────────────────────────┐
                 │ PostgreSQL + pgvector  │
                 │                        │
                 │ Users                  │
                 │ Sessions               │
                 │ Profiles               │
                 │ Favorites              │
                 │ Recommendations        │
                 │ Comparisons             │
                 │ Simulations             │
                 │ Settings                │
                 │ Conversations           │
                 │ Card documents/vectors  │
                 └────────────────────────┘
```

---

## 🛠️ Complete technology stack

### Frontend

- **React** — component-based web application
- **TypeScript** — typed frontend development
- **Vite** — development server and production bundling
- **CSS** — custom responsive visual system and theming
- **Lucide React** — interface icons
- **Recharts** — data visualization

### Backend

- **Python**
- **FastAPI** — REST API framework
- **Pydantic** — request validation and typed API models
- **Uvicorn** — ASGI server
- **httpx** — asynchronous HTTP communication with external providers
- **python-multipart** — multipart/audio upload handling

### API and application architecture

- **REST API**
- **HTTP/JSON**
- **FastAPI dependency injection**
- **HTTP-only session cookies**
- **CORS**
- **request IDs**
- **API rate limiting**
- **health and readiness endpoints**

### Database and persistence

- **PostgreSQL**
- **SQLAlchemy** — ORM/database access
- **Alembic** — database migrations
- **psycopg** — PostgreSQL driver
- **pgvector** — vector storage and similarity search

### AI / LLM

- **OpenAI-compatible LLM adapter**
- configurable chat model
- deterministic tool-assisted responses
- optional language-model explanations

The AI provider is deliberately replaceable through environment configuration rather than tightly coupling the application to one provider.

### Embeddings and RAG

- **Embedding API**
- **vector embeddings**
- **pgvector cosine-similarity retrieval**
- chunked document ingestion
- source metadata and verification dates
- grounded response generation
- insufficient-evidence fallback

### Voice

- browser **MediaRecorder**
- browser speech recognition where available
- browser **SpeechSynthesis** fallback
- optional server-side speech-to-text
- optional server-side text-to-speech

### Deployment and infrastructure

- **Vercel Services** — frontend + FastAPI deployment
- **Docker / Docker Compose** — production-like local stack
- **GitHub Actions** — automated verification and production database migration workflow
- **PostgreSQL with pgvector** — persistent production datastore

---

## 🔐 Security and reliability

The project includes several safeguards around user and infrastructure data.

- Passwords are stored as scrypt-derived hashes.
- Sessions use hashed tokens and HTTP-only cookies.
- Protected resources resolve the authenticated user on the backend.
- Account deletion removes related user data through the existing relational model.
- Production CORS requires explicit HTTPS origins.
- Provider secrets remain server-side.
- Frontend `VITE_*` variables are not used for secret credentials.
- API requests use bounded provider timeouts.
- Selected POST endpoints have rate limiting.
- Health and readiness endpoints make deployment checks easier.
- API failures return user-safe messages instead of raw stack traces.

---

## 📂 Project structure

```text
CardLens_AI/
│
├── backend/
│   ├── app/
│   │   ├── ai/
│   │   │   └── providers.py
│   │   ├── auth.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── models.py
│   │   └── rag.py
│   │
│   ├── migrations/
│   ├── requirements.txt
│   └── requirements-dev.txt
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── AuthGate.tsx
│   │   ├── main.tsx
│   │   └── style.css
│   └── package.json
│
├── scripts/
│   ├── seed_database.py
│   └── ingest_documents.py
│
├── docs/
├── .env.example
├── vercel.json
└── README.md
```

---

## 🚀 Run locally

### Requirements

- Python 3.11+
- Node.js 20+
- PostgreSQL
- pgvector extension for the full database/RAG setup

### Backend setup

```powershell
git clone https://github.com/REDDIPALLIPHANIKOUSHIK/CardLens_AI.git
cd CardLens_AI

Copy-Item .env.example .env

python -m venv .venv
.venv\Scripts\Activate.ps1

python -m pip install -r backend/requirements-dev.txt
```

Configure a valid local `DATABASE_URL`.

Apply the existing migrations:

```powershell
python -m alembic -c backend/alembic.ini upgrade head
python scripts/seed_database.py
```

Start the API:

```powershell
python -m uvicorn backend.app.main:app --reload
```

API:

`http://localhost:8000`

API documentation:

`http://localhost:8000/docs`

### Frontend setup

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:

`http://localhost:5173`

For the single-domain Vercel configuration, leave `VITE_API_BASE_URL` unset so the browser uses same-origin `/api/...` requests.

---

## 🔌 API surface

The backend exposes REST endpoints around the main product features.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/auth/signup` | Create an account |
| `POST /api/auth/login` | Start a session |
| `POST /api/auth/logout` | End a session |
| `GET /api/auth/me` | Get the current signed-in user |
| `GET /api/profile` | Load the saved profile |
| `PUT /api/profile` | Save the profile |
| `DELETE /api/profile` | Reset the profile |
| `POST /api/profile/extract` | Extract profile fields from natural language |
| `POST /api/recommend` | Calculate recommendations |
| `GET /api/recommendations/latest` | Load the latest saved recommendation result |
| `POST /api/simulate` | Run a temporary What-If calculation |
| `POST /api/compare` | Compare selected cards |
| `GET /api/cards` | Read the available card catalog |
| `GET/POST/DELETE /api/favorites...` | Manage saved cards |
| `POST /api/chat` | Ask the CardLens Advisor |
| `POST /api/rag/search` | Search indexed card knowledge |
| `POST /api/voice/transcribe` | Speech-to-text |
| `POST /api/voice/speak` | Text-to-speech |
| `GET /api/history` | Read user activity |
| `GET /api/conversations` | Read Advisor conversations |
| `GET /api/settings` | Read user settings |
| `PUT /api/settings` | Save user settings |
| `GET /api/health` | Liveness check |
| `GET /api/ready` | Database/readiness check |

The complete interactive API schema is available at `/docs`.

---

## 📚 Adding RAG documents

The document-ingestion script expects JSONL records containing:

- `card_id`
- `card_name`
- `source`
- `document_version`
- `last_verified`
- `text`

Example:

```json
{"card_id":"demo-cashback","card_name":"Example Card","source":"https://example.com/terms","document_version":"v1","last_verified":"2026-01-01","text":"Verified source text...","is_demo":false}
```

Run ingestion with:

```bash
python scripts/ingest_documents.py path/to/documents.jsonl
```

The script chunks the document, generates embeddings, and stores the vectors in pgvector.

Only source-linked material should be treated as verified knowledge.

---

## ⚙️ Configuration

The main environment variables are documented in `.env.example`.

Core:

- `APP_ENV`
- `DATABASE_URL`
- `FRONTEND_ORIGINS`
- `DATABASE_POOL_SIZE`
- `DATABASE_MAX_OVERFLOW`

Optional LLM:

- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL`
- `OPENAI_BASE_URL`

Optional embeddings/RAG:

- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`
- `EMBEDDING_BASE_URL`

Optional voice:

- `VOICE_API_KEY`
- `VOICE_STT_MODEL`
- `VOICE_TTS_MODEL`
- `VOICE_BASE_URL`
- `VOICE_NAME`

AI and voice credentials are optional for the core deterministic recommendation flow.

---

## 🧪 Verification

Backend tests:

```bash
python -m pytest -q backend/tests
```

Frontend production build:

```bash
npm --prefix frontend install
npm --prefix frontend run build
```

The repository also contains Docker and GitHub Actions workflows used for production-like verification.

A successful build confirms that the code compiles and bundles correctly; deployed database connectivity, environment configuration, browser-specific voice support, and external provider availability still depend on the target environment.

---

## ☁️ Deployment

CardLens is configured for a Vercel Services deployment:

```text
Vercel
│
├── frontend/ → Vite
└── backend/  → FastAPI
                 │
                 └── PostgreSQL / pgvector
```

The root `vercel.json` routes:

```text
/api/*  → FastAPI service
/*      → React/Vite frontend
```

Production database schema changes are managed through Alembic, and the repository includes a manually triggered GitHub Actions migration workflow.

See [Vercel deployment](deployment-vercel.md) for the complete production setup.

---

## 📊 Current data model

The relational model covers:

- users
- authentication sessions
- user profiles
- user settings
- credit cards
- card benefits
- card documents
- recommendations
- recommendation explanations
- saved cards
- comparison history
- What-If simulation history
- Advisor conversations
- conversation messages

This gives the application a persistent foundation rather than keeping the complete experience inside frontend state.

---

## ⚠️ Data and product limitations

The current catalog intentionally uses synthetic card records and reward rates.

That means the application should not be treated as a source of current issuer terms.

Real-world card products can include rules that this demo does not fully model, including:

- reward caps
- exclusions
- joining fees
- redemption restrictions
- changing benefits
- issuer-specific eligibility conditions

A production financial product would need verified and continuously maintained issuer data before presenting those details as current.

CardLens also does not provide an issuer approval decision or a guarantee of approval.

---

## 🔗 Project links

**GitHub**  
https://github.com/REDDIPALLIPHANIKOUSHIK/CardLens_AI

**Live application**  
https://cardlensai.vercel.app/

---

## 🌱 Project direction

CardLens is built around a transparent idea:

**the system should be able to explain how it reached a recommendation.**

The application therefore separates:

```text
Calculation
    ↓
Recommendation
    ↓
Explanation
    ↓
User interaction
```

The deterministic engine handles the numeric decision. Optional AI and RAG features sit around that core to make the results easier to explore, explain, and query.

