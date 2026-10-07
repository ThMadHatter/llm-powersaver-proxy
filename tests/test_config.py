import pytest

from app.config import Settings


def test_settings_default_and_validation():
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    assert settings.listen_host == "0.0.0.0"
    assert settings.listen_port == 8080
    assert settings.upstream_base_url == "http://192.168.1.50:11434"
    assert settings.proxmox_verify is False


def test_settings_strip_slash():
    settings = Settings(
        router_api_key="1234567890123456",
        upstream_base_url="http://192.168.1.50:11434/",
        proxmox_base_url="https://192.168.1.10:8006/",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    assert settings.upstream_base_url == "http://192.168.1.50:11434"
    assert settings.proxmox_base_url == "https://192.168.1.10:8006"


def test_settings_invalid_vm_type():
    with pytest.raises(ValueError):
        Settings(
            router_api_key="1234567890123456",
            proxmox_vm_type="invalid",
            proxmox_token_id="user@pve!token",
            proxmox_token_secret="secret",
        )


def test_settings_short_api_key():
    with pytest.raises(ValueError):
        Settings(
            router_api_key="short",
            proxmox_token_id="user@pve!token",
            proxmox_token_secret="secret",
        )
