from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

from app.services.email_analysis.llm.errors import LLMValidationError

T = TypeVar("T", bound=BaseModel)


class LLMService:
    def __init__(self, client):
        self._client = client

    async def generate(self, system: str, user: str, response_model: Type[T]) -> T:
        raw = await self._client.complete_json(system, user, response_model)
        try:
            return response_model.model_validate_json(raw)
        except ValidationError as exc:
            raise LLMValidationError(f"LLM response failed validation: {exc}") from exc
