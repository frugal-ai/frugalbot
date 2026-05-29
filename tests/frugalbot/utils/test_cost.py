from unittest.mock import AsyncMock, MagicMock

import pytest

from frugalbot.utils.cost import ConversationCostCalculator
from frugalbot.utils.models_dev import Model, ModelCost
from frugalbot.utils.openrouter import OpenRouterModel, OpenRouterPricing

# --- Helpers & Factories ---


def _make_usage(
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
    reasoning_tokens: int = 0,
    cost: float | None = None,
) -> dict:
    """Build a usage dict matching the shape expected by _calculate_chunk_cost."""
    usage: dict = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "prompt_tokens_details": {"cached_tokens": cached_tokens},
        "completion_tokens_details": {"reasoning_tokens": reasoning_tokens},
    }
    if cost is not None:
        usage["cost"] = cost
    return usage


def _make_cost(
    input_price: float = 1.0,
    output_price: float = 2.0,
    cache_read: float | None = None,
    reasoning: float | None = None,
) -> ModelCost:
    return ModelCost(
        input=input_price,
        output=output_price,
        cache_read=cache_read,
        reasoning=reasoning,
    )


def _make_completion_event(
    model: str = "gpt-4",
    provider: str = "openai",
    usage: dict | None = None,
) -> dict:
    """Build a completion-type event dict."""
    return {
        "type": "completion",
        "provider": provider,
        "data": {
            "model": model,
            "usage": usage or _make_usage(),
        },
    }


def _make_openrouter_model(
    model_id: str = "openai/gpt-4",
    prompt_price: float = 1e-6,
    completion_price: float = 2e-6,
    input_cache_read: float | None = None,
) -> OpenRouterModel:
    """Build a minimal OpenRouterModel for stubbing."""
    pricing = OpenRouterPricing(
        prompt=prompt_price,
        completion=completion_price,
        input_cache_read=input_cache_read,
    )
    # We only need the pricing-relevant fields; the rest can be MagicMock.
    mock_model = MagicMock(spec=OpenRouterModel)
    mock_model.id = model_id
    mock_model.pricing = pricing
    return mock_model  # type: ignore[return-value]


@pytest.fixture
def mock_models_dev_client():
    client = MagicMock()
    client.get_model = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_openrouter_client():
    client = MagicMock()
    client.get_model = AsyncMock(return_value=None)
    return client


@pytest.fixture
def calculator(mock_models_dev_client, mock_openrouter_client):
    return ConversationCostCalculator(mock_models_dev_client, mock_openrouter_client)


# --- Tests for _calculate_chunk_cost ---


class TestCalculateChunkCost:
    def test_basic_input_and_output_tokens_calculates_cost(self, calculator):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=500_000)
        cost_config = _make_cost(input_price=1.0, output_price=2.0)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        assert result == 2.0  # (1.0 * 1.0) + (0.5 * 2.0)

    def test_with_cached_tokens_uses_cache_read_price(self, calculator):
        # Given
        usage = _make_usage(
            prompt_tokens=1_000_000,
            completion_tokens=0,
            cached_tokens=800_000,
        )
        cost_config = _make_cost(input_price=1.0, cache_read=0.25)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        # 200k input tokens at $1/M + 800k cached at $0.25/M
        assert result == 0.4  # 0.2 + 0.2

    def test_with_cached_tokens_falls_back_to_input_price(self, calculator):
        # Given
        usage = _make_usage(
            prompt_tokens=1_000_000,
            completion_tokens=0,
            cached_tokens=500_000,
        )
        cost_config = _make_cost(input_price=2.0, cache_read=None)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        # All 1M tokens priced at input rate since cache_read is None
        assert result == 2.0

    def test_with_reasoning_tokens_uses_reasoning_price(self, calculator):
        # Given
        usage = _make_usage(
            prompt_tokens=0,
            completion_tokens=1_000_000,
            reasoning_tokens=300_000,
        )
        cost_config = _make_cost(output_price=2.0, reasoning=4.0)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        # 700k output at $2/M + 300k reasoning at $4/M
        assert result == pytest.approx(2.6)  # 1.4 + 1.2

    def test_with_reasoning_tokens_falls_back_to_output_price(self, calculator):
        # Given
        usage = _make_usage(
            prompt_tokens=0,
            completion_tokens=1_000_000,
            reasoning_tokens=600_000,
        )
        cost_config = _make_cost(output_price=3.0, reasoning=None)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        # All 1M completion tokens priced at output rate
        assert result == 3.0

    def test_with_all_token_types_calculates_combined_cost(self, calculator):
        # Given
        usage = _make_usage(
            prompt_tokens=2_000_000,
            completion_tokens=1_000_000,
            cached_tokens=1_000_000,
            reasoning_tokens=200_000,
        )
        cost_config = _make_cost(input_price=1.0, output_price=3.0, cache_read=0.1, reasoning=5.0)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        # 1M input at $1/M = 1.0
        # 1M cached at $0.1/M = 0.1
        # 0.8M output at $3/M = 2.4
        # 0.2M reasoning at $5/M = 1.0
        assert result == 4.5

    def test_zero_tokens_returns_zero_cost(self, calculator):
        # Given
        usage = _make_usage(prompt_tokens=0, completion_tokens=0)
        cost_config = _make_cost()

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        assert result == 0.0

    def test_missing_token_details_treats_as_zero(self, calculator):
        # Given
        usage = {
            "prompt_tokens": 1_000_000,
            "completion_tokens": 500_000,
        }
        cost_config = _make_cost(input_price=1.0, output_price=2.0)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        assert result == 2.0  # same as basic test

    def test_none_token_counts_treated_as_zero(self, calculator):
        # Given
        usage = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "prompt_tokens_details": {"cached_tokens": None},
            "completion_tokens_details": {"reasoning_tokens": None},
        }
        cost_config = _make_cost(input_price=1.0, output_price=2.0)

        # When
        result = calculator._calculate_chunk_cost(usage, cost_config)

        # Then
        assert result == 0.0


