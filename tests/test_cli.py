import pytest

from icloud_calendar_mcp import cli


def test_missing_credentials_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("ICLOUD_APPLE_ID", raising=False)
    monkeypatch.delenv("ICLOUD_APP_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
    assert "ICLOUD_APPLE_ID" in capsys.readouterr().err


def test_sse_requires_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ICLOUD_APPLE_ID", "u@example.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "pw")
    monkeypatch.delenv("MCP_BEARER_TOKEN", raising=False)
    monkeypatch.delenv("MCP_BEARER_TOKEN_FILE", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main(["--transport", "sse"])
    assert exc.value.code == 2
    assert "MCP_BEARER_TOKEN" in capsys.readouterr().err


def test_stdio_runs_server(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[str] = []
    monkeypatch.setenv("ICLOUD_APPLE_ID", "u@example.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "pw")
    monkeypatch.setattr(
        "mcp.server.mcpserver.MCPServer.run", lambda self, transport: ran.append(transport)
    )
    cli.main([])
    assert ran == ["stdio"]


def test_sse_runs_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("ICLOUD_APPLE_ID", "u@example.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "pw")
    monkeypatch.setenv("MCP_BEARER_TOKEN", "tok")
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, **kw: calls.append(kw))
    cli.main(["--transport", "sse", "--host", "127.0.0.2", "--port", "9000"])
    assert calls == [{"host": "127.0.0.2", "port": 9000, "log_level": "warning"}]
