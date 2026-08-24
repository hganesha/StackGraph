"""Service heartbeat for the deployment-managed HTTP transport.

The Admin -> Services & health page derives liveness from the shared
``service_heartbeat`` table. The stdio transport is a client-owned subprocess and
never records heartbeats; the HTTP transport records them when a database URL is
configured so the workspace Admin UI can distinguish an online MCP endpoint from
an offline one.
"""

from __future__ import annotations

import logging
import os
import socket
import threading

from .errors import ConfigurationError

logger = logging.getLogger("stackgraph_mcp.heartbeat")

SERVICE_KEY = "mcp"

_HEARTBEAT_SQL = """
INSERT INTO service_heartbeat(service_key,instance_id,status,metadata)
VALUES (%s,%s,'RUNNING','{}')
ON CONFLICT(service_key) DO UPDATE SET
  instance_id=EXCLUDED.instance_id,status='RUNNING',metadata=EXCLUDED.metadata,
  started_at=CASE WHEN service_heartbeat.instance_id=EXCLUDED.instance_id
    THEN service_heartbeat.started_at ELSE now() END,
  last_heartbeat_at=now()
"""


def record_heartbeat(database_url: str, *, instance_id: str | None = None) -> None:
    """Upsert one RUNNING heartbeat row for this MCP instance.

    Args:
        database_url: PostgreSQL connection URL.
        instance_id: Stable identity for this process, defaulting to host:pid.

    Raises:
        ConfigurationError: When psycopg is not installed.
    """
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - depends on the install profile
        raise ConfigurationError(
            "STACKGRAPH_MCP_DATABASE_URL needs psycopg. Install it with 'pip install psycopg[binary]'."
        ) from exc
    identity = instance_id or f"{socket.gethostname()}:{os.getpid()}"
    with psycopg.connect(database_url) as connection:
        connection.execute(_HEARTBEAT_SQL, (SERVICE_KEY, identity))


def start_heartbeat(database_url: str, interval_seconds: float) -> threading.Event:
    """Start a daemon thread that records heartbeats until the returned event is set.

    The first heartbeat is written synchronously so a misconfigured database URL
    fails at startup instead of silently showing OFFLINE in Admin.

    Args:
        database_url: PostgreSQL connection URL.
        interval_seconds: Delay between heartbeats.

    Returns:
        threading.Event: Set it to stop the heartbeat loop.
    """
    record_heartbeat(database_url)
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(interval_seconds):
            try:
                record_heartbeat(database_url)
            except Exception:  # noqa: BLE001 - a transient outage must not kill the loop
                logger.warning("service heartbeat failed; retrying next interval", exc_info=True)

    threading.Thread(target=loop, name="stackgraph-mcp-heartbeat", daemon=True).start()
    return stop
