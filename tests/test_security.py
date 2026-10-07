import pytest
from fastapi import HTTPException

from app.config import Settings
from app.security import verify_router_key


class DummyRequest:
    def __init__(self, path: str, headers: dict):
        self.url = type("URL", (), {"path": path})()
        self.headers = headers


def test_verify_router_key_public_path():
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    req = DummyRequest("/health/live", {})
    # Should not raise exception
    verify_router_key(req, settings)


def test_verify_router_key_valid():
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    req = DummyRequest("/api/chat", {"authorization": "Bearer 1234567890123456"})
    verify_router_key(req, settings)


def test_verify_router_key_invalid():
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    req = DummyRequest("/api/chat", {"authorization": "Bearer wrong_key_0000000"})
    with pytest.raises(HTTPException) as exc_info:
        verify_router_key(req, settings)
    assert exc_info.value.status_code == 401
