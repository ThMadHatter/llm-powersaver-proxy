# Ollama Proxmox Router

Reverse proxy asincrono per Ollama/LiteLLM con streaming end-to-end, avvio automatico di una VM/CT su Proxmox e Wake-on-LAN facoltativo.

## Architettura

- Il router gira in un LXC Debian sempre acceso.
- Controlla direttamente l'endpoint HTTP di Ollama, non ICMP/ping.
- Se Ollama non risponde, legge lo stato della VM/CT e la avvia via API Proxmox.
- Un lock impedisce avvii concorrenti nello stesso processo.
- La risposta upstream viene inoltrata a chunk, incluso `text/event-stream`.
- Un'unica route proxy conserva endpoint come `/api/chat`, `/api/generate`, `/v1/chat/completions` e `/v1/models`.

## 1. Crea il container LXC

Dal sito Community Scripts crea un **Debian LXC**. Impostazioni consigliate:

- non privilegiato;
- 1 vCPU;
- 512 MB o 1 GB RAM;
- 4-8 GB disco;
- IP statico o prenotazione DHCP;
- accesso di rete verso Proxmox `:8006`, Ollama `:11434` e il broadcast LAN per WOL;
- nesting non necessario.

Non installare il servizio sull'host Proxmox.

## 2. Crea il token Proxmox con privilegi minimi

Nella GUI Proxmox:

1. `Datacenter > Permissions > Users`: crea ad esempio `router@pve`.
2. `Datacenter > Permissions > API Tokens`: crea il token `ollama-router` e salva subito il secret.
3. Assegna al token o all'utente, sul solo path della VM/CT interessata, un ruolo che includa almeno:
   - `VM.Audit`
   - `VM.PowerMgmt`
4. Se abiliti **Privilege Separation**, assegna l'ACL anche al token, non soltanto all'utente.

Il token ID completo ha forma `router@pve!ollama-router`.

## 3. Carica e installa

Nel LXC:

```bash
apt-get update && apt-get install -y git
cd /opt
https://github.com/ThMadHatter/llm-powersaver-proxy.git
cd ollama-proxmox-router
chmod +x scripts/*.sh
./scripts/install.sh
```

Modifica il file locale dei segreti:

```bash
nano /opt/ollama-router/.env
```

Genera una chiave del router:

```bash
openssl rand -hex 32
```

Poi avvia:

```bash
systemctl restart ollama-router
systemctl status ollama-router --no-pager
journalctl -u ollama-router -f
```

`.env` è escluso da Git. Committa soltanto `.env.example`.

## 4. Verifica

```bash
curl http://IP_LXC:8080/health/live
curl -i http://IP_LXC:8080/health/ready
```

Test Ollama non-streaming:

```bash
curl -sS http://IP_LXC:8080/api/tags \
  -H 'Authorization: Bearer LA_TUA_ROUTER_API_KEY'
```

Test streaming:

```bash
export ROUTER_URL=http://IP_LXC:8080
export ROUTER_API_KEY=LA_TUA_ROUTER_API_KEY
./scripts/test_stream.sh
```

Per un client OpenAI-compatible usa:

```text
base_url = http://IP_LXC:8080/v1
api_key  = valore di ROUTER_API_KEY
```

## 5. Reverse proxy

Esempio Nginx:

```nginx
location /workstation-proxy/ {
    proxy_pass http://IP_LXC:8080/;
    proxy_http_version 1.1;
    proxy_buffering off;
    proxy_request_buffering off;
    proxy_cache off;
    gzip off;
    proxy_read_timeout 1800s;
    proxy_send_timeout 1800s;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Con Cloudflare, escludi il path dalla cache e disabilita il **response body buffering** solo per questo endpoint. Verifica prima lo streaming direttamente sull'IP LXC, poi attraverso Nginx e infine attraverso Cloudflare: così individui subito il livello che introduce buffering.

## 6. Gaming / Wake-on-LAN

Compila `GAMING_MAC` e `GAMING_BROADCAST`, poi:

```bash
curl -i -X POST http://IP_LXC:8080/gaming/start \
  -H 'Authorization: Bearer LA_TUA_ROUTER_API_KEY'
```

L'endpoint restituisce `202 Accepted` subito dopo l'invio del magic packet. Se il WOL non attraversa la rete, controlla broadcast, VLAN e firewall del LXC.

## Aggiornamento

```bash
cd /opt/ollama-proxmox-router
git pull
./scripts/install.sh
systemctl restart ollama-router
```

Se il repository sorgente non coincide con `/opt/ollama-router`, l'installer copia il contenuto in quella directory. Il file `.env` esistente non viene sovrascritto.

## Sviluppo e test

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
ruff check app tests
```

## Sicurezza

- Non pubblicare `.env` o il secret Proxmox.
- Usa un token Proxmox dedicato e ACL limitate alla sola VM/CT.
- Preferisci TLS valido o una CA privata configurata con `PROXMOX_CA_FILE`.
- Non esporre direttamente la porta 8080 a Internet.
- Mantieni un solo worker Uvicorn: il lock di avvio è in memoria. Per più worker/repliche serve un lock distribuito.
