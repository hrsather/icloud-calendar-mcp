import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

import icalendar
from caldav.calendarobjectresource import Event
from caldav.collection import Calendar, Principal
from caldav.davclient import DAVClient
from caldav.lib import error as caldav_error

from icloud_calendar_mcp import __version__
from icloud_calendar_mcp.config import Settings

# caldav logs diffs of event data (titles, attendees) on malformed iCalendar; keep that out of logs.
logging.getLogger("caldav").setLevel(logging.CRITICAL)


class CalendarError(Exception):
    """Raised with a plain-string message that is safe to show to the model."""


@contextmanager
def _caldav() -> Iterator[None]:
    try:
        yield
    except CalendarError:
        raise
    except caldav_error.AuthorizationError as exc:
        raise CalendarError("authentication failed: check Apple ID and app password") from exc
    except caldav_error.DAVError as exc:
        raise CalendarError(f"CalDAV error: {exc.reason or type(exc).__name__}") from exc
    except OSError as exc:
        raise CalendarError(f"cannot reach CalDAV server: {type(exc).__name__}") from exc


def parse_when(value: str, tz: ZoneInfo) -> date | datetime:
    """Parse an ISO 8601 date (all-day) or datetime; naive datetimes use `tz`."""
    value = value.strip()
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise CalendarError(f"invalid ISO 8601 date or datetime: {value!r}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=tz)


def _as_datetime(value: date | datetime, tz: ZoneInfo) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz)
    return datetime(value.year, value.month, value.day, tzinfo=tz)


def _format(value: date | datetime, tz: ZoneInfo) -> str:
    if isinstance(value, datetime):
        return _as_datetime(value, tz).astimezone(tz).isoformat()
    return value.isoformat()


def _text(component: Any, key: str) -> str | None:
    value = component.get(key)
    return str(value) if value is not None else None


def _calendar_id(calendar: Calendar) -> str:
    return str(calendar.url).rstrip("/").rsplit("/", 1)[-1]


class CalendarClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tz = ZoneInfo(settings.timezone)
        self._principal: Principal | None = None

    def _get_principal(self) -> Principal:
        if self._principal is None:
            with _caldav():
                client = DAVClient(
                    url=self._settings.caldav_url,
                    username=self._settings.apple_id,
                    password=self._settings.app_password,
                    require_tls=self._settings.caldav_url.startswith("https"),
                )
                self._principal = cast(Principal, client.principal())  # type: ignore[no-untyped-call]
        return self._principal

    def _calendars(self) -> list[Calendar]:
        with _caldav():
            found = cast(list[Calendar], self._get_principal().calendars())
        return [c for c in found if self._supports_events(c)]

    @staticmethod
    def _supports_events(calendar: Calendar) -> bool:
        try:
            components = cast(list[str], calendar.get_supported_components())
        except Exception:
            return True
        return not components or "VEVENT" in components

    def _resolve(self, name: str | None) -> list[Calendar]:
        calendars = self._calendars()
        if name is None:
            return calendars
        matches = [c for c in calendars if name in (c.get_display_name(), _calendar_id(c))]
        if not matches:
            raise CalendarError(f"calendar not found: {name!r}")
        if len(matches) > 1:
            raise CalendarError(f"calendar name is ambiguous, use its id: {name!r}")
        return matches

    def _find(self, uid: str, calendar: str | None) -> tuple[Calendar, Any]:
        for cal in self._resolve(calendar):
            try:
                with _caldav():
                    return cal, cal.event_by_uid(uid)
            except CalendarError as exc:
                if not isinstance(exc.__cause__, caldav_error.NotFoundError):
                    raise
        raise CalendarError(f"event not found: {uid!r}")

    def _event_dict(self, calendar: Calendar, component: Any) -> dict[str, Any]:
        start = component.decoded("DTSTART")
        if "DTEND" in component:
            end = component.decoded("DTEND")
        elif "DURATION" in component:
            end = start + component.decoded("DURATION")
        else:
            end = start + timedelta(days=1) if not isinstance(start, datetime) else start
        rrule = component.get("RRULE")
        return {
            "uid": str(component.get("UID")),
            "calendar": calendar.get_display_name(),
            "summary": _text(component, "SUMMARY") or "",
            "start": _format(start, self._tz),
            "end": _format(end, self._tz),
            "all_day": not isinstance(start, datetime),
            "location": _text(component, "LOCATION"),
            "description": _text(component, "DESCRIPTION"),
            "recurring": rrule is not None or "RECURRENCE-ID" in component,
            "rrule": rrule.to_ical().decode() if rrule is not None else None,
        }

    def list_calendars(self) -> list[dict[str, str]]:
        return [
            {"id": _calendar_id(c), "name": str(c.get_display_name())} for c in self._calendars()
        ]

    def list_events(
        self, start: str, end: str, calendar: str | None = None
    ) -> list[dict[str, Any]]:
        start_dt = _as_datetime(parse_when(start, self._tz), self._tz)
        end_value = parse_when(end, self._tz)
        if not isinstance(end_value, datetime):
            end_value += timedelta(days=1)
        end_dt = _as_datetime(end_value, self._tz)
        if end_dt <= start_dt:
            raise CalendarError("end must be after start")
        events: list[dict[str, Any]] = []
        for cal in self._resolve(calendar):
            with _caldav():
                found = cast(
                    list[Event], cal.search(start=start_dt, end=end_dt, event=True, expand=True)
                )
            for obj in found:
                for component in obj.icalendar_instance.walk("VEVENT"):
                    events.append(self._event_dict(cal, component))
        events.sort(key=lambda e: (e["start"], e["uid"]))
        return events

    @staticmethod
    def _master(obj: Any) -> Any:
        components = list(obj.icalendar_instance.walk("VEVENT"))
        return next((c for c in components if "RECURRENCE-ID" not in c), components[0])

    def get_event(self, uid: str, calendar: str | None = None) -> dict[str, Any]:
        cal, obj = self._find(uid, calendar)
        return self._event_dict(cal, self._master(obj))

    def create_event(
        self,
        calendar: str,
        summary: str,
        start: str,
        end: str | None = None,
        location: str | None = None,
        description: str | None = None,
        rrule: str | None = None,
    ) -> dict[str, Any]:
        cal = self._resolve(calendar)[0]
        start_value = parse_when(start, self._tz)
        end_value: date | datetime
        if end is not None:
            end_value = parse_when(end, self._tz)
        elif isinstance(start_value, datetime):
            end_value = start_value + timedelta(hours=1)
        else:
            end_value = start_value + timedelta(days=1)
        if isinstance(end_value, datetime) != isinstance(start_value, datetime):
            raise CalendarError("start and end must both be dates or both be datetimes")
        if _as_datetime(end_value, self._tz) <= _as_datetime(start_value, self._tz):
            raise CalendarError("end must be after start")

        event = icalendar.Event()
        uid = str(uuid.uuid4())
        event.add("uid", uid)
        event.add("dtstamp", datetime.now(ZoneInfo("UTC")))
        event.add("summary", summary)
        self._set_times(event, start_value, end_value)
        if location:
            event.add("location", location)
        if description:
            event.add("description", description)
        if rrule:
            try:
                parsed = icalendar.vRecur.from_ical(rrule.removeprefix("RRULE:"))
            except ValueError as exc:
                raise CalendarError(f"invalid RRULE: {rrule!r}") from exc
            if "FREQ" not in parsed:
                raise CalendarError(f"invalid RRULE: {rrule!r}")
            event.add("rrule", parsed)
        ical = icalendar.Calendar()
        ical.add("prodid", f"-//icloud-calendar-mcp//{__version__}//EN")
        ical.add("version", "2.0")
        ical.add_component(event)
        ical.add_missing_timezones()
        with _caldav():
            cal.save_event(ical.to_ical().decode())
        return self.get_event(uid, calendar)

    def _set_times(self, component: Any, start: date | datetime, end: date | datetime) -> None:
        for key in ("DTSTART", "DTEND", "DURATION"):
            component.pop(key, None)
        if isinstance(start, datetime):
            start = start.astimezone(self._tz)
            end = _as_datetime(end, self._tz).astimezone(self._tz)
        component.add("dtstart", start)
        component.add("dtend", end)

    def update_event(
        self,
        uid: str,
        calendar: str | None = None,
        summary: str | None = None,
        start: str | None = None,
        end: str | None = None,
        location: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        cal, obj = self._find(uid, calendar)
        component = self._master(obj)
        if summary is not None:
            component["SUMMARY"] = summary
        if location is not None:
            component.pop("LOCATION", None)
            if location:
                component.add("location", location)
        if description is not None:
            component.pop("DESCRIPTION", None)
            if description:
                component.add("description", description)
        if start is not None or end is not None:
            if any(
                "RECURRENCE-ID" in c or "EXDATE" in c for c in obj.icalendar_instance.walk("VEVENT")
            ):
                raise CalendarError(
                    "cannot change the time of a recurring event that has modified or "
                    "excluded occurrences"
                )
            current = self._event_dict(cal, component)
            start_value = parse_when(start or current["start"], self._tz)
            end_value: date | datetime
            if end is not None:
                end_value = parse_when(end, self._tz)
            elif start is not None:
                length = _as_datetime(
                    parse_when(current["end"], self._tz), self._tz
                ) - _as_datetime(parse_when(current["start"], self._tz), self._tz)
                end_value = start_value + length
            else:
                end_value = parse_when(current["end"], self._tz)
            if isinstance(end_value, datetime) != isinstance(start_value, datetime):
                raise CalendarError("start and end must both be dates or both be datetimes")
            if _as_datetime(end_value, self._tz) <= _as_datetime(start_value, self._tz):
                raise CalendarError("end must be after start")
            self._set_times(component, start_value, end_value)
        obj.icalendar_instance.add_missing_timezones()
        with _caldav():
            obj.save()
        return self.get_event(uid, calendar)

    def delete_event(self, uid: str, calendar: str | None = None) -> dict[str, str]:
        _, obj = self._find(uid, calendar)
        with _caldav():
            obj.delete()
        return {"deleted": uid}
