from dataclasses import dataclass


@dataclass(slots=True)
class TokenUsage:
    total_prompt_tokens: int = 0
    total_tokens: int = 0
    total_cached_tokens: int = 0
