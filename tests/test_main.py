import pytest
from starlette.requests import ClientDisconnect

from app.config import Settings
from app.main import create_app
from app.proxmox import ProxmoxError


@pytest.fixture
def test_settings():
    return Settings(
        _env_file=None,
        router_api_key="1234567890123456",
        upstream_base_url="http://127.0.0.1:11434",
        proxmox_base_url="https://127.0.0.1:8006",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
        gaming_mac="AA:BB:CC:DD:EE:FF",
        gaming_broadcast="127.0.0.1",
        startup_timeout=1.0,
    )


def test_root_endpoint(test_settings):
    app = create_app(test_settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert res.json() == {"service": "ollama-proxmox-router", "docs": "/docs"}


def test_live_health_endpoint(test_settings):
    app = create_app(test_settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/health/live")
        assert res.status_code == 200
        assert res.json() == {"router": "ok"}


def test_unauthorized_proxy(test_settings):
    app = create_app(test_settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.get("/api/tags")
        assert res.status_code == 401


def test_gaming_start_endpoint(test_settings):
    app = create_app(test_settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.post(
            "/gaming/start",
            headers={"Authorization": f"Bearer {test_settings.router_api_key}"},
        )
        assert res.status_code == 202
        assert res.json()["status"] == "accepted"


def test_gaming_start_not_configured():
    settings = Settings(
        _env_file=None,
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
        gaming_mac="",
    )
    app = create_app(settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
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

    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.post(
            "/api/chat",
            headers={"Authorization": f"Bearer {test_settings.router_api_key}"},
            json={"model": "llama3"},
        )
        assert res.status_code == 499
        assert res.json() == {"detail": "Client disconnesso durante la lettura del body"}


def test_wol_fallback_and_proxmox_boot_retry(test_settings, httpx_mock, monkeypatch):
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/version",
        status_code=503,
    )
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/version",
        status_code=503,
    )
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/version",
        status_code=200,
    )
    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/tags",
        json={"models": []},
    )

    wol_sent = []
    proxmox_calls = 0

    def mock_send_wol(mac, broadcast, port):
        wol_sent.append((mac, broadcast, port))

    async def mock_ensure_started(self):
        nonlocal proxmox_calls
        proxmox_calls += 1
        if proxmox_calls == 1:
            raise ProxmoxError("Host Proxmox offline durante il WoL")
        return True

    monkeypatch.setattr("app.main.send_wol", mock_send_wol)
    monkeypatch.setattr("app.proxmox.ProxmoxClient.ensure_started", mock_ensure_started)

    app = create_app(test_settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.get(
            "/api/tags",
            headers={"Authorization": f"Bearer {test_settings.router_api_key}"},
        )
        assert res.status_code == 200
        assert len(wol_sent) == 1
        assert proxmox_calls == 2


def test_proxmox_error_without_wol(monkeypatch):
    settings = Settings(
        _env_file=None,
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
        upstream_base_url="http://127.0.0.1:11434",
        proxmox_base_url="https://127.0.0.1:8006",
        gaming_mac="",
    )

    async def mock_ensure_started(self):
        raise ProxmoxError("Connection failed")

    monkeypatch.setattr("app.proxmox.ProxmoxClient.ensure_started", mock_ensure_started)

    app = create_app(settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.get(
            "/api/tags",
            headers={"Authorization": f"Bearer {settings.router_api_key}"},
        )
        assert res.status_code == 502


def test_streaming_remote_protocol_error(test_settings, httpx_mock):
    import httpx

    httpx_mock.add_response(
        url="http://127.0.0.1:11434/api/version",
        status_code=200,
    )

    def custom_stream_callback(request):
        class FaultyStream(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"data: chunk1\n\n"
                raise httpx.RemoteProtocolError("peer closed connection without sending complete message body")

        return httpx.Response(
            200,
            stream=FaultyStream(),
            headers={"Content-Type": "text/event-stream"},
        )

    httpx_mock.add_callback(
        custom_stream_callback,
        url="http://127.0.0.1:11434/v1/chat/completions",
        method="POST",
    )

    app = create_app(test_settings)
    with pytest.importorskip("fastapi.testclient").TestClient(app, raise_server_exceptions=False) as client:
        res = client.post(
            "/v1/chat/completions",
            headers={"Authorization": f"Bearer {test_settings.router_api_key}"},
            json={"model": "llama3", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert res.status_code == 200
        # The first chunk should be received before stream drops without crashing the server
        assert b"data: chunk1" in res.content
