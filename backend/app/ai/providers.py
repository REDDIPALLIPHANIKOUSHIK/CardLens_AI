from __future__ import annotations

import os
from typing import Any, Protocol
import httpx

class LLMProvider(Protocol):
    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]: ...

class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]: ...

class SpeechToTextProvider(Protocol):
    async def transcribe(self, audio: bytes, filename: str, language: str) -> str: ...

class TextToSpeechProvider(Protocol):
    async def speak(self, text: str, language: str) -> tuple[bytes, str]: ...

class OpenAICompatibleProvider:
    """Optional OpenAI API adapter. Requests have bounded timeouts and require an explicit key."""
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        if not api_key:
            raise ValueError("API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        self.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.timeout = httpx.Timeout(12.0, connect=3.0)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"model": self.llm_model, "messages": messages, "temperature": 0}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        choice = data.get("choices", [{}])[0].get("message")
        if not isinstance(choice, dict):
            raise ValueError("Provider returned an invalid chat response")
        return choice

    async def embed(self, text: str) -> list[float]:
        payload = {"model": self.embedding_model, "input": text, "dimensions": 384}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(f"{self.base_url}/embeddings", headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        vector = data.get("data", [{}])[0].get("embedding")
        if not isinstance(vector, list) or len(vector) != 384:
            raise ValueError("Embedding provider must return exactly 384 dimensions")
        return [float(value) for value in vector]

    async def transcribe(self, audio: bytes, filename: str, language: str) -> str:
        language_names = {"en":"English","hi":"Hindi","te":"Telugu","ta":"Tamil"}
        data = {"model": os.getenv("VOICE_STT_MODEL", "whisper-1"), "language": language, "prompt": f"Transcribe the speech in {language_names.get(language, 'English')}. Preserve spoken financial amounts."}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0)) as client:
            response = await client.post(f"{self.base_url}/audio/transcriptions", headers=self._headers(), data=data, files={"file":(filename,audio,"audio/webm")})
            response.raise_for_status()
            result = response.json().get("text")
        if not isinstance(result, str) or not result.strip():
            raise ValueError("Speech service returned no transcript")
        return result.strip()

    async def speak(self, text: str, language: str) -> tuple[bytes, str]:
        payload = {"model": os.getenv("VOICE_TTS_MODEL", "tts-1"), "voice": os.getenv("VOICE_NAME", "alloy"), "input": text, "response_format": "mp3"}
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=3.0)) as client:
            response = await client.post(f"{self.base_url}/audio/speech", headers={**self._headers(),"Content-Type":"application/json"}, json=payload)
            response.raise_for_status()
        return response.content, response.headers.get("content-type", "audio/mpeg")

def configured_provider() -> OpenAICompatibleProvider | None:
    if os.getenv("LLM_PROVIDER", "openai").lower() != "openai":
        return None
    key = os.getenv("LLM_API_KEY", "").strip()
    return OpenAICompatibleProvider(key, os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")) if key else None

def configured_embedding_provider() -> OpenAICompatibleProvider | None:
    key = os.getenv("EMBEDDING_API_KEY", "").strip() or os.getenv("LLM_API_KEY", "").strip()
    if not key:
        return None
    base = os.getenv("EMBEDDING_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    provider = OpenAICompatibleProvider(key, base)
    provider.embedding_model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    return provider

def configured_voice_provider() -> OpenAICompatibleProvider | None:
    key = os.getenv("VOICE_API_KEY", "").strip() or os.getenv("LLM_API_KEY", "").strip()
    if not key:
        return None
    base = os.getenv("VOICE_BASE_URL", os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    return OpenAICompatibleProvider(key, base)
