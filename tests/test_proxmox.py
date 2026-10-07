import pytest

from app.config import Settings
from app.proxmox import ProxmoxClient, ProxmoxError


@pytest.mark.asyncio
async def test_proxmox_urls():
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_base_url="https://pve.example.com:8006",
        proxmox_node="node1",
        proxmox_vm_type="qemu",
        proxmox_vmid=100,
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    client = ProxmoxClient(settings)
    assert client.status_url == "https://pve.example.com:8006/api2/json/nodes/node1/qemu/100/status/current"
    assert client.start_url == "https://pve.example.com:8006/api2/json/nodes/node1/qemu/100/status/start"
    await client.close()


@pytest.mark.asyncio
async def test_proxmox_status_running(httpx_mock):
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_base_url="https://pve.example.com:8006",
        proxmox_node="node1",
        proxmox_vm_type="qemu",
        proxmox_vmid=100,
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    client = ProxmoxClient(settings)

    # Mock status response twice or allow reuse
    httpx_mock.add_response(
        url=client.status_url,
        json={"data": {"status": "running"}},
    )

    status = await client.status()
    assert status == "running"

    httpx_mock.add_response(
        url=client.status_url,
        json={"data": {"status": "running"}},
    )
    started = await client.ensure_started()
    assert started is False
    await client.close()


@pytest.mark.asyncio
async def test_proxmox_ensure_started_stopped(httpx_mock):
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_base_url="https://pve.example.com:8006",
        proxmox_node="node1",
        proxmox_vm_type="qemu",
        proxmox_vmid=100,
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    client = ProxmoxClient(settings)

    httpx_mock.add_response(
        url=client.status_url,
        json={"data": {"status": "stopped"}},
    )
    httpx_mock.add_response(
        url=client.start_url,
        json={"data": "UPID:node1:00001:00001:start"},
    )

    started = await client.ensure_started()
    assert started is True
    await client.close()


@pytest.mark.asyncio
async def test_proxmox_ensure_started_error(httpx_mock):
    settings = Settings(
        router_api_key="1234567890123456",
        proxmox_base_url="https://pve.example.com:8006",
        proxmox_token_id="user@pve!token",
        proxmox_token_secret="secret",
    )
    client = ProxmoxClient(settings)

    httpx_mock.add_response(
        url=client.status_url,
        status_code=500,
    )

    with pytest.raises(ProxmoxError):
        await client.ensure_started()
    await client.close()
