import dataclasses
from typing import Any

import httpx
from mcp.client import Client

from icloud_calendar_mcp.calendar import CalendarClient
from icloud_calendar_mcp.config import Settings
from icloud_calendar_mcp.server import BearerAuth, build_server, build_sse_app

ALL_TOOLS = {
    "list_calendars",
    "list_events",
    "get_event",
    "create_event",
    "update_event",
    "delete_event",
}
READ_TOOLS = {"list_calendars", "list_events", "get_event"}


async def test_tool_roundtrip(settings: Settings, client: CalendarClient) -> None:
    async with Client(build_server(settings, client)) as mcp:
        tools = {t.name for t in (await mcp.list_tools()).tools}
        assert tools == ALL_TOOLS

        calendars = await mcp.call_tool("list_calendars", {})
        assert sorted(c["name"] for c in calendars.structured_content["result"]) == ["Home", "Work"]

        created = await mcp.call_tool(
            "create_event", {"calendar": "Home", "summary": "Lunch", "start": "2030-03-01T12:00"}
        )
        assert not created.is_error
        uid = created.structured_content["uid"]

        listed = await mcp.call_tool("list_events", {"start": "2030-03-01", "end": "2030-03-02"})
        assert [e["uid"] for e in listed.structured_content["result"]] == [uid]

        fetched = await mcp.call_tool("get_event", {"uid": uid})
        assert fetched.structured_content["summary"] == "Lunch"

        updated = await mcp.call_tool("update_event", {"uid": uid, "summary": "Brunch"})
        assert updated.structured_content["summary"] == "Brunch"

        deleted = await mcp.call_tool("delete_event", {"uid": uid})
        assert deleted.structured_content == {"deleted": uid}


async def test_errors_reach_the_model_as_plain_strings(
    settings: Settings, client: CalendarClient
) -> None:
    async with Client(build_server(settings, client)) as mcp:
        result = await mcp.call_tool("get_event", {"uid": "missing"})
        assert result.is_error
        assert "event not found: 'missing'" in result.content[0].text


async def test_read_only_hides_write_tools(settings: Settings, client: CalendarClient) -> None:
    read_only = dataclasses.replace(settings, read_only=True)
    async with Client(build_server(read_only, client)) as mcp:
        assert {t.name for t in (await mcp.list_tools()).tools} == READ_TOOLS


async def _request(app: Any, headers: dict[str, str]) -> int:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        return (await http.get("/other", headers=headers)).status_code


async def _inner(scope: Any, receive: Any, send: Any) -> None:
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


async def test_bearer_auth() -> None:
    app = BearerAuth(_inner, "s3cret")
    assert await _request(app, {}) == 401
    assert await _request(app, {"Authorization": "Bearer wrong"}) == 401
    assert await _request(app, {"Authorization": "s3cret"}) == 401
    assert await _request(app, {"Authorization": "Bearer s3cret"}) == 204


async def test_sse_app_requires_token(settings: Settings, client: CalendarClient) -> None:
    app = build_sse_app(build_server(settings, client), "s3cret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get("/sse")
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"
