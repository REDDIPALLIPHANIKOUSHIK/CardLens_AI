from __future__ import annotations

from typing import Literal
from collections import defaultdict, deque
from threading import Lock
from datetime import datetime, timezone
import json, logging, os, re, time, uuid
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi import File, Form, UploadFile
from sqlalchemy.exc import IntegrityError
from .database import check_database, database_url, get_session_factory
from .auth import current_user, optional_current_user, router as auth_router
from .models import ComparisonHistory, ConversationMessage, ConversationSession, CreditCard, Recommendation, SimulationHistory, User, UserFavorite, UserProfile, UserSettings
from .ai.providers import configured_provider, configured_embedding_provider, configured_voice_provider
from .rag import INSUFFICIENT_EVIDENCE, search_card_knowledge
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger('cardlens.api')
app = FastAPI(title="CardLens AI", version="0.1.0", description="Deterministic demo credit-card suitability recommendations")
app.include_router(auth_router)
origins = [value.strip() for value in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if value.strip()]

def validate_runtime_configuration() -> None:
    if os.getenv("APP_ENV", "development").strip().lower() != "production":
        return
    missing = []
    if not database_url():
        missing.append("DATABASE_URL")
    configured_origins = os.getenv("FRONTEND_ORIGINS", "").strip()
    if not configured_origins:
        missing.append("FRONTEND_ORIGINS")
    if missing:
        raise RuntimeError("Production startup requires: " + ", ".join(missing))
    production_origins = [origin.strip() for origin in configured_origins.split(",") if origin.strip()]
    if "*" in production_origins or any(not origin.startswith("https://") for origin in production_origins):
        raise RuntimeError("Production FRONTEND_ORIGINS must contain explicit HTTPS origins and cannot use '*'.")
    if not production_origins:
        raise RuntimeError("Production FRONTEND_ORIGINS must contain at least one HTTPS origin.")

validate_runtime_configuration()
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["Content-Type", "X-Request-ID"])

_RATE_WINDOW = 60
_RATE_LIMIT = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "60"))
_requests: dict[str, deque[float]] = defaultdict(deque)
_rate_lock = Lock()

@app.middleware("http")
async def request_controls(request: Request, call_next):
    started = time.perf_counter()
    supplied = request.headers.get("x-request-id", "")
    request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else str(uuid.uuid4())
    request.state.request_id = request_id
    limited = request.method == "POST" and request.url.path in {"/api/recommend", "/api/simulate", "/api/compare", "/api/chat", "/api/rag/search", "/api/voice/transcribe", "/api/voice/speak", "/api/profile/extract", "/api/auth/signup", "/api/auth/login"}
    if limited:
        client = request.client.host if request.client else "unknown"
        key = f"{client}:{request.url.path}"
        now = time.monotonic()
        with _rate_lock:
            bucket = _requests[key]
            while bucket and bucket[0] <= now - _RATE_WINDOW:
                bucket.popleft()
            if len(bucket) >= _RATE_LIMIT:
                response = JSONResponse(status_code=429, content={"success": False, "error_code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly."}, headers={"Retry-After": "60"})
                response.headers["X-Request-ID"] = request_id
                return response
            bucket.append(now)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(json.dumps({"request_id": request_id, "endpoint": request.url.path, "status": 500, "event": "unhandled_error"}))
        response = JSONResponse(status_code=500, content={"success": False, "error_code": "INTERNAL_ERROR", "message": "CardLens AI could not complete that request."})
    response.headers["X-Request-ID"] = request_id
    logger.info(json.dumps({"request_id": request_id, "endpoint": request.url.path, "latency_ms": round((time.perf_counter()-started)*1000, 2), "status": response.status_code}))
    return response

# Synthetic demo offers only. These rates are not real issuer terms.
CARDS = [
    {"id":"demo-cashback","name":"Everyday Cashback (Demo)","issuer":"CardLens Demo Bank","network":"Visa","annual_fee":499,"minimum_income":25000,"minimum_credit_score":650,"reward_type":"cashback","rates":{"shopping":0.04,"dining":0.02,"fuel":0.01,"travel":0.01,"grocery":0.02,"utilities":0.01},"lounge_access":False,"forex_fee":0.035,"source_url":"https://example.com/demo-terms"},
    {"id":"demo-travel","name":"Explorer Travel (Demo)","issuer":"CardLens Demo Bank","network":"Visa","annual_fee":1499,"minimum_income":50000,"minimum_credit_score":700,"reward_type":"travel","rates":{"shopping":0.01,"dining":0.02,"fuel":0.005,"travel":0.05,"grocery":0.01,"utilities":0.01},"lounge_access":True,"forex_fee":0.02,"source_url":"https://example.com/demo-terms"},
    {"id":"demo-fuel","name":"Fuel & Dine (Demo)","issuer":"CardLens Demo Bank","network":"RuPay","annual_fee":999,"minimum_income":30000,"minimum_credit_score":675,"reward_type":"fuel","rates":{"shopping":0.01,"dining":0.035,"fuel":0.04,"travel":0.01,"grocery":0.015,"utilities":0.01},"lounge_access":False,"forex_fee":0.035,"source_url":"https://example.com/demo-terms"},
    {"id":"demo-no-fee","name":"Simple No-Fee (Demo)","issuer":"CardLens Demo Bank","network":"Mastercard","annual_fee":0,"minimum_income":15000,"minimum_credit_score":600,"reward_type":"cashback","rates":{"shopping":0.015,"dining":0.015,"fuel":0.01,"travel":0.01,"grocery":0.015,"utilities":0.01},"lounge_access":False,"forex_fee":0.035,"source_url":"https://example.com/demo-terms"},
]
WEIGHTS = {"spending_match":0.30,"reward_value":0.20,"preference_match":0.15,"eligibility":0.15,"fee_value":0.10,"benefits":0.10}
CATEGORIES = tuple(CARDS[0]["rates"])

class Profile(BaseModel):
    monthly_income: float | None = Field(None, ge=0, le=100_000_000)
    credit_score: int | None = Field(None, ge=300, le=900)
    age: int | None = Field(None, ge=18, le=100)
    annual_fee_max: float | None = Field(None, ge=0, le=1_000_000)
    reward_preference: Literal["cashback","travel","fuel","rewards"] | None = None
    spending: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def valid_spending(self):
        unknown = set(self.spending) - set(CATEGORIES)
        if unknown:
            raise ValueError(f"Unknown spending categories: {', '.join(sorted(unknown))}")
        if any(v < 0 or v > 10_000_000 for v in self.spending.values()):
            raise ValueError("Spending must be between 0 and 10,000,000 per month")
        return self

