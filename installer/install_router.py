#!/usr/bin/env python3
"""Install or update the always-on router from the monorepo."""
from __future__ import annotations
import argparse, os, pwd, grp, shutil, signal, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "router"
SERVICE = Path("/etc/systemd/system/litellm-router.service")

def run(cmd, **kwargs):
    return subprocess.run(cmd, text=True, check=kwargs.pop("check", True), **kwargs)

def log(message):
    print(message, flush=True)

def env_value(key, default=""):
    path = ROUTER / ".env"
    if path.exists():
        for raw in path.read_text().splitlines():
            if raw.startswith(key + "="):
                return raw.split("=", 1)[1].strip().strip('"').strip("'")
    return default

def stop_orphan_listener(port):
    result = run(["ss", "-ltnp", f"sport = :{port}"], check=False, capture_output=True)
    pids = set()
    import re
    for match in re.finditer(r"pid=(\d+)", result.stdout):
        pids.add(int(match.group(1)))
    for pid in pids:
        try:
            cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "uvicorn" not in cmdline:
            raise SystemExit(f"Porta {port} occupata da processo non-Uvicorn PID {pid}: {cmdline}")
        log(f"      arresto listener Uvicorn orfano PID {pid}: {cmdline}")
        os.kill(pid, signal.SIGTERM)
    if pids:
        time.sleep(3)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", default="litellm-router")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Eseguire come root")
    if not (ROUTER / ".env").exists():
        raise SystemExit("router/.env mancante: copiarlo da router/.env.example e configurarlo")
    log("[1/7] Arresto servizio esistente")
    run(["systemctl", "stop", "litellm-router.service"], check=False)
    run(["systemctl", "reset-failed", "litellm-router.service"], check=False)
    port = env_value("LISTEN_PORT", "8080")
    stop_orphan_listener(port)
    log("[2/7] Utente di servizio")
    try:
        account = pwd.getpwnam(args.user)
    except KeyError:
        run(["useradd", "--system", "--home", str(ROUTER), "--shell", "/usr/sbin/nologin", args.user])
        account = pwd.getpwnam(args.user)
    log("[3/7] Virtualenv e dipendenze")
    if not (ROUTER / ".venv/bin/python").exists():
        run(["python3", "-m", "venv", str(ROUTER / ".venv")])
    run([str(ROUTER / ".venv/bin/pip"), "install", "-r", str(ROUTER / "requirements.txt")])
    log("[4/7] Permessi")
    for base, dirs, files in os.walk(ROUTER):
        os.chown(base, account.pw_uid, account.pw_gid)
        for name in dirs + files:
            os.chown(os.path.join(base, name), account.pw_uid, account.pw_gid)
    os.chmod(ROUTER / ".env", 0o640)
    log("[5/7] Unita systemd monorepo")
    shutil.copy2(ROUTER / "systemd/litellm-router.service", SERVICE)
    run(["systemctl", "daemon-reload"])
    run(["systemctl", "enable", "litellm-router.service"])
    log("[6/7] Avvio router")
    run(["systemctl", "restart", "litellm-router.service"])
    deadline = time.time() + 30
    import urllib.request
    last = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health/live", timeout=3) as response:
                if response.status == 200:
                    last = response.read().decode()
                    break
        except Exception as exc:
            last = str(exc)
        time.sleep(1)
    if not isinstance(last, str) or "router" not in last:
        run(["journalctl", "-u", "litellm-router.service", "-n", "50", "--no-pager"], check=False)
        raise SystemExit(f"Health check router fallito: {last}")
    log(f"[7/7] Router operativo: {last}")

if __name__ == "__main__":
    main()
