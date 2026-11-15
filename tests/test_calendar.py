from zoneinfo import ZoneInfo

import pytest

from icloud_calendar_mcp.calendar import CalendarClient, CalendarError, parse_when
from icloud_calendar_mcp.config import Settings

from .support import CREDENTIAL

WEEK = ("2030-01-01", "2030-02-01")


def test_parse_when_variants() -> None:
    tz = ZoneInfo("Europe/London")
    assert parse_when("2030-06-01", tz).isoformat() == "2030-06-01"
    assert parse_when("2030-06-01T10:00", tz).isoformat() == "2030-06-01T10:00:00+01:00"
    assert parse_when("2030-06-01T10:00:00Z", tz).utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    with pytest.raises(CalendarError, match="invalid ISO 8601"):
        parse_when("tomorrow", tz)


def test_list_calendars_only_event_calendars(client: CalendarClient) -> None:
    names = sorted(c["name"] for c in client.list_calendars())
    assert names == ["Home", "Work"]


def test_create_get_list_roundtrip(client: CalendarClient) -> None:
    created = client.create_event(
        "Home", "Dentist", "2030-01-10T09:00", location="Clinic", description="Checkup"
    )
    assert created["summary"] == "Dentist"
    assert created["start"] == "2030-01-10T09:00:00+00:00"
    assert created["end"] == "2030-01-10T10:00:00+00:00"
    assert created["location"] == "Clinic"
    assert created["calendar"] == "Home"
    assert created["recurring"] is False
    assert client.get_event(created["uid"])["description"] == "Checkup"
    listed = client.list_events(*WEEK)
    assert [e["uid"] for e in listed] == [created["uid"]]
    assert client.list_events(*WEEK, calendar="Work") == []


def test_calendar_selectable_by_id(client: CalendarClient) -> None:
    home_id = next(c["id"] for c in client.list_calendars() if c["name"] == "Home")
    created = client.create_event(home_id, "By id", "2030-01-10T09:00")
    assert created["calendar"] == "Home"


def test_all_day_event(client: CalendarClient) -> None:
    created = client.create_event("Home", "Holiday", "2030-01-15")
    assert created["all_day"] is True
    assert created["start"] == "2030-01-15"
    assert created["end"] == "2030-01-16"


def test_update_fields_and_clear(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Old", "2030-01-10T09:00", location="Here")["uid"]
    updated = client.update_event(uid, summary="New", location="", description="Notes")
    assert updated["summary"] == "New"
    assert updated["location"] is None
    assert updated["description"] == "Notes"


def test_update_start_keeps_duration(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Mtg", "2030-01-10T09:00", "2030-01-10T11:00")["uid"]
    updated = client.update_event(uid, start="2030-01-11T13:00")
    assert updated["start"] == "2030-01-11T13:00:00+00:00"
    assert updated["end"] == "2030-01-11T15:00:00+00:00"


def test_update_end_only(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Mtg", "2030-01-10T09:00")["uid"]
    updated = client.update_event(uid, end="2030-01-10T12:00")
    assert updated["end"] == "2030-01-10T12:00:00+00:00"


def test_update_all_day_start(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Day", "2030-01-15")["uid"]
    updated = client.update_event(uid, start="2030-01-20")
    assert (updated["start"], updated["end"]) == ("2030-01-20", "2030-01-21")


def test_delete(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Gone", "2030-01-10T09:00")["uid"]
    assert client.delete_event(uid) == {"deleted": uid}
    assert client.list_events(*WEEK) == []
    with pytest.raises(CalendarError, match="event not found"):
        client.get_event(uid)


def test_recurring_expands_and_acts_on_series(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Standup", "2030-01-07T09:00", rrule="FREQ=WEEKLY;COUNT=3")[
        "uid"
    ]
    occurrences = client.list_events("2030-01-01", "2030-02-01")
    assert [e["start"][:10] for e in occurrences] == ["2030-01-07", "2030-01-14", "2030-01-21"]
    assert {e["uid"] for e in occurrences} == {uid}
    assert all(e["recurring"] for e in occurrences)
    series = client.get_event(uid)
    assert series["rrule"] == "FREQ=WEEKLY;COUNT=3"
    client.update_event(uid, summary="Daily sync")
    assert {e["summary"] for e in client.list_events("2030-01-01", "2030-02-01")} == {"Daily sync"}
    client.delete_event(uid)
    assert client.list_events("2030-01-01", "2030-02-01") == []


def test_timezone_conversion_for_output(client: CalendarClient) -> None:
    created = client.create_event("Home", "Summer", "2030-07-01T12:00:00Z")
    assert created["start"] == "2030-07-01T13:00:00+01:00"


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda c: c.list_events("2030-02-01", "2030-01-01"), "end must be after start"),
        (lambda c: c.list_events(*WEEK, calendar="Nope"), "calendar not found"),
        (lambda c: c.list_events(*WEEK, calendar="Tasks"), "calendar not found"),
        (
            lambda c: c.create_event("Home", "x", "2030-01-01T10:00", "2030-01-01T09:00"),
            "end must be after",
        ),
        (lambda c: c.create_event("Home", "x", "2030-01-01", "2030-01-02T09:00"), "both be dates"),
        (
            lambda c: c.create_event("Home", "x", "2030-01-01T10:00", rrule="NOT-A-RULE"),
            "invalid RRULE",
        ),
        (lambda c: c.create_event("Nope", "x", "2030-01-01T10:00"), "calendar not found"),
        (lambda c: c.get_event("missing-uid"), "event not found"),
        (lambda c: c.update_event("missing-uid", summary="x"), "event not found"),
        (lambda c: c.delete_event("missing-uid"), "event not found"),
    ],
)
def test_error_strings(client: CalendarClient, call, message: str) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(CalendarError, match=message):
        call(client)


def test_update_rejects_inverted_range(client: CalendarClient) -> None:
    uid = client.create_event("Home", "Mtg", "2030-01-10T09:00")["uid"]
    with pytest.raises(CalendarError, match="end must be after start"):
        client.update_event(uid, end="2030-01-10T08:00")


def test_bad_credentials_and_unreachable_server(settings: Settings) -> None:
    unreachable = CalendarClient(
        Settings(apple_id="a", app_password=CREDENTIAL, caldav_url="http://127.0.0.1:1")
    )
    with pytest.raises(CalendarError, match="cannot reach CalDAV server|CalDAV error"):
        unreachable.list_calendars()
