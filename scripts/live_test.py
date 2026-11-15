"""Live round-trip against real iCloud: create, read, update and delete one test event.

    ICLOUD_APPLE_ID=... ICLOUD_APP_PASSWORD=... uv run python scripts/live_test.py [calendar]

Without a calendar argument it only lists calendars and exits. The test event is deleted in all
cases, including when a step fails.
"""

import sys

from icloud_calendar_mcp.calendar import CalendarClient, CalendarError
from icloud_calendar_mcp.config import Settings


def main() -> int:
    client = CalendarClient(Settings.from_env())
    calendars = client.list_calendars()
    print("calendars:", ", ".join(c["name"] for c in calendars) or "(none)")
    if len(sys.argv) < 2:
        print("pass a calendar name as the first argument to run the create/update/delete test")
        return 0

    calendar = sys.argv[1]
    uid = None
    try:
        created = client.create_event(
            calendar, "icloud-calendar-mcp live test", "2031-01-15T10:00", location="Test"
        )
        uid = created["uid"]
        print("created:", created["start"], created["end"])
        assert client.get_event(uid)["summary"] == "icloud-calendar-mcp live test"
        assert uid in [e["uid"] for e in client.list_events("2031-01-15", "2031-01-15")]
        updated = client.update_event(uid, summary="icloud-calendar-mcp live test (updated)")
        assert updated["summary"].endswith("(updated)")
        print("read, listed and updated: ok")
    except (CalendarError, AssertionError) as exc:
        print(f"FAILED: {exc}")
        return 1
    finally:
        if uid:
            client.delete_event(uid)
            print("deleted test event")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
