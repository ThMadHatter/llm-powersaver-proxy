#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" -ne 0 ]; then echo "Esegui come root" >&2; exit 1; fi
APP_DIR=/opt/ollama-router
APP_USER=ollama-router
apt-get update
apt-get install -y python3 python3-venv git curl
if ! id "$APP_USER" >/dev/null 2>&1; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cp -a "$SOURCE_DIR/." "$APP_DIR/"
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Creato $APP_DIR/.env: compilalo prima di avviare il servizio."
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
install -m 0644 "$APP_DIR/systemd/ollama-router.service" /etc/systemd/system/ollama-router.service
systemctl daemon-reload
systemctl enable ollama-router.service
echo "Installazione completata. Modifica $APP_DIR/.env, poi: systemctl restart ollama-router"
