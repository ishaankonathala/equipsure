from collections.abc import Callable

from app.ai.provider import AIProviderError, AIResponse, PROVIDER_FAKE


class FakeAIProvider:
    name = PROVIDER_FAKE

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        response_factory: Callable[[str], str | None] | None = None,
    ) -> None:
        self.responses = dict(responses or {})
        self.response_factory = response_factory
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, schema_hint: str) -> AIResponse:
        self.calls.append((prompt, schema_hint))
        if prompt in self.responses:
            return AIResponse(provider=self.name, text=self.responses[prompt])
        if self.response_factory is not None:
            text = self.response_factory(prompt)
            if text is not None:
                return AIResponse(provider=self.name, text=text)
        raise AIProviderError("No canned response for this prompt")