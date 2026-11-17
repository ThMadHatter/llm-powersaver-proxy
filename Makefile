.PHONY: setup setup-poweroff doctor test
ENV_FILE ?= router/.env
setup:
	python3 installer/setup.py --env-file $(ENV_FILE)
setup-poweroff:
	python3 installer/setup.py --env-file $(ENV_FILE) --enable-poweroff
doctor:
	python3 scripts/doctor.py --env-file $(ENV_FILE)
test:
	python3 -m compileall -q agent installer scripts router/app
	cd router && python3 -m pytest -q