def _rank(profile: Profile):
    rows, excluded = [], []
    total = sum(profile.spending.values())
    for c in CARDS:
        reasons = []
        if profile.monthly_income is not None and profile.monthly_income < c["minimum_income"]:
            reasons.append("income below stated demo minimum")
        if profile.credit_score is not None and profile.credit_score < c["minimum_credit_score"]:
            reasons.append("score below stated demo minimum")
        if reasons:
            excluded.append({"card_id":c["id"],"reasons":reasons})
            continue
        gross = sum(profile.spending.get(k, 0) * 12 * rate for k, rate in c["rates"].items())
        net = gross - c["annual_fee"]
        match = (sum(profile.spending.get(k, 0) * c["rates"][k] for k in CATEGORIES) / total * 100 / max(c["rates"].values())) if total else 50
        match = min(100, max(0, match))
        reward_score = min(100, gross / max(1, total * 12 * 0.05) * 100) if total else 50
        preference = 70 if profile.reward_preference is None else (100 if c["reward_type"] == profile.reward_preference else 55)
        fee_fit = 50 if profile.annual_fee_max is None else (100 if c["annual_fee"] <= profile.annual_fee_max else max(0, 100 - (c["annual_fee"]-profile.annual_fee_max)/20))
        eligibility = 85 if profile.monthly_income is not None and profile.credit_score is not None else 60
        benefits = 60 if c["lounge_access"] else 40
        score = round(WEIGHTS["spending_match"]*match + WEIGHTS["reward_value"]*reward_score + WEIGHTS["preference_match"]*preference + WEIGHTS["eligibility"]*eligibility + WEIGHTS["fee_value"]*fee_fit + WEIGHTS["benefits"]*benefits)
        score_breakdown = {
            "spending_match": round(match),
            "reward_value": round(reward_score),
            "preference_match": preference,
            "eligibility": eligibility,
            "fee_value": round(fee_fit),
            "benefits": benefits,
        }
        category_rewards = {
            k: round(profile.spending.get(k, 0) * 12 * rate)
            for k, rate in c["rates"].items() if profile.spending.get(k, 0) > 0
        }
        top_spend_categories = sorted(
            (k for k, amount in profile.spending.items() if amount > 0),
            key=lambda k: (-profile.spending[k], k),
        )[:2]
        why = [
            f"{k.title()} earns an illustrative {c['rates'][k] * 100:g}% demo reward rate"
            for k in top_spend_categories
        ]
        why.append("Fee preference was not provided; fee fit is scored neutrally" if profile.annual_fee_max is None else ("Annual fee is within your stated preference" if c["annual_fee"] <= profile.annual_fee_max else "Fee preference lowers this card's fit"))
        why.append(f"Estimated net annual value ₹{round(net):,} from your entered spending")
        eligibility_known = int(profile.monthly_income is not None) + int(profile.credit_score is not None)
        completeness = round(100 * (0.65 * min(1, len(profile.spending) / len(CATEGORIES)) + 0.35 * eligibility_known / 2))
        rows.append({
            **c,
            "score": score,
            "score_breakdown": score_breakdown,
            "profile_completeness": completeness,
            "confidence": 0,
            "confidence_reason": "",
            "category_rewards": category_rewards,
            "estimated_annual_rewards": round(gross),
            "estimated_net_annual_value": round(net),
            "why": why,
            "why_not": [],
            "limitations": ["Illustrative demo reward rates; issuer caps, exclusions, and redemption terms are not modeled", "Eligibility is indicative and does not guarantee approval"],
        })
    rows.sort(key=lambda r:(-r["score"],-r["estimated_net_annual_value"],r["id"]))
    if rows:
        leader = rows[0]
        gap = leader["score"] - rows[1]["score"] if len(rows) > 1 else 20
        separation = min(100, round(max(0, gap) / 20 * 100))
        for row in rows:
            row_gap = leader["score"] - row["score"]
            confidence = round(0.7 * row["profile_completeness"] + 0.3 * separation)
            row["confidence"] = max(0, min(100, confidence))
            missing = len(CATEGORIES) - len(profile.spending)
            unknown_eligibility = []
            if profile.monthly_income is None:
                unknown_eligibility.append("income")
            if profile.credit_score is None:
                unknown_eligibility.append("credit score")
            if missing:
                row["confidence_reason"] = f"Moderate: {missing} spending categories and {', '.join(unknown_eligibility) or 'no eligibility fields'} are unknown."
            elif gap < 8:
                row["confidence_reason"] = "Moderate: the leading cards have similar suitability scores."
            else:
                row["confidence_reason"] = "Based on the profile fields supplied and separation from the next-ranked card."
            if row["id"] == leader["id"]:
                row["why_not"] = [f"{other['name']} may suit a different profile; its estimated net value is ₹{other['estimated_net_annual_value']:,}." for other in rows[1:2]]
            else:
                reasons = [f"Ranked {row_gap} CardLens Score points below {leader['name']}."]
                if row["estimated_net_annual_value"] < leader["estimated_net_annual_value"]:
                    reasons.append(f"Estimated net value is ₹{leader['estimated_net_annual_value'] - row['estimated_net_annual_value']:,} lower for the entered spending.")
                if row["annual_fee"] > leader["annual_fee"]:
                    reasons.append(f"Annual fee is ₹{row['annual_fee'] - leader['annual_fee']:,} higher.")
                row["why_not"] = reasons
    return {"recommendations":rows,"excluded":excluded,"message":None if rows else "We couldn't find a strong match based on your current profile."}

@app.get("/health")
@app.get("/api/health", include_in_schema=False)
def health():
    ready, database = check_database()
    return {"status":"ok","service":"CardLens AI","mode":"DEMO" if not database_url() else "POSTGRESQL","database":database,"catalog":"synthetic demo data"}

@app.get("/api/cards")
def cards():
    return {"data":CARDS,"notice":"Synthetic demo data. Terms are not current issuer offers."}

@app.get("/api/cards/{card_id}")
def card_details(card_id: str):
    card = next((item for item in CARDS if item["id"] == card_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail={"success":False,"error_code":"CARD_NOT_FOUND","message":"Card not found in the demo catalog."})
    return {"data":card,"notice":"Synthetic demo data. Terms are not current issuer offers."}

def _account_db():
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"code":"ACCOUNT_STORAGE_UNAVAILABLE","message":"Account storage is temporarily unavailable."})
    return factory

class SettingsInput(BaseModel):
    voice_language: Literal["en","hi","te","ta"] = "en"

