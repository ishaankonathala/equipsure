from app.ai.canned_responses import canned_response_for
from app.ai.fake_provider import FakeAIProvider
from app.ai.gemini_provider import GeminiProvider
from app.ai.provider import (
    AIProvider,
    AIProviderError,
    KNOWN_PROVIDERS,
    PROVIDER_FAKE,
    PROVIDER_GEMINI,
)
from app.core.config import settings


def build_provider(
    name: str | None = None,
    *,
    fake_responses: dict[str, str] | None = None,
) -> AIProvider:
    chosen = (name if name is not None else settings.ai_provider).strip().lower()
    if chosen not in KNOWN_PROVIDERS:
        raise AIProviderError(
            "Unknown AI provider: configured value is not supported"
        )
    if chosen == PROVIDER_FAKE:
        return FakeAIProvider(
            fake_responses,
            response_factory=canned_response_for if fake_responses is None else None,
        )
    if chosen == PROVIDER_GEMINI:
        return GeminiProvider()
    raise AIProviderError("Unknown AI provider: configured value is not supported")


def run_ai_completion(provider: AIProvider, prompt: str, schema_hint: str) -> str:
    response = provider.complete(prompt, schema_hint)
    return response.text