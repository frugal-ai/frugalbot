from datetime import timedelta
from typing import Any, Literal

import httpx
from cachier import cachier
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    model_validator,
)

JsonValue = str | int | float | bool | None | list[Any] | dict[str, Any]

Modality = Literal["text", "audio", "image", "video", "pdf"]


class InterleavedConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["reasoning_content", "reasoning_details"]


class Modalities(BaseModel):
    input: list[Modality]
    output: list[Modality]


class Cost(BaseModel):
    input: float = Field(ge=0)
    output: float = Field(ge=0)
    reasoning: float | None = Field(default=None, ge=0)
    cache_read: float | None = Field(default=None, ge=0)
    cache_write: float | None = Field(default=None, ge=0)
    input_audio: float | None = Field(default=None, ge=0)
    output_audio: float | None = Field(default=None, ge=0)


class ModelCost(Cost):
    context_over_200k: Cost | None = None


class ModelLimit(BaseModel):
    context: int = Field(ge=0)
    input: int | None = Field(default=None, ge=0)
    output: int = Field(ge=0)


class ExperimentalMode(BaseModel):
    cost: Cost | None = None
    provider: dict[str, Any] | None = None


class ModelProviderInfo(BaseModel):
    npm: str | None = None
    api: str | None = None
    shape: Literal["responses", "completions"] | None = None
    body: dict[str, JsonValue] | None = None
    headers: dict[str, str] | None = None


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str = Field(min_length=1)
    family: str | None = None
    attachment: bool
    reasoning: bool
    tool_call: bool
    interleaved: bool | InterleavedConfig | None = None
    structured_output: bool | None = None
    temperature: bool | None = None
    knowledge: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}(-\d{2})?$")
    release_date: str = Field(pattern=r"^\d{4}-\d{2}(-\d{2})?$")
    last_updated: str = Field(pattern=r"^\d{4}-\d{2}(-\d{2})?$")
    modalities: Modalities
    open_weights: bool
    cost: ModelCost | None = None
    limit: ModelLimit
    status: Literal["alpha", "beta", "deprecated"] | None = None
    experimental: dict[str, dict[str, ExperimentalMode]] | None = None
    provider: ModelProviderInfo | None = None

    @model_validator(mode="after")
    def validate_reasoning_cost(self) -> Model:
        if self.reasoning is False and self.cost and self.cost.reasoning is not None:
            raise ValueError("Cannot set cost.reasoning when reasoning is false")
        return self


class Provider(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    env: list[str] = Field(min_length=1)
    npm: str = Field(min_length=1)
    api: str | None = None
    name: str = Field(min_length=1)
    doc: str = Field(min_length=1)
    models: dict[str, Model]


class ModelsRegistry(RootModel):
    root: dict[str, Provider]


class ModelsDevClient:
    def __init__(self, endpoint: str = "https://models.dev/api.json"):
        self.endpoint = endpoint

    async def fetch_raw_data(self) -> dict[str, Any]:
        """
        Retrieves the JSON index.
        Uses cachier to refresh once a day.
        next_time=True returns stale data while updating in background.
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(self.endpoint)
            response.raise_for_status()
            return response.json()

    @cachier(stale_after=timedelta(hours=4), next_time=True, backend="memory")
    async def get_registry(self) -> dict[str, Provider]:
        """Returns validated provider and model data."""
        data = await self.fetch_raw_data()
        return ModelsRegistry.model_validate(data).root

    async def get_provider(self, provider_id: str) -> Provider | None:
        registry = await self.get_registry()
        return registry.get(provider_id)

    async def get_provider_by_url(self, base_url: str) -> Provider | None:
        registry = await self.get_registry()
        for provider in registry.values():
            if provider.api == base_url:
                return provider
        return None

    async def get_model(self, provider_id: str | None, model_id: str) -> Model | None:
        """Returns the model for the specified provider. If the model is not found for the specified provider, the first matching model with any provider is returned."""
        if provider_id:
            provider = await self.get_provider(provider_id)
            if provider:
                model = provider.models.get(model_id)
                if model:
                    return model
        registry = await self.get_registry()
        for p in registry.values():
            if model_id in p.models:
                return p.models[model_id]
        return None
