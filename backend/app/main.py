from __future__ import annotations

from typing import Literal
from collections import defaultdict, deque
from threading import Lock
import json, logging, os, re, time, uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi import File, Form, UploadFile
from .database import check_database, database_url
from .ai.providers import configured_provider, configured_embedding_provider, configured_voice_provider
from .rag import INSUFFICIENT_EVIDENCE, search_card_knowledge
from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger('cardlens.api')
app = FastAPI(title="CardLens AI", version="0.1.0", description="Deterministic demo credit-card suitability recommendations")
origins = [value.strip() for value in os.getenv("FRONTEND_ORIGINS", "http://localhost:5173").split(",") if value.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Request-ID"])

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
    limited = request.method == "POST" and request.url.path in {"/api/recommend", "/api/simulate", "/api/compare", "/api/chat", "/api/rag/search"}
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
    annual_fee_max: float = Field(1500, ge=0, le=1_000_000)
    reward_preference: Literal["cashback","travel","fuel","rewards"] = "cashback"
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
        preference = 100 if c["reward_type"] == profile.reward_preference else 55
        fee_fit = 100 if c["annual_fee"] <= profile.annual_fee_max else max(0, 100 - (c["annual_fee"]-profile.annual_fee_max)/20)
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
        why.append("Annual fee is within your stated preference" if c["annual_fee"] <= profile.annual_fee_max else "Fee preference lowers this card's fit")
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

@app.get("/api/health")
def health():
    ready, database = check_database()
    return {"status":"ok","service":"CardLens AI","mode":"DEMO" if not database_url() else "POSTGRESQL","database":database,"catalog":"synthetic demo data"}

@app.get("/api/cards")
def cards():
    return {"data":CARDS,"notice":"Synthetic demo data. Terms are not current issuer offers."}

@app.post("/api/recommend")
def recommend(profile: Profile):
    return _rank(profile)

@app.post("/api/simulate")
def simulate(payload: dict):
    profile = Profile.model_validate(payload.get("profile", {}))
    changes = payload.get("changes", {})
    allowed = set(CATEGORIES) | {"monthly_income", "credit_score", "annual_fee_max"}
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
        {"card_id": card_id, "from": before_positions.get(card_id), "to": after_positions.get(card_id)}
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
    return {"before":before,"after":after,"moved":moved,"explanation":explanation,"changes":changes}

@app.post("/api/compare")
def compare(payload: dict):
    ids = payload.get("card_ids", [])
    if len(ids) < 2 or len(ids) > 4:
        raise HTTPException(422, "Choose between two and four cards")
    profile = Profile.model_validate(payload.get("profile", {}))
    ranked = _rank(profile)["recommendations"]
    found = [r for r in ranked if r["id"] in ids]
    if len(found) != len(set(ids)):
        raise HTTPException(404, "One or more cards are not eligible or unknown")
    return {"cards":found}

@app.post("/api/voice/transcribe")
async def voice_transcribe(audio: UploadFile = File(...), language: str = Form("en")):
    if language not in {"en", "hi", "te"}:
        raise HTTPException(status_code=422, detail="Language must be en, hi, or te.")
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
    if language not in {"en", "hi", "te"}:
        raise HTTPException(status_code=422, detail="Language must be en, hi, or te.")
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

@app.post("/api/chat")
async def chat(payload: dict):
    question = str(payload.get("message", "")).strip()
    if not question:
        raise HTTPException(status_code=422, detail="Message is required")
    lower = question.lower()
    factual = any(term in lower for term in ("lounge", "forex", "foreign exchange", "annual fee", "joining fee", "cashback rule", "redemption", "exclusion"))
    if factual:
        knowledge = await search_card_knowledge(question, configured_embedding_provider(), payload.get("card_id"))
        if not knowledge["grounded"]:
            return {"answer":INSUFFICIENT_EVIDENCE,"mode":"retrieval_fallback","grounded":False,"sources":[],"tools_called":["search_card_knowledge"]}
        excerpts = knowledge["chunks"][:2]
        answer = "Verified source excerpts:\n" + "\n".join(f"• {item['card_name']}: {item['text']}" for item in excerpts)
        return {"answer":answer,"mode":"retrieval","grounded":True,"sources":knowledge["sources"],"tools_called":["search_card_knowledge"]}
    try:
        profile = Profile.model_validate(payload.get("profile", {}))
    except Exception:
        raise HTTPException(status_code=422, detail="A valid structured profile is required for personalized answers.")
    ranked = _rank(profile)["recommendations"]
    if not ranked:
        return {"answer":"There are no eligible synthetic demo cards for the supplied profile.","mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations"]}
    if any(term in lower for term in ("compare", "top two", "difference", "versus", " vs ")):
        compared = ranked[:2]
        if len(compared) < 2:
            return {"answer":"I found only one eligible demo card to compare.","mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations"]}
        delta = compared[0]["estimated_net_annual_value"] - compared[1]["estimated_net_annual_value"]
        answer = f"{compared[0]['name']} ranks first with a CardLens Score of {compared[0]['score']} and estimated net value ₹{compared[0]['estimated_net_annual_value']:,}. {compared[1]['name']} has estimated net value ₹{compared[1]['estimated_net_annual_value']:,}. The estimated-value difference is ₹{abs(delta):,}; these are synthetic demo estimates."
        return {"answer":answer,"mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations","compare_cards"],"cards":compared}
    if any(term in lower for term in ("why", "recommend", "best card", "shopping")):
        first = ranked[0]
        answer = f"{first['name']} is currently ranked first with a model-generated suitability score of {first['score']}/100. " + "; ".join(first["why"]) + " This is a demo estimate, not an approval prediction."
        return {"answer":answer,"mode":"deterministic_tools","grounded":True,"tools_called":["get_recommendations"],"card":first}
    if "what if" in lower or "simulation" in lower:
        return {"answer":"Use the What-If controls to change spending or fee preference; the deterministic simulator will recalculate eligibility, values, scores, and ranking without an AI call.","mode":"deterministic_tools","grounded":True,"tools_called":["run_what_if_simulation"]}
    return {"answer":"I can explain your current ranking, compare your top eligible demo cards, and search the verified card knowledge base. Card terms are not answered unless a source document is indexed.","mode":"deterministic_fallback","grounded":True,"tools_called":[]}

@app.get("/api/ready")
def ready():
    available, database = check_database()
    if not available:
        raise HTTPException(status_code=503, detail={"success":False,"error_code":"DATABASE_UNAVAILABLE","message":"Persistent storage is temporarily unavailable."})
    return {"status":"ready","mode":"DEMO" if not database_url() else "POSTGRESQL","database":database}
