import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx
import pytest
from mcp.client import Client
from mcp.client.sse import sse_client
from mcp.client.stdio import StdioServerParameters

from icloud_calendar_mcp.config import Settings

TOKEN = "test-token"


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
    process = subprocess.Popen(
        [sys.executable, "-m", "icloud_calendar_mcp", "--transport", "sse", "--port", str(port)],
        env=_env(settings, MCP_BEARER_TOKEN=TOKEN),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
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
        process.terminate()
        process.wait(timeout=10)


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
    transport = sse_client(sse_url, headers={"Authorization": f"Bearer {TOKEN}"})
    async with Client(transport) as mcp:
        assert len((await mcp.list_tools()).tools) == 6
        created = await mcp.call_tool(
            "create_event", {"calendar": "Work", "summary": "Sync", "start": "2030-05-01T10:00"}
        )
        assert not created.is_error
        deleted = await mcp.call_tool("delete_event", {"uid": created.structured_content["uid"]})
        assert not deleted.is_error
