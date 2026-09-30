"""Idempotently seed synthetic demo card offers. Requires DATABASE_URL."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.database import get_session_factory
from backend.app.main import CARDS
from backend.app.models import CardBenefit, CreditCard

def main():
    factory = get_session_factory()
    if factory is None:
        raise SystemExit("DATABASE_URL is not set. Set it to a PostgreSQL connection string first.")
    with factory.begin() as session:
        for card in CARDS:
            session.merge(CreditCard(
                id=card["id"], name=card["name"], issuer=card["issuer"], network=card["network"],
                annual_fee=card["annual_fee"], minimum_income=card["minimum_income"],
                minimum_credit_score=card["minimum_credit_score"], reward_type=card["reward_type"],
                source_url=card["source_url"], status="synthetic_demo",
            ))
            for category, rate in card["rates"].items():
                benefit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"cardlens:{card['id']}:{category}"))
                session.merge(CardBenefit(
                    id=benefit_id, card_id=card["id"], category=category,
                    reward_rate=rate, annual_cap=None,
                    description="Synthetic illustrative rate; not issuer-verified.",
                ))
    print(f"Seeded {len(CARDS)} clearly labeled synthetic demo cards.")

if __name__ == "__main__":
    main()
