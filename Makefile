.DEFAULT_GOAL := help
.RECIPEPREFIX := >

ENV_FILE ?= router/.env

.PHONY: help up down lock unlock lock-status logs install-router setup setup-poweroff doctor doctor-quick test test-router test-doctor clean

help: ## Mostra questo elenco di comandi
>@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

up: ## Accende la workstation con WoL e attende SSH
>python3 scripts/power.py up --env-file $(ENV_FILE)

down: ## Richiede lo shutdown sicuro senza ignorare i blocker
>python3 scripts/power.py down --env-file $(ENV_FILE)

lock: ## Blocca l'autoshutdown creando un wakelock
>python3 scripts/wakelock.py lock --env-file $(ENV_FILE)

unlock: ## Riabilita l'autoshutdown rimuovendo il wakelock
>python3 scripts/wakelock.py unlock --env-file $(ENV_FILE)

lock-status: ## Mostra wakelock, blocker e stato del Power Agent
>python3 scripts/wakelock.py status --env-file $(ENV_FILE)

logs: ## Segue insieme i log del router e del Power Agent
>ENV_FILE=$(ENV_FILE) scripts/logs.sh

install-router: ## Installa o aggiorna il router always-on e systemd
>python3 installer/install_router.py

setup: ## Installa il Power Agent in modalità osservazione
>python3 installer/setup.py --env-file $(ENV_FILE)

setup-poweroff: ## Installa il Power Agent con poweroff automatico
>python3 installer/setup.py --env-file $(ENV_FILE) --enable-poweroff

doctor: ## Esegue il collaudo end-to-end completo e distruttivo
>python3 scripts/doctor.py --env-file $(ENV_FILE)

doctor-quick: ## Esegue la diagnostica senza power-cycle finale
>python3 scripts/doctor.py --env-file $(ENV_FILE) --quick

test: test-router test-doctor ## Esegue tutti i test e la compilazione Python
>python3 -m compileall -q agent installer scripts router/app

test-router: ## Esegue la suite pytest del router
>cd router && .venv/bin/python -m pytest -q

test-doctor: ## Esegue i test unitari del doctor
>python3 -m unittest discover -s tests/doctor -v

clean: ## Rimuove cache e file Python generati
>find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
>find . -type f -name '*.pyc' -delete
