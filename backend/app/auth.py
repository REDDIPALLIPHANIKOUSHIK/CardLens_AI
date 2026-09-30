from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from .database import get_session_factory
from .models import AuthSession, User

router = APIRouter(prefix="/api/auth", tags=["authentication"])
COOKIE_NAME = "cardlens_session"
SESSION_DAYS = 30
_EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

class SignupInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=10, max_length=128)
    name: str = Field(min_length=1, max_length=120)

class LoginInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)

def _factory():
    factory = get_session_factory()
    if factory is None:
        raise HTTPException(status_code=503, detail={"code":"ACCOUNT_STORAGE_UNAVAILABLE","message":"Account storage is temporarily unavailable."})
    return factory

def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(derived).decode()

def _verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        # Perform a dummy hash to reduce account-enumeration timing differences.
        _hash_password(password)
        return False
    try:
        scheme, n, r, p, salt_text, hash_text = encoded.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(hash_text.encode())
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False

def _new_session(db, user: User, response: Response) -> None:
    raw = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    now = datetime.now(timezone.utc)
    db.add(AuthSession(token_hash=token_hash, user_id=user.id, expires_at=now + timedelta(days=SESSION_DAYS)))
    db.commit()
    response.set_cookie(
        COOKIE_NAME, raw, max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True, secure=os.getenv("APP_ENV", "development").lower() == "production",
        samesite="strict", path="/",
    )

def _public_user(user: User) -> dict:
    return {"id":user.id,"email":user.email,"name":user.name}

def optional_current_user(request: Request) -> User | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    factory = get_session_factory()
    if factory is None:
        return None
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    with factory() as db:
        row = db.execute(select(AuthSession, User).join(User, User.id == AuthSession.user_id).where(
            AuthSession.token_hash == token_hash,
            AuthSession.expires_at > datetime.now(timezone.utc),
        )).first()
        return row[1] if row else None

def current_user(request: Request) -> User:
    user = optional_current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail={"code":"AUTH_REQUIRED","message":"Please sign in to continue."})
    return user

@router.post("/signup", status_code=201)
def signup(payload: SignupInput, response: Response):
    email = payload.email.strip().lower()
    name = payload.name.strip()
    if not _EMAIL.fullmatch(email) or not name:
        raise HTTPException(status_code=422, detail="Enter a valid email and name.")
    if len(payload.password) < 10 or not any(c.isalpha() for c in payload.password) or not any(c.isdigit() for c in payload.password):
        raise HTTPException(status_code=422, detail="Use a password with at least 10 characters, including a letter and a number.")
    factory = _factory()
    with factory() as db:
        if db.scalar(select(User.id).where(User.email == email)):
            raise HTTPException(status_code=409, detail={"code":"EMAIL_EXISTS","message":"An account with this email already exists."})
        user = User(email=email, name=name, password_hash=_hash_password(payload.password))
        db.add(user)
        db.flush()
        _new_session(db, user, response)
        return {"user":_public_user(user)}

@router.post("/login")
def login(payload: LoginInput, response: Response):
    email = payload.email.strip().lower()
    factory = _factory()
    with factory() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None or not _verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail={"code":"INVALID_CREDENTIALS","message":"Email or password is incorrect."})
        _new_session(db, user, response)
        return {"user":_public_user(user)}

@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"user":_public_user(user)}

@router.post("/logout")
def logout(request: Request, response: Response):
    raw = request.cookies.get(COOKIE_NAME)
    factory = get_session_factory()
    if raw and factory:
        token_hash = hashlib.sha256(raw.encode()).hexdigest()
        with factory() as db:
            db.query(AuthSession).filter(AuthSession.token_hash == token_hash).delete()
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=os.getenv("APP_ENV", "development").lower() == "production", samesite="strict")
    return {"ok":True}
