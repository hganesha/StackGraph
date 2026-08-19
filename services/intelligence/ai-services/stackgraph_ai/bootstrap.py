from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from stackgraph_ai.catalog import CompositePromptCatalog, LocalPromptCatalog, PostgresPromptCatalog
from stackgraph_ai.invocations import InvocationDatabase, PostgresInvocationRecorder
from stackgraph_ai.models import ModelRoute
from stackgraph_ai.providers import AnthropicAdapter, OpenAIAdapter, OpenRouterAdapter, RetryingProvider
from stackgraph_ai.registry import ModelRouteRegistry, ProviderRegistry
from stackgraph_ai.service import AIService


@dataclass(frozen=True, slots=True)
class AISettings:
    prompts_dir: Path
    routes: tuple[ModelRoute, ...]
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    openrouter_api_key: str | None = None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_site_url: str | None = None
    openrouter_site_name: str = "StackGraph"
    max_attempts: int = 2

    @classmethod
    def from_env(cls) -> "AISettings":
        default_prompts = Path(__file__).resolve().parent.parent / "prompts"
        routes = _routes_from_env()
        return cls(
            prompts_dir=Path(os.getenv("STACKGRAPH_AI_PROMPTS_DIR", str(default_prompts))),
            routes=routes,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            anthropic_base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
            openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
            openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            openrouter_site_url=os.getenv("OPENROUTER_SITE_URL"),
            openrouter_site_name=os.getenv("OPENROUTER_SITE_NAME", "StackGraph"),
            max_attempts=max(1, int(os.getenv("STACKGRAPH_AI_MAX_ATTEMPTS", "2"))),
        )


def _routes_from_env() -> tuple[ModelRoute, ...]:
    raw_routes = os.getenv("STACKGRAPH_AI_ROUTES_JSON")
    if raw_routes:
        payload = json.loads(raw_routes)
        if not isinstance(payload, dict):
            raise ValueError("STACKGRAPH_AI_ROUTES_JSON must be a JSON object")
        routes = []
        for name, value in payload.items():
            if not isinstance(value, dict) or not value.get("provider") or not value.get("model"):
                raise ValueError(f"AI route {name!r} requires provider and model")
            routes.append(
                ModelRoute(name=str(name), provider=str(value["provider"]), model=str(value["model"]))
            )
        return tuple(routes)

    provider = os.getenv("STACKGRAPH_AI_DEFAULT_PROVIDER")
    model = os.getenv("STACKGRAPH_AI_DEFAULT_MODEL")
    if not provider or not model:
        raise ValueError(
            "Configure STACKGRAPH_AI_ROUTES_JSON or both "
            "STACKGRAPH_AI_DEFAULT_PROVIDER and STACKGRAPH_AI_DEFAULT_MODEL"
        )
    return (ModelRoute(name="default", provider=provider, model=model),)


def build_ai_service(
    settings: AISettings,
    *,
    database: InvocationDatabase | None = None,
) -> AIService:
    providers = ProviderRegistry()
    if settings.openai_api_key:
        providers.register(
            RetryingProvider(
                OpenAIAdapter(settings.openai_api_key, base_url=settings.openai_base_url),
                max_attempts=settings.max_attempts,
            )
        )
    if settings.anthropic_api_key:
        providers.register(
            RetryingProvider(
                AnthropicAdapter(settings.anthropic_api_key, base_url=settings.anthropic_base_url),
                max_attempts=settings.max_attempts,
            )
        )
    if settings.openrouter_api_key:
        providers.register(
            RetryingProvider(
                OpenRouterAdapter(
                    settings.openrouter_api_key,
                    base_url=settings.openrouter_base_url,
                    site_url=settings.openrouter_site_url,
                    site_name=settings.openrouter_site_name,
                ),
                max_attempts=settings.max_attempts,
            )
        )

    for route in settings.routes:
        providers.get(route.provider)

    local_prompts = LocalPromptCatalog(settings.prompts_dir)
    prompts = (
        CompositePromptCatalog(PostgresPromptCatalog(database), local_prompts)
        if database is not None
        else local_prompts
    )
    return AIService(
        prompts=prompts,
        providers=providers,
        routes=ModelRouteRegistry(settings.routes),
        invocation_recorder=PostgresInvocationRecorder(database) if database is not None else None,
    )
