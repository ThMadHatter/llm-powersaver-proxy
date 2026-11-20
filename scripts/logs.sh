#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/router/.env}"
value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -n1; }
HOST="$(value POWER_HOST)"
USER="$(value POWER_SSH_USER)"
PORT="$(value POWER_SSH_PORT)"
USER="${USER:-root}"
PORT="${PORT:-22}"
if [ -z "$HOST" ]; then echo "ERRORE: POWER_HOST mancante in $ENV_FILE" >&2; exit 1; fi
cleanup() { trap - INT TERM EXIT; jobs -pr | xargs -r kill 2>/dev/null || true; wait 2>/dev/null || true; }
trap cleanup INT TERM EXIT
echo "=== LOG ROUTER LOCALE ==="
echo "=== LOG AGENT root@$HOST:$PORT ==="
journalctl -u litellm-router.service -f -n 50 -o cat 2>&1 | sed -u "s/^/[ROUTER] /" &
ROUTER_PID=$!
ssh -p "$PORT" -o BatchMode=yes -o ConnectTimeout=5 "$USER@$HOST" "journalctl -u workstation-power-agent.service -f -n 50 -o cat" 2>&1 | sed -u "s/^/[AGENT]  /" &
AGENT_PID=$!
wait "$ROUTER_PID" "$AGENT_PID"
