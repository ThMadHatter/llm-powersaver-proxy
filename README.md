# Workstation Powersaver

Tool minimale per gestire una workstation Proxmox accesa on-demand.

## Cosa fa oggi

La repository contiene tre elementi:

- `router/`: servizio FastAPI always-on. Espone un proxy OpenAI-compatible, controlla LiteLLM, avvia la VM LLM tramite API Proxmox e invia Wake-on-LAN quando Proxmox non e raggiungibile. L'endpoint manuale WoL attualmente implementato e `POST /gaming/start`.
- `agent/`: servizio Python installato direttamente sull'host Proxmox. Controlla le VM gaming e LLM tramite `qm status`, riceve heartbeat LLM, gestisce il wakelock e decide se l'host puo essere spento.
- `installer/`: wizard che costruisce il bundle, usa WoL se necessario, attende SSH, trasferisce con `scp`, installa una release versionata, esegue health check e ripristina la release precedente in caso di errore.

La repository non include il precedente script Bash di autoshutdown, timer Git o deployment legacy.

## Comportamento operativo

- VM gaming `running`: spegnimento sempre bloccato.
- Attivita LLM recente: spegnimento bloccato.
- Wakelock presente: spegnimento bloccato.
- Stato di una VM `unknown`: spegnimento bloccato in modo fail-safe.
- Nessun blocker: trascorsa la grace period, l'agent puo eseguire `systemctl poweroff`.

Per impostazione predefinita il wizard installa l'agent con `observe_only = true`. In questa modalita la decisione viene calcolata ed esposta, ma il poweroff non viene eseguito. Il poweroff reale richiede `--enable-poweroff`.

## Requisiti

### Macchina always-on

- Linux con Python 3.11 o successivo;
- `ssh` e `scp`;
- router installato secondo `router/README.md`;
- chiave SSH non interattiva verso l'host Proxmox.

### Host Proxmox

- Proxmox VE/Debian con Python 3.11 o successivo;
- `qm`, `systemctl`, `curl` e `tar`;
- accesso SSH root nella baseline corrente;
- VMID gaming e LLM validi.

## Installazione dell'agent

```bash
make setup ARGS="\
  --host 192.168.1.50 \
  --ssh-user root \
  --mac AA:BB:CC:DD:EE:FF \
  --broadcast 192.168.1.255 \
  --gaming-vmid 100 \
  --llm-vmid 101 \
  --yes"
```

Il wizard installa:

```text
/opt/workstation-power-agent/releases/<timestamp>
/opt/workstation-power-agent/current
/etc/workstation-power-agent/config.toml
/etc/workstation-power-agent/token
/etc/systemd/system/workstation-power-agent.service
```

Per abilitare lo spegnimento reale, ripetere il setup aggiungendo:

```bash
--enable-poweroff
```

## API agent

Porta predefinita: `8765`.

| Metodo | Endpoint | Autenticazione | Funzione |
|---|---|---|---|
| GET | `/health` | No | Health check |
| GET | `/status` | Bearer token | Stato VM, blocker e modalita osservazione |
| POST | `/activity/llm` | Bearer token | Rinnova l'attivita LLM |
| POST | `/wakelock` | Bearer token | Crea il wakelock |

Il token si trova sull'host in `/etc/workstation-power-agent/token` con permessi `0600`.

## Diagnostica con un singolo comando

Dalla root della repository sulla macchina always-on:

```bash
make doctor ARGS="--host 192.168.1.50 --ssh-user root"
```

Se la configurazione router non e in `/opt/litellm-router/.env`:

```bash
make doctor ARGS="\
  --env-file router/.env \
  --host 192.168.1.50 \
  --ssh-user root"
```

La checklist verifica:

1. presenza delle variabili essenziali del router;
2. validita della configurazione Wake-on-LAN;
3. servizio `litellm-router.service` attivo;
4. `/health/live` del router;
5. `/health/ready` del router;
6. accesso SSH all'host Proxmox;
7. presenza di Python, `qm`, `systemctl`, `curl` e `tar`;
8. agent systemd `enabled` e `active`;
9. token agent;
10. `/health` e `/status` dell'agent;
11. visibilita delle VM 100 e 101;
12. rifiuto HTTP 401 senza token.

`/health/ready` puo restituire HTTP 503 quando la workstation o LiteLLM sono spenti. Per il modello on-demand viene riportato come `WARN`, non come guasto. Il comando termina con codice `1` se esiste almeno un `FAIL`. Con `--strict`, anche `WARN` e `SKIP` producono codice `2`.

Il check WoL e configurativo: non spegne la workstation per provare un'accensione reale. Il test end-to-end del WoL va eseguito deliberatamente a host spento con il wizard o con l'endpoint `POST /gaming/start`.

## Test

Test locali:

```bash
make test
```

Test d'integrazione su un host reale, sempre in `observe_only=true`:

```bash
make test-integration-ssh \
  SSH_TEST_HOST=192.168.1.50 \
  SSH_TEST_USER=root
```

La suite SSH verifica installazione, systemd, API autenticata, aggiornamento e rollback. La porta di test predefinita e `18765`.

## Limiti attuali

- Il router non invia ancora automaticamente l'heartbeat a `POST /activity/llm`.
- Il router mantiene ancora il nome endpoint `POST /gaming/start`, non `/power/wake`.
- Il wizard stampa il token dopo l'installazione, ma non lo inserisce automaticamente nella configurazione del router.
- Non viene configurato automaticamente il firewall della porta `8765`.
- L'API agent implementa la creazione del wakelock, ma non ancora la sua rimozione via `DELETE`.
