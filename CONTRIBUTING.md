# Contributing

1. Install [uv](https://docs.astral.sh/uv/) and run `uv sync`.
2. Branch from `main` and keep the change focused.
3. Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` and `uv run pytest`. Tests
   run against a throwaway local Radicale CalDAV server; no iCloud account is needed.
4. Prefix commit messages with `feat:` or `fix:`.
5. Use synthetic data only: `user@example.com`, placeholder calendars and events.
6. Open a pull request. CI must pass.

Releases follow [ZeroVer](https://0ver.org/) and are cut by tagging `vX.Y.Z`.
