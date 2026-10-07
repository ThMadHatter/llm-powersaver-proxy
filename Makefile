.PHONY: help test verify-config install lint format clean

.DEFAULT_GOAL := help

PYTHON ?= python3

help: ## Mostra questa guida di aiuto
	@echo "Comandi disponibili:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

test: ## Esegue la suite completa dei test unitari
	$(PYTHON) -m pytest

verify-config: ## Verifica sul campo se i parametri in .env consentono l'esecuzione dei comandi
	$(PYTHON) scripts/verify_config.py

install: ## Esegue l'installer interattivo (richiede privilegi root)
	./scripts/install.sh

lint: ## Controlla lo stile e la sintassi del codice con Ruff
	ruff check app tests scripts

format: ## Formatta il codice e corregge gli errori automatici con Ruff
	ruff check --fix app tests scripts
	ruff format app tests scripts

clean: ## Rimuove file temporanei e cache di Python/pytest
	rm -rf .pytest_cache .venv build dist *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
