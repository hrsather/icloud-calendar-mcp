import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_CALDAV_URL = "https://caldav.icloud.com"


class ConfigError(Exception):
    pass


def _read(env: Mapping[str, str], name: str) -> str | None:
    file_name = env.get(f"{name}_FILE")
    if file_name:
        try:
            return Path(file_name).read_text().strip()
        except OSError as exc:
            raise ConfigError(f"cannot read {name}_FILE: {exc.strerror}") from exc
    value = env.get(name)
    return value.strip() if value else None


@dataclass(frozen=True)
class Settings:
    apple_id: str
    app_password: str = field(repr=False)
    bearer_token: str | None = field(default=None, repr=False)
    read_only: bool = False
    timezone: str = "UTC"
    caldav_url: str = DEFAULT_CALDAV_URL

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        apple_id = _read(env, "ICLOUD_APPLE_ID")
        app_password = _read(env, "ICLOUD_APP_PASSWORD")
        if not apple_id or not app_password:
            raise ConfigError("ICLOUD_APPLE_ID and ICLOUD_APP_PASSWORD are required")
        timezone = env.get("ICLOUD_MCP_TIMEZONE") or env.get("TZ") or "UTC"
        try:
            ZoneInfo(timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ConfigError(f"unknown timezone: {timezone}") from exc
        return cls(
            apple_id=apple_id,
            app_password=app_password,
            bearer_token=_read(env, "MCP_BEARER_TOKEN"),
            read_only=env.get("ICLOUD_MCP_READ_ONLY", "").strip().lower() in {"1", "true", "yes"},
            timezone=timezone,
            caldav_url=env.get("ICLOUD_CALDAV_URL") or DEFAULT_CALDAV_URL,
        )
