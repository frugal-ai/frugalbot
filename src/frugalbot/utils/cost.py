from typing import Any

from frugalbot.utils.models_dev import Model, ModelCost, ModelsDevClient
from frugalbot.utils.openrouter import OpenRouterClient


class ConversationCostCalculator:
    def __init__(self, models_dev_client: ModelsDevClient, openrouter_client: OpenRouterClient):
        self.models_dev_client = models_dev_client
        self.openrouter_client = openrouter_client

    def _calculate_chunk_cost(self, usage: dict[str, Any], cost_config: ModelCost) -> float:
        """
        Calculates cost for a single usage object based on models.dev pricing.
        Prices are typically per 1,000,000 tokens.
        """
        # Extract Token Counts
        prompt_total = usage.get("prompt_tokens", 0) or 0
        completion_total = usage.get("completion_tokens", 0) or 0

        prompt_details = usage.get("prompt_tokens_details", {})
        cached_tokens = prompt_details.get("cached_tokens", 0) or 0
        input_tokens = prompt_total - cached_tokens

        completion_details = usage.get("completion_tokens_details", {})
        reasoning_tokens = completion_details.get("reasoning_tokens", 0) or 0
        # Non-reasoning output tokens
        output_tokens = completion_total - reasoning_tokens

        # Apply Pricing Logic
        total = 0.0

        # 1. Input Cost
        total += (input_tokens / 1_000_000) * cost_config.input

        # 2. Cache Read Cost (fallback to standard input if not specified)
        cache_price = cost_config.cache_read if cost_config.cache_read is not None else cost_config.input
        total += (cached_tokens / 1_000_000) * cache_price

        # 3. Reasoning Cost (fallback to standard output if not specified)
        reasoning_price = cost_config.reasoning if cost_config.reasoning is not None else cost_config.output
        total += (reasoning_tokens / 1_000_000) * reasoning_price

        # 4. Standard Output Cost
        total += (output_tokens / 1_000_000) * cost_config.output

        return total

    async def calculate_total_cost(self, events: list[dict[str, Any]], forced_provider: str | None = None, forced_model: str | None = None) -> float:
        """
        Sums the cost of all 'completion' type events in the conversation.
        """
        total_conversation_cost = 0.0

        # Cache for models found during the loop to avoid redundant registry lookups
        model_cache: dict[str, Model | None] = {}

        for event in events:
            if event.get("type") != "completion":
                continue

            data = event.get("data", {})
            model_id = forced_model or data.get("model")
            provider = forced_provider or event.get("provider")
            usage = data.get("usage")

            if not model_id or not usage:
                continue

            if "cost" in usage:
                total_conversation_cost += usage["cost"]
                continue

            if model_id not in model_cache:
                model_cache[model_id] = await self.models_dev_client.get_model(provider, model_id)

            model_info = model_cache[model_id]
            model_cost = None

            if model_info and model_info.cost:
                model_cost = model_info.cost
            elif provider == "openrouter":
                openrouter_model_info = await self.openrouter_client.get_model(model_id)
                if openrouter_model_info:
                    model_cost = ModelCost(
                        input=openrouter_model_info.pricing.prompt * 1_000_000,
                        output=openrouter_model_info.pricing.completion * 1_000_000,
                        cache_read=(openrouter_model_info.pricing.input_cache_read * 1_000_000 if openrouter_model_info.pricing.input_cache_read else openrouter_model_info.pricing.prompt * 1_000_000),
                    )

            if model_cost:
                total_conversation_cost += self._calculate_chunk_cost(usage, model_cost)

        return total_conversation_cost