@app.get("/api/settings")
def get_settings(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
        return {"voice_language":row.voice_language if row else "en"}

@app.put("/api/settings")
def save_settings(payload: SettingsInput, user: User = Depends(current_user)):
    factory = _account_db()
    with factory.begin() as db:
        row = db.query(UserSettings).filter(UserSettings.user_id == user.id).first()
        if row is None:
            db.add(UserSettings(user_id=user.id, voice_language=payload.voice_language))
        else:
            row.voice_language = payload.voice_language
    return {"voice_language":payload.voice_language,"saved":True}

@app.get("/api/favorites")
def list_favorites(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        favorites = db.query(UserFavorite).filter(UserFavorite.user_id == user.id).order_by(UserFavorite.created_at.desc()).all()
        catalog = {card["id"]:card for card in CARDS}
        return {"items":[{"card_id":item.card_id,"saved_at":item.created_at.isoformat() if item.created_at else None,"card":catalog.get(item.card_id)} for item in favorites]}

@app.post("/api/favorites/{card_id}", status_code=201)
def save_favorite(card_id: str, user: User = Depends(current_user)):
    card = next((item for item in CARDS if item["id"] == card_id), None)
    if card is None:
        raise HTTPException(status_code=404, detail="Card not found.")
    factory = _account_db()
    with factory.begin() as db:
        if db.get(CreditCard, card_id) is None:
            try:
                with db.begin_nested():
                    db.add(CreditCard(
                        id=card_id, name=card["name"], issuer=card["issuer"],
                        network=card["network"], annual_fee=card["annual_fee"],
                        minimum_income=card.get("minimum_income"),
                        minimum_credit_score=card.get("minimum_credit_score"),
                        reward_type=card["reward_type"], source_url=card.get("source_url", ""),
                        status="demo",
                    ))
                    db.flush()
            except IntegrityError:
                # Another request inserted this catalog card concurrently.
                pass
        existing = db.query(UserFavorite).filter(UserFavorite.user_id == user.id, UserFavorite.card_id == card_id).first()
        if existing is None:
            try:
                with db.begin_nested():
                    db.add(UserFavorite(user_id=user.id, card_id=card_id))
                    db.flush()
            except IntegrityError:
                # The unique constraint is the final guard for concurrent saves.
                pass
    return {"saved":True,"card_id":card_id}

@app.delete("/api/favorites/{card_id}")
def remove_favorite(card_id: str, user: User = Depends(current_user)):
    factory = _account_db()
    with factory.begin() as db:
        db.query(UserFavorite).filter(UserFavorite.user_id == user.id, UserFavorite.card_id == card_id).delete()
    return {"saved":False,"card_id":card_id}

@app.get("/api/profile")
def load_profile(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        row = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        return {"profile":row.profile if row else None,"complete":row is not None}

@app.put("/api/profile")
@app.post("/api/profile")
def save_profile(profile: Profile, user: User = Depends(current_user)):
    factory = _account_db()
    value = profile.model_dump()
    with factory.begin() as db:
        row = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if row is None:
            row = UserProfile(user_id=user.id, profile=value)
            db.add(row)
        else:
            row.profile = value
    return {"profile":value,"complete":True,"saved":True}

@app.delete("/api/profile")
def reset_profile(user: User = Depends(current_user)):
    factory = _account_db()
    with factory.begin() as db:
        db.query(UserProfile).filter(UserProfile.user_id == user.id).delete()
        db.query(Recommendation).filter(Recommendation.user_id == user.id).delete()
        db.query(SimulationHistory).filter(SimulationHistory.user_id == user.id).delete()
        db.query(ComparisonHistory).filter(ComparisonHistory.user_id == user.id).delete()
    return {"reset":True}

class ConversationPayload(BaseModel):
    language: Literal["en","hi","te","ta"] = "en"
    messages: list[dict] = Field(max_length=30)

def _safe_messages(items: list[dict]) -> list[dict]:
    safe = []
    for item in items[-30:]:
        role, content = item.get("role"), item.get("text", item.get("content"))
        if role not in {"user","assistant"} or not isinstance(content, str):
            raise HTTPException(status_code=422, detail="Conversation messages must have a user or assistant role and text.")
        content = content.strip()
        if not content or len(content) > 6000:
            raise HTTPException(status_code=422, detail="Conversation messages must be between 1 and 6000 characters.")
        safe.append({"role":role,"text":content})
    return safe

def _conversation_dict(session, db):
    messages = db.query(ConversationMessage).filter(ConversationMessage.session_id == session.id).order_by(ConversationMessage.created_at.asc()).all()
    title = (session.context or {}).get("title")
    if not title:
        first = next((m.content for m in messages if m.role == "user"), "")
        title = first[:52] + ("…" if len(first) > 52 else "") if first else "New conversation"
    return {"id":session.id,"title":title,"language":session.language,"messages":[{"role":m.role,"text":m.content} for m in messages]}

class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=80)

@app.get("/api/conversations")
def list_conversations(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        sessions = db.query(ConversationSession).filter(ConversationSession.user_id == user.id).order_by(ConversationSession.updated_at.desc()).limit(50).all()
        items = []
        for session in sessions:
            conversation = _conversation_dict(session, db)
            conversation["messages"] = conversation["messages"][-1:]
            items.append(conversation)
        return {"items":items}

@app.get("/api/conversations/latest")
def latest_conversation(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        session = db.query(ConversationSession).filter(ConversationSession.user_id == user.id).order_by(ConversationSession.updated_at.desc()).first()
        return {"conversation":_conversation_dict(session, db) if session else None}


@app.get("/api/conversations/{conversation_id}")
def get_conversation(conversation_id: str, user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        session = db.query(ConversationSession).filter(ConversationSession.id == conversation_id, ConversationSession.user_id == user.id).first()
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return {"conversation":_conversation_dict(session, db)}

@app.patch("/api/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRename, user: User = Depends(current_user)):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail="Conversation title cannot be empty.")
    factory = _account_db()
    with factory.begin() as db:
        session = db.query(ConversationSession).filter(ConversationSession.id == conversation_id, ConversationSession.user_id == user.id).first()
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        session.context = {**(session.context or {}), "title":title}
        session.updated_at = datetime.now(timezone.utc)
        return {"conversation":_conversation_dict(session, db)}

@app.delete("/api/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, user: User = Depends(current_user)):
    factory = _account_db()
    with factory.begin() as db:
        session = db.query(ConversationSession).filter(ConversationSession.id == conversation_id, ConversationSession.user_id == user.id).first()
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        db.query(ConversationMessage).filter(ConversationMessage.session_id == session.id).delete()
        db.delete(session)
    return {"deleted":True}

@app.delete("/api/conversations")
def clear_conversations(user: User = Depends(current_user)):
    factory = _account_db()
    with factory.begin() as db:
        sessions = db.query(ConversationSession).filter(ConversationSession.user_id == user.id).all()
        session_ids = [session.id for session in sessions]
        if session_ids:
            db.query(ConversationMessage).filter(ConversationMessage.session_id.in_(session_ids)).delete(synchronize_session=False)
            db.query(ConversationSession).filter(ConversationSession.id.in_(session_ids)).delete(synchronize_session=False)
    return {"deleted":len(session_ids)}

@app.post("/api/conversations", status_code=201)
def create_conversation(payload: ConversationPayload, user: User = Depends(current_user)):
    factory = _account_db()
    messages = _safe_messages(payload.messages)
    with factory.begin() as db:
        session = ConversationSession(user_id=user.id, language=payload.language)
        db.add(session)
        db.flush()
        for item in messages:
            db.add(ConversationMessage(session_id=session.id, role=item["role"], content=item["text"]))
        db.flush()
        return {"conversation":_conversation_dict(session, db)}

@app.put("/api/conversations/{conversation_id}")
def update_conversation(conversation_id: str, payload: ConversationPayload, user: User = Depends(current_user)):
    factory = _account_db()
    messages = _safe_messages(payload.messages)
    with factory.begin() as db:
        session = db.query(ConversationSession).filter(ConversationSession.id == conversation_id, ConversationSession.user_id == user.id).first()
        if session is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        session.language = payload.language
        session.updated_at = datetime.now(timezone.utc)
        db.query(ConversationMessage).filter(ConversationMessage.session_id == session.id).delete()
        for item in messages:
            db.add(ConversationMessage(session_id=session.id, role=item["role"], content=item["text"]))
        db.flush()
        return {"conversation":_conversation_dict(session, db)}

@app.get("/api/history")
def account_history(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        recommendations = db.query(Recommendation).filter(Recommendation.user_id == user.id).order_by(Recommendation.created_at.desc()).limit(5).all()
        simulations = db.query(SimulationHistory).filter(SimulationHistory.user_id == user.id).order_by(SimulationHistory.created_at.desc()).limit(5).all()
        comparisons = db.query(ComparisonHistory).filter(ComparisonHistory.user_id == user.id).order_by(ComparisonHistory.created_at.desc()).limit(5).all()
        conversations = db.query(ConversationSession).filter(ConversationSession.user_id == user.id).order_by(ConversationSession.updated_at.desc()).limit(3).all()
        activity = [
            {"type":"recommendation","created_at":item.created_at.isoformat() if item.created_at else None,
             "summary":(item.results[0].get("name","Recommendation run") + " ranked first") if item.results else "Recommendation run saved"}
            for item in recommendations
        ] + [
            {"type":"simulation","created_at":item.created_at.isoformat() if item.created_at else None,
             "summary":item.results.get("explanation","What-If scenario saved")}
            for item in simulations
        ]
        activity.extend(
            {"type":"comparison","created_at":item.created_at.isoformat() if item.created_at else None,
             "summary":"Compared " + " and ".join(card.get("name","card") for card in item.results[:3])}
            for item in comparisons
        )
        activity.extend(
            {"type":"conversation","created_at":item.updated_at.isoformat() if item.updated_at else None,
             "summary":"Advisor conversation in " + item.language.upper()}
            for item in conversations
        )
        activity.sort(key=lambda item:item["created_at"] or "", reverse=True)
        return {"items":activity[:8]}

class ProfileExtractionRequest(BaseModel):
    text: str = Field(min_length=5, max_length=4000)
    language: Literal["en","hi","te","ta"] = "en"

def _deterministic_profile_extract(text: str) -> dict:
    values: dict = {}
    amount = r"(?:₹|rs\.?\s*)?([0-9][0-9,]*(?:\.[0-9]+)?)"
    income = re.search(r"(?:earn(?:ing)?|income|salary)[^0-9]{0,35}" + amount, text, re.I)
    if income:
        values["monthly_income"] = float(income.group(1).replace(",", ""))
    credit = re.search(r"(?:credit\s+score|cibil(?:\s+score)?|score)[^0-9]{0,15}([0-9]{3})", text, re.I)
    if credit:
        values["credit_score"] = int(credit.group(1))
    fee = re.search(r"(?:annual|yearly) fee[^0-9]{0,25}" + amount, text, re.I)
    if fee:
        values["annual_fee_max"] = float(fee.group(1).replace(",", ""))
    preference = re.search(r"prefer(?:ence)?(?:\s+(?:cashback|cash back|travel|fuel|rewards?))|(?:cashback|cash back|travel|fuel)\s+prefer", text, re.I)
    if preference:
        found = preference.group(0).lower()
        values["reward_preference"] = "cashback" if "cash" in found else ("travel" if "travel" in found else ("fuel" if "fuel" in found else "rewards"))
    categories = {
        "shopping":r"(?:online\s+shopping|shopping|online)",
        "dining":r"(?:dining|restaurants?)",
        "fuel":r"fuel",
        "travel":r"travel",
        "grocery":r"(?:grocer(?:y|ies)|supermarket)",
        "utilities":r"(?:utilities|utility bills?)",
    }
    spending = {}
    # Prefer amounts explicitly followed by a category, such as "₹8,000 on dining".
    for key, term in categories.items():
        match = re.search(amount + r"[^0-9]{0,15}(?:" + term + r")", text, re.I)
        if match:
            spending[key] = float(match.group(1).replace(",", ""))
    # Then accept a category before its amount, without overriding a clearer postfix match.
    for key, term in categories.items():
        if key in spending:
            continue
        match = re.search(r"(?:" + term + r")[^0-9]{0,24}" + amount, text, re.I)
        if match:
            spending[key] = float(match.group(1).replace(",", ""))
    if spending:
        values["spending"] = spending
    return values

@app.post("/api/profile/extract")
async def extract_profile(request: ProfileExtractionRequest):
    candidate = None
    method = "deterministic"
    provider = configured_provider()
    if provider:
        system = (
            "Extract only facts explicitly stated by the user into a JSON object. "
            "Allowed keys: monthly_income, credit_score, age, annual_fee_max, reward_preference, spending. "
            "spending keys: shopping, dining, fuel, travel, grocery, utilities. "
            "Return only valid JSON; omit unknown fields and never infer values. Preserve numeric INR values."
        )
        try:
            response = await provider.chat([{"role":"system","content":system},{"role":"user","content":request.text}])
            raw = response.get("content")
            candidate = json.loads(raw) if isinstance(raw, str) else None
            if not isinstance(candidate, dict):
                raise ValueError("Expected a JSON object")
            method = "llm_extraction"
        except Exception:
            try:
                response = await provider.chat([{"role":"system","content":system+" Output a strict JSON object only; no markdown."},{"role":"user","content":request.text}])
                raw = response.get("content")
                candidate = json.loads(raw) if isinstance(raw, str) else None
                if not isinstance(candidate, dict):
                    raise ValueError("Expected a JSON object")
                method = "llm_extraction_retry"
            except Exception:
                candidate = None
    if candidate is None:
        candidate = _deterministic_profile_extract(request.text)
    try:
        normalized = Profile.model_validate(candidate).model_dump(exclude_unset=True)
    except Exception as exc:
        raise HTTPException(status_code=422, detail={"success":False,"error_code":"PROFILE_EXTRACTION_INVALID","message":"We couldn't validate the extracted values. Please review and enter them manually."}) from exc
    fields = {key:value for key,value in normalized.items() if key in {"monthly_income","credit_score","age","annual_fee_max","reward_preference","spending"}}
    missing = [name for name in ("monthly_income","credit_score","shopping","dining","fuel","travel") if name not in (fields.get("spending",{}) if name in CATEGORIES else fields)]
    return {"extracted_fields":fields,"missing_fields":missing,"method":method,"requires_confirmation":True,"message":"Review and edit these extracted values before generating recommendations."}

@app.post("/api/recommend")
def recommend(profile: Profile, user: User | None = Depends(optional_current_user)):
    result = _rank(profile)
    factory = get_session_factory()
    if user is not None and factory is not None:
        with factory.begin() as db:
            db.add(Recommendation(user_id=user.id, profile_snapshot=profile.model_dump(), results=result["recommendations"]))
    return result

@app.get("/api/recommendations/latest")
def latest_recommendations(user: User = Depends(current_user)):
    factory = _account_db()
    with factory.begin() as db:
        saved_profile = db.query(UserProfile).filter(UserProfile.user_id == user.id).first()
        if saved_profile is None:
            return {"recommendations":[]}
        latest = db.query(Recommendation).filter(Recommendation.user_id == user.id).order_by(Recommendation.created_at.desc()).first()
        if latest is not None and latest.profile_snapshot == saved_profile.profile:
            return {"recommendations":latest.results}
        profile = Profile.model_validate(saved_profile.profile)
        result = _rank(profile)
        db.add(Recommendation(user_id=user.id, profile_snapshot=profile.model_dump(), results=result["recommendations"]))
        return result

@app.post("/api/simulate")
def simulate(payload: dict, user: User | None = Depends(optional_current_user)):
    profile = Profile.model_validate(payload.get("profile", {}))
    changes = payload.get("changes", {})
    allowed = set(CATEGORIES) | {"monthly_income", "credit_score", "annual_fee_max", "reward_preference"}
    unknown = set(changes) - allowed
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unsupported simulation fields: {', '.join(sorted(unknown))}")
    updated_data = profile.model_dump()
    for key, value in changes.items():
        if key in CATEGORIES:
            updated_data["spending"][key] = value
        else:
            updated_data[key] = value
    updated = Profile.model_validate(updated_data)
    before, after = _rank(profile), _rank(updated)
    before_positions = {r["id"]: i + 1 for i, r in enumerate(before["recommendations"])}
    after_positions = {r["id"]: i + 1 for i, r in enumerate(after["recommendations"])}
    moved = [
        {"card_id": card_id, "card_name": next((r["name"] for r in before["recommendations"] + after["recommendations"] if r["id"] == card_id), card_id), "from": before_positions.get(card_id), "to": after_positions.get(card_id)}
        for card_id in sorted(set(before_positions) | set(after_positions))
        if before_positions.get(card_id) != after_positions.get(card_id)
    ]
    before_top = before["recommendations"][0] if before["recommendations"] else None
    after_top = after["recommendations"][0] if after["recommendations"] else None
    if before_top and after_top and before_top["id"] != after_top["id"]:
        explanation = f"{after_top['name']} moved to #1 because the changed profile shifted its score to {after_top['score']}."
    elif before_top and after_top:
        explanation = f"{after_top['name']} remains #1 under the changed profile; its estimated value is ₹{after_top['estimated_net_annual_value']:,}."
    else:
        explanation = "No eligible demo cards match the simulated profile."
    result = {"before":before,"after":after,"moved":moved,"explanation":explanation,"changes":changes}
    factory = get_session_factory()
    if isinstance(user, User) and factory is not None:
        with factory.begin() as db:
            db.add(SimulationHistory(user_id=user.id, before_profile=profile.model_dump(), changes=changes, results=result))
    return result

@app.post("/api/compare")
def compare(payload: dict, user: User | None = Depends(optional_current_user)):
    ids = payload.get("card_ids", [])
    if not isinstance(ids, list) or len(ids) < 2 or len(ids) > 3 or any(not isinstance(item, str) for item in ids) or len(set(ids)) != len(ids):
        raise HTTPException(422, "Choose two or three different cards")
    profile = Profile.model_validate(payload.get("profile", {}))
    ranked = _rank(profile)["recommendations"]
    found = [r for r in ranked if r["id"] in ids]
    if len(found) != len(set(ids)):
        raise HTTPException(404, "One or more cards are not eligible or unknown")
    if isinstance(user, User):
        factory = get_session_factory()
        if factory:
            with factory.begin() as db:
                latest = db.query(ComparisonHistory).filter(ComparisonHistory.user_id == user.id).order_by(ComparisonHistory.created_at.desc()).first()
                if latest is None or latest.card_ids != ids or latest.profile_snapshot != profile.model_dump():
                    db.add(ComparisonHistory(user_id=user.id, profile_snapshot=profile.model_dump(), card_ids=ids, results=found))
    return {"cards":found}

@app.get("/api/compare/latest")
def latest_comparison(user: User = Depends(current_user)):
    factory = _account_db()
    with factory() as db:
        item = db.query(ComparisonHistory).filter(ComparisonHistory.user_id == user.id).order_by(ComparisonHistory.created_at.desc()).first()
        if item is None:
            return {"comparison":None}
        return {"comparison":{"card_ids":item.card_ids,"profile":item.profile_snapshot,"cards":item.results}}

@app.post("/api/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...), language: str = Form("en")):
    if language not in {"en", "hi", "te", "ta"}:
        raise HTTPException(status_code=422, detail="Language must be en, hi, te, or ta.")
    if audio.content_type not in {"audio/webm", "audio/wav", "audio/mpeg", "audio/mp4", "audio/ogg"}:
        raise HTTPException(status_code=415, detail="Unsupported audio format.")
    raw = await audio.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio must be under 10 MiB.")
    provider = configured_voice_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail={"success":False,"error_code":"VOICE_UNAVAILABLE","message":"Voice is temporarily unavailable. Continue with text."})
    try:
        transcript = await provider.transcribe(raw, audio.filename or "recording.webm", language)
        return {"text":transcript,"language":language}
    except Exception:
        logger.warning(json.dumps({"event":"voice_transcription_unavailable","language":language}))
        raise HTTPException(status_code=503, detail={"success":False,"error_code":"VOICE_UNAVAILABLE","message":"Voice is temporarily unavailable. Continue with text."})

@app.post("/api/voice/speak")
async def voice_speak(payload: dict):
    language = str(payload.get("language", "en"))
    text_value = str(payload.get("text", "")).strip()
    if language not in {"en", "hi", "te", "ta"}:
        raise HTTPException(status_code=422, detail="Language must be en, hi, te, or ta.")
    if not text_value or len(text_value) > 4000:
        raise HTTPException(status_code=422, detail="Text is required and must be under 4,000 characters.")
    provider = configured_voice_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail={"success":False,"error_code":"VOICE_UNAVAILABLE","message":"Voice is temporarily unavailable. Continue with text."})
    try:
        audio, media_type = await provider.speak(text_value, language)
        return Response(content=audio, media_type=media_type)
    except Exception:
        logger.warning(json.dumps({"event":"voice_synthesis_unavailable","language":language}))
        raise HTTPException(status_code=503, detail={"success":False,"error_code":"VOICE_UNAVAILABLE","message":"Voice is temporarily unavailable. Continue with text."})

@app.post("/api/rag/search")
async def rag_search(payload: dict):
    query = str(payload.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=422, detail="query is required")
    return await search_card_knowledge(query, configured_embedding_provider(), payload.get("card_id"), int(payload.get("limit", 5)))

AI_TOOLS = [
    {"type":"function","function":{"name":"get_user_profile","description":"Return the user-provided structured profile fields.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"get_recommendations","description":"Run deterministic eligibility and CardLens ranking for the supplied profile.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"get_card_details","description":"Return catalog metadata for a specific demo card. All current card terms are synthetic.","parameters":{"type":"object","properties":{"card_id":{"type":"string"}},"required":["card_id"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"compare_cards","description":"Compare the two top eligible cards using actual backend score and value calculations.","parameters":{"type":"object","properties":{},"additionalProperties":False}}},
    {"type":"function","function":{"name":"calculate_card_value","description":"Calculate estimated value for a card using the deterministic engine.","parameters":{"type":"object","properties":{"card_id":{"type":"string"}},"required":["card_id"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"run_what_if_simulation","description":"Recompute eligibility, scores, rewards, and ranking after profile changes.","parameters":{"type":"object","properties":{"changes":{"type":"object","additionalProperties":{"type":"number"}}},"required":["changes"],"additionalProperties":False}}},
    {"type":"function","function":{"name":"search_card_knowledge","description":"Retrieve source-linked indexed card knowledge. Empty evidence means there is no verified answer.","parameters":{"type":"object","properties":{"query":{"type":"string"},"card_id":{"type":["string","null"]}},"required":["query"],"additionalProperties":False}}},
]

async def _dispatch_assistant_tool(name: str, arguments: dict, profile: Profile):
    ranked = _rank(profile)["recommendations"]
    sources = []
    if name == "get_user_profile":
        return profile.model_dump(), sources
    if name == "get_recommendations":
        return ranked[:3], sources
    if name == "compare_cards":
        return {"cards":ranked[:2],"value_difference":abs(ranked[0]["estimated_net_annual_value"]-ranked[1]["estimated_net_annual_value"]) if len(ranked)>1 else None}, sources
    if name == "get_card_details":
        card = next((c for c in CARDS if c["id"] == arguments.get("card_id")), None)
        if not card:
            return {"error":"Unknown card id"}, sources
        return {"card":card,"notice":"Synthetic demo catalog; not current issuer terms."}, sources
    if name == "calculate_card_value":
        card = next((c for c in ranked if c["id"] == arguments.get("card_id")), None)
        return card or {"error":"Unknown or ineligible card"}, sources
    if name == "run_what_if_simulation":
        result = simulate({"profile":profile.model_dump(),"changes":arguments.get("changes", {})})
        return result, sources
    if name == "search_card_knowledge":
        result = await search_card_knowledge(str(arguments.get("query","")),configured_embedding_provider(),arguments.get("card_id"))
        return result, result.get("sources", [])
    return {"error":"Unknown tool"}, sources

async def _llm_tool_answer(question: str, profile: Profile, language: str, history: list | None = None, previous_simulation: dict | None = None):
    provider = configured_provider()
    if provider is None:
        return None
    language_name = {"en":"English","hi":"Hindi","te":"Telugu","ta":"Tamil"}[language]
    system = (
        "You are the CardLens AI Advisor. You present and explain backend outputs; you are never the recommender. "
        "You MUST call the appropriate tool before making profile, ranking, comparison, simulation, reward, eligibility, or card-term claims. "
        "Never calculate or invent values. Treat demo card data as synthetic. For issuer facts use search_card_knowledge and only state retrieved evidence; if it returns no evidence, say you lack verified information. "
        "Do not imply approval. Keep the response concise and answer in " + language_name + "."
    )
    if previous_simulation:
        system += " Previous deterministic simulation result: " + json.dumps(previous_simulation,ensure_ascii=False,default=str)[:5000] + ". Use run_what_if_simulation if the user asks why it changed."
    safe_history = []
    for item in (history or [])[-6:]:
        if isinstance(item, dict) and item.get("role") in {"user","assistant"} and isinstance(item.get("content"),str):
            safe_history.append({"role":item["role"],"content":item["content"][:1500]})
    messages = [{"role":"system","content":system},*safe_history,{"role":"user","content":question}]
    first = await provider.chat(messages, AI_TOOLS)
    calls = first.get("tool_calls") or []
    if not calls:
        return None
    messages.append(first)
    sources, used = [], []
    for call in calls[:4]:
        fn = call.get("function", {})
        name = fn.get("name", "")
        try:
            arguments = json.loads(fn.get("arguments") or "{}")
            if not isinstance(arguments, dict):
                raise ValueError("Tool arguments must be an object")
        except (ValueError, TypeError):
            return None
        result, found_sources = await _dispatch_assistant_tool(name, arguments, profile)
        used.append(name)
        sources.extend(found_sources)
        messages.append({"role":"tool","tool_call_id":call.get("id",""),"content":json.dumps(result,ensure_ascii=False,default=str)})
    final = await provider.chat(messages)
    answer = final.get("content")
    if not isinstance(answer, str) or not answer.strip():
        return None
    unique_sources = {item["source"]:item for item in sources}
    return {"answer":answer.strip(),"sources":list(unique_sources.values()),"tools_called":used}

@app.post("/api/chat")
async def chat(payload: dict):
    question = str(payload.get("message", "")).strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message is required")
    requested_language = str(payload.get("language", "en"))
    if requested_language not in {"en","hi","te","ta"}:
        raise HTTPException(status_code=422, detail="Language must be en, hi, te, or ta.")
    # Honour a language the user actually typed, while using their selector for
    # English/transliterated input. Model-generated replies receive this same
    # resolved language below.
    language = requested_language
    if any("\u0900" <= char <= "\u097f" for char in question):
        language = "hi"
    elif any("\u0c00" <= char <= "\u0c7f" for char in question):
        language = "te"
    elif any("\u0b80" <= char <= "\u0bff" for char in question):
        language = "ta"
    localized = {
        "en": {"insufficient": INSUFFICIENT_EVIDENCE,
               "no_cards": "There are no eligible synthetic demo cards for the supplied profile.",
               "one_card": "I found only one eligible demo card to compare.",
               "compare": "{first} ranks first with a CardLens Score of {score} and estimated net value ₹{first_value:,}. {second} has estimated net value ₹{second_value:,}. The estimated-value difference is ₹{difference:,}; these are synthetic demo estimates.",
               "why": "{name} is currently ranked first with a model-generated suitability score of {score}/100. {reasons} This is a demo estimate, not an approval prediction.",
               "whatif": "Use the What-If controls to change spending or fee preference; the deterministic simulator will recalculate eligibility, values, scores, and ranking without an AI call.",
               "fallback": "I can explain your current ranking, compare your top eligible demo cards, and search the verified card knowledge base. Card terms are not answered unless a source document is indexed.",
               "simulation_moved": "{name} moved to #1 because the changed profile shifted its score to {score}.",
               "simulation_stays": "{name} remains #1 under the changed profile; its estimated value is ₹{value:,}.",
               "simulation_none": "No eligible demo cards match the simulated profile."},
        "hi": {"insufficient": "इस कार्ड की शर्तों के बारे में मुझे कोई सत्यापित जानकारी नहीं मिली।",
               "no_cards": "दी गई प्रोफ़ाइल के लिए कोई पात्र डेमो कार्ड नहीं मिला।",
               "one_card": "तुलना के लिए केवल एक पात्र डेमो कार्ड मिला।",
               "compare": "{first} पहले स्थान पर है (CardLens स्कोर {score}); इसका अनुमानित शुद्ध वार्षिक मूल्य ₹{first_value:,} है। {second} का अनुमानित शुद्ध वार्षिक मूल्य ₹{second_value:,} है। दोनों के अनुमानित मूल्य में ₹{difference:,} का अंतर है। ये डेमो अनुमान हैं।",
               "why": "{name} अभी {score}/100 के मॉडल-आधारित उपयुक्तता स्कोर के साथ पहले स्थान पर है। {reasons} यह डेमो अनुमान है, स्वीकृति की भविष्यवाणी नहीं।",
               "whatif": "खर्च या शुल्क की पसंद बदलने के लिए What-If नियंत्रण इस्तेमाल करें। सिम्युलेटर बिना AI कॉल के पात्रता, मूल्य और रैंकिंग फिर से निकालेगा।",
               "fallback": "मैं आपकी मौजूदा रैंकिंग समझा सकता हूँ, पात्र डेमो कार्डों की तुलना कर सकता हूँ और सत्यापित कार्ड जानकारी खोज सकता हूँ। स्रोत दस्तावेज़ के बिना कार्ड की शर्तों का उत्तर नहीं दिया जाता।",
               "simulation_moved": "बदली हुई प्रोफ़ाइल के कारण {name} का स्कोर {score} हुआ और वह पहले स्थान पर आ गया।",
               "simulation_stays": "बदली हुई प्रोफ़ाइल में {name} पहले स्थान पर बना हुआ है; इसका अनुमानित मूल्य ₹{value:,} है।",
               "simulation_none": "इस सिम्युलेटेड प्रोफ़ाइल से कोई पात्र डेमो कार्ड नहीं मिला।"},
        "te": {"insufficient": "ఈ కార్డ్ నిబంధనల గురించి ధృవీకరించిన సమాచారం నాకు లభించలేదు.",
               "no_cards": "ఇచ్చిన ప్రొఫైల్‌కు అర్హమైన డెమో కార్డులు లేవు.",
               "one_card": "పోల్చడానికి ఒక్క అర్హమైన డెమో కార్డ్ మాత్రమే దొరికింది.",
               "compare": "{first} మొదటి స్థానంలో ఉంది (CardLens స్కోర్ {score}); అంచనా నికర వార్షిక విలువ ₹{first_value:,}. {second} అంచనా నికర వార్షిక విలువ ₹{second_value:,}. అంచనా విలువల మధ్య తేడా ₹{difference:,}. ఇవి డెమో అంచనాలు.",
               "why": "{name} ప్రస్తుతం {score}/100 మోడల్ అనుకూలత స్కోర్‌తో మొదటి స్థానంలో ఉంది. {reasons} ఇది డెమో అంచనా మాత్రమే; ఆమోద అంచనా కాదు.",
               "whatif": "ఖర్చు లేదా ఫీజు ఎంపికలను మార్చడానికి What-If నియంత్రణలను ఉపయోగించండి. AI కాల్ లేకుండా సిమ్యులేటర్ అర్హత, విలువలు, ర్యాంకింగ్‌ను మళ్లీ లెక్కిస్తుంది.",
               "fallback": "ప్రస్తుత ర్యాంకింగ్‌ను వివరించగలను, అర్హమైన డెమో కార్డులను పోల్చగలను, ధృవీకరించిన కార్డ్ సమాచారాన్ని వెతకగలను. మూల పత్రం లేకుండా కార్డ్ నిబంధనలకు సమాధానం ఇవ్వను.",
               "simulation_moved": "మారిన ప్రొఫైల్ వల్ల {name} స్కోరు {score}కు మారి మొదటి స్థానానికి వచ్చింది.",
               "simulation_stays": "మారిన ప్రొఫైల్‌లో {name} మొదటి స్థానంలోనే ఉంది; అంచనా విలువ ₹{value:,}.",
               "simulation_none": "ఈ సిమ్యులేటెడ్ ప్రొఫైల్‌కు అర్హమైన డెమో కార్డులు లేవు."},
        "ta": {"insufficient": "இந்த அட்டையின் விதிமுறைகள் குறித்து சரிபார்க்கப்பட்ட தகவல் கிடைக்கவில்லை.",
               "no_cards": "கொடுக்கப்பட்ட சுயவிவரத்திற்கு தகுதியான டெமோ அட்டைகள் இல்லை.",
               "one_card": "ஒப்பிடுவதற்கு ஒரு தகுதியான டெமோ அட்டை மட்டுமே கிடைத்தது.",
               "compare": "{first} CardLens மதிப்பெண் {score} உடன் முதலிடத்தில் உள்ளது; அதன் மதிப்பிடப்பட்ட நிகர ஆண்டு மதிப்பு ₹{first_value:,}. {second} மதிப்பிடப்பட்ட நிகர ஆண்டு மதிப்பு ₹{second_value:,}. மதிப்புகளின் வேறுபாடு ₹{difference:,}. இவை டெமோ மதிப்பீடுகள்.",
               "why": "{name} தற்போது {score}/100 மாதிரி பொருத்த மதிப்பெண்ணுடன் முதலிடத்தில் உள்ளது. {reasons} இது டெமோ மதிப்பீடு; ஒப்புதல் கணிப்பு அல்ல.",
               "whatif": "செலவு அல்லது கட்டண விருப்பத்தை மாற்ற What-If கட்டுப்பாடுகளைப் பயன்படுத்தவும். AI அழைப்பின்றி சிமுலேட்டர் தகுதி, மதிப்புகள், தரவரிசையை மீண்டும் கணக்கிடும்.",
               "fallback": "தற்போதைய தரவரிசையை விளக்கவும் தகுதியான டெமோ அட்டைகளை ஒப்பிடவும் சரிபார்க்கப்பட்ட அட்டைத் தகவலைத் தேடவும் முடியும். ஆதார ஆவணம் இல்லாமல் அட்டை விதிமுறைகளுக்குப் பதிலளிக்க மாட்டேன்.",
               "simulation_moved": "மாறிய சுயவிவரத்தால் {name} மதிப்பெண் {score} ஆகி முதலிடத்திற்கு வந்தது.",
               "simulation_stays": "மாறிய சுயவிவரத்திலும் {name} முதலிடத்தில் உள்ளது; மதிப்பிடப்பட்ட மதிப்பு ₹{value:,}.",
               "simulation_none": "இந்த உருவகப்படுத்தப்பட்ட சுயவிவரத்திற்கு தகுதியான டெமோ அட்டைகள் இல்லை."},
    }[language]
    lower = question.lower()
    factual = any(term in lower for term in ("lounge", "forex", "foreign exchange", "annual fee", "joining fee", "cashback rule", "redemption", "exclusion"))
    try:
        profile = Profile.model_validate(payload.get("profile", {}))
    except Exception:
        if factual:
            profile = Profile()
        else:
            raise HTTPException(status_code=422, detail="A valid structured profile is required for personalized answers.")
    if factual:
        knowledge = await search_card_knowledge(question, configured_embedding_provider(), payload.get("card_id"))
        if not knowledge["grounded"]:
            return {"answer":localized["insufficient"],"language":language,"mode":"retrieval_fallback","grounded":False,"sources":[],"tools_called":["search_card_knowledge"]}
        excerpts = knowledge["chunks"][:3]
        provider = configured_provider()
        if provider:
            try:
                system = "Answer the user's card-terms question only from the retrieved source excerpts below. If they do not answer it, say you do not have enough verified information. Do not infer or add terms. Respond in " + {"en":"English","hi":"Hindi","te":"Telugu","ta":"Tamil"}[language] + "."
                evidence = "\n".join(f"[{i+1}] {item['card_name']} | {item['source']} | verified {item['last_verified']}: {item['text']}" for i, item in enumerate(excerpts))
                answer_message = await provider.chat([{"role":"system","content":system+"\n\n"+evidence},{"role":"user","content":question}])
                answer = answer_message.get("content")
                if isinstance(answer, str) and answer.strip():
                    return {"answer":answer.strip(),"language":language,"mode":"rag_llm","grounded":True,"sources":knowledge["sources"],"tools_called":["search_card_knowledge"]}
            except Exception as exc:
                logger.warning(json.dumps({"event":"rag_llm_fallback","error_type":type(exc).__name__}))
        intro = {"en":"Verified source excerpts:","hi":"सत्यापित स्रोत अंश:","te":"ధృవీకరించిన మూల వాక్యాలు:","ta":"சரிபார்க்கப்பட்ட ஆதாரப் பகுதிகள்:"}[language]
        answer = intro + "\n" + "\n".join(f"• {item['card_name']}: {item['text']}" for item in excerpts)
        return {"answer":answer,"language":language,"mode":"retrieval","grounded":True,"sources":knowledge["sources"],"tools_called":["search_card_knowledge"]}
    try:
        llm_result = await _llm_tool_answer(question, profile, language, payload.get('history'), payload.get('last_simulation'))
        if llm_result:
            return {**llm_result,"language":language,"mode":"llm_tools","grounded":True}
    except Exception as exc:
        logger.warning(json.dumps({"event":"llm_tool_fallback","error_type":type(exc).__name__}))
    last_simulation = payload.get("last_simulation")
    if isinstance(last_simulation, dict) and any(term in lower for term in ("why", "ranking changed", "ranking change")):
        changes = last_simulation.get("changes", {})
        if isinstance(changes, dict):
            try:
                recalculated = simulate({"profile":profile.model_dump(),"changes":changes})
                before_top = (recalculated.get("before", {}).get("recommendations") or [{}])[0]
                after_top = (recalculated.get("after", {}).get("recommendations") or [{}])[0]
                if not after_top:
                    simulation_answer = localized["simulation_none"]
                elif before_top.get("id") != after_top.get("id"):
                    simulation_answer = localized["simulation_moved"].format(name=after_top.get("name", ""), score=after_top.get("score", 0))
                else:
                    simulation_answer = localized["simulation_stays"].format(name=after_top.get("name", ""), value=after_top.get("estimated_net_annual_value", 0))
                return {"answer":simulation_answer,"language":language,"mode":"deterministic_tools","grounded":True,"tools_called":["run_what_if_simulation"],"simulation":recalculated}
            except (HTTPException, TypeError, ValueError):
                pass
    ranked = _rank(profile)["recommendations"]
    if not ranked:
        return {"answer":localized["no_cards"],"language":language,"mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations"]}
    if any(term in lower for term in ("compare", "top two", "difference", "versus", " vs ")):
        compared = ranked[:2]
        if len(compared) < 2:
            return {"answer":localized["one_card"],"language":language,"mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations"]}
        delta = compared[0]["estimated_net_annual_value"] - compared[1]["estimated_net_annual_value"]
        answer = localized["compare"].format(first=compared[0]['name'],score=compared[0]['score'],first_value=compared[0]['estimated_net_annual_value'],second=compared[1]['name'],second_value=compared[1]['estimated_net_annual_value'],difference=abs(delta))
        return {"answer":answer,"language":language,"mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations","compare_cards"],"cards":compared}
    if any(term in lower for term in ("why", "recommend", "best card", "shopping")):
        first = ranked[0]
        answer = localized["why"].format(name=first['name'],score=first['score'],reasons="; ".join(first["why"]))
        return {"answer":answer,"language":language,"mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations"],"card":first}
    if "what if" in lower or "simulation" in lower:
        return {"answer":localized["whatif"],"language":language,"mode":"deterministic_tools","grounded":True,"tools_called":["run_what_if_simulation"]}
    return {"answer":localized["fallback"],"language":language,"mode":"deterministic_fallback","grounded":True,"tools_called":[]}

@app.get("/ready")
@app.get("/api/ready", include_in_schema=False)
def ready():
    available, database = check_database()
    if not available:
        raise HTTPException(status_code=503, detail={"success":False,"error_code":"DATABASE_UNAVAILABLE","message":"Persistent storage is temporarily unavailable."})
    return {"status":"ready","mode":"DEMO" if not database_url() else "POSTGRESQL","database":database}



