"""Ingest JSONL card documents into pgvector after embedding each chunk.

Each JSON line requires card_id, card_name, source (HTTPS), document_version,
last_verified (ISO date), and text. Set is_demo=true for synthetic documents.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.ai.providers import configured_provider
from backend.app.database import get_session_factory
from backend.app.models import CardDocument

def chunks(text: str, size: int = 900, overlap: int = 120) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    output = []
    start = 0
    while start < len(cleaned):
        part = cleaned[start:start + size].strip()
        if part:
            output.append(part)
        if start + size >= len(cleaned):
            break
        start += size - overlap
    return output

async def ingest(path: Path):
    factory = get_session_factory()
    provider = configured_provider()
    if not factory:
        raise SystemExit("DATABASE_URL is required.")
    if not provider:
        raise SystemExit("Set LLM_API_KEY and EMBEDDING_MODEL to enable document embeddings.")
    docs = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    inserted = 0
    with factory.begin() as session:
        for doc in docs:
            required = {"card_id","card_name","source","document_version","last_verified","text"}
            if not required.issubset(doc):
                raise ValueError(f"Document is missing fields: {sorted(required - set(doc))}")
            if not str(doc["source"]).startswith("https://"):
                raise ValueError("Source must be an HTTPS URL.")
            date.fromisoformat(str(doc["last_verified"]))
            is_demo = bool(doc.get("is_demo", False))
            for index, part in enumerate(chunks(str(doc["text"]))):
                vector = await provider.embed(part)
                identifier = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc['card_id']}:{doc['document_version']}:{index}:{doc['source']}"))
                session.merge(CardDocument(id=identifier,card_id=doc["card_id"],card_name=doc["card_name"],source=doc["source"],document_version=doc["document_version"],last_verified=date.fromisoformat(doc["last_verified"]),chunk_text=part,embedding=vector,is_demo=is_demo))
                inserted += 1
    print(f"Ingested {inserted} chunks from {len(docs)} source document(s).")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("jsonl", type=Path)
    asyncio.run(ingest(parser.parse_args().jsonl))
