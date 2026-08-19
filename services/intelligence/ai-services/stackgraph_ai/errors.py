from __future__ import annotations


class AIServiceError(Exception):
    """Base error for the provider-neutral AI layer."""


class PromptCatalogError(AIServiceError):
    """The prompt catalog is invalid or unavailable."""


class PromptNotFoundError(PromptCatalogError):
    def __init__(self, prompt_key: str, version: str | None = None) -> None:
        suffix = f" at version {version}" if version else ""
        super().__init__(f"Prompt {prompt_key!r}{suffix} was not found")
        self.prompt_key = prompt_key
        self.version = version


class PromptValidationError(PromptCatalogError):
    """A persisted prompt does not satisfy the catalog contract."""


class PromptRenderError(AIServiceError):
    """A prompt could not be rendered with the supplied variables."""


class ProviderNotFoundError(AIServiceError):
    def __init__(self, provider: str) -> None:
        super().__init__(f"AI provider {provider!r} is not registered")
        self.provider = provider


class ModelRouteNotFoundError(AIServiceError):
    def __init__(self, route: str) -> None:
        super().__init__(f"AI model route {route!r} is not registered")
        self.route = route


class ProviderResponseError(AIServiceError):
    """The provider returned a successful HTTP response with an invalid body."""


class ProviderRequestError(AIServiceError):
    def __init__(
        self,
        *,
        provider: str,
        code: str,
        message: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.retryable = retryable
        self.status_code = status_code
