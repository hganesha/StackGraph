from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from stackgraph_ai.errors import ProviderRequestError
from stackgraph_ai.models import ModelRequest, ModelResponse
from stackgraph_ai.registry import AIProvider


class RetryingProvider:
    """Provider decorator with bounded retries for explicitly retryable errors."""

    def __init__(
        self,
        provider: AIProvider,
        *,
        max_attempts: int = 2,
        base_delay_seconds: float = 0.25,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.provider = provider
        self.max_attempts = max_attempts
        self.base_delay_seconds = max(0, base_delay_seconds)
        self.sleep = sleep

    @property
    def provider_name(self) -> str:
        return self.provider.provider_name

    async def complete(self, request: ModelRequest) -> ModelResponse:
        for attempt in range(self.max_attempts):
            try:
                return await self.provider.complete(request)
            except ProviderRequestError as error:
                if not error.retryable or attempt + 1 >= self.max_attempts:
                    raise
                await self.sleep(self.base_delay_seconds * (2**attempt))
        raise AssertionError("unreachable")
