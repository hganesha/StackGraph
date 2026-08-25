#!/usr/bin/env python3
"""Manual smoke-test harness for the StackGraph MCP server.

Launches the real server as a subprocess and drives it with a genuine MCP
client over stdio, exercising the path the mocked unit tests skip: process
startup, the initialize handshake, and JSON-RPC framing.

Usage:
    python scripts/harness.py                          # list every tool
    python scripts/harness.py --call stackgraph_get_estate_summary
    python scripts/harness.py --call stackgraph_get_graph_neighborhood \\
        --args '{"center_id": "3f1c9a2e-0000-4000-8000-000000000001", "depth": 1}'

Reads the same STACKGRAPH_MCP_* environment variables as the server (see
README.md). Point STACKGRAPH_MCP_API_BASE_URL / STACKGRAPH_MCP_API_TOKEN at a
real running API first; otherwise it defaults to http://localhost:8000.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

SERVER_DIR = Path(__file__).resolve().parent.parent


async def run(args: argparse.Namespace) -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "stackgraph_mcp", "--log-level", args.log_level],
        cwd=str(SERVER_DIR),
        env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"connected: {init.server_info.name} {init.server_info.version}", file=sys.stderr)

            if args.call:
                arguments = json.loads(args.args) if args.args else {}
                result = await session.call_tool(args.call, arguments)
                for block in result.content:
                    print(getattr(block, "text", block))
                return 1 if result.is_error else 0

            tools = await session.list_tools()
            for tool in tools.tools:
                print(f"{tool.name}\t{tool.title or ''}")
            print(f"\n{len(tools.tools)} tools", file=sys.stderr)
            return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--call", metavar="TOOL", help="Call one tool instead of listing the catalog.")
    parser.add_argument("--args", metavar="JSON", help="JSON object of arguments for --call.")
    parser.add_argument("--log-level", default="WARNING", help="Server log level (goes to stderr only).")
    args = parser.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
