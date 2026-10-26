from collections.abc import Callable

from app.ai.provider import AIProviderError, AIResponse, PROVIDER_FAKE


class FakeAIProvider:
    name = PROVIDER_FAKE

    def __init__(
        self,
        responses: dict[str, str] | None = None,
        *,
        response_factory: Callable[[str], dict[str, str]] | None = None,
    ) -> None:
        self.responses = dict(responses or {})
        self._response_factory = response_factory
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, schema_hint: str) -> AIResponse:
        self.calls.append((prompt, schema_hint))
        if prompt in self.responses:
            return AIResponse(provider=self.name, text=self.responses[prompt])

        if self._response_factory is not None:
            demo_response = self._response_factory(prompt).get(prompt)
            if demo_response is not None:
                return AIResponse(provider=self.name, text=demo_response)
        raise AIProviderError("No canned response for this prompt")