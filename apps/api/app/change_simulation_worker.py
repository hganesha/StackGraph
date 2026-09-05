from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket

from psycopg.types.json import Jsonb

from app.config import Settings
from app.database import Database
from app.read_models import ReadModelStore


logger = logging.getLogger(__name__)


async def record_heartbeat(database: Database, *, instance_id: str, poll_seconds: float) -> None:
    async with database.session() as connection:
        await connection.execute(
            """
            INSERT INTO service_heartbeat(service_key,instance_id,status,metadata)
            VALUES ('change-simulator',%s,'RUNNING',%s)
            ON CONFLICT(service_key) DO UPDATE SET
              instance_id=EXCLUDED.instance_id,status='RUNNING',metadata=EXCLUDED.metadata,
              started_at=CASE WHEN service_heartbeat.instance_id=EXCLUDED.instance_id
                THEN service_heartbeat.started_at ELSE now() END,
              last_heartbeat_at=now()
            """,
            (instance_id, Jsonb({"poll_seconds": poll_seconds})),
        )


async def work_once(store: ReadModelStore, settings: Settings) -> bool:
    return await store.run_next_simulation(
        max_nodes=settings.change_simulation_max_nodes,
        max_edges=settings.change_simulation_max_edges,
        timeout_seconds=settings.change_simulation_timeout_seconds,
    )


async def run(mode: str, poll_seconds: float) -> None:
    settings = Settings()
    database = Database(settings)
    store = ReadModelStore(database)
    instance_id = f"{socket.gethostname()}:{os.getpid()}"
    await database.open()
    try:
        await record_heartbeat(database, instance_id=instance_id, poll_seconds=poll_seconds)
        if mode == "work":
            await work_once(store, settings)
            return
        while True:
            worked = await work_once(store, settings)
            await record_heartbeat(database, instance_id=instance_id, poll_seconds=poll_seconds)
            if not worked:
                await asyncio.sleep(poll_seconds)
    finally:
        await database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Process durable deterministic change simulations")
    parser.add_argument("mode", choices=("work", "serve"), nargs="?", default="work")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds < 0.1 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 0.1 and 60")
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.mode, args.poll_seconds))


if __name__ == "__main__":
    main()
