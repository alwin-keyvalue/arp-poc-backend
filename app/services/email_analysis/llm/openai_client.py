import asyncio

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.services.email_analysis.llm.errors import LLMProviderError, LLMTimeoutError


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout: int,
        temperature: float,
        base_url: str | None = None,
    ):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self._model = model
        self._temperature = temperature
        self._timeout = timeout

    def _supports_custom_temperature(self) -> bool:
        # gpt-5* only accept the default temperature=1.
        name = self._model.lower().rsplit("/", 1)[-1]
        return not (name.startswith("gpt-5"))

    async def complete_json(
        self, system: str, user: str, response_model: type[BaseModel]
    ) -> str:
        params = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "response_format": response_model,
        }
        if self._supports_custom_temperature():
            params["temperature"] = self._temperature

        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.parse(**params),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise LLMTimeoutError(f"OpenAI request timed out after {self._timeout}s") from exc
        except Exception as exc:
            raise LLMProviderError(f"OpenAI request failed: {exc}") from exc

        message = response.choices[0].message
        if message.refusal:
            raise LLMProviderError(f"OpenAI refused request: {message.refusal}")
        if message.parsed is None:
            raise LLMProviderError("OpenAI returned no parsed response")

        return message.parsed.model_dump_json()
