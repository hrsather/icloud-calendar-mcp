from pathlib import Path

import pytest

from icloud_calendar_mcp.config import ConfigError, Settings

from .support import BEARER, CREDENTIAL


def test_defaults() -> None:
    settings = Settings.from_env({"ICLOUD_APPLE_ID": "u@example.com", "ICLOUD_APP_PASSWORD": "pw"})
    assert settings.timezone == "UTC"
    assert settings.read_only is False
    assert settings.bearer_token is None
    assert settings.caldav_url == "https://caldav.icloud.com"


def test_all_options() -> None:
    bearer = "bearer-value"
    settings = Settings.from_env(
        {
            "ICLOUD_APPLE_ID": "u@example.com",
            "ICLOUD_APP_PASSWORD": "pw",
            "MCP_BEARER_TOKEN": bearer,
            "ICLOUD_MCP_READ_ONLY": "TRUE",
            "TZ": "Europe/London",
            "ICLOUD_MCP_TIMEZONE": "Asia/Tokyo",
        }
    )
    assert settings.read_only is True
    assert settings.bearer_token == bearer
    assert settings.timezone == "Asia/Tokyo"


def test_tz_fallback() -> None:
    env = {"ICLOUD_APPLE_ID": "a", "ICLOUD_APP_PASSWORD": "b", "TZ": "Europe/London"}
    assert Settings.from_env(env).timezone == "Europe/London"


def test_file_variants(tmp_path: Path) -> None:
    file_key, file_bearer = "key-from-file", "bearer-from-file"
    password = tmp_path / "password"
    password.write_text(f"{file_key}\n")
    token = tmp_path / "token"
    token.write_text(f"{file_bearer}\n")
    settings = Settings.from_env(
        {
            "ICLOUD_APPLE_ID": "u@example.com",
            "ICLOUD_APP_PASSWORD_FILE": str(password),
            "MCP_BEARER_TOKEN_FILE": str(token),
        }
    )
    assert settings.app_password == file_key
    assert settings.bearer_token == file_bearer


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="ICLOUD_APP_PASSWORD_FILE"):
        Settings.from_env(
            {
                "ICLOUD_APPLE_ID": "a",
                "ICLOUD_APP_PASSWORD_FILE": str(tmp_path / "absent"),
            }
        )


@pytest.mark.parametrize(
    "env",
    [{}, {"ICLOUD_APPLE_ID": "a"}, {"ICLOUD_APP_PASSWORD": "b"}],
)
def test_missing_credentials(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError, match="required"):
        Settings.from_env(env)


def test_bad_timezone() -> None:
    env = {"ICLOUD_APPLE_ID": "a", "ICLOUD_APP_PASSWORD": "b", "ICLOUD_MCP_TIMEZONE": "Mars/Base"}
    with pytest.raises(ConfigError, match="unknown timezone"):
        Settings.from_env(env)


def test_secrets_not_in_repr() -> None:
    settings = Settings(apple_id="a", app_password=CREDENTIAL, bearer_token=BEARER)
    assert CREDENTIAL not in repr(settings)
    assert BEARER not in repr(settings)
