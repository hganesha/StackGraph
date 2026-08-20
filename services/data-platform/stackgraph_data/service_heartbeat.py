from __future__ import annotations

import os
import socket
from typing import Any, Mapping

import psycopg
from psycopg.types.json import Jsonb


def record_service_heartbeat(
    database_url: str,
    service_key: str,
    *,
    instance_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    identity = instance_id or f"{socket.gethostname()}:{os.getpid()}"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """
            INSERT INTO service_heartbeat(service_key,instance_id,status,metadata)
            VALUES (%s,%s,'RUNNING',%s)
            ON CONFLICT(service_key) DO UPDATE SET
              instance_id=EXCLUDED.instance_id,status='RUNNING',metadata=EXCLUDED.metadata,
              started_at=CASE WHEN service_heartbeat.instance_id=EXCLUDED.instance_id
                THEN service_heartbeat.started_at ELSE now() END,
              last_heartbeat_at=now()
            """,
            (service_key, identity, Jsonb(dict(metadata or {}))),
        )
