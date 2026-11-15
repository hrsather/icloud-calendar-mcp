import importlib
import logging


def test_caldav_logger_is_silenced_so_event_content_is_not_logged() -> None:
    importlib.import_module("icloud_calendar_mcp.calendar")
    assert logging.getLogger("caldav").level == logging.CRITICAL
