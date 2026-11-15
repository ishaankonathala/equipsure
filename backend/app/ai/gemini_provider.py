from app.ai.provider import AIProviderError, AIResponse, PROVIDER_GEMINI
from app.core.config import settings


class GeminiProvider:
    name = PROVIDER_GEMINI

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        key = api_key if api_key is not None else settings.gemini_api_key
        if not key or not key.strip():
            raise AIProviderError("GEMINI_API_KEY is not configured")

        from google import genai

        self._model = model or settings.gemini_model
        self._client = genai.Client(api_key=key)

    def complete(self, prompt: str, schema_hint: str) -> AIResponse:
        request_text = schema_hint + "\n\n" + prompt
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=request_text,
                config={"response_mime_type": "application/json"},
            )
        except Exception:
            raise AIProviderError("Gemini request failed") from None

        text = response.text or ""
        if not text.strip():
            raise AIProviderError("Gemini returned an empty response")
        return AIResponse(provider=self.name, text=text)