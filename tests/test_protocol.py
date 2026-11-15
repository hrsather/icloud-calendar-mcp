import os
import socket
import sys
import threading
import time
from collections.abc import Iterator

import httpx
import pytest
import uvicorn
from mcp.client import Client
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters

from icloud_calendar_mcp.config import Settings
from icloud_calendar_mcp.server import build_server, build_sse_app

from .support import BEARER


def _env(settings: Settings, **extra: str) -> dict[str, str]:
    return {
        **os.environ,
        "ICLOUD_APPLE_ID": settings.apple_id,
        "ICLOUD_APP_PASSWORD": settings.app_password,
        "ICLOUD_CALDAV_URL": settings.caldav_url,
        "ICLOUD_MCP_TIMEZONE": "Europe/London",
        **extra,
    }


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def sse_url(settings: Settings, calendars: list[str]) -> Iterator[str]:
    port = _free_port()
    app = build_sse_app(build_server(settings), BEARER)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/sse"
    try:
        for _ in range(100):
            try:
                httpx.get(url, timeout=1)
                break
            except httpx.TransportError:
                time.sleep(0.1)
        yield url
    finally:
        server.should_exit = True
        thread.join(timeout=10)


async def test_stdio(settings: Settings, calendars: list[str]) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "icloud_calendar_mcp"], env=_env(settings)
    )
    async with Client(params) as mcp:
        assert len((await mcp.list_tools()).tools) == 6
        result = await mcp.call_tool("list_calendars", {})
        assert sorted(c["name"] for c in result.structured_content["result"]) == ["Home", "Work"]


async def test_stdio_read_only(settings: Settings, calendars: list[str]) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "icloud_calendar_mcp"],
        env=_env(settings, ICLOUD_MCP_READ_ONLY="true"),
    )
    async with Client(params) as mcp:
        assert len((await mcp.list_tools()).tools) == 3


def test_sse_rejects_missing_and_wrong_token(sse_url: str) -> None:
    assert httpx.get(sse_url).status_code == 401
    assert httpx.get(sse_url, headers={"Authorization": "Bearer nope"}).status_code == 401


async def test_sse_with_token(sse_url: str) -> None:
    transport = sse_client(sse_url, headers={"Authorization": f"Bearer {BEARER}"})
    async with Client(transport) as mcp:
        assert len((await mcp.list_tools()).tools) == 6
        created = await mcp.call_tool(
            "create_event", {"calendar": "Work", "summary": "Sync", "start": "2030-05-01T10:00"}
        )
        assert not created.is_error
        deleted = await mcp.call_tool("delete_event", {"uid": created.structured_content["uid"]})
        assert not deleted.is_error
