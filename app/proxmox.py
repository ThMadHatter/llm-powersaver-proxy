import httpx

from .config import Settings


class ProxmoxError(RuntimeError):
    pass


class ProxmoxClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(
            timeout=settings.proxmox_timeout,
            verify=settings.proxmox_verify,
            headers={"Authorization": f"PVEAPIToken={settings.proxmox_token_id}={settings.proxmox_token_secret}"},
        )

    @property
    def status_url(self) -> str:
        s = self.settings
        return (
            f"{s.proxmox_base_url}/api2/json/nodes/{s.proxmox_node}/{s.proxmox_vm_type}/{s.proxmox_vmid}/status/current"
        )

    @property
    def start_url(self) -> str:
        s = self.settings
        return (
            f"{s.proxmox_base_url}/api2/json/nodes/{s.proxmox_node}/{s.proxmox_vm_type}/{s.proxmox_vmid}/status/start"
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def status(self) -> str:
        response = await self.client.get(self.status_url)
        response.raise_for_status()
        return response.json()["data"]["status"]

    async def ensure_started(self) -> bool:
        try:
            if await self.status() == "running":
                return False
            response = await self.client.post(self.start_url)
            response.raise_for_status()
            return True
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise ProxmoxError(f"Errore API Proxmox: {exc}") from exc