# --- Tests for calculate_total_cost ---


class TestCalculateTotalCost:
    async def test_single_completion_event_returns_correct_cost(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=500_000)
        events = [_make_completion_event(model="gpt-4", usage=usage)]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 2.0

    async def test_multiple_completion_events_sums_costs(self, calculator, mock_models_dev_client):
        # Given
        usage1 = _make_usage(prompt_tokens=1_000_000, completion_tokens=0)
        usage2 = _make_usage(prompt_tokens=0, completion_tokens=1_000_000)
        events = [
            _make_completion_event(model="gpt-4", usage=usage1),
            _make_completion_event(model="gpt-4", usage=usage2),
        ]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 3.0  # 1.0 + 2.0

    async def test_non_completion_events_are_ignored(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=0)
        completion_event = _make_completion_event(model="gpt-4", usage=usage)
        tool_event = {"type": "tool_call", "data": {"model": "gpt-4", "usage": usage}}
        message_event = {"type": "message", "data": {"model": "gpt-4", "usage": usage}}
        events = [completion_event, tool_event, message_event]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 1.0

    async def test_empty_events_returns_zero(self, calculator):
        # Given
        events: list[dict] = []

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 0.0

    async def test_usage_with_cost_field_uses_direct_value(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, cost=5.50)
        events = [_make_completion_event(model="gpt-4", usage=usage)]

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 5.50
        mock_models_dev_client.get_model.assert_not_called()

    async def test_missing_model_id_skips_event(self, calculator, mock_models_dev_client):
        # Given
        event = {
            "type": "completion",
            "provider": "openai",
            "data": {"usage": _make_usage(prompt_tokens=1_000_000)},
        }
        events = [event]

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 0.0
        mock_models_dev_client.get_model.assert_not_called()

    async def test_missing_usage_skips_event(self, calculator, mock_models_dev_client):
        # Given
        event = {
            "type": "completion",
            "provider": "openai",
            "data": {"model": "gpt-4"},
        }
        events = [event]

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 0.0
        mock_models_dev_client.get_model.assert_not_called()

    async def test_forced_provider_overrides_event_provider(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=0)
        events = [_make_completion_event(model="gpt-4", provider="openai", usage=usage)]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        await calculator.calculate_total_cost(events, forced_provider="anthropic")

        # Then
        mock_models_dev_client.get_model.assert_called_once_with("anthropic", "gpt-4")

    async def test_forced_model_overrides_event_model(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=0)
        events = [_make_completion_event(model="gpt-4", provider="openai", usage=usage)]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        await calculator.calculate_total_cost(events, forced_model="claude-3")

        # Then
        mock_models_dev_client.get_model.assert_called_once_with("openai", "claude-3")

    async def test_model_not_found_in_models_dev_falls_back_to_openrouter(self, calculator, mock_models_dev_client, mock_openrouter_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=500_000)
        events = [_make_completion_event(model="openai/gpt-4", provider="openrouter", usage=usage)]
        mock_models_dev_client.get_model = AsyncMock(return_value=None)
        mock_openrouter_client.get_model = AsyncMock(
            return_value=_make_openrouter_model(
                prompt_price=1e-6,
                completion_price=2e-6,
                input_cache_read=0.5e-6,
            )
        )

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        # OpenRouter prices are per-token, multiplied by 1_000_000 → $1/M input, $2/M output
        assert result == 2.0

    async def test_openrouter_fallback_uses_cache_read_price(self, calculator, mock_models_dev_client, mock_openrouter_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=0, cached_tokens=800_000)
        events = [_make_completion_event(model="openai/gpt-4", provider="openrouter", usage=usage)]
        mock_models_dev_client.get_model = AsyncMock(return_value=None)
        mock_openrouter_client.get_model = AsyncMock(
            return_value=_make_openrouter_model(
                prompt_price=1e-6,
                completion_price=2e-6,
                input_cache_read=0.1e-6,
            )
        )

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        # 200k input at $1/M + 800k cached at $0.1/M = 0.2 + 0.08
        assert result == 0.28

    async def test_openrouter_fallback_without_cache_read_falls_back_to_prompt(self, calculator, mock_models_dev_client, mock_openrouter_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000, completion_tokens=0, cached_tokens=500_000)
        events = [_make_completion_event(model="openai/gpt-4", provider="openrouter", usage=usage)]
        mock_models_dev_client.get_model = AsyncMock(return_value=None)
        mock_openrouter_client.get_model = AsyncMock(
            return_value=_make_openrouter_model(
                prompt_price=2e-6,
                completion_price=3e-6,
                input_cache_read=None,
            )
        )

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        # cache_read falls back to prompt price ($2/M), so:
        # 500k input at $2/M = 1.0 + 500k cached at $2/M = 1.0 → total 2.0
        assert result == 2.0

    async def test_openrouter_returns_none_skips_event(self, calculator, mock_models_dev_client, mock_openrouter_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000)
        events = [_make_completion_event(model="unknown/model", provider="openrouter", usage=usage)]
        mock_models_dev_client.get_model = AsyncMock(return_value=None)
        mock_openrouter_client.get_model = AsyncMock(return_value=None)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 0.0

    async def test_model_cost_none_and_not_openrouter_skips_event(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=1_000_000)
        events = [_make_completion_event(model="gpt-4", provider="openai", usage=usage)]
        # Model found but has no cost config
        mock_model = MagicMock(spec=Model)
        mock_model.cost = None
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 0.0

    async def test_model_cache_avoids_redundant_lookups(self, calculator, mock_models_dev_client):
        # Given
        usage = _make_usage(prompt_tokens=500_000, completion_tokens=0)
        events = [
            _make_completion_event(model="gpt-4", usage=usage),
            _make_completion_event(model="gpt-4", usage=usage),
            _make_completion_event(model="gpt-4", usage=usage),
        ]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=2.0, output_price=4.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        await calculator.calculate_total_cost(events)

        # Then
        mock_models_dev_client.get_model.assert_called_once_with("openai", "gpt-4")

    async def test_mixed_cost_field_and_calculated_costs(self, calculator, mock_models_dev_client):
        # Given
        usage_with_cost = _make_usage(cost=3.0)
        usage_calculated = _make_usage(prompt_tokens=1_000_000, completion_tokens=0)
        events = [
            _make_completion_event(model="gpt-4", usage=usage_with_cost),
            _make_completion_event(model="gpt-4", usage=usage_calculated),
        ]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == 4.0  # 3.0 (direct) + 1.0 (calculated)

    @pytest.mark.parametrize(
        "prompt,completion,cached,reasoning,expected",
        [
            (0, 0, 0, 0, 0.0),
            (1_000_000, 0, 0, 0, 1.0),
            (0, 1_000_000, 0, 0, 2.0),
            (500_000, 500_000, 0, 0, 1.5),
            (1_000_000, 1_000_000, 500_000, 500_000, 3.25),
        ],
    )
    async def test_various_token_combinations_produce_correct_cost(
        self,
        calculator,
        mock_models_dev_client,
        prompt,
        completion,
        cached,
        reasoning,
        expected,
    ):
        # Given
        usage = _make_usage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            cached_tokens=cached,
            reasoning_tokens=reasoning,
        )
        events = [_make_completion_event(model="gpt-4", usage=usage)]
        mock_model = MagicMock(spec=Model)
        mock_model.cost = _make_cost(input_price=1.0, output_price=2.0, cache_read=0.5, reasoning=3.0)
        mock_models_dev_client.get_model = AsyncMock(return_value=mock_model)

        # When
        result = await calculator.calculate_total_cost(events)

        # Then
        assert result == expected
