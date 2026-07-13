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

    async def complete_json(self, system: str, user: str, response_model: type[BaseModel]) -> str:
        try:
            response = await asyncio.wait_for(
                self._client.chat.completions.parse(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format=response_model,
                    temperature=self._temperature,
                ),
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
