#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from envfile import load


def ssh(env, command):
    opts = [
        "-o", f"UserKnownHostsFile={env.get('SSH_KNOWN_HOSTS', '/root/.ssh/known_hosts')}",
        "-o", "StrictHostKeyChecking=yes",
        "-o", "IdentitiesOnly=yes",
        "-i", env.get("SSH_IDENTITY", "/root/.ssh/id_ed25519"),
    ]
    return subprocess.run(
        [
            "ssh",
            "-p",
            env.get("POWER_SSH_PORT", "22"),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            *opts,
            f"{env.get('POWER_SSH_USER', 'root')}@{env['POWER_HOST']}",
            command,
        ],
        text=True,
        capture_output=True,
    )


def request(env, method, path):
    header = f"Authorization: Bearer {env['AGENT_TOKEN']}"
    url = f"http://127.0.0.1:{env.get('AGENT_PORT', '8765')}{path}"
    command = f"curl -sS -o /tmp/powersaver-wakelock.json -w '%{{http_code}}' -X {method} -H '{header}' {url}"
    result = ssh(env, command)
    if result.returncode != 0:
        print(f"FAIL: workstation o Power Agent non raggiungibile: {result.stderr.strip()}", file=sys.stderr)
        return None, None
    body = ssh(env, "cat /tmp/powersaver-wakelock.json 2>/dev/null || true").stdout.strip()
    return result.stdout.strip(), body


def status(env):
    code, body = request(env, "GET", "/status")
    if code != "200":
        print(f"FAIL: lettura stato agent HTTP {code or '?'}: {body or ''}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print(f"FAIL: risposta agent non valida: {body}", file=sys.stderr)
        return 1
    state = payload["state"]
    print(json.dumps(payload, indent=2))
    print(f"Policy: wakelock={state['wakelock']}, blocker={state['blocker']}, idle_seconds={state['idle_seconds']}")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Gestione wakelock Power Agent")
    parser.add_argument("action", choices=("lock", "unlock", "status"))
    parser.add_argument("--env-file", default="router/.env")
    args = parser.parse_args()

    env = load(args.env_file)
    missing = [key for key in ("POWER_HOST", "AGENT_TOKEN") if not env.get(key)]
    if missing:
        raise SystemExit("Variabili mancanti nel .env: " + ", ".join(missing))

    if args.action == "status":
        raise SystemExit(status(env))

    method = "POST" if args.action == "lock" else "DELETE"
    code, body = request(env, method, "/wakelock")

    if code != "200":
        print(f"FAIL: operazione {args.action} HTTP {code or '?'}: {body or ''}", file=sys.stderr)
        raise SystemExit(1)

    print(body)
    if args.action == "lock":
        print("PASS: autoshutdown bloccato")
    else:
        print("PASS: autoshutdown riabilitato; la grace period ripartirà se non esistono altri blocker")

    raise SystemExit(status(env))


if __name__ == "__main__":
    main()
