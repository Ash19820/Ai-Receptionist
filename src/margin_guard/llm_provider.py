from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str
    api_key: str
    base_url: str | None


_PROVIDERS = {
    "litellm-gateway": ("LLM_API_KEY", "receptionist-openai", "", "http://localhost:4000/v1"),
    "openai": ("OPENAI_API_KEY", "gpt-4.1-mini", "openai", ""),
}


def get_llm_config() -> LLMConfig:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    if provider not in _PROVIDERS:
        choices = ", ".join(_PROVIDERS)
        raise ValueError(f"Unsupported LLM_PROVIDER {provider!r}. Choose one of: {choices}.")

    key_name, default_model, _, default_base_url = _PROVIDERS[provider]
    api_key = os.getenv(key_name, "").strip()
    if not api_key:
        raise ValueError(f"Set {key_name} in your .env file to use LLM_PROVIDER={provider}.")

    base_url = os.getenv("LLM_BASE_URL", "").strip() or default_base_url or None
    return LLMConfig(
        provider=provider,
        model=os.getenv("LLM_MODEL", "").strip() or default_model,
        api_key=api_key,
        base_url=base_url,
    )


def make_agent_model():
    config = get_llm_config()
    if config.provider == "litellm-gateway":
        from agents import AsyncOpenAI, OpenAIChatCompletionsModel, set_tracing_disabled

        set_tracing_disabled(disabled=True)
        client = AsyncOpenAI(api_key=config.api_key, base_url=config.base_url)
        return OpenAIChatCompletionsModel(model=config.model, openai_client=client)
    if config.provider == "openai":
        # Keep OpenAI on the Agents SDK's native Responses API path.
        return config.model
    raise ValueError(f"Unsupported LLM_PROVIDER: {config.provider}")
