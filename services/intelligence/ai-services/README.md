# StackGraph AI services

Provider-neutral AI execution and versioned prompt catalogs for StackGraph intelligence workloads.

The layer intentionally separates four concerns:

1. Domain callers select a logical model route and prompt key.
2. A prompt catalog resolves a versioned prompt from PostgreSQL or local JSON.
3. A provider adapter translates the normalized request to OpenAI, OpenRouter, or Anthropic.
4. An optional invocation recorder stores operational metadata without storing prompt/source content.

It does not create estate facts, execute model-requested tools, or silently substitute mock output. Domain orchestration remains responsible for executing allowlisted deterministic tools and validating any proposed inference before persistence.

## Prompt catalogs

Local prompts live in [`prompts`](./prompts). Each JSON record contains:

- `key`, `version`, and lifecycle `status`;
- an ordered message list using strict `${variable}` placeholders;
- the complete declared variable set;
- optional JSON output schema;
- provider-neutral model defaults;
- policy/purpose metadata; and
- a calculated content hash.

`CompositePromptCatalog(PostgresPromptCatalog(...), LocalPromptCatalog(...))` gives tenant-scoped PostgreSQL records precedence over global PostgreSQL records, then falls back to local files only when the prompt is absent. Database errors do not trigger an implicit fallback because doing so could silently change policy/version.

Apply migration `004_ai_prompt_catalog.sql`, then synchronize the deployable baseline:

```bash
make ai-prompts-sync
```

To create tenant overrides, run the sync command with `--tenant-id`. The sync retires a prior active version for the same scope/key, upserts by `(tenant_id, prompt_key, version)`, and never deletes prompt history.

## Provider configuration

Configure logical routes independently from prompts:

```bash
export STACKGRAPH_AI_ROUTES_JSON='{
  "default": {"provider": "openrouter", "model": "your/model-id"},
  "high-confidence": {"provider": "anthropic", "model": "your-model-id"},
  "openai-structured": {"provider": "openai", "model": "your-model-id"}
}'
```

Set only the credentials for providers enabled by those routes:

- `OPENROUTER_API_KEY`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Base URLs are separately configurable for test gateways or compatible deployments. No default model is compiled into the service; deployment configuration must choose it explicitly.

```python
from stackgraph_ai import AISettings, build_ai_service

settings = AISettings.from_env()
ai = build_ai_service(settings, database=database)
result = await ai.invoke(
    "capability.inference",
    {
        "subject": subject_ref,
        "taxonomy": taxonomy_payload,
        "evidence_bundle": evidence_payload,
    },
    tenant_id=tenant_id,
)
```

The provider adapters expose the same normalized text, structured-output, tool-call, token-usage, finish-reason, and request-ID result contract. OpenAI uses the Responses API; OpenRouter uses its stable Chat Completions compatibility API; Anthropic uses the Messages API. All structured output is validated locally against the persisted prompt schema after provider validation.

## Data handling

- Provider-side storage defaults to disabled where the provider offers a storage switch.
- OpenRouter requests default to `data_collection: deny` and per-request zero-data-retention routing. A caller may supply a stricter/different tenant-resolved `DataHandlingPolicy`; prompt authors cannot weaken this policy through prompt parameters.
- The invocation table stores prompt/content hashes, input fingerprint, model/provider identity, token/cost metadata, status, and sanitized error classification.
- Raw rendered prompts, source excerpts, tool results, and provider response bodies are not written to invocation records.
- Prompt and invocation tables use the existing tenant RLS model.
- Local prompt files are global product policy and must contain no tenant data.

## Verification

```bash
make ai-test
```

The tests use provider HTTP mock transports; they never call external models or require API keys.

Provider wire formats follow the official [OpenAI Responses API](https://developers.openai.com/api/reference/resources/responses), [OpenRouter structured output](https://openrouter.ai/docs/guides/features/structured-outputs) and [tool calling](https://openrouter.ai/docs/guides/features/tool-calling), and [Anthropic structured output](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) and [tool use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview) contracts.
