import pytest
from fastapi.testclient import TestClient
from starlette.requests import ClientDisconnect

from app.config import Settings
from app.main import create_app


@pytest.fixture
def test_settings():
    return Settings(
        router_api_key="1234567890123456",
        upstream_base_url="http://127.0.0.1:11434",
        proxmox_base_url="https://127.0.0.1:8006",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
        gaming_mac="AA:BB:CC:DD:EE:FF",
        gaming_broadcast="127.0.0.1",
    )


def test_root_endpoint(test_settings):
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert res.json() == {"service": "ollama-proxmox-router", "docs": "/docs"}


def test_live_health_endpoint(test_settings):
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/health/live")
        assert res.status_code == 200
        assert res.json() == {"router": "ok"}


def test_unauthorized_proxy(test_settings):
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/api/tags")
        assert res.status_code == 401


def test_gaming_start_endpoint(test_settings):
    app = create_app(test_settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.post(
            "/gaming/start",
            headers={"Authorization": f"Bearer {test_settings.router_api_key}"},
        )
        assert res.status_code == 202
        assert res.json()["status"] == "accepted"


def test_gaming_start_not_configured():
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
        gaming_mac="",
    )
    app = create_app(settings)
    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.post(
            "/gaming/start",
            headers={"Authorization": f"Bearer {settings.router_api_key}"},
        )
        assert res.status_code == 501


def test_client_disconnect_handling(test_settings, monkeypatch):
    app = create_app(test_settings)

    async def mock_body(self):
        raise ClientDisconnect()

    monkeypatch.setattr("starlette.requests.Request.body", mock_body)

    with TestClient(app, raise_server_exceptions=False) as client:
        res = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {test_settings.router_api_key}"},
            json={"model": "llama3"},
        )
        assert res.status_code == 499
        assert res.json() == {"detail": "Client disconnesso durante la lettura del body"}
