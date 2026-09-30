from __future__ import annotations

import uuid
from datetime import datetime
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from pgvector.sqlalchemy import Vector

def new_id() -> str:
    return str(uuid.uuid4())

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class UserProfile(Base):
    __tablename__ = "user_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class CreditCard(Base):
    __tablename__ = "credit_cards"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    network: Mapped[str] = mapped_column(String(50), nullable=False)
    annual_fee: Mapped[float] = mapped_column(Float, nullable=False)
    minimum_income: Mapped[float | None] = mapped_column(Float)
    minimum_credit_score: Mapped[int | None] = mapped_column(Integer)
    reward_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    last_verified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="demo")

class CardBenefit(Base):
    __tablename__ = "card_benefits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    card_id: Mapped[str] = mapped_column(ForeignKey("credit_cards.id", ondelete="CASCADE"), index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    reward_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    annual_cap: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str] = mapped_column(Text, default="")

class CardDocument(Base):
    __tablename__ = "card_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("credit_cards.id", ondelete="SET NULL"), index=True)
    card_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(1000), nullable=False)
    document_version: Mapped[str] = mapped_column(String(120), nullable=False)
    last_verified: Mapped[object | None] = mapped_column(Date())
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(384))
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)

class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    profile_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    results: Mapped[list] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class RecommendationExplanation(Base):
    __tablename__ = "recommendation_explanations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recommendation_id: Mapped[str] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"), index=True)
    card_id: Mapped[str] = mapped_column(ForeignKey("credit_cards.id", ondelete="CASCADE"), index=True)
    why: Mapped[list] = mapped_column(JSON, default=list)
    why_not: Mapped[list] = mapped_column(JSON, default=list)
    score_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)

class ConversationSession(Base):
    __tablename__ = "conversation_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    language: Mapped[str] = mapped_column(String(10), default="en")
    context: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("conversation_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class SimulationHistory(Base):
    __tablename__ = "simulation_history"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    before_profile: Mapped[dict] = mapped_column(JSON, nullable=False)
    changes: Mapped[dict] = mapped_column(JSON, nullable=False)
    results: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
