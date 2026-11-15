import pytest

from icloud_calendar_mcp.calendar import CalendarClient

HEAD = "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//test//EN\nBEGIN:VEVENT\nDTSTAMP:20300101T000000Z\n"
TAIL = "END:VEVENT\nEND:VCALENDAR\n"


def _save(client: CalendarClient, uid: str, body: str) -> None:
    client._resolve("Home")[0].save_event(f"{HEAD}UID:{uid}\nSUMMARY:{uid}\n{body}{TAIL}")


@pytest.mark.parametrize(
    ("body", "start", "end", "all_day"),
    [
        (
            "DTSTART:20300107T090000\nDTEND:20300107T100000\n",
            "2030-01-07T09:00:00+00:00",
            "2030-01-07T10:00:00+00:00",
            False,
        ),
        (
            "DTSTART:20300107T090000Z\nDURATION:PT90M\n",
            "2030-01-07T09:00:00+00:00",
            "2030-01-07T10:30:00+00:00",
            False,
        ),
        (
            "DTSTART:20300107T090000Z\n",
            "2030-01-07T09:00:00+00:00",
            "2030-01-07T09:00:00+00:00",
            False,
        ),
        ("DTSTART;VALUE=DATE:20300107\n", "2030-01-07", "2030-01-08", True),
        (
            "DTSTART;VALUE=DATE:20300107\nDTEND;VALUE=DATE:20300110\n",
            "2030-01-07",
            "2030-01-10",
            True,
        ),
        ("DTSTART;VALUE=DATE:20300107\nDURATION:P2D\n", "2030-01-07", "2030-01-09", True),
        (
            "DTSTART;TZID=America/New_York:20300107T090000\n"
            "DTEND;TZID=America/New_York:20300107T100000\n",
            "2030-01-07T14:00:00+00:00",
            "2030-01-07T15:00:00+00:00",
            False,
        ),
        (
            "DTSTART;TZID=America/New_York:20300107T090000\n"
            "DTEND;TZID=Europe/London:20300107T150000\n",
            "2030-01-07T14:00:00+00:00",
            "2030-01-07T15:00:00+00:00",
            False,
        ),
    ],
)
def test_event_shapes(
    client: CalendarClient, body: str, start: str, end: str, all_day: bool
) -> None:
    _save(client, "shape", body)
    event = client.get_event("shape")
    assert (event["start"], event["end"], event["all_day"]) == (start, end, all_day)
    listed = client.list_events("2030-01-01", "2030-01-31")
    assert [(e["start"], e["end"]) for e in listed] == [(start, end)]


def test_exdate_and_cancelled_occurrences_are_not_listed(client: CalendarClient) -> None:
    _save(
        client,
        "ex",
        "DTSTART:20300107T090000Z\nDTEND:20300107T100000Z\nRRULE:FREQ=WEEKLY;COUNT=3\n"
        "EXDATE:20300114T090000Z\n",
    )
    starts = [e["start"][:10] for e in client.list_events("2030-01-01", "2030-02-01")]
    assert starts == ["2030-01-07", "2030-01-21"]


def test_special_characters_and_folded_text_roundtrip(client: CalendarClient) -> None:
    created = client.create_event(
        "Home",
        "Lunch, with; semi\\colon é中",
        "2030-01-07T12:00",
        location="Café, 1st Ave",
        description="line one\nline two " + "x" * 200,
    )
    fetched = client.get_event(created["uid"])
    assert fetched["summary"] == "Lunch, with; semi\\colon é中"
    assert fetched["location"] == "Café, 1st Ave"
    assert fetched["description"] == "line one\nline two " + "x" * 200
