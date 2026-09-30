from __future__ import annotations

from typing import Any
from sqlalchemy import select
from .ai.providers import EmbeddingProvider
from .database import get_session_factory
from .models import CardDocument

INSUFFICIENT_EVIDENCE = "I don't have enough verified information to answer that confidently."

async def search_card_knowledge(query: str, provider: EmbeddingProvider | None, card_id: str | None = None, limit: int = 5) -> dict[str, Any]:
    query = " ".join(query.split())[:2000]
    if not query:
        return {"available":False,"grounded":False,"answer":INSUFFICIENT_EVIDENCE,"sources":[],"chunks":[]}
    if provider is None:
        return {"available":False,"grounded":False,"answer":INSUFFICIENT_EVIDENCE,"sources":[],"chunks":[]}
    factory = get_session_factory()
    if factory is None:
        return {"available":False,"grounded":False,"answer":INSUFFICIENT_EVIDENCE,"sources":[],"chunks":[]}
    try:
        vector = await provider.embed(query)
        if len(vector) != 384:
            raise ValueError("Expected 384-dimensional query embedding")
        distance = CardDocument.embedding.cosine_distance(vector).label("distance")
        statement = select(CardDocument, distance).where(CardDocument.embedding.is_not(None))
        if card_id:
            statement = statement.where(CardDocument.card_id == card_id)
        statement = statement.order_by(distance).limit(max(1, min(limit, 10)))
        with factory() as session:
            results = session.execute(statement).all()
        chunks = [
            {"text":doc.chunk_text,"card_id":doc.card_id,"card_name":doc.card_name,"source":doc.source,"document_version":doc.document_version,"last_verified":doc.last_verified.isoformat() if doc.last_verified else None,"is_demo":doc.is_demo,"distance":float(dist)}
            for doc, dist in results if dist is not None and float(dist) <= 0.55
        ]
        if not chunks:
            return {"available":True,"grounded":False,"answer":INSUFFICIENT_EVIDENCE,"sources":[],"chunks":[]}
        sources = list({item["source"]:{"source":item["source"],"card_name":item["card_name"],"document_version":item["document_version"],"last_verified":item["last_verified"],"is_demo":item["is_demo"]} for item in chunks}.values())
        return {"available":True,"grounded":True,"answer":None,"sources":sources,"chunks":chunks}
    except Exception:
        return {"available":False,"grounded":False,"answer":INSUFFICIENT_EVIDENCE,"sources":[],"chunks":[]}
