"""Khala MCP Server 진입점.

Usage:
    # stdio (기본 — 로컬 Agent 연동)
    python -m khala.mcp

    # streamable-http (원격 Agent 연동)
    python -m khala.mcp --transport http --port 8001
"""

from __future__ import annotations

import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("khala.mcp")


def main() -> None:
    parser = argparse.ArgumentParser(description="Khala MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    from khala.mcp.server import mcp

    logger.info("Khala MCP Server 시작 (transport=%s)", args.transport)

    if args.transport == "http":
        mcp.run(transport="streamable-http", port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
