#!/usr/bin/env python3
"""
Script di verifica della configurazione .env per Ollama Proxmox Router.
Controlla sul campo la validità dei parametri e la connettività verso i servizi.
"""

import os
import sys

# Se eseguito con il Python di sistema privo di dipendenze (es. httpx),
# individua il virtualenv locale (.venv) e riesegui lo script con quello.
try:
    import httpx
except ImportError:
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.abspath(os.path.join(script_dir, ".."))
    venv_candidates = [
        os.path.join(repo_root, ".venv", "bin", "python"),
        os.path.join("/opt/ollama-router", ".venv", "bin", "python"),
    ]
    for venv_python in venv_candidates:
        if os.path.exists(venv_python) and os.access(venv_python, os.X_OK):
            os.execv(venv_python, [venv_python] + sys.argv)

# Assicura che la directory radice sia nel sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import httpx
from pydantic import ValidationError

from app.config import get_settings
from app.proxmox import ProxmoxClient
from app.wol import magic_packet


def print_step(title: str):
    print(f"\n[+] {title}")


def print_success(msg: str):
    print(f"  \033[32m✔\033[0m {msg}")


def print_warning(msg: str):
    print(f"  \033[33m⚠\033[0m {msg}")


def print_error(msg: str):
    print(f"  \033[31m✖\033[0m {msg}")


def verify_config() -> bool:
    all_ok = True

    # 1. Caricamento ed esame delle impostazioni
    print_step("Caricamento configurazione (.env)")
    try:
        get_settings.cache_clear()
        settings = get_settings()
        print_success("File di configurazione caricato e validato correttamente.")
    except ValidationError as err:
        print_error("Errore di validazione nel file .env:")
        for error in err.errors():
            loc = " -> ".join(str(e) for e in error["loc"])
            print_error(f"  Campo '{loc}': {error['msg']}")
        return False
    except Exception as err:  # noqa: BLE001
        print_error(f"Impossibile caricare .env: {err}")
        return False

    # 2. Controllo Proxmox VE
    print_step("Verifica connessione Proxmox API")
    print(
        f"  Target: {settings.proxmox_base_url} (Node: {settings.proxmox_node}, Type: {settings.proxmox_vm_type}, VMID: {settings.proxmox_vmid})"
    )

    proxmox_client = ProxmoxClient(settings)
    try:
        # Tenta di leggere lo stato attuale della VM/CT
        with httpx.Client(
            timeout=settings.proxmox_timeout,
            verify=settings.proxmox_verify,
            headers={"Authorization": f"PVEAPIToken={settings.proxmox_token_id}={settings.proxmox_token_secret}"},
        ) as client:
            res = client.get(proxmox_client.status_url)
            if res.status_code == 200:
                vm_status = res.json().get("data", {}).get("status", "sconosciuto")
                print_success(
                    f"Connessione a Proxmox API riuscita. Stato VM/CT #{settings.proxmox_vmid}: '{vm_status}'"
                )
            elif res.status_code in (401, 403):
                print_error(
                    f"Autenticazione Proxmox fallita (HTTP {res.status_code}). Verifica PROXMOX_TOKEN_ID e PROXMOX_TOKEN_SECRET."
                )
                all_ok = False
            elif res.status_code == 404:
                print_error(f"VM/CT #{settings.proxmox_vmid} non trovata sul nodo '{settings.proxmox_node}'.")
                all_ok = False
            else:
                print_error(f"Risposta inattesa da Proxmox API (HTTP {res.status_code}): {res.text}")
                all_ok = False
    except httpx.TimeoutException:
        print_error(
            f"Timeout nella risposta da Proxmox ({settings.proxmox_base_url}). "
            "Verifica che l'IP e la porta 8006 siano raggiungibili, che il firewall non blocchi la connessione "
            f"e che il nome nodo '{settings.proxmox_node}' o l'URL siano corretti."
        )
        all_ok = False
    except httpx.ConnectError as exc:
        print_error(
            f"Impossibile connettersi all'host Proxmox su {settings.proxmox_base_url}: {exc}. "
            "Controlla IP, porta e certificato TLS (PROXMOX_VERIFY_TLS)."
        )
        all_ok = False
    except httpx.HTTPError as exc:
        print_error(f"Errore durante la comunicazione con Proxmox: {exc}")
        all_ok = False
    except Exception as exc:  # noqa: BLE001
        print_error(f"Errore imprevisto Proxmox: {exc}")
        all_ok = False

    # 3. Controllo Upstream Ollama / LiteLLM
    print_step("Verifica endpoint Upstream Ollama / LiteLLM")
    health_url = f"{settings.upstream_base_url}{settings.upstream_health_path}"
    print(f"  Target: {health_url}")

    headers = {}
    if settings.upstream_authorization:
        headers["Authorization"] = settings.upstream_authorization

    try:
        with httpx.Client(timeout=settings.upstream_connect_timeout) as client:
            res = client.get(health_url, headers=headers)
            if 200 <= res.status_code < 300:
                print_success(f"Upstream raggiungibile ed operativo (HTTP {res.status_code}).")
            else:
                print_warning(
                    f"Upstream ha risposto con codice HTTP {res.status_code}. (Nota: Se la VM è attualmente spenta, questo è normale)"
                )
    except httpx.ConnectError:
        print_warning(
            f"Upstream non raggiungibile su {health_url}. (La VM/CT potrebbe essere attualmente spenta, verrà avviata al primo request)"
        )
    except httpx.HTTPError as exc:
        print_warning(f"Errore di rete/connessione verso Upstream: {exc}")

    # 4. Controllo configurazione Gaming / Wake-on-LAN
    print_step("Verifica parametri Wake-on-LAN (Gaming)")
    if settings.gaming_mac:
        try:
            packet = magic_packet(settings.gaming_mac)
            print_success(
                f"Sintassi MAC '{settings.gaming_mac}' valida (Magic Packet generato: {len(packet)} bytes). Broadcast target: {settings.gaming_broadcast}:{settings.gaming_wol_port}"
            )
        except ValueError as exc:
            print_error(f"Sintassi GAMING_MAC non valida: {exc}")
            all_ok = False
    else:
        print_warning("GAMING_MAC non impostato. Endpoint /gaming/start disabilitato.")

    # Risultato finale
    print("\n" + "=" * 50)
    if all_ok:
        print(" SUCCESS: La configurazione .env è valida e pronta per l'uso!")
        print("=" * 50 + "\n")
        return True
    else:
        print(" FAILED: Alcuni parametri in .env richiedono attenzione.")
        print("=" * 50 + "\n")
        return False


if __name__ == "__main__":
    success = verify_config()
    sys.exit(0 if success else 1)
