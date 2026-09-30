from __future__ import annotations

import os
from functools import lru_cache
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

def database_url() -> str | None:
    value = os.getenv("DATABASE_URL", "").strip()
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://"):]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://"):]
    return value or None

@lru_cache(maxsize=1)
def get_engine() -> Engine | None:
    url = database_url()
    if not url:
        return None
    return create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)

def get_session_factory():
    engine = get_engine()
    return sessionmaker(bind=engine, expire_on_commit=False) if engine else None

def check_database() -> tuple[bool, str]:
    engine = get_engine()
    if engine is None:
        return True, "demo_fallback"
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "postgresql"
    except Exception:
        return False, "database_unavailable"
