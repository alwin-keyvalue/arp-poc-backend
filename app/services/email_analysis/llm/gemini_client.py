import asyncio
import json

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.services.email_analysis.llm.errors import LLMProviderError, LLMTimeoutError


class GeminiClient:
    def __init__(self, api_key: str, model: str, timeout: int, temperature: float):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._temperature = temperature
        self._timeout = timeout

    async def complete_json(self, system: str, user: str, response_model: type[BaseModel]) -> str:
        schema = response_model.model_json_schema()
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=self._temperature,
            response_mime_type="application/json",
            response_schema=schema,
        )

        try:
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=user,
                    config=config,
                ),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(f"Gemini request timed out after {self._timeout}s") from exc
        except Exception as exc:
            raise LLMProviderError(f"Gemini request failed: {exc}") from exc

        text = response.text
        if not text:
            raise LLMProviderError("Gemini returned empty response")

        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"Gemini returned invalid JSON: {exc}") from exc

        return text
