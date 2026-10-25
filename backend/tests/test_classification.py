import pytest

from app.ai.fake_provider import FakeAIProvider
from app.ai.provider import AIProviderError
from app.models.enums import DocumentType
from app.services.classification import (
    ClassificationError,
    build_classification_prompt,
    build_classification_schema_hint,
    classify_document,
)


def _provider_for(text, filename="a.pdf", declared_type="INVOICE", excerpt=None):
    prompt = build_classification_prompt(filename, declared_type, excerpt)
    schema_hint = build_classification_schema_hint()
    return FakeAIProvider({prompt: text})


def test_valid_type_is_returned():
    provider = _provider_for('{"document_type": "INVOICE"}')

    result = classify_document(provider, "a.pdf", "INVOICE", None)

    assert result is DocumentType.INVOICE


def test_unknown_type_is_rejected():
    provider = _provider_for('{"document_type": "DRAFT"}')

    with pytest.raises(ClassificationError, match="not a known document type"):
        classify_document(provider, "a.pdf", "INVOICE", None)


def test_non_json_is_rejected():
    provider = _provider_for("invoice")

    with pytest.raises(ClassificationError, match="not valid JSON"):
        classify_document(provider, "a.pdf", "INVOICE", None)


def test_non_object_is_rejected():
    provider = _provider_for('["INVOICE"]')

    with pytest.raises(ClassificationError, match="must be a JSON object"):
        classify_document(provider, "a.pdf", "INVOICE", None)


def test_extra_field_is_rejected():
    provider = _provider_for(
        '{"document_type": "PHOTO", "approved": true}'
    )

    with pytest.raises(ClassificationError):
        classify_document(provider, "a.pdf", "INVOICE", None)


def test_provider_error_propagates():
    provider = FakeAIProvider()

    with pytest.raises(AIProviderError) as exc_info:
        classify_document(provider, "a.pdf", "INVOICE", None)

    assert not isinstance(exc_info.value, ClassificationError)


def test_excerpt_is_truncated_in_prompt():
    prompt = build_classification_prompt("a.pdf", "INVOICE", "x" * 5000)

    assert "x" * 2000 in prompt
    assert "x" * 2001 not in prompt


def test_missing_excerpt_is_marked():
    prompt = build_classification_prompt("a.pdf", "PHOTO", None)

    assert "Text excerpt: (none)" in prompt


def test_error_does_not_echo_response():
    provider = _provider_for("secret-value not json")

    with pytest.raises(ClassificationError) as exc_info:
        classify_document(provider, "a.pdf", "INVOICE", None)

    assert "secret-value" not in str(exc_info.value)