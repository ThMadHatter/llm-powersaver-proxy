.PHONY: install-router setup setup-poweroff doctor doctor-quick test test-router test-doctor clean
ENV_FILE ?= router/.env

install-router:
	python3 installer/install_router.py

setup:
	python3 installer/setup.py --env-file $(ENV_FILE)

setup-poweroff:
	python3 installer/setup.py --env-file $(ENV_FILE) --enable-poweroff

doctor:
	python3 scripts/doctor.py --env-file $(ENV_FILE)

doctor-quick:
	python3 scripts/doctor.py --env-file $(ENV_FILE) --quick

test: test-router test-doctor
	python3 -m compileall -q agent installer scripts router/app

test-router:
	cd router && .venv/bin/python -m pytest -q

test-doctor:
	python3 -m unittest discover -s tests/doctor -v

clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \) -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
