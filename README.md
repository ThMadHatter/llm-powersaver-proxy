# LLM Powersaver Proxy

Monorepo completa per accendere on-demand una workstation Proxmox, rendere trasparente il cold start ai client LiteLLM e spegnere l'host quando gaming e LLM sono inattivi.

## Componenti

- `router/`: proxy FastAPI always-on, API Proxmox, Wake-on-LAN e heartbeat automatico verso l'agent per tutta la durata delle richieste LiteLLM.
- `agent/`: agent Python Proxmox 0.4.1 con VM gaming come blocker, heartbeat LLM, wakelock, grace period e poweroff automatico.
- `installer/setup.py`: wizard `.env`-driven con WoL, SSH, SCP, installazione versionata, restart reale, health check e rollback.
- `scripts/doctor.py`: collaudo rapido o completo; non effettua inferenze LiteLLM, ma avvia la VM configurata e verifica `running`.

## Configurazione

```bash
cp router/.env.example router/.env
chmod 600 router/.env
```

Tutti i comandi usano `router/.env`. Il wizard genera e salva `AGENT_TOKEN` e completa `POWER_*`/`AGENT_*`.

## Installazione agent

```bash
make setup-poweroff
```

## Doctor

Controlli senza power-cycle finale:

```bash
make doctor-quick
```

Test completo, incluso VM start/stop, shutdown host, WoL, secondo boot e persistenza agent:

```dotenv
POWER_CYCLE_TEST=true
```

```bash
make doctor
```

La modalità completa rifiuta il power-cycle se la VM LLM era già accesa, per non interrompere un workload preesistente.

## Heartbeat automatico

Il router invia subito `POST /activity/llm` e lo rinnova ogni `AGENT_HEARTBEAT_INTERVAL` secondi fino alla chiusura della risposta, incluso streaming. Gli errori heartbeat vengono registrati ma non interrompono la richiesta LLM.

## Sicurezza repository

Il `.gitignore` esclude `.env`, chiavi, cache Python, virtualenv, build, log, file temporanei e archivi generati. `.env.example` resta versionato.
