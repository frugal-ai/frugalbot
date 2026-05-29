from typing import Any, Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cachier import disable_caching, enable_caching
from pydantic import ValidationError

from frugalbot.utils.models_dev import (
    Cost,
    InterleavedConfig,
    Modalities,
    Model,
    ModelCost,
    ModelLimit,
    ModelsDevClient,
    Provider,
)

# --- Helpers & Factories ---


@pytest.fixture(autouse=True, scope="session")
def disable_cachier_globally():
    disable_caching()
    yield
    enable_caching()


def create_model(**kwargs: Any) -> Model:
    defaults: dict[str, Any] = {
        "id": "gpt-4",
        "name": "GPT-4",
        "attachment": False,
        "reasoning": False,
        "tool_call": True,
        "interleaved": None,
        "structured_output": None,
        "temperature": None,
        "knowledge": None,
        "release_date": "2023-03",
        "last_updated": "2023-03",
        "modalities": Modalities(input=["text"], output=["text"]),
        "open_weights": False,
        "cost": None,
        "limit": ModelLimit(context=4096, output=2048),
        "status": None,
        "experimental": None,
        "provider": None,
    }
    return Model(**{**defaults, **kwargs})


def create_provider(models: dict[str, Any] | None = None, **kwargs: Any) -> Provider:
    defaults: dict[str, Any] = {
        "id": "openai",
        "env": ["OPENAI_API_KEY"],
        "npm": "@ai-sdk/openai",
        "api": None,
        "name": "OpenAI",
        "doc": "https://platform.openai.com",
        "models": models or {"gpt-4": create_model()},
    }
    return Provider(**{**defaults, **kwargs})


def _create_mock_http_response(data: dict[str, Any]) -> MagicMock:
    """Create a mock HTTP response object that returns *data* from ``.json()``."""

    mock_response = MagicMock()
    mock_response.json.return_value = data
    return mock_response


@pytest.fixture
def sample_model() -> Model:
    return create_model()


@pytest.fixture
def sample_provider(sample_model: Model) -> Provider:
    return create_provider(models={"gpt-4": sample_model})


# --- Tests ---


class TestInterleavedConfig:
    @pytest.mark.parametrize("field", ["reasoning_content", "reasoning_details"])
    def test_interleaved_config_with_valid_field_sets_value(self, field: Literal["reasoning_content", "reasoning_details"]) -> None:
        # Given
        # (no setup needed)

        # When
        config = InterleavedConfig(field=field)

        # Then
        assert config.field == field

    def test_interleaved_config_with_invalid_field_raises_validation_error(self) -> None:
        # Given
        invalid_data = {"field": "invalid_field"}

        # When / Then
        with pytest.raises(ValidationError):
            InterleavedConfig.model_validate(invalid_data)


class TestModalities:
    def test_modalities_with_valid_input_and_output_sets_values(self) -> None:
        # Given
        # (no setup needed)

        # When
        modalities = Modalities(input=["text", "image"], output=["text", "audio"])

        # Then
        assert "image" in modalities.input
        assert "audio" in modalities.output

    def test_modalities_with_invalid_input_raises_validation_error(self) -> None:
        # Given
        invalid_data = {"input": ["invalid"], "output": ["text"]}

        # When / Then
        with pytest.raises(ValidationError):
            Modalities.model_validate(invalid_data)


class TestCost:
    def test_cost_with_all_fields_sets_values(self) -> None:
        # Given
        # (no setup needed)

        # When
        cost = Cost(input=1.0, output=2.0, reasoning=0.5, cache_read=0.1)

        # Then
        assert cost.input == 1.0
        assert cost.reasoning == 0.5

    @pytest.mark.parametrize("field", ["input", "output", "reasoning"])
    def test_cost_with_negative_value_raises_validation_error(self, field: str) -> None:
        # Given
        cost_data = {"input": 1.0, "output": 1.0, field: -1.0}

        # When / Then
        with pytest.raises(ValidationError):
            Cost(**cost_data)


class TestModelLimit:
    def test_model_limit_with_all_fields_sets_values(self) -> None:
        # Given
        # (no setup needed)

        # When
        limit = ModelLimit(context=4096, input=2048, output=1024)

        # Then
        assert limit.context == 4096
        assert limit.input == 2048

    def test_model_limit_with_negative_context_raises_validation_error(self) -> None:
        # Given
        # (no setup needed)

        # When / Then
        with pytest.raises(ValidationError):
            ModelLimit(context=-1, output=2048)


class TestModel:
    def test_model_with_valid_data_sets_id(self) -> None:
        # Given
        # (no setup needed)

        # When
        model = create_model()

        # Then
        assert model.id == "gpt-4"

    def test_model_with_interleaved_config_sets_interleaved(self) -> None:
        # Given
        interleaved = InterleavedConfig(field="reasoning_content")

        # When
        model = create_model(interleaved=interleaved)

        # Then
        assert isinstance(model.interleaved, InterleavedConfig)

    def test_model_with_reasoning_disabled_and_reasoning_cost_raises_error(self) -> None:
        # Given
        cost = ModelCost(input=1.0, output=2.0, reasoning=0.5)

        # When / Then
        with pytest.raises(ValueError, match=r"Cannot set cost.reasoning"):
            create_model(reasoning=False, cost=cost)

    def test_model_with_reasoning_enabled_and_reasoning_cost_sets_cost(self) -> None:
        # Given
        cost = ModelCost(input=1.0, output=2.0, reasoning=0.5)

        # When
        model = create_model(reasoning=True, cost=cost)

        # Then
        assert model.cost is not None
        assert model.cost.reasoning == 0.5

    def test_model_with_extra_field_raises_validation_error(self) -> None:
        # Given
        model_data = {**create_model().model_dump(), "extra": "forbidden"}

        # When / Then
        with pytest.raises(ValidationError):
            Model.model_validate(model_data)


