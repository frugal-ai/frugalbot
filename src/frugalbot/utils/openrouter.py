from datetime import timedelta
from typing import Any

import httpx
from cachier import cachier
from pydantic import BaseModel

# OpenRouter specific types
ModalityString = str  # e.g., "text->text", "text+image->text"


class OpenRouterPricing(BaseModel):
    """Prices are per 1 token in USD."""

    prompt: float
    completion: float
    request: float | None = None
    image: float | None = None
    input_cache_read: float | None = None


class OpenRouterTopProvider(BaseModel):
    context_length: int | None = None
    max_completion_tokens: int | None = None
    is_moderated: bool


class OpenRouterArchitecture(BaseModel):
    modality: ModalityString
    tokenizer: str | None = None
    instruct_type: str | None = None


class OpenRouterModel(BaseModel):
    id: str
    name: str
    description: str
    context_length: int
    architecture: OpenRouterArchitecture
    pricing: OpenRouterPricing
    top_provider: OpenRouterTopProvider
    supported_parameters: list[str]


class OpenRouterResponse(BaseModel):
    data: list[OpenRouterModel]


class OpenRouterClient:
    def __init__(self, endpoint: str = "https://openrouter.ai/api/v1/models"):
        self.endpoint = endpoint

    async def fetch_raw_data(self) -> dict[str, Any]:
        """
        Retrieves the model list from OpenRouter.
        Caches results for 1 day.
        """
        async with httpx.AsyncClient(timeout=20.0) as client:
            # OpenRouter models endpoint doesn't strictly require a key,
            # but you can add one to headers if needed for higher rate limits.
            response = await client.get(self.endpoint)
            response.raise_for_status()
            return response.json()

    @cachier(stale_after=timedelta(hours=4), next_time=True, backend="memory")
    async def get_models(self) -> list[OpenRouterModel]:
        """Returns a validated list of all available models."""
        data = await self.fetch_raw_data()
        validated = OpenRouterResponse.model_validate(data)
        return validated.data

    async def get_model(self, model_id: str) -> OpenRouterModel | None:
        """
        Retrieves a specific model by its ID (e.g., 'anthropic/claude-3-opus').
        """
        models = await self.get_models()
        return next((m for m in models if m.id == model_id), None)

    async def get_models_by_provider(self, provider_prefix: str) -> list[OpenRouterModel]:
        """
        Retrieves models for a specific provider (e.g., 'anthropic' or 'openai').
        """
        models = await self.get_models()
        return [m for m in models if m.id.startswith(f"{provider_prefix}/")]
