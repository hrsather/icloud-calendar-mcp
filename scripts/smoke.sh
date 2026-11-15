#!/usr/bin/env bash
# Container smoke test: stdio initialize, and SSE 401 without a token / 200 with one.
set -eu

IMAGE="${1:?usage: smoke.sh <image>}"
PORT="${PORT:-18080}"
NAME="icloud-calendar-mcp-smoke-$$"
ENV_ARGS="-e ICLOUD_APPLE_ID=user@example.com -e ICLOUD_APP_PASSWORD=app-password"

cleanup() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}'
# shellcheck disable=SC2086
OUT="$(printf '%s\n' "$INIT" | docker run --rm -i $ENV_ARGS "$IMAGE" | head -n 1)"
case "$OUT" in
  *serverInfo*) echo "stdio initialize ok" ;;
  *) echo "stdio initialize failed: $OUT" >&2; exit 1 ;;
esac

# shellcheck disable=SC2086
docker run -d --name "$NAME" -p "$PORT:8080" $ENV_ARGS -e MCP_BEARER_TOKEN=smoke-token \
  "$IMAGE" --transport sse --host 0.0.0.0 --port 8080 >/dev/null

i=0
until curl -s -o /dev/null "http://127.0.0.1:$PORT/sse"; do
  i=$((i + 1))
  if [ "$i" -gt 50 ]; then
    docker logs "$NAME" >&2
    echo "server did not start" >&2
    exit 1
  fi
  sleep 0.2
done

NO_TOKEN="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/sse")"
[ "$NO_TOKEN" = "401" ] || { echo "expected 401 without token, got $NO_TOKEN" >&2; exit 1; }
echo "sse 401 without token ok"

WITH_TOKEN="$(curl -s -o /dev/null -m 2 -w '%{http_code}' -H 'Authorization: Bearer smoke-token' "http://127.0.0.1:$PORT/sse" || true)"
[ "$WITH_TOKEN" = "200" ] || { echo "expected 200 with token, got $WITH_TOKEN" >&2; exit 1; }
echo "sse 200 with token ok"
