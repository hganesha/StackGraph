"""The HTTP transport records Admin-visible heartbeats; stdio never does."""

from __future__ import annotations

import os
import socket

import psycopg
import pytest
from pydantic import ValidationError

from stackgraph_mcp import heartbeat
from stackgraph_mcp.config import Settings


class FakeConnection:
    def __init__(self, log: list[tuple[str, tuple]]) -> None:
        self.log = log

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, query: str, params: tuple) -> None:
        self.log.append((query, params))


def test_record_heartbeat_upserts_one_running_row(monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[tuple[str, tuple]] = []
    urls: list[str] = []

    def connect(url: str) -> FakeConnection:
        urls.append(url)
        return FakeConnection(executed)

    monkeypatch.setattr(psycopg, "connect", connect)
    heartbeat.record_heartbeat("postgresql://example/stackgraph")

    assert urls == ["postgresql://example/stackgraph"]
    (query, params), = executed
    assert "INSERT INTO service_heartbeat" in query
    assert "ON CONFLICT(service_key)" in query
    assert "last_heartbeat_at=now()" in query
    assert params[0] == "mcp"
    assert params[1] == f"{socket.gethostname()}:{os.getpid()}"


def test_start_heartbeat_writes_synchronously_and_is_stoppable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(heartbeat, "record_heartbeat", lambda url, **_: calls.append(url))

    stop = heartbeat.start_heartbeat("postgresql://example/stackgraph", 300.0)
    try:
        assert calls == ["postgresql://example/stackgraph"]
    finally:
        stop.set()


def test_start_heartbeat_surfaces_a_broken_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_record(url: str, **_: object) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(heartbeat, "record_heartbeat", failing_record)
    with pytest.raises(RuntimeError):
        heartbeat.start_heartbeat("postgresql://example/stackgraph", 300.0)


def test_settings_bound_the_heartbeat_interval() -> None:
    assert Settings().database_url is None
    assert Settings(database_url="postgresql://example/stackgraph").heartbeat_seconds == 15.0
    with pytest.raises(ValidationError):
        Settings(heartbeat_seconds=1.0)
