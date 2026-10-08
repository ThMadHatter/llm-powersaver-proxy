import httpx

from scripts.verify_config import verify_config


def test_verify_config_success(httpx_mock, monkeypatch):
    monkeypatch.setenv("ROUTER_API_KEY", "1234567890123456")
    monkeypatch.setenv("PROXMOX_TOKEN_ID", "user@pve!token")
    monkeypatch.setenv("PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setenv("PROXMOX_BASE_URL", "https://pve.example.com:8006")
    monkeypatch.setenv("PROXMOX_NODE", "node1")
    monkeypatch.setenv("PROXMOX_VM_TYPE", "qemu")
    monkeypatch.setenv("PROXMOX_VMID", "100")
    monkeypatch.setenv("UPSTREAM_BASE_URL", "http://127.0.0.1:11434")
    monkeypatch.setenv("GAMING_MAC", "AA:BB:CC:DD:EE:FF")

    httpx_mock.add_response(
        url="https://pve.example.com:8006/api2/json/nodes/node1/qemu/100/status/current",
        json={"data": {"status": "running"}},
    )
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/version",
        json={"version": "0.1.0"},
    )

    assert verify_config() is True


def test_verify_config_proxmox_error(httpx_mock, monkeypatch):
    monkeypatch.setenv("ROUTER_API_KEY", "1234567890123456")
    monkeypatch.setenv("PROXMOX_TOKEN_ID", "user@pve!token")
    monkeypatch.setenv("PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setenv("PROXMOX_BASE_URL", "https://pve.example.com:8006")
    monkeypatch.setenv("PROXMOX_NODE", "node1")
    monkeypatch.setenv("PROXMOX_VM_TYPE", "qemu")
    monkeypatch.setenv("PROXMOX_VMID", "100")

    httpx_mock.add_response(
        url="https://pve.example.com:8006/api2/json/nodes/node1/qemu/100/status/current",
        status_code=401,
    )
    httpx_mock.add_response(
        url="http://192.168.1.50:11434/api/version",
        status_code=200,
    )

    assert verify_config() is False


def test_verify_config_proxmox_timeout(httpx_mock, monkeypatch):
    monkeypatch.setenv("ROUTER_API_KEY", "1234567890123456")
    monkeypatch.setenv("PROXMOX_TOKEN_ID", "user@pve!token")
    monkeypatch.setenv("PROXMOX_TOKEN_SECRET", "secret")
    monkeypatch.setenv("PROXMOX_BASE_URL", "https://pve.example.com:8006")
    monkeypatch.setenv("PROXMOX_NODE", "node1")
    monkeypatch.setenv("PROXMOX_VM_TYPE", "qemu")
    monkeypatch.setenv("PROXMOX_VMID", "100")

    httpx_mock.add_exception(
        httpx.ReadTimeout("The read operation timed out"),
        url="https://pve.example.com:8006/api2/json/nodes/node1/qemu/100/status/current",
    )
    httpx_mock.add_response(
        url="http://192.168.1.50:11434/api/version",
        status_code=200,
    )

    assert verify_config() is False
