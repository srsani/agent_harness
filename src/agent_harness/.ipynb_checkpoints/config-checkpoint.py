from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    logfire_token: str | None = None

    # Set to e.g. "anthropic:claude-sonnet-4-6", "openai:gpt-4o", or "local:model-name"
    agent_bench_model: str = "anthropic:claude-sonnet-4-6"

    # LM Studio / local OpenAI-compatible server
    # Set AGENT_BENCH_LOCAL_BASE_URL to use a local model.
    # AGENT_BENCH_MODEL should then be "local:<model-name-as-shown-in-lm-studio>"
    agent_bench_local_base_url: str | None = None  # e.g. http://192.168.68.60:1234/v1
    agent_bench_local_api_key: str = "lm-studio"   # LM Studio ignores this value

    @property
    def is_local(self) -> bool:
        return self.agent_bench_model.startswith("local:")

    @property
    def local_model_name(self) -> str:
        """Strip the 'local:' prefix to get the bare model identifier."""
        return self.agent_bench_model.removeprefix("local:")

    def build_pydantic_ai_model(self):
        """Return a pydantic-ai model object configured for the active provider."""
        if self.is_local:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            base_url = self.agent_bench_local_base_url or "http://localhost:1234/v1"
            provider = OpenAIProvider(base_url=base_url, api_key=self.agent_bench_local_api_key)
            return OpenAIChatModel(self.local_model_name, provider=provider)

        # Cloud providers — pydantic-ai resolves "anthropic:…" / "openai:…" natively
        return self.agent_bench_model


settings = Settings()
