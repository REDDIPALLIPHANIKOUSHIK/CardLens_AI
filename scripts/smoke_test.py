"""Smoke-test the Compose production-like stack using only the Python standard library."""
from __future__ import annotations

import json
import os
import time
import uuid
from http.cookiejar import CookieJar
from urllib.request import HTTPCookieProcessor, build_opener
from urllib.error import URLError
from urllib.request import Request, urlopen

API = os.getenv("CARDLENS_API_URL", "http://127.0.0.1:8000")
WEB = os.getenv("CARDLENS_WEB_URL", "http://127.0.0.1:5173")
opener = build_opener(HTTPCookieProcessor(CookieJar()))

PROFILE = {
    "monthly_income": 70000,
    "credit_score": 760,
    "annual_fee_max": 1500,
    "reward_preference": "cashback",
    "spending": {"shopping": 15000, "dining": 8000, "fuel": 4000, "travel": 5000},
}


def request_json(url: str, payload: dict | None = None, method: str | None = None) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=data, headers={"Content-Type": "application/json"} if data else {}, method=method)
    with opener.open(request, timeout=8) as response:
        return json.load(response)


def main() -> None:
    last_error = None
    for _ in range(30):
        try:
            request_json(f"{API}/ready")
            break
        except (URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(2)
    else:
        raise SystemExit(f"API did not become ready: {last_error}")

    assert request_json(f"{API}/health")["status"] == "ok"
    assert request_json(f"{API}/ready")["status"] == "ready"

    email = f"smoke-{uuid.uuid4()}@example.test"
    account = request_json(f"{API}/api/auth/signup", {"email":email,"password":"smoke test 2026","name":"Smoke Test"})
    assert account["user"]["email"] == email
    profile_response = request_json(f"{API}/api/profile", PROFILE, method="PUT")
    assert profile_response["saved"] is True
    assert request_json(f"{API}/api/profile")["profile"]["credit_score"] == PROFILE["credit_score"]

    result = request_json(f"{API}/api/recommend", PROFILE)
    cards = result["recommendations"]
    assert len(cards) >= 3, "Expected at least three eligible demo recommendations"
    first = cards[0]
    for key in ("score", "score_breakdown", "estimated_annual_rewards", "estimated_net_annual_value", "confidence", "why", "why_not"):
        assert key in first, f"Recommendation missing {key}"

    compared = request_json(f"{API}/api/compare", {"profile": PROFILE, "card_ids": [card["id"] for card in cards[:2]]})
    assert len(compared["cards"]) == 2

    scenario = request_json(f"{API}/api/simulate", {"profile": PROFILE, "changes": {"travel": 15000}})
    assert len(scenario["after"]["recommendations"]) >= 3
    assert "explanation" in scenario

    answer = request_json(f"{API}/api/chat", {"profile": PROFILE, "message": "Why did you recommend this card?"})
    assert answer["mode"] == "deterministic_tools"
    assert answer["tools_called"]

    rag = request_json(f"{API}/api/rag/search", {"query": "lounge access"})
    assert rag["grounded"] is False
    factual_answer = request_json(f"{API}/api/chat", {"profile": PROFILE, "message": "Does this card have lounge access?"})
    assert "verified information" in factual_answer["answer"].lower()

    no_match = request_json(f"{API}/api/recommend", {"monthly_income": 1, "credit_score": 300, "spending": {}})
    assert no_match["recommendations"] == []

    web_request = Request(WEB)
    with urlopen(web_request, timeout=8) as response:
        html = response.read().decode("utf-8")
    assert response.status == 200 and "<html" in html.lower()
    request_json(f"{API}/api/auth/logout", {}, method="POST")
    print("Compose smoke test passed: account signup, profile persistence, health/readiness, recommendations, compare, What-If, chat fallback, RAG fallback, no-match profile, and frontend.")
    

if __name__ == "__main__":
    main()
