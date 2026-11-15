import functools
import hmac
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from icloud_calendar_mcp import __version__
from icloud_calendar_mcp.calendar import CalendarClient, CalendarError
from icloud_calendar_mcp.config import Settings

P = ParamSpec("P")
R = TypeVar("R")


def _surface(fn: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return fn(*args, **kwargs)
        except CalendarError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


class BearerAuth:
    def __init__(self, app: ASGIApp, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}".encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "lifespan":
            headers = dict(scope["headers"])
            supplied = headers.get(b"authorization", b"")
            if not hmac.compare_digest(supplied, self._expected):
                if scope["type"] == "http":
                    response = PlainTextResponse(
                        "unauthorized", status_code=401, headers={"WWW-Authenticate": "Bearer"}
                    )
                    await response(scope, receive, send)
                return
        await self._app(scope, receive, send)


def build_server(settings: Settings, client: CalendarClient | None = None) -> MCPServer:
    client = client or CalendarClient(settings)
    mcp = MCPServer("icloud-calendar", version=__version__)

    @mcp.tool()
    @_surface
    def list_calendars() -> list[dict[str, str]]:
        """List the calendars that can hold events, with their id and name."""
        return client.list_calendars()

    @mcp.tool()
    @_surface
    def list_events(start: str, end: str, calendar: str | None = None) -> list[dict[str, Any]]:
        """List events between start and end (ISO 8601 date or datetime; naive times use the
        server's default timezone). A date-only `end` is inclusive. Omit `calendar` (name or id)
        to search all calendars. Recurring events are expanded into individual occurrences, each
        with the series UID."""
        return client.list_events(start, end, calendar)

    @mcp.tool()
    @_surface
    def get_event(uid: str, calendar: str | None = None) -> dict[str, Any]:
        """Get one event by UID. For a recurring event this returns the series, including its
        RRULE."""
        return client.get_event(uid, calendar)

    if not settings.read_only:

        @mcp.tool()
        @_surface
        def create_event(
            calendar: str,
            summary: str,
            start: str,
            end: str | None = None,
            location: str | None = None,
            description: str | None = None,
            rrule: str | None = None,
        ) -> dict[str, Any]:
            """Create an event in `calendar` (name or id). A date-only start makes an all-day
            event. `end` defaults to one hour (or one day) after start. `rrule` is an optional
            iCalendar recurrence rule such as FREQ=WEEKLY;COUNT=4. Naive times use the server's
            default timezone."""
            return client.create_event(calendar, summary, start, end, location, description, rrule)

        @mcp.tool()
        @_surface
        def update_event(
            uid: str,
            calendar: str | None = None,
            summary: str | None = None,
            start: str | None = None,
            end: str | None = None,
            location: str | None = None,
            description: str | None = None,
        ) -> dict[str, Any]:
            """Update fields of an event by UID; omitted fields are unchanged and an empty string
            clears location or description. Changing only `start` keeps the event's duration.
            For a recurring event this changes the whole series."""
            return client.update_event(uid, calendar, summary, start, end, location, description)

        @mcp.tool()
        @_surface
        def delete_event(uid: str, calendar: str | None = None) -> dict[str, str]:
            """Delete an event by UID. For a recurring event this deletes the whole series."""
            return client.delete_event(uid, calendar)

    return mcp


def build_sse_app(mcp: MCPServer, token: str, host: str = "127.0.0.1") -> ASGIApp:
    return BearerAuth(mcp.sse_app(host=host), token)
