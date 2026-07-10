from app.config import Settings
from app.services.email_analysis.llm.errors import LLMProviderError
from app.services.email_analysis.llm.gemini_client import GeminiClient
from app.services.email_analysis.llm.openai_client import OpenAIClient


def create_llm_client(settings: Settings):
    provider = settings.llm_provider.lower()

    if provider == "openai":
        if not settings.openai_api_key:
            raise LLMProviderError("OPENAI_API_KEY is required when LLM_PROVIDER=openai")
        return OpenAIClient(
            api_key=settings.openai_api_key,
            model=settings.model,
            timeout=settings.llm_timeout,
            temperature=settings.llm_temperature,
        )

    if provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMProviderError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")
        return GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.model,
            timeout=settings.llm_timeout,
            temperature=settings.llm_temperature,
        )

    raise LLMProviderError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
