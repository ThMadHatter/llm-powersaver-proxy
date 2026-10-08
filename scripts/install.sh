#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Errore: Esegui questo script come root (o tramite sudo)." >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Valori di default
DEFAULT_APP_DIR="$SOURCE_DIR"
DEFAULT_APP_USER="ollama-router"
DEFAULT_LISTEN_HOST="0.0.0.0"
DEFAULT_LISTEN_PORT="8080"

# Funzione helper per chiedere input con valore di default
prompt_input() {
  local prompt_text="$1"
  local default_val="$2"
  local env_var_val="$3"
  local user_val=""

  # Se siamo in ambiente non interattivo o se è passata una var d'ambiente specifica
  if [ -n "$env_var_val" ]; then
    echo "$env_var_val"
    return
  fi

  if [ -t 0 ]; then
    read -rp "$prompt_text [$default_val]: " user_val
    if [ -z "$user_val" ]; then
      echo "$default_val"
    else
      echo "$user_val"
    fi
  else
    echo "$default_val"
  fi
}

echo "=================================================="
echo " Configurazione Installazione Ollama Proxmox Router "
echo "=================================================="

APP_DIR=$(prompt_input "Percorso di installazione (APP_DIR)" "$DEFAULT_APP_DIR" "${APP_DIR:-}")
APP_USER=$(prompt_input "Utente di sistema per il servizio (APP_USER)" "$DEFAULT_APP_USER" "${APP_USER:-}")
LISTEN_HOST=$(prompt_input "Host di ascolto per uvicorn (LISTEN_HOST)" "$DEFAULT_LISTEN_HOST" "${LISTEN_HOST:-}")
LISTEN_PORT=$(prompt_input "Porta di ascolto per uvicorn (LISTEN_PORT)" "$DEFAULT_LISTEN_PORT" "${LISTEN_PORT:-}")

echo "--------------------------------------------------"
echo "Parametri selezionati:"
echo "  APP_DIR:     $APP_DIR"
echo "  APP_USER:    $APP_USER"
echo "  LISTEN_HOST: $LISTEN_HOST"
echo "  LISTEN_PORT: $LISTEN_PORT"
echo "--------------------------------------------------"

echo "Installazione dipendenze di sistema (apt)..."
apt-get update
apt-get install -y python3 python3-venv git curl

# Creazione utente di sistema se non esiste
if ! id "$APP_USER" >/dev/null 2>&1; then
  echo "Creazione utente di sistema '$APP_USER'..."
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

# Creazione directory ed installazione dei sorgenti
install -d -o "$APP_USER" -g "$APP_USER" "$APP_DIR"
if [ "$SOURCE_DIR" != "$APP_DIR" ]; then
  echo "Copia dei file sorgente da $SOURCE_DIR in $APP_DIR..."
  cp -a "$SOURCE_DIR/." "$APP_DIR/"
fi

# Configurazione virtualenv e dipendenze Python
echo "Configurazione dell'ambiente virtuale Python in $APP_DIR/.venv..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip wheel
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# Gestione del file .env
if [ ! -f "$APP_DIR/.env" ]; then
  echo "Creazione file di configurazione $APP_DIR/.env..."
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  # Aggiorna LISTEN_HOST e LISTEN_PORT se definiti diversamente nei prompt
  sed -i "s/^LISTEN_HOST=.*/LISTEN_HOST=$LISTEN_HOST/" "$APP_DIR/.env"
  sed -i "s/^LISTEN_PORT=.*/LISTEN_PORT=$LISTEN_PORT/" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
  echo "Creato $APP_DIR/.env: ricordati di modificarlo inserendo chiavi e secret."
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# Creazione personalizzata del file di servizio systemd
SERVICE_FILE="/etc/systemd/system/ollama-router.service"
echo "Generazione file di servizio systemd ($SERVICE_FILE)..."

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Ollama Proxmox Router
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/uvicorn app.main:app --host \${LISTEN_HOST} --port \${LISTEN_PORT} --workers 1 --proxy-headers --forwarded-allow-ips=*
Restart=always
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ollama-router.service

echo "=================================================="
echo " Installazione completata con successo!           "
echo " Modifica il file $APP_DIR/.env, poi avvia:       "
echo "   systemctl restart ollama-router                "
echo "=================================================="