class TestProvider:
    @pytest.mark.parametrize(
        "npm,api",
        [
            ("@ai-sdk/openai", None),
            ("@ai-sdk/openai-compatible", "https://custom.com/api"),
            ("@ai-sdk/anthropic", "https://api.anthropic.com"),
            ("@ai-sdk/anthropic", None),
        ],
    )
    def test_provider_with_valid_npm_and_api_sets_fields(self, npm: str, api: str | None) -> None:
        # Given
        # (no setup needed)

        # When
        provider = create_provider(npm=npm, api=api)

        # Then
        assert provider.npm == npm
        assert provider.api == api

    def test_provider_with_empty_env_raises_validation_error(self) -> None:
        # Given
        # (no setup needed)

        # When / Then
        with pytest.raises(ValidationError):
            create_provider(env=[])


class TestModelsDevClient:
    @pytest.fixture
    def client(self) -> ModelsDevClient:
        return ModelsDevClient()

    @pytest.fixture
    def mock_registry_data(self, sample_provider: Provider) -> dict[str, Provider]:
        return {"openai": sample_provider}

    def test_models_dev_client_with_default_endpoint_sets_url(self) -> None:
        # Given
        # (no setup needed)

        # When
        client = ModelsDevClient()

        # Then
        assert client.endpoint == "https://models.dev/api.json"

    def test_models_dev_client_with_custom_endpoint_sets_url(self) -> None:
        # Given
        custom_url = "https://custom.com"

        # When
        client = ModelsDevClient(endpoint=custom_url)

        # Then
        assert client.endpoint == custom_url

    async def test_fetch_raw_data_with_valid_endpoint_returns_json(self, client: ModelsDevClient) -> None:
        # Given
        mock_response = _create_mock_http_response({"p1": {"id": "p1"}})
        mock_http_client = AsyncMock()
        mock_http_client.get.return_value = mock_response

        # When
        with patch("frugalbot.utils.models_dev.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__ = AsyncMock(return_value=mock_http_client)
            mock_client.return_value.__aexit__ = AsyncMock(return_value=None)
            data = await client.fetch_raw_data()

        # Then
        assert data == {"p1": {"id": "p1"}}

    async def test_get_registry_with_valid_data_returns_provider_dict(self, client: ModelsDevClient, sample_model: Model) -> None:
        # Given
        raw_data = {"openai": create_provider(models={"gpt-4": sample_model.model_dump()}).model_dump()}

        # When
        with patch.object(client, "fetch_raw_data", AsyncMock(return_value=raw_data)):
            registry = await client.get_registry()

        # Then
        assert isinstance(registry["openai"], Provider)

    async def test_get_provider_with_existing_id_returns_provider(
        self,
        client: ModelsDevClient,
        mock_registry_data: dict[str, Provider],
    ) -> None:
        # Given
        # mock_registry_data provided by fixture

        # When
        with patch.object(client, "get_registry", AsyncMock(return_value=mock_registry_data)):
            provider = await client.get_provider("openai")

        # Then
        assert provider is not None
        assert provider.id == "openai"

    async def test_get_provider_with_nonexistent_id_returns_none(
        self,
        client: ModelsDevClient,
        mock_registry_data: dict[str, Provider],
    ) -> None:
        # Given
        # mock_registry_data provided by fixture

        # When
        with patch.object(client, "get_registry", AsyncMock(return_value=mock_registry_data)):
            provider = await client.get_provider("nonexistent")

        # Then
        assert provider is None

    async def test_get_model_with_valid_provider_and_model_returns_model(
        self,
        client: ModelsDevClient,
        mock_registry_data: dict[str, Provider],
    ) -> None:
        # Given
        # mock_registry_data provided by fixture

        # When
        with patch.object(client, "get_registry", AsyncMock(return_value=mock_registry_data)):
            model = await client.get_model("openai", "gpt-4")

        # Then
        assert model is not None
        assert model.id == "gpt-4"

    async def test_get_model_with_missing_provider_falls_back_to_global_search(
        self,
        client: ModelsDevClient,
        mock_registry_data: dict[str, Provider],
    ) -> None:
        # Given
        # mock_registry_data provided by fixture

        # When
        with patch.object(client, "get_registry", AsyncMock(return_value=mock_registry_data)):
            model = await client.get_model("missing", "gpt-4")

        # Then
        assert model is not None
        assert model.id == "gpt-4"

    async def test_get_model_with_nonexistent_model_returns_none(
        self,
        client: ModelsDevClient,
        mock_registry_data: dict[str, Provider],
    ) -> None:
        # Given
        # mock_registry_data provided by fixture

        # When
        with patch.object(client, "get_registry", AsyncMock(return_value=mock_registry_data)):
            model = await client.get_model("openai", "gpt-none")

        # Then
        assert model is None

    async def test_get_provider_by_url_with_matching_api_returns_provider(self, client: ModelsDevClient) -> None:
        # Given
        api_url = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        alibaba_provider = create_provider(
            id="alibaba",
            name="Alibaba",
            api=api_url,
        )

        # When
        with patch.object(
            client,
            "fetch_raw_data",
            AsyncMock(return_value={"alibaba": alibaba_provider.model_dump()}),
        ):
            provider = await client.get_provider_by_url(api_url)

        # Then
        assert provider is not None
        assert provider.name == "Alibaba"
