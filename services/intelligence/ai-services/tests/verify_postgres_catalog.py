from __future__ import annotations

import os
from pathlib import Path

import psycopg

from stackgraph_ai.catalog import LocalPromptCatalog
from stackgraph_ai.sync_prompts import sync_prompt_definitions


def main() -> None:
    database_url = os.environ["STACKGRAPH_DATABASE_URL"]
    migration_path = Path(os.environ["STACKGRAPH_AI_MIGRATION"])
    prompts_dir = Path(os.environ["STACKGRAPH_AI_PROMPTS_DIR"])
    prompts = LocalPromptCatalog(prompts_dir).definitions()

    connection = psycopg.connect(database_url)
    try:
        connection.execute(migration_path.read_text(encoding="utf-8"))
        synced = sync_prompt_definitions(
            connection,
            prompts,
            tenant_id=None,
            actor_key="transactional-verification",
        )
        row = connection.execute(
            "SELECT count(*) FROM ai_prompt_template WHERE status='ACTIVE'"
        ).fetchone()
        assert synced == len(prompts)
        assert row is not None and row[0] == len(prompts)
    finally:
        connection.rollback()
        connection.close()

    print(f"validated {len(prompts)} prompts; transaction rolled back")


if __name__ == "__main__":
    main()
