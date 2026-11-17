# LLM Powersaver Proxy

Sistema semplice per tenere spenta una workstation Proxmox quando non serve, accenderla tramite Wake-on-LAN e rendere trasparente il cold start ai client LiteLLM.

## Componenti

- `router/`: proxy FastAPI always-on già esistente. Avvia la VM LLM tramite API Proxmox e invia WoL quando l'host non è raggiungibile.
- `agent/`: servizio Python installato sull'host Proxmox. VM gaming accesa, heartbeat LLM o wakelock bloccano il poweroff.
- `installer/setup.py`: wizard remoto con build, WoL, attesa SSH, SCP, installazione systemd, health check e rollback.
- `scripts/doctor.py`: collaudo end-to-end, incluso un vero ciclo shutdown/WoL.

Non è presente codice legacy Bash.

## Unica fonte di configurazione

Tutti i comandi leggono `router/.env`. Il wizard aggiunge e aggiorna nello stesso file le variabili `POWER_*` e `AGENT_*`; non stampa un token da copiare altrove.

Partire da:

```bash
cp router/.env.example router/.env
chmod 600 router/.env
```

Compilare le variabili esistenti del router. Per il power management servono anche:

```dotenv
POWER_HOST=192.168.1.85
POWER_SSH_USER=root
POWER_SSH_PORT=22
POWER_GAMING_VMID=100
POWER_LLM_VMID=101
AGENT_PORT=8765
AGENT_TOKEN=
POWER_BOOT_TIMEOUT=180
POWER_SHUTDOWN_TIMEOUT=120
POWER_CYCLE_TEST=false
```

`POWER_HOST` è facoltativo prima del primo setup: il wizard lo ricava da `PROXMOX_BASE_URL`. Se `AGENT_TOKEN` è vuoto, il wizard lo genera e lo salva nel `.env`.

## Installazione

Prima installazione sicura, senza poweroff automatico:

```bash
make setup
```

Installazione con poweroff automatico abilitato:

```bash
make setup-poweroff
```

Il wizard:

1. legge esclusivamente `router/.env`;
2. completa `POWER_HOST`, VMID, porta, timeout e token;
3. prova SSH e invia WoL se necessario;
4. attende il boot;
5. trasferisce il bundle con SCP;
6. installa una release in `/opt/workstation-power-agent/releases/`;
7. aggiorna atomicamente il symlink `current`;
8. configura e avvia `workstation-power-agent.service`;
9. verifica `/health`;
10. ripristina la release precedente se l'installazione fallisce.

## Diagnostica completa

Il doctor è deliberatamente un collaudo funzionale distruttivo. Per autorizzarlo impostare nel `.env`:

```dotenv
POWER_CYCLE_TEST=true
```

Poi eseguire un solo comando:

```bash
make doctor
```

Il collaudo verifica realmente:

- completezza del `.env`;
- servizio e liveness del router;
- WoL e attesa SSH, se la workstation è spenta;
- comandi remoti `python3`, `qm`, `systemctl`, `curl`, `tar`;
- agent systemd enabled/active;
- `/health`, `/status` e autenticazione 401;
- creazione del wakelock e relativo blocker;
- rimozione del wakelock;
- heartbeat LLM e relativo blocker;
- lettura delle VM gaming/LLM con `qm status`;
- richiesta di shutdown sicuro;
- reale scomparsa dell'host da SSH;
- secondo Wake-on-LAN dopo il poweroff;
- boot finale e riavvio automatico dell'agent.

Successo finale:

```text
Outcome: TUTTE LE FUNZIONI VERIFICATE
```

### Precondizione per il test di shutdown

Le VM gaming e LLM devono essere spente e non devono esserci attività LLM o wakelock. `/shutdown` è fail-safe: risponde HTTP 409 anziché spegnere l'host se rileva un blocker. Il doctor rimuove solo i marker creati dal test; non forza lo spegnimento delle VM.

## API agent

- `GET /health`, senza token;
- `GET /status`, Bearer token;
- `POST /activity/llm`, Bearer token;
- `POST /wakelock`, Bearer token;
- `DELETE /wakelock`, Bearer token;
- `POST /shutdown`, Bearer token, eseguito solo senza blocker reali.

## Test non coperti dal doctor

Il doctor non invia una richiesta di inferenza reale a un modello perché modello, payload e credenziali LiteLLM sono deployment-specific. Verifica però router, host, agent, WoL, policy e power cycle. Un test modello può essere aggiunto successivamente usando variabili `DOCTOR_MODEL` e un prompt minimo.

### Output del wizard

Il wizard stampa immediatamente le otto fasi: lettura `.env`, target SSH, verifica SSH, eventuale WoL, attesa boot con tentativi e secondi residui, creazione/trasferimento bundle, installazione remota e risultato finale. SCP e installazione remota hanno timeout espliciti rispettivamente di 120 e 180 secondi.
