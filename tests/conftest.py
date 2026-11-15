import threading
from collections.abc import Iterator
from pathlib import Path
from wsgiref.simple_server import WSGIRequestHandler, make_server

import caldav
import pytest
from radicale import Application
from radicale import config as radicale_config

from icloud_calendar_mcp.calendar import CalendarClient
from icloud_calendar_mcp.config import Settings

from .support import CREDENTIAL


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture(scope="session")
def radicale_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    storage: Path = tmp_path_factory.mktemp("radicale")
    configuration = radicale_config.load()
    configuration.update(
        {
            "auth": {"type": "none"},
            "storage": {"filesystem_folder": str(storage)},
            "logging": {"level": "error"},
        },
        "test",
    )
    httpd = make_server("127.0.0.1", 0, Application(configuration), handler_class=_QuietHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def settings(radicale_url: str) -> Settings:
    return Settings(
        apple_id="user@example.com",
        app_password=CREDENTIAL,
        timezone="Europe/London",
        caldav_url=radicale_url,
    )


@pytest.fixture
def calendars(settings: Settings) -> Iterator[list[str]]:
    principal = caldav.DAVClient(
        url=settings.caldav_url,
        username=settings.apple_id,
        password=settings.app_password,
        require_tls=False,
    ).principal()
    created = [
        principal.make_calendar(name="Home", supported_calendar_component_set=["VEVENT"]),
        principal.make_calendar(name="Work", supported_calendar_component_set=["VEVENT"]),
        principal.make_calendar(name="Tasks", supported_calendar_component_set=["VTODO"]),
    ]
    yield ["Home", "Work", "Tasks"]
    for calendar in created:
        calendar.delete()


@pytest.fixture
def client(settings: Settings, calendars: list[str]) -> CalendarClient:
    return CalendarClient(settings)
