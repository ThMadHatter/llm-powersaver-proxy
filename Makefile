.PHONY: install-router setup setup-poweroff doctor doctor-quick test clean
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
test:
	python3 -m compileall -q agent installer scripts router/app
	cd router && python3 -m pytest -q
clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
