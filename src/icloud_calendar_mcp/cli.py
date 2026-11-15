import argparse
import sys
from collections.abc import Sequence

import uvicorn

from icloud_calendar_mcp import __version__
from icloud_calendar_mcp.config import ConfigError, Settings
from icloud_calendar_mcp.server import build_server, build_sse_app


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="icloud-calendar-mcp")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    try:
        settings = Settings.from_env()
        token = settings.bearer_token
        if args.transport == "sse" and not token:
            raise ConfigError("MCP_BEARER_TOKEN is required for the sse transport")
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    mcp = build_server(settings)
    if args.transport == "stdio" or token is None:
        mcp.run("stdio")
    else:
        uvicorn.run(
            build_sse_app(mcp, token, args.host),
            host=args.host,
            port=args.port,
            log_level="warning",
        )
