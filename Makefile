.PHONY: help setup doctor test test-agent test-installer test-integration-ssh clean
PYTHON ?= python3
ARGS ?=
help:
	@echo "make setup ARGS='...'"
	@echo "make doctor ARGS='--host 192.168.1.50'"
	@echo "make test"
	@echo "make test-integration-ssh SSH_TEST_HOST=... SSH_TEST_USER=root"
setup:
	$(PYTHON) installer/setup.py $(ARGS)
doctor:
	$(PYTHON) scripts/doctor.py $(ARGS)
test: test-agent test-installer
	$(PYTHON) -m unittest discover -s tests/diagnostics -v
test-agent:
	cd agent && PYTHONPATH=src $(PYTHON) -m unittest discover -s tests -v
test-installer:
	$(PYTHON) -m unittest discover -s installer/tests -v
test-integration-ssh:
	SSH_TEST_HOST=$(SSH_TEST_HOST) SSH_TEST_USER=$(SSH_TEST_USER) SSH_TEST_PORT=$(or $(SSH_TEST_PORT),22) $(PYTHON) -m unittest tests.integration.test_ssh_install -v
clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
