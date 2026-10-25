"""AI provider interface. Implementations must return raw text only. Callers validate output before use; the provider never updates application state."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AIResponse:
    provider: str
    text: str

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")


class AIProviderError(Exception):
    """Raised when a provider cannot produce a response. Callers must handle it."""


class AIProvider(Protocol):
    name: str

    def complete(self, prompt: str, schema_hint: str) -> AIResponse: ...


PROVIDER_FAKE = "fake"
PROVIDER_GEMINI = "gemini"
KNOWN_PROVIDERS = frozenset({PROVIDER_FAKE, PROVIDER_GEMINI})