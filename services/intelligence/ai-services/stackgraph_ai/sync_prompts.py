from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from stackgraph_ai.catalog import LocalPromptCatalog
from stackgraph_ai.models import PromptDefinition


def sync_prompt_definitions(
    connection: psycopg.Connection,
    prompts: tuple[PromptDefinition, ...],
    *,
    tenant_id: UUID | None,
    actor_key: str,
) -> int:
    for prompt in prompts:
        if prompt.status == "ACTIVE":
            connection.execute(
                """
                UPDATE ai_prompt_template SET status='RETIRED',updated_at=now()
                WHERE tenant_id IS NOT DISTINCT FROM %s AND prompt_key=%s
                  AND version<>%s AND status='ACTIVE'
                """,
                (tenant_id, prompt.key, prompt.version),
            )
        connection.execute(
            """
            INSERT INTO ai_prompt_template(
              tenant_id,prompt_key,version,status,messages,input_variables,
              output_schema,model_parameters,metadata,content_hash,created_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id,prompt_key,version) DO UPDATE SET
              status=EXCLUDED.status,messages=EXCLUDED.messages,
              input_variables=EXCLUDED.input_variables,output_schema=EXCLUDED.output_schema,
              model_parameters=EXCLUDED.model_parameters,metadata=EXCLUDED.metadata,
              content_hash=EXCLUDED.content_hash,updated_at=now()
            """,
            (
                tenant_id,
                prompt.key,
                prompt.version,
                prompt.status,
                Jsonb(prompt.as_record()["messages"]),
                list(prompt.input_variables),
                Jsonb(prompt.output_schema) if prompt.output_schema is not None else None,
                Jsonb(dict(prompt.model_parameters)),
                Jsonb(dict(prompt.metadata)),
                prompt.content_hash,
                actor_key,
            ),
        )
    return len(prompts)


def sync_prompts(
    database_url: str,
    prompts_dir: Path,
    *,
    tenant_id: UUID | None,
    actor_key: str,
) -> int:
    prompts = LocalPromptCatalog(prompts_dir).definitions()
    with psycopg.connect(database_url) as connection:
        return sync_prompt_definitions(
            connection,
            prompts,
            tenant_id=tenant_id,
            actor_key=actor_key,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync local StackGraph prompts into PostgreSQL")
    parser.add_argument("--prompts-dir", type=Path, required=True)
    parser.add_argument("--tenant-id", type=UUID)
    parser.add_argument("--actor-key", default="prompt-catalog-sync")
    args = parser.parse_args()
    database_url = os.getenv("STACKGRAPH_DATABASE_URL")
    if not database_url:
        parser.error("STACKGRAPH_DATABASE_URL is required")
    count = sync_prompts(
        database_url,
        args.prompts_dir,
        tenant_id=args.tenant_id,
        actor_key=args.actor_key,
    )
    print(json.dumps({"synced": count, "tenant_id": str(args.tenant_id) if args.tenant_id else None}))


if __name__ == "__main__":
    main()
