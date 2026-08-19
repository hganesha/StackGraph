from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from stackgraph_ai.errors import ModelRouteNotFoundError, ProviderNotFoundError
from stackgraph_ai.models import ModelRequest, ModelResponse, ModelRoute


class AIProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class ProviderRegistry:
    def __init__(self, providers: Iterable[AIProvider] = ()) -> None:
        self._providers: dict[str, AIProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: AIProvider) -> None:
        name = provider.provider_name.strip().lower()
        if not name:
            raise ValueError("provider_name must not be empty")
        if name in self._providers:
            raise ValueError(f"AI provider {name!r} is already registered")
        self._providers[name] = provider

    def get(self, provider: str) -> AIProvider:
        try:
            return self._providers[provider.strip().lower()]
        except KeyError as error:
            raise ProviderNotFoundError(provider) from error

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._providers))


class ModelRouteRegistry:
    def __init__(self, routes: Iterable[ModelRoute] = ()) -> None:
        self._routes: dict[str, ModelRoute] = {}
        for route in routes:
            self.register(route)

    def register(self, route: ModelRoute) -> None:
        name = route.name.strip().lower()
        if not name:
            raise ValueError("route name must not be empty")
        if name in self._routes:
            raise ValueError(f"AI model route {name!r} is already registered")
        self._routes[name] = route

    def get(self, route: str) -> ModelRoute:
        try:
            return self._routes[route.strip().lower()]
        except KeyError as error:
            raise ModelRouteNotFoundError(route) from error
