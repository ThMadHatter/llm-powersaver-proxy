import os

import pytest

# Imposta valori di fallback di default per le variabili obbligatorie durante i test
os.environ.setdefault("ROUTER_API_KEY", "1234567890123456")
os.environ.setdefault("PROXMOX_TOKEN_ID", "dummy@pve!token")
os.environ.setdefault("PROXMOX_TOKEN_SECRET", "dummy_secret")

APP_ENV_VARS = [
    "LISTEN_HOST",
    "LISTEN_PORT",
    "LOG_LEVEL",
    "UPSTREAM_BASE_URL",
    "UPSTREAM_AUTHORIZATION",
    "UPSTREAM_HEALTH_PATH",
    "UPSTREAM_CONNECT_TIMEOUT",
    "UPSTREAM_WRITE_TIMEOUT",
    "UPSTREAM_POOL_TIMEOUT",
    "PROXMOX_BASE_URL",
    "PROXMOX_NODE",
    "PROXMOX_VM_TYPE",
    "PROXMOX_VMID",
    "PROXMOX_VERIFY_TLS",
    "PROXMOX_CA_FILE",
    "PROXMOX_TIMEOUT",
    "STARTUP_TIMEOUT",
    "STARTUP_POLL_INITIAL",
    "STARTUP_POLL_MAX",
    "GAMING_MAC",
    "GAMING_BROADCAST",
    "GAMING_WOL_PORT",
    "ENV_FILE",
]


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """
    Ripristina le variabili d'ambiente dell'applicazione ai valori di base di test
    prima di ogni test per garantire test riproducibili ed isolati.
    """
    for var in APP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
