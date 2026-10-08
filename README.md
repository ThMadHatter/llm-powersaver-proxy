# Ollama Proxmox Router

Reverse proxy asincrono per Ollama/LiteLLM con streaming end-to-end, avvio automatico di una VM/CT su Proxmox VE al momento del bisogno (cold start on-demand) e Wake-on-LAN facoltativo.

---

## Indice

1. [Architettura e Funzionamento](#architettura-e-funzionamento)
2. [Guida Rapida con Makefile](#guida-rapida-con-makefile)
3. [Requisiti di Sistema](#requisiti-di-sistema)
4. [Configurazione del Container LXC Debian](#1-crea-il-container-lxc)
5. [Configurazione del Token Proxmox VE](#2-crea-il-token-proxmox-con-privilegi-minimi)
6. [Installazione e Configurazione Interattiva](#3-carica-ed-installa)
7. [Verifica sul Campo della Configurazione (.env)](#4-verifica-della-configurazione- make-verify-config)
8. [Verifica degli Endpoint ed Esempi di Uso](#5-verifica-degli-endpoint)
9. [Configurazione Reverse Proxy (Nginx / Cloudflare)](#6-reverse-proxy)
10. [Endpoint Gaming / Wake-on-LAN](#7-gaming--wake-on-lan)
11. [Guida alle Variabili di Ambiente (.env)](#guida-alle-variabili-di-ambiente-env)
12. [Sviluppo, Linting e Test](#sviluppo-linting-e-test)
13. [Sicurezza](#sicurezza)

---

## Architettura e Funzionamento

- **Reverse Proxy Asincrono**: Costruito su FastAPI, Starlette ed `httpx` per garantire alte prestazioni e basso consumo di memoria.
- **Ispezione HTTP On-Demand**: Il router verifica direttamente lo stato HTTP di Ollama/LiteLLM anziché basarsi su ping ICMP.
- **Cold Start Automatico Proxmox**: Se l'upstream Ollama risulta offline, il router invia la richiesta di avvio della VM/CT tramite API Proxmox VE e attende il completamento dell'avvio prima di inoltrare la richiesta del client.
- **Lock Concorrente**: Un sistema di lock in memoria impedisce avvii multipli o concorrenti della stessa VM/CT.
- **Streaming End-to-End**: Inoltra la risposta chunk-by-chunk (incluso `text/event-stream` per Server-Sent Events / SSE) senza bufferizzare la risposta.
- **Trasparenza Endpoint**: Un'unica route catch-all inoltra senza alterazioni endpoint standard quali `/api/chat`, `/api/generate`, `/v1/chat/completions` e `/v1/models`.

---

## Guida Rapida con Makefile

Il repository include un **Makefile** per facilitare le principali operazioni di installazione, verifica, test e manutenzione:

```bash
make help
```

I comandi principali disponibili tramite `make` sono:

| Comando | Descrizione |
| :--- | :--- |
| `make install` | Avvia l'installer interattivo (richiede privilegi `root` o `sudo`). |
| `make verify-config` | Verifica sul campo che tutti i parametri in `.env` consentano l'esecuzione e la connessione a Proxmox VE, Upstream e WoL. |
| `make test` | Esegue la suite completa di test unitari con `pytest`. |
| `make lint` | Analizza il codice con `Ruff` per verificare lo stile e prevenire errori. |
| `make format` | Corregge e formatta automaticamente il codice sorgente con `Ruff`. |
| `make clean` | Rimuove file temporanei, cache e ambienti `.pytest_cache` / `__pycache__`. |

---

## Requisiti di Sistema

- Host/LXC con Linux (Debian 12 raccomandato).
- Python 3.10 o superiore.
- Accesso di rete verso:
  - Proxmox VE API (di norma porta TCP `:8006`).
  - Upstream Ollama / LiteLLM (di norma porta TCP `:11434`).
  - Indirizzo di Broadcast LAN per l'invio dei pacchetti WoL (di norma porta UDP `:9`).

---

## 1. Crea il container LXC

Dal sito Community Scripts (o tramite GUI Proxmox VE) crea un **Debian LXC**. Impostazioni consigliate:

- **Non privilegiato** (Unprivileged)
- **1 vCPU**
- **512 MB** o **1 GB RAM**
- **4-8 GB disco**
- **IP statico** o prenotazione DHCP
- Accesso di rete verso Proxmox `:8006`, Ollama `:11434` e il broadcast LAN per WoL.
- Nesting non necessario.

*Nota*: Non installare il servizio direttamente sull'host Proxmox VE principale, ma sempre all'interno di un LXC/VM dedicato.

---

## 2. Crea il token Proxmox con privilegi minimi

Nella GUI di Proxmox VE:

1. Vai su `Datacenter > Permissions > Users`: crea un utente dedicato, ad esempio `router@pve`.
2. Vai su `Datacenter > Permissions > API Tokens`: crea il token `ollama-router` per l'utente appena creato. Copia e salva subito il valore `Secret`.
3. Assegna all'utente/token un ruolo con privilegi minimi limitatamente alla sola VM/CT interessata:
   - `VM.Audit` (per leggere lo stato corrente della VM/CT)
   - `VM.PowerMgmt` (per inviare il comando di avvio alla VM/CT)
4. Se è abilitata la **Privilege Separation**, assegna l'ACL direttamente al token (es. `router@pve!ollama-router`).

Il Token ID completo ha forma: `router@pve!ollama-router`.

---

## 3. Carica ed installa

Nel container LXC clona il repository ed esegui l'installer:

```bash
apt-get update && apt-get install -y git make
cd /opt
git clone https://github.com/ThMadHatter/llm-powersaver-proxy.git
cd ollama-proxmox-router
chmod +x scripts/*.sh
make install
```

### Personalizzazione tramite Installer Interattivo

Durante l'esecuzione di `make install` (o `./scripts/install.sh`), l'installer proporrà dei prompt interattivi per definire in maniera attiva:

1. **Path di installazione (`APP_DIR`)**: [Default: `/opt/ollama-router`]
2. **Utente di sistema (`APP_USER`)**: [Default: `ollama-router`]
3. **Host di ascolto (`LISTEN_HOST`)**: [Default: `0.0.0.0`]
4. **Porta di ascolto (`LISTEN_PORT`)**: [Default: `8080`]

*I campi lasciati vuoti (premendo Invio) utilizzeranno automaticamente i valori di default.*

L'installer:
- Creerà l'utente ed la directory di installazione prescelta.
- Creerà l'ambiente virtuale Python `.venv` ed installerà le dipendenze.
- Genererà il file `.env` dal modello `.env.example` se non già presente.
- Adatterà ed installerà automaticamente il servizio systemd (`/etc/systemd/system/ollama-router.service`) sulla base dei percorsi ed utente configurati.

---

## 4. Verifica della Configurazione (`make verify-config`)

Dopo aver compilato il file `.env` con i tuoi parametri:

```bash
nano /opt/ollama-router/.env
```

Genera una chiave API sicura per il router (se non l'hai già definita):

```bash
openssl rand -hex 32
```

Prima di avviare il servizio systemd, puoi testare direttamente sul campo la correttezza di ogni parametro tramite:

```bash
make verify-config
```

Lo script `scripts/verify_config.py`:
1. Validarà la struttura del file `.env` (controllo di tipo e presenza campi obbligatori).
2. Effettuerà una chiamata reale verso le API di Proxmox VE verificando l'autenticazione Token e lo stato attuale della VM/CT.
3. Testarà la raggiungibilità dell'endpoint Upstream Ollama/LiteLLM.
4. Verificherà la correttezza della sintassi del MAC address per il Wake-on-LAN.

Se tutti i controlli hanno esito positivo, avvia e abilita il servizio:

```bash
systemctl restart ollama-router
systemctl status ollama-router --no-pager
journalctl -u ollama-router -f
```

---

## 5. Verifica degli Endpoint

Verifica che il router sia attivo:

```bash
curl http://IP_LXC:8080/health/live
curl -i http://IP_LXC:8080/health/ready
```

### Test Ollama Non-Streaming

```bash
curl -sS http://IP_LXC:8080/api/tags \
  -H 'Authorization: Bearer LA_TUA_ROUTER_API_KEY'
```

### Test Streaming

```bash
export ROUTER_URL=http://IP_LXC:8080
export ROUTER_API_KEY=LA_TUA_ROUTER_API_KEY
./scripts/test_stream.sh
```

### Client Compatibili OpenAI / LiteLLM

Per client compatibili con l'API OpenAI (es. Open WebUI, Jan, Continue, ecc.), imposta:

```text
Base URL: http://IP_LXC:8080/v1
API Key:  <valore di ROUTER_API_KEY>
```

---

## 6. Reverse Proxy

### Esempio Nginx

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

*Nota Cloudflare*: Se utilizzi Cloudflare, escludi questo path dalla cache e disabilita il **Response Body Buffering** per consentire il perfetto funzionamento dello streaming SSE in tempo reale.

---

## 7. Gaming / Wake-on-LAN

Il router offre un endpoint dedicato per l'invio di Magic Packet WoL verso host della LAN (es. PC da gioco):

Compila in `.env` i campi `GAMING_MAC` e `GAMING_BROADCAST`, poi invia una richiesta POST:

```bash
curl -i -X POST http://IP_LXC:8080/gaming/start \
  -H 'Authorization: Bearer LA_TUA_ROUTER_API_KEY'
```

L'endpoint risponde immediatamente con HTTP `202 Accepted`.

---

## Guida alle Variabili di Ambiente (.env)

| Variabile | Default | Descrizione |
| :--- | :--- | :--- |
| `LISTEN_HOST` | `0.0.0.0` | Indirizzo IP di ascolto di Uvicorn. |
| `LISTEN_PORT` | `8080` | Porta TCP di ascolto del proxy router. |
| `LOG_LEVEL` | `INFO` | Livello di log (`DEBUG`, `INFO`, `WARNING`, `ERROR`). |
| `ROUTER_API_KEY` | *(Obbligatorio)* | Chiave segreta richiesta nell'header `Authorization: Bearer <KEY>` (minimo 16 caratteri). |
| `UPSTREAM_BASE_URL` | `http://192.168.1.50:11434` | URL base dell'istanza Ollama o LiteLLM. |
| `UPSTREAM_HEALTH_PATH` | `/api/version` | Path HTTP per verificare lo stato di salute dell'upstream. |
| `UPSTREAM_AUTHORIZATION` | *(Vuoto)* | Header `Authorization` opzionale da inoltrare all'upstream. |
| `PROXMOX_BASE_URL` | `https://192.168.1.10:8006` | URL API dell'host Proxmox VE. |
| `PROXMOX_NODE` | `pve` | Nome del nodo Proxmox su cui risiede la VM/CT. |
| `PROXMOX_VM_TYPE` | `qemu` | Tipo di risorsa su Proxmox: `qemu` (VM) oppure `lxc` (CT). |
| `PROXMOX_VMID` | `101` | VMID numerico della VM o Container. |
| `PROXMOX_TOKEN_ID` | *(Obbligatorio)* | Token ID API Proxmox (es. `user@pve!ollama-router`). |
| `PROXMOX_TOKEN_SECRET` | *(Obbligatorio)* | Secret UUID associato al token Proxmox. |
| `PROXMOX_VERIFY_TLS` | `false` | Se `true`, verifica il certificato SSL/TLS di Proxmox VE. |
| `PROXMOX_CA_FILE` | *(Vuoto)* | Percorso facoltativo al file CA `.pem` per certificati custom. |
| `STARTUP_TIMEOUT` | `180` | Tempo massimo in secondi per l'avvio ed il readiness dell'upstream durante un cold start. |
| `GAMING_MAC` | *(Vuoto)* | MAC Address dell'host per Wake-on-LAN (es. `AA:BB:CC:DD:EE:FF`). |
| `GAMING_BROADCAST` | `255.255.255.255` | Indirizzo di broadcast di rete per il Magic Packet WoL. |

---

## Sviluppo, Linting e Test

Per contribuire o sviluppare sul progetto:

1. Crea e attiva l'ambiente virtuale:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements-dev.txt
   ```

2. Esegui la suite dei test:
   ```bash
   make test
   ```

3. Controlla e formatta il codice:
   ```bash
   make lint
   make format
   ```

---

## Sicurezza

- Non committare mai il file `.env` o le credenziali/secret Proxmox VE.
- Imposta una `ROUTER_API_KEY` complessa (generata ad esempio con `openssl rand -hex 32`).
- Assegna al Token Proxmox VE privilegi strettamente minimi (`VM.Audit` e `VM.PowerMgmt`) limitatamente alla VM/CT interessata.
- Non esporre direttamente la porta 8080 su Internet senza HTTPS ed un adeguato reverse proxy / firewall.
