from datetime import UTC, datetime, timedelta

import pytest

from app.schemas.buyer import ParsedIntent
from app.services.mandate_service import MandateService
from app.services.model_gateway import (
    MockModelProvider,
    ModelGateway,
    OpenAICompatibleProvider,
)


@pytest.mark.anyio
async def test_model_gateway_fallback_and_validation():
    expected = ParsedIntent(product_query="headphones", max_budget_minor=100_000)
    gateway = ModelGateway(
        [
            MockModelProvider([RuntimeError("provider down")]),
            MockModelProvider([expected.model_dump(mode="json")]),
        ]
    )
    result, trace = await gateway.parse("safe prompt without secrets", ParsedIntent)
    assert result == expected
    assert trace.status == "SUCCESS"
    assert len(gateway.traces) == 2


@pytest.mark.anyio
async def test_model_gateway_fails_closed_without_provider():
    with pytest.raises(RuntimeError, match="No model provider configured"):
        await ModelGateway([]).parse("intent", ParsedIntent)


def test_strict_schema_normalization_closes_all_objects():
    normalized = OpenAICompatibleProvider._strict_schema(
        ParsedIntent.model_json_schema()
    )
    assert normalized["additionalProperties"] is False
    assert normalized["required"] == list(normalized["properties"])


def test_mandate_hash_is_canonical_and_expiry_enforced():
    service = MandateService()
    first = {"b": 2, "a": 1}
    second = {"a": 1, "b": 2}
    assert service.hash(first) == service.hash(second)
    with pytest.raises(ValueError, match="expired"):
        service.ensure_active("ACTIVE", datetime.now(UTC) - timedelta(seconds=1), 0, 1)


def test_nonce_uniqueness():
    service = MandateService()
    assert len({service.nonce() for _ in range(100)}) == 100
