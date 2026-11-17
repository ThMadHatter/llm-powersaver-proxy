# LLM Powersaver Proxy v0.5.0

Monorepo per accendere on-demand una workstation Proxmox, rendere trasparente il cold start ai client LiteLLM e spegnere l'host quando gaming e LLM sono inattivi.

## Componenti

- `router/`: proxy FastAPI always-on, API Proxmox, Wake-on-LAN e heartbeat automatico verso l'agent durante le richieste LiteLLM.
- `agent/`: agent Python 0.4.1 installato sul nodo Proxmox; VM gaming, heartbeat LLM e wakelock bloccano il poweroff.
- `installer/install_router.py`: installa o aggiorna il router nella struttura monorepo, elimina listener Uvicorn orfani, configura systemd e verifica `/health/live`.
- `installer/setup.py`: wizard agent basato su `router/.env`; esegue WoL, SSH, SCP, release versionata, rollback, restart reale e health check.
- `scripts/doctor.py`: collaudo end-to-end senza inferenze LiteLLM. Verifica che la VM LLM vada `running`, poi testa stop, poweroff host, WoL ripetuto, secondo boot e persistenza agent.

## Configurazione

```bash
cp router/.env.example router/.env
chmod 600 router/.env
```

Tutti i comandi usano `router/.env`. Il wizard genera e salva `AGENT_TOKEN` e completa le variabili `POWER_*` e `AGENT_*`.

## Installazione o aggiornamento router

```bash
make install-router
```

Il comando usa `/opt/llm-powersaver-proxy/router`, crea `router/.venv`, installa le dipendenze, installa `litellm-router.service`, termina solo eventuali listener Uvicorn orfani sulla porta configurata e verifica il health check.

## Installazione agent e WoL persistente

```bash
make setup-poweroff
```

Il wizard individua anche interfacce fisiche con nomi come `nic0`, verifica `ethtool` e il supporto Magic Packet `g`, crea `powersaver-wol.service` con `ExecStart` e `ExecStop` shell-safe e corregge eventuali unità legacy che contengono `wol d`.

## Doctor

Test senza power-cycle finale:

```bash
make doctor-quick
```

Test completo:

```dotenv
POWER_CYCLE_TEST=true
```

```bash
make doctor
```

Il boot finale attende 10 secondi dopo il poweroff e ripete il Magic Packet ogni 10 secondi fino al ritorno di SSH. Il test validato sul sistema reale termina con:

```text
PASS: TUTTE LE FUNZIONI OPERATIVE (18 controlli)
```

## Heartbeat automatico

Il router invia `POST /activity/llm` appena una richiesta viene inoltrata e lo rinnova ogni `AGENT_HEARTBEAT_INTERVAL` secondi fino alla chiusura della risposta, incluso streaming. Un errore heartbeat viene registrato ma non interrompe la richiesta LLM.

## Comandi

- `make install-router`: installa/aggiorna il router.
- `make setup`: installa l'agent in osservazione.
- `make setup-poweroff`: installa l'agent con poweroff abilitato.
- `make doctor-quick`: diagnostica senza power-cycle finale.
- `make doctor`: collaudo end-to-end distruttivo.
- `make test`: compilazione e suite test.
- `make clean`: rimuove cache Python.

## Sicurezza repository

Il `.gitignore` esclude `.env`, chiavi, cache Python, virtualenv, build, log, file temporanei e archivi generati. `.env.example` resta versionato.
