from __future__ import annotations

from collections.abc import Mapping
from time import perf_counter
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from stackgraph_ai.catalog import PromptCatalog
from stackgraph_ai.errors import ProviderRequestError, ProviderResponseError
from stackgraph_ai.invocations import InvocationRecorder
from stackgraph_ai.models import (
    DataHandlingPolicy,
    ModelRequest,
    PromptInvocation,
    ToolChoice,
    ToolDefinition,
    sha256_key,
)
from stackgraph_ai.registry import ModelRouteRegistry, ProviderRegistry


def _schema_validation_summary(
    error: ValidationError,
    output: Mapping[str, Any] | list[Any],
    schema: Mapping[str, Any],
) -> str:
    path = "$" + "".join(
        f"[{item}]" if isinstance(item, int) else f".{item}"
        for item in error.absolute_path
    )
    details = [f"path={path}", f"rule={error.validator}"]
    if isinstance(output, Mapping):
        properties = schema.get("properties")
        expected = set(properties) if isinstance(properties, Mapping) else set()
        required = schema.get("required")
        required_fields = set(required) if isinstance(required, list) else set()
        missing = sorted(required_fields - set(output))
        unexpected = sorted(set(output) - expected) if expected else []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if unexpected:
            details.append(f"unexpected={','.join(unexpected)}")
    return "; ".join(details)


class AIService:
    """Coordinates prompt resolution and provider execution.

    Domain code depends on this service rather than any provider SDK or wire
    format. Prompt content is always loaded from a catalog; only operational
    request overrides are accepted in code.
    """

    def __init__(
        self,
        *,
        prompts: PromptCatalog,
        providers: ProviderRegistry,
        routes: ModelRouteRegistry,
        invocation_recorder: InvocationRecorder | None = None,
        default_data_policy: DataHandlingPolicy | None = None,
    ) -> None:
        self.prompts = prompts
        self.providers = providers
        self.routes = routes
        self.invocation_recorder = invocation_recorder
        self.default_data_policy = default_data_policy or DataHandlingPolicy()

    async def invoke(
        self,
        prompt_key: str,
        variables: Mapping[str, Any],
        *,
        route: str = "default",
        prompt_version: str | None = None,
        tenant_id: UUID | None = None,
        tools: tuple[ToolDefinition, ...] = (),
        tool_choice: ToolChoice = "auto",
        request_overrides: Mapping[str, Any] | None = None,
        metadata: Mapping[str, Any] | None = None,
        data_policy: DataHandlingPolicy | None = None,
    ) -> PromptInvocation:
        prompt = await self.prompts.get(
            prompt_key,
            version=prompt_version,
            tenant_id=tenant_id,
        )
        model_route = self.routes.get(route)
        parameters = dict(prompt.model_parameters)
        parameters.update(request_overrides or {})

        allowed = {"max_output_tokens", "temperature", "output_schema_name"}
        unknown = sorted(set(parameters) - allowed)
        if unknown:
            raise ValueError(f"Unsupported model parameters: {', '.join(unknown)}")

        rendered_messages = prompt.render(variables)
        input_fingerprint = sha256_key(
            {
                "prompt_content_hash": prompt.content_hash,
                "messages": [
                    {"role": message.role, "content": message.content}
                    for message in rendered_messages
                ],
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "input_schema": tool.input_schema,
                        "strict": tool.strict,
                    }
                    for tool in tools
                ],
            }
        )
        request = ModelRequest(
            model=model_route.model,
            messages=rendered_messages,
            max_output_tokens=int(parameters.get("max_output_tokens", 1200)),
            temperature=parameters.get("temperature"),
            tools=tools,
            tool_choice=tool_choice,
            output_schema=prompt.output_schema,
            output_schema_name=str(parameters.get("output_schema_name", "stackgraph_response")),
            metadata={
                "prompt_key": prompt.key,
                "prompt_version": prompt.version,
                "prompt_content_hash": prompt.content_hash,
                "input_fingerprint": input_fingerprint,
                **(metadata or {}),
            },
            data_policy=data_policy or self.default_data_policy,
        )
        provider = self.providers.get(model_route.provider)
        invocation_id = None
        policy_version = str(prompt.metadata.get("policy_version") or "") or None
        if self.invocation_recorder is not None:
            invocation_id = await self.invocation_recorder.start(
                tenant_id=tenant_id,
                prompt=prompt,
                route=model_route,
                input_fingerprint=input_fingerprint,
                policy_version=policy_version,
            )
        started = perf_counter()
        try:
            response = await provider.complete(request)
            if request.output_schema is not None:
                if response.structured_output is None:
                    raise ProviderResponseError(
                        f"{response.provider} returned no structured output for {prompt.key!r}"
                    )
                try:
                    Draft202012Validator.check_schema(request.output_schema)
                    Draft202012Validator(request.output_schema).validate(response.structured_output)
                except (SchemaError, ValidationError) as error:
                    summary = (
                        _schema_validation_summary(
                            error, response.structured_output, request.output_schema,
                        )
                        if isinstance(error, ValidationError)
                        else "prompt schema is invalid"
                    )
                    raise ProviderResponseError(
                        f"{response.provider} output did not satisfy prompt schema "
                        f"{prompt.key!r} ({summary})"
                    ) from error
        except Exception as error:
            if self.invocation_recorder is not None and invocation_id is not None:
                await self.invocation_recorder.fail(
                    invocation_id,
                    tenant_id=tenant_id,
                    error_code=(error.code if isinstance(error, ProviderRequestError) else type(error).__name__),
                    retryable=(error.retryable if isinstance(error, ProviderRequestError) else None),
                    duration_ms=max(0, int((perf_counter() - started) * 1000)),
                )
            raise
        if self.invocation_recorder is not None and invocation_id is not None:
            await self.invocation_recorder.succeed(
                invocation_id,
                tenant_id=tenant_id,
                response=response,
                duration_ms=max(0, int((perf_counter() - started) * 1000)),
            )
        return PromptInvocation(
            prompt=prompt,
            route=model_route,
            input_fingerprint=input_fingerprint,
            response=response,
            invocation_id=invocation_id,
        )
