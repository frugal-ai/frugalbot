"""Tests for src/frugalbot/utils/openrouter.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from cachier import disable_caching, enable_caching
from pydantic import ValidationError

from frugalbot.utils.openrouter import (
    OpenRouterArchitecture,
    OpenRouterClient,
    OpenRouterModel,
    OpenRouterPricing,
    OpenRouterResponse,
    OpenRouterTopProvider,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="session")
def disable_cachier_globally():
    """Disable cachier for all tests to avoid populating the cache with mock data."""
    disable_caching()
    yield
    enable_caching()


def _make_raw_model(
    model_id: str = "anthropic/claude-3-opus",
    name: str = "Claude 3 Opus",
    description: str = "A powerful model",
    context_length: int = 200_000,
    modality: str = "text->text",
    prompt_price: float = 0.000015,
    completion_price: float = 0.000075,
    is_moderated: bool = True,
    supported_parameters: list[str] | None = None,
) -> dict[str, Any]:
    """Build a raw dict matching the OpenRouter model schema."""
    return {
        "id": model_id,
        "name": name,
        "description": description,
        "context_length": context_length,
        "architecture": {
            "modality": modality,
            "tokenizer": None,
            "instruct_type": None,
        },
        "pricing": {
            "prompt": prompt_price,
            "completion": completion_price,
            "request": None,
            "image": None,
            "input_cache_read": None,
        },
        "top_provider": {
            "context_length": context_length,
            "max_completion_tokens": 4096,
            "is_moderated": is_moderated,
        },
        "supported_parameters": supported_parameters or [],
    }


def _mock_httpx_client(json_data: dict[str, Any]) -> AsyncMock:
    """Build a mocked httpx.AsyncClient that returns the given JSON data."""
    mock_response = MagicMock()
    mock_response.json.return_value = json_data
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    return mock_client


# ---------------------------------------------------------------------------
# OpenRouterClient.__init__
# ---------------------------------------------------------------------------


class TestOpenRouterClientInit:
    def test_init_with_default_endpoint_sets_default_url(self) -> None:
        # Given
        # No inputs needed

        # When
        client = OpenRouterClient()

        # Then
        assert client.endpoint == "https://openrouter.ai/api/v1/models"

    def test_init_with_custom_endpoint_sets_custom_url(self) -> None:
        # Given
        custom_url = "https://custom.example.com/models"

        # When
        client = OpenRouterClient(endpoint=custom_url)

        # Then
        assert client.endpoint == custom_url


# ---------------------------------------------------------------------------
# OpenRouterClient.fetch_raw_data
# ---------------------------------------------------------------------------


class TestOpenRouterClientFetchRawData:
    async def test_fetch_raw_data_with_success_response_returns_json(self) -> None:
        # Given
        expected_data: dict[str, Any] = {"data": [_make_raw_model()]}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(expected_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            result = await client.fetch_raw_data()

        # Then
        assert result == expected_data

    async def test_fetch_raw_data_with_error_response_raises_http_error(self) -> None:
        # Given
        client = OpenRouterClient()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock()))

        mock_async_client = AsyncMock()
        mock_async_client.get = AsyncMock(return_value=mock_response)
        mock_async_client.__aenter__ = AsyncMock(return_value=mock_async_client)
        mock_async_client.__aexit__ = AsyncMock(return_value=None)

        # When & Then
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            with pytest.raises(httpx.HTTPStatusError):
                await client.fetch_raw_data()

    async def test_fetch_raw_data_calls_correct_endpoint(self) -> None:
        # Given
        custom_endpoint = "https://custom.example.com/models"
        client = OpenRouterClient(endpoint=custom_endpoint)
        mock_async_client = _mock_httpx_client({"data": []})

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            await client.fetch_raw_data()

        # Then
        mock_async_client.get.assert_called_once_with(custom_endpoint)


# ---------------------------------------------------------------------------
# OpenRouterClient.get_models
# ---------------------------------------------------------------------------


class TestOpenRouterClientGetModels:
    async def test_get_models_with_valid_data_returns_parsed_models(self) -> None:
        # Given
        raw_data = {"data": [_make_raw_model(model_id="anthropic/claude-3-opus", name="Claude 3 Opus")]}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models()

        # Then
        assert len(models) == 1
        assert models[0].id == "anthropic/claude-3-opus"
        assert models[0].name == "Claude 3 Opus"

    async def test_get_models_with_empty_data_returns_empty_list(self) -> None:
        # Given
        raw_data: dict[str, Any] = {"data": []}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models()

        # Then
        assert models == []

    async def test_get_models_with_multiple_models_returns_all_parsed(self) -> None:
        # Given
        raw_data = {
            "data": [
                _make_raw_model(model_id="anthropic/claude-3-opus", name="Claude 3 Opus"),
                _make_raw_model(model_id="openai/gpt-4", name="GPT-4"),
                _make_raw_model(model_id="google/gemini-pro", name="Gemini Pro"),
            ]
        }
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models()

        # Then
        assert len(models) == 3
        assert models[0].id == "anthropic/claude-3-opus"
        assert models[1].id == "openai/gpt-4"
        assert models[2].id == "google/gemini-pro"

    async def test_get_models_with_invalid_data_raises_validation_error(self) -> None:
        # Given
        raw_data = {"data": "not a list"}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When & Then
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            with pytest.raises(ValidationError):
                await client.get_models()

    async def test_get_models_with_missing_required_field_raises_validation_error(self) -> None:
        # Given
        raw_data = {"data": [{"id": "test/model"}]}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When & Then
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            with pytest.raises(ValidationError):
                await client.get_models()


# ---------------------------------------------------------------------------
# OpenRouterClient.get_model
# ---------------------------------------------------------------------------


class TestOpenRouterClientGetModel:
    async def test_get_model_with_existing_id_returns_model(self) -> None:
        # Given
        raw_data = {
            "data": [
                _make_raw_model(model_id="anthropic/claude-3-opus", name="Claude 3 Opus"),
                _make_raw_model(model_id="openai/gpt-4", name="GPT-4"),
            ]
        }
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            model = await client.get_model("openai/gpt-4")

        # Then
        assert model is not None
        assert model.id == "openai/gpt-4"
        assert model.name == "GPT-4"

    async def test_get_model_with_nonexistent_id_returns_none(self) -> None:
        # Given
        raw_data = {"data": [_make_raw_model(model_id="anthropic/claude-3-opus")]}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            model = await client.get_model("nonexistent/model")

        # Then
        assert model is None

    async def test_get_model_with_empty_model_list_returns_none(self) -> None:
        # Given
        raw_data: dict[str, Any] = {"data": []}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            model = await client.get_model("any/model")

        # Then
        assert model is None


# ---------------------------------------------------------------------------
# OpenRouterClient.get_models_by_provider
# ---------------------------------------------------------------------------


class TestOpenRouterClientGetModelsByProvider:
    async def test_get_models_by_provider_with_matching_prefix_returns_filtered_models(self) -> None:
        # Given
        raw_data = {
            "data": [
                _make_raw_model(model_id="anthropic/claude-3-opus", name="Claude 3 Opus"),
                _make_raw_model(model_id="anthropic/claude-3-sonnet", name="Claude 3 Sonnet"),
                _make_raw_model(model_id="openai/gpt-4", name="GPT-4"),
            ]
        }
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models_by_provider("anthropic")

        # Then
        assert len(models) == 2
        assert models[0].id == "anthropic/claude-3-opus"
        assert models[1].id == "anthropic/claude-3-sonnet"

    async def test_get_models_by_provider_with_no_matching_prefix_returns_empty_list(self) -> None:
        # Given
        raw_data = {
            "data": [
                _make_raw_model(model_id="anthropic/claude-3-opus"),
                _make_raw_model(model_id="openai/gpt-4"),
            ]
        }
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models_by_provider("google")

        # Then
        assert models == []

    async def test_get_models_by_provider_with_partial_match_excludes_similar_prefix(self) -> None:
        # Given
        raw_data = {
            "data": [
                _make_raw_model(model_id="openai/gpt-4", name="GPT-4"),
                _make_raw_model(model_id="openrouter/test", name="Test"),
            ]
        }
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models_by_provider("open")

        # Then
        assert models == []

    async def test_get_models_by_provider_with_empty_model_list_returns_empty_list(self) -> None:
        # Given
        raw_data: dict[str, Any] = {"data": []}
        client = OpenRouterClient()
        mock_async_client = _mock_httpx_client(raw_data)

        # When
        with patch("httpx.AsyncClient", return_value=mock_async_client):
            models = await client.get_models_by_provider("anthropic")

        # Then
        assert models == []


# ---------------------------------------------------------------------------
# Pydantic model tests
# ---------------------------------------------------------------------------


class TestOpenRouterPricing:
    def test_pricing_with_all_fields_parses_correctly(self) -> None:
        # Given
        data = {
            "prompt": 0.000015,
            "completion": 0.000075,
            "request": 0.001,
            "image": 0.002,
            "input_cache_read": 0.000005,
        }

        # When
        pricing = OpenRouterPricing(**data)

        # Then
        assert pricing.prompt == 0.000015
        assert pricing.completion == 0.000075
        assert pricing.request == 0.001
        assert pricing.image == 0.002
        assert pricing.input_cache_read == 0.000005

    def test_pricing_with_only_required_fields_parses_correctly(self) -> None:
        # Given
        data = {"prompt": 0.01, "completion": 0.03}

        # When
        pricing = OpenRouterPricing(**data)

        # Then
        assert pricing.prompt == 0.01
        assert pricing.completion == 0.03
        assert pricing.request is None
        assert pricing.image is None
        assert pricing.input_cache_read is None


class TestOpenRouterArchitecture:
    def test_architecture_with_all_fields_parses_correctly(self) -> None:
        # Given
        data = {"modality": "text+image->text", "tokenizer": "cl100k_base", "instruct_type": "chatml"}

        # When
        arch = OpenRouterArchitecture(**data)

        # Then
        assert arch.modality == "text+image->text"
        assert arch.tokenizer == "cl100k_base"
        assert arch.instruct_type == "chatml"

    def test_architecture_with_only_modality_parses_correctly(self) -> None:
        # Given
        data = {"modality": "text->text"}

        # When
        arch = OpenRouterArchitecture(**data)

        # Then
        assert arch.modality == "text->text"
        assert arch.tokenizer is None
        assert arch.instruct_type is None


class TestOpenRouterTopProvider:
    def test_top_provider_with_all_fields_parses_correctly(self) -> None:
        # Given
        data = {"context_length": 200_000, "max_completion_tokens": 8192, "is_moderated": True}

        # When
        provider = OpenRouterTopProvider(**data)

        # Then
        assert provider.context_length == 200_000
        assert provider.max_completion_tokens == 8192
        assert provider.is_moderated is True

    def test_top_provider_with_only_is_moderated_parses_correctly(self) -> None:
        # Given
        data = {"is_moderated": False}

        # When
        provider = OpenRouterTopProvider(**data)

        # Then
        assert provider.is_moderated is False
        assert provider.context_length is None
        assert provider.max_completion_tokens is None


class TestOpenRouterModel:
    def test_model_with_valid_data_parses_correctly(self) -> None:
        # Given
        data = _make_raw_model()

        # When
        model = OpenRouterModel(**data)

        # Then
        assert model.id == "anthropic/claude-3-opus"
        assert model.name == "Claude 3 Opus"
        assert model.description == "A powerful model"
        assert model.context_length == 200_000
        assert model.architecture.modality == "text->text"
        assert model.pricing.prompt == 0.000015
        assert model.pricing.completion == 0.000075
        assert model.top_provider.is_moderated is True
        assert model.supported_parameters == []


class TestOpenRouterResponse:
    def test_response_with_valid_data_parses_correctly(self) -> None:
        # Given
        data: dict[str, Any] = {"data": [_make_raw_model(), _make_raw_model(model_id="openai/gpt-4", name="GPT-4")]}

        # When
        response = OpenRouterResponse(**data)

        # Then
        assert len(response.data) == 2
        assert response.data[0].id == "anthropic/claude-3-opus"
        assert response.data[1].id == "openai/gpt-4"

    def test_response_with_empty_data_parses_correctly(self) -> None:
        # Given
        data: dict[str, Any] = {"data": []}

        # When
        response = OpenRouterResponse(**data)

        # Then
        assert response.data == []
