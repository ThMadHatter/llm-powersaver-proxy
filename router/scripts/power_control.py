#!/usr/bin/env python3
"""Controlli manuali di accensione e spegnimento per il Makefile."""

import argparse
import asyncio
import sys
from pathlib import Path

# Permette l'esecuzione diretta dalla directory scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings
from app.proxmox import ProxmoxClient, ProxmoxError
from app.wol import send_wol


def send_configured_wol() -> None:
    settings = get_settings()
    if not settings.gaming_mac:
        raise SystemExit("Errore: GAMING_MAC non configurato nel file .env")
    send_wol(settings.gaming_mac, settings.gaming_broadcast, settings.gaming_wol_port)
    print(
        f"Wake-on-LAN inviato a {settings.gaming_mac} "
        f"via {settings.gaming_broadcast}:{settings.gaming_wol_port}"
    )


async def shutdown_vm() -> None:
    settings = get_settings()
    client = ProxmoxClient(settings)
    try:
        changed = await client.ensure_stopped()
    except ProxmoxError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        await client.close()

    if changed:
        print(f"Spegnimento richiesto per {settings.proxmox_vm_type.upper()} {settings.proxmox_vmid}.")
    else:
        print(f"{settings.proxmox_vm_type.upper()} {settings.proxmox_vmid} gia spento.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Gestione alimentazione LiteLLM Proxmox Router")
    parser.add_argument("action", choices=("up", "down"))
    args = parser.parse_args()

    if args.action == "up":
        send_configured_wol()
    else:
        asyncio.run(shutdown_vm())


if __name__ == "__main__":
    main()
