import pytest

APP_ENV_VARS = [
    "LISTEN_HOST",
    "LISTEN_PORT",
    "LOG_LEVEL",
    "ROUTER_API_KEY",
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
    "PROXMOX_TOKEN_ID",
    "PROXMOX_TOKEN_SECRET",
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
    Rimuove qualsiasi variabile d'ambiente dell'applicazione presente nell'ambiente host
    prima di ogni test per garantire test riproducibili ed isolati.
    """
    for var in APP_ENV_VARS:
        monkeypatch.delenv(var, raising=False)
