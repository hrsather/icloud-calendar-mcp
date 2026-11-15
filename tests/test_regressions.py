from typing import Any

import pytest

from icloud_calendar_mcp.calendar import CalendarClient, CalendarError
from icloud_calendar_mcp.config import ConfigError, Settings
from icloud_calendar_mcp.server import BearerAuth

OVERRIDE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//test//EN
BEGIN:VEVENT
UID:series-1
DTSTAMP:20300101T000000Z
DTSTART:20300107T090000Z
DTEND:20300107T100000Z
RRULE:FREQ=WEEKLY;COUNT=3
SUMMARY:Series
END:VEVENT
BEGIN:VEVENT
UID:series-1
RECURRENCE-ID:20300114T090000Z
DTSTAMP:20300101T000000Z
DTSTART:20300114T110000Z
DTEND:20300114T120000Z
SUMMARY:Moved occurrence
END:VEVENT
END:VCALENDAR
"""


def test_recurring_event_keeps_local_time_across_dst(client: CalendarClient) -> None:
    client.create_event("Home", "Standup", "2030-03-18T09:00", rrule="FREQ=WEEKLY;COUNT=3")
    starts = [e["start"] for e in client.list_events("2030-03-01", "2030-04-30")]
    assert starts == [
        "2030-03-18T09:00:00+00:00",
        "2030-03-25T09:00:00+00:00",
        "2030-04-01T09:00:00+01:00",
    ]


def test_update_keeps_local_time_across_dst(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Standup", "2030-03-18T09:00", rrule="FREQ=WEEKLY;COUNT=3")[
        "uid"
    ]
    client.update_event(uid, end="2030-03-18T10:30")
    starts = [e["start"] for e in client.list_events("2030-03-01", "2030-04-30")]
    assert starts[-1] == "2030-04-01T09:00:00+01:00"


def test_update_targets_series_master_and_rejects_time_change(client: CalendarClient) -> None:
    client._resolve("Home")[0].save_event(OVERRIDE_ICS)
    updated = client.update_event("series-1", summary="Renamed")
    assert updated["summary"] == "Renamed"
    assert updated["rrule"] == "FREQ=WEEKLY;COUNT=3"
    with pytest.raises(CalendarError, match="modified or excluded occurrences"):
        client.update_event("series-1", start="2030-01-08T09:00")


def test_list_events_date_only_end_is_inclusive(client: CalendarClient) -> None:
    client.create_event("Home", "Today", "2030-01-10T09:00")
    assert len(client.list_events("2030-01-10", "2030-01-10")) == 1


@pytest.mark.parametrize("rule", ["FREQ=SOMETIMES", "FREQ=WEEKLY;BYDAY=XX", "garbage"])
def test_invalid_rrule_strings(client: CalendarClient, rule: str) -> None:
    with pytest.raises(CalendarError, match="invalid RRULE"):
        client.create_event("Home", "x", "2030-01-01T10:00", rrule=rule)


def test_rrule_prefix_is_accepted(client: CalendarClient) -> None:
    created = client.create_event("Home", "x", "2030-01-07T10:00", rrule="RRULE:FREQ=DAILY;COUNT=2")
    assert created["rrule"] == "FREQ=DAILY;COUNT=2"


@pytest.mark.parametrize(("value", "expected"), [("0", False), ("no", False), ("Yes", True)])
def test_read_only_flag_values(value: str, expected: bool) -> None:
    env = {"ICLOUD_APPLE_ID": "a", "ICLOUD_APP_PASSWORD": "b", "ICLOUD_MCP_READ_ONLY": value}
    assert Settings.from_env(env).read_only is expected


def test_read_only_flag_rejects_unknown_values() -> None:
    env = {"ICLOUD_APPLE_ID": "a", "ICLOUD_APP_PASSWORD": "b", "ICLOUD_MCP_READ_ONLY": "enabled"}
    with pytest.raises(ConfigError, match="ICLOUD_MCP_READ_ONLY must be true or false"):
        Settings.from_env(env)


async def test_bearer_auth_guards_websocket_scopes() -> None:
    called: list[bool] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        called.append(True)

    app = BearerAuth(inner, "s3cret")
    await app({"type": "websocket", "headers": []}, None, None)  # type: ignore[arg-type]
    assert called == []
    headers = [(b"authorization", b"Bearer s3cret")]
    await app({"type": "websocket", "headers": headers}, None, None)  # type: ignore[arg-type]
    assert called == [True]
