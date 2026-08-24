"""Entry point: ``python -m stackgraph_mcp``."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import mcp.server.stdio
from pydantic import ValidationError

from .config import Settings
from .errors import ConfigurationError
from .server import build_app, create_server


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="stackgraph_mcp",
        description=(
            "MCP server for the StackGraph API. Tools are generated from the frozen OpenAPI "
            "contract; configure the target deployment with STACKGRAPH_MCP_* environment variables."
        ),
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="stdio for a local client subprocess (default), http for a remote streamable-HTTP server.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host for --transport http.")
    parser.add_argument("--port", type=int, default=8080, help="Bind port for --transport http.")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="Logging verbosity. Logs always go to stderr so stdio stays a clean protocol channel.",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the tools that would be exposed, then exit without serving.",
    )
    return parser.parse_args(argv)


async def _serve_stdio(settings: Settings) -> None:
    app = build_app(settings)
    server = create_server(app)
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def _serve_http(settings: Settings, host: str, port: int) -> None:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover - depends on the install profile
        raise ConfigurationError(
            "--transport http needs uvicorn. Install it with 'pip install uvicorn[standard]'."
        ) from exc

    from .heartbeat import start_heartbeat

    app = build_app(settings)
    server = create_server(app)
    stop_heartbeat = (
        start_heartbeat(settings.database_url, settings.heartbeat_seconds)
        if settings.database_url
        else None
    )
    try:
        uvicorn.run(server.streamable_http_app(json_response=True, stateless_http=True, host=host), host=host, port=port)
    finally:
        if stop_heartbeat is not None:
            stop_heartbeat.set()


def main(argv: list[str] | None = None) -> int:
    """Run the server.

    Args:
        argv: Command-line arguments, defaulting to ``sys.argv[1:]``.

    Returns:
        int: Process exit code - 0 on clean shutdown, 2 on a configuration error.
    """
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level, stream=sys.stderr, format="%(levelname)s %(name)s: %(message)s")

    try:
        settings = Settings()
        if args.list_tools:
            app = build_app(settings)
            for tool in app.list_tools():
                print(f"{tool.name}\t{tool.title}")
            return 0
        if args.transport == "http":
            _serve_http(settings, args.host, args.port)
        else:
            asyncio.run(_serve_stdio(settings))
    except ValidationError as exc:
        print(f"Configuration error: invalid STACKGRAPH_MCP_* environment:\n{exc}", file=sys.stderr)
        return 2
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:  # pragma: no cover - interactive shutdown
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
