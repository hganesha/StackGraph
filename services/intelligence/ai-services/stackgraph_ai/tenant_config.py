from __future__ import annotations

from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from stackgraph_ai.bootstrap import AISettings


def load_tenant_ai_settings(
    database_url: str,
    *,
    tenant_id: UUID,
    encryption_key: str,
) -> AISettings | None:
    """Resolve one enabled tenant provider without exposing its stored credential."""
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        row = connection.execute(
            """
            SELECT configuration.provider,configuration.model,
              pgp_sym_decrypt(secret.ciphertext,%s)::text AS api_key
            FROM tenant_ai_configuration configuration
            JOIN tenant_secret secret
              ON secret.id=configuration.credential_secret_id
             AND secret.tenant_id=configuration.tenant_id
            WHERE configuration.tenant_id=%s AND configuration.enabled
              AND configuration.model<>''
            """,
            (encryption_key, tenant_id),
        ).fetchone()
    if row is None:
        return None
    return AISettings.for_provider(row["provider"], row["model"], row["api_key"])
