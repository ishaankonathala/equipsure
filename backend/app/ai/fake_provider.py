from app.ai.provider import AIProviderError, AIResponse, PROVIDER_FAKE


class FakeAIProvider:
    name = PROVIDER_FAKE

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = dict(responses or {})
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, schema_hint: str) -> AIResponse:
        self.calls.append((prompt, schema_hint))
        if prompt not in self.responses:
            raise AIProviderError("No canned response for this prompt")
        return AIResponse(provider=self.name, text=self.responses[prompt])