"""Home Assistant MQTT stats for the LiteLLM Proxmox Router.

Pubblica su MQTT (con discovery Home Assistant) lo stato del router e del
Workstation Power Agent, e comanda il wakelock / l'accensione:

- ``sensor.<prefix>_stato``            stato health del router (online/offline)
- ``sensor.<prefix>_upstream``         stato dell'upstream (ready/offline)
- ``sensor.<prefix>_potere``           stato completo del Power Agent (JSON)
- ``binary_sensor.<prefix>_vm_gaming`` VM gaming accesa
- ``lock.<entity>_wakelock``           blocca/sblocca l'autoshutdown
- ``<prefix>/power/set``               ``UP`` -> WoL + avvio VM gaming

Tutto passa dagli stessi percorsi usati dai target del Makefile
(``make lock``, ``make unlock``, ``make up``): nessuna credenziale aggiuntiva.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import httpx
import paho.mqtt.client as mqtt

from .config import Settings

logger = logging.getLogger("litellm-router.mqtt")

DISCOVERY_SCHEMA = "v1"
AVAILABILITY_ONLINE = "online"
AVAILABILITY_OFFLINE = "offline"

POWER_ACTIONS = {
    "UP": ("up", "avvio gaming"),
    "GAMING_START": ("up", "avvio gaming"),
    "LOCK": ("lock", "wakelock"),
    "UNLOCK": ("unlock", "wakelock"),
    "DOWN": ("down", "spegnimento controllato"),
}


@dataclass
class PowerResult:
    ok: bool
    detail: str


class PowerController:
    """Stesso canale del Makefile: SSH verso il Power Agent + target make."""

    def __init__(self, settings: Settings, workdir: str) -> None:
        self._s = settings
        self._workdir = workdir

    @property
    def enabled(self) -> bool:
        return bool(self._s.power_host and self._s.agent_token)

    def agent_request(self, method: str, path: str) -> dict[str, Any]:
        assert self._s.power_host and self._s.power_ssh_user and self._s.agent_token
        token = self._s.agent_token
        url = f"http://127.0.0.1:{self._s.agent_port}{path}"
        remote = (
            "python3 - <<'PY'\n"
            "import json, urllib.request\n"
            f"token = {token!r}\n"
            f"url = {url!r}\n"
            f"method = {method!r}\n"
            "req = urllib.request.Request(url, method=method,\n"
            "                              headers={'Authorization': 'Bearer ' + token})\n"
            "try:\n"
            "    r = urllib.request.urlopen(req, timeout=8)\n"
            "    print('HTTP', r.status, json.dumps(json.loads(r.read().decode() or '{}')))\n"
            "except Exception as exc:\n"
            "    print('EXC', repr(exc)[:200])\n"
            "PY"
        )
        cmd = [
            "ssh",
            "-p",
            str(self._s.power_ssh_port),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=5",
            f"{self._s.power_ssh_user}@{self._s.power_host}",
            remote,
        ]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        line = (out.stdout + out.stderr).strip().splitlines()[-1] if (out.stdout + out.stderr).strip() else ""
        if not line.startswith("HTTP "):
            raise RuntimeError(f"power agent non raggiungibile: {line[:120] or out.returncode}")
        parts = line.split(" ", 2)
        code = parts[1] if len(parts) > 1 else ""
        body = parts[2] if len(parts) > 2 else ""
        if code != "200":
            raise RuntimeError(f"power agent HTTP {code}: {body[:120]}")
        return json.loads(body) if body else {}

    def agent_state(self) -> dict[str, Any]:
        return self.agent_request("GET", "/status").get("state", {})

    def make(self, target: str) -> PowerResult:
        if target not in {"lock", "unlock", "up", "down"}:
            return PowerResult(False, f"target non consentito: {target}")
        if shutil.which("make") is None:
            return PowerResult(False, "make non disponibile")
        res = subprocess.run(
            ["make", target, "-C", self._workdir],
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        detail = (res.stdout + res.stderr).strip().splitlines()[-1:] or [""]
        return PowerResult(res.returncode == 0, detail[0][:200])


class HomeAssistantStats:
    """Client MQTT con discovery Home Assistant e loop di polling."""

    def __init__(self, settings: Settings, power: PowerController) -> None:
        self._s = settings
        self._power = power
        self._prefix = settings.mqtt_stats_topic_prefix
        self._entity = settings.mqtt_stats_entity_prefix
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"litellm-router-{settings.mqtt_stats_entity_prefix}",
        )
        self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        self._client.will_set(f"{self._prefix}/availability", AVAILABILITY_OFFLINE, qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._last_ok: dict[str, bool] = {}

    # ---------------------------------------------------------------- topics
    def _topic(self, *parts: str) -> str:
        return "/".join((self._prefix, *parts))

    def _publish(self, topic: str, payload: str, retain: bool = True) -> None:
        self._client.publish(topic, payload, qos=1, retain=retain)

    # ------------------------------------------------------------- discovery
    def _device(self) -> dict[str, Any]:
        return {
            "ids": [f"litellm-router-{self._entity}"],
            "name": "LiteLLM Router",
            "manufacturer": "Home Lab",
            "model": "llm-powersaver-proxy",
            "configuration_url": f"http://127.0.0.1:{self._s.listen_port}/health/ready",
        }

    def _discovery(self, component: str, object_id: str, name: str, extra: dict[str, Any]) -> None:
        cfg = {
            "schema": DISCOVERY_SCHEMA,
            "name": name,
            "unique_id": object_id,
            "object_id": object_id,
            "origin": {"name": "llm-powersaver-proxy", "sw": "router"},
            "device": self._device(),
            "availability_mode": "all",
        }
        cfg.update(extra)
        self._client.publish(
            f"homeassistant/{component}/{object_id}/config",
            json.dumps(cfg, ensure_ascii=False),
            qos=1,
            retain=True,
        )

    def _publish_discovery(self) -> None:
        base = {"availability_topic": self._topic("availability")}
        self._discovery(
            "sensor",
            f"{self._entity}_stato",
            f"Router ({self._entity}) Stato",
            {**base, "state_topic": self._topic("sensor", "router_state"),
             "icon": "mdi:router", "entity_category": "diagnostic"},
        )
        self._discovery(
            "sensor",
            f"{self._entity}_upstream",
            f"Router ({self._entity}) Upstream",
            {**base, "state_topic": self._topic("sensor", "upstream_state"),
             "icon": "mdi:server-network", "entity_category": "diagnostic"},
        )
        if self._power.enabled:
            self._discovery(
                "sensor",
                f"{self._entity}_potere",
                f"Router ({self._entity}) Power",
                {**base, "state_topic": self._topic("sensor", "power_state"),
                 "icon": "mdi:power", "entity_category": "diagnostic"},
            )
            self._discovery(
                "binary_sensor",
                f"{self._entity}_vm_gaming_attiva",
                f"Router ({self._entity}) VM Gaming Attiva",
                {**base, "state_topic": self._topic("binary_sensor", "gaming_state"),
                 "device_class": "running"},
            )
            self._discovery(
                "lock",
                f"{self._entity}_wakelock",
                f"Router Wakelock",
                {**base,
                 "state_topic": self._topic("lock", "state"),
                 "command_topic": self._topic("lock", "set"),
                 "payload_lock": "LOCK",
                 "payload_open": "UNLOCK",
                 "payload_on": "LOCK",
                 "payload_off": "UNLOCK",
                 "state_locked": "CLOSED",
                 "state_open": "OPEN",
                 "availability_online": AVAILABILITY_ONLINE,
                 "availability_offline": AVAILABILITY_OFFLINE,
                 "icon": "mdi:power-plug"},
            )

    # ------------------------------------------------------------ publishing
    def _publish_sensor(self, name: str, value: str) -> None:
        self._publish(self._topic("sensor", name), value)

    async def _router_health(self) -> tuple[bool, str]:
        url = f"http://127.0.0.1:{self._s.listen_port}/health/ready"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.get(url)
            data = res.json() if res.content.startswith(b"{") else {}
            return res.status_code == 200, str(data.get("upstream", ""))
        except Exception as exc:  # noqa: BLE001 - report, never crash the loop
            return False, str(exc)[:120]

    async def poll_once(self) -> None:
        ok, detail = await self._router_health()
        self._publish_sensor("router_state", "online" if ok else "offline")
        self._publish_sensor("upstream_state", detail or ("ready" if ok else "unreachable"))
        if not self._power.enabled:
            return
        try:
            state = await asyncio.to_thread(self._power.agent_state)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Power Agent non raggiungibile: %s", exc)
            self._publish(self._topic("power", "availability"), AVAILABILITY_OFFLINE)
            return
        self._publish(self._topic("power", "availability"), AVAILABILITY_ONLINE)
        self._publish(
            self._topic("lock", "state"),
            "CLOSED" if state.get("wakelock") else "OPEN",
        )
        self._publish(
            self._topic("binary_sensor", "gaming_state"),
            "on" if state.get("gaming_vm") == "running" else "off",
        )
        self._publish_sensor("power_state", json.dumps(state, ensure_ascii=False))

    # ------------------------------------------------------------- commands
    def _on_message(self, _client: Any, _user: Any, msg: Any) -> None:
        segments = msg.topic.split("/")
        action = segments[-3]
        leaf = segments[-1]
        if leaf != "set":
            return
        payload = (msg.payload or b"").decode().strip().upper()
        entry = POWER_ACTIONS.get(payload)
        if entry is None:
            logger.warning("payload MQTT sconosciuto su %s: %s", msg.topic, payload)
            return
        if action == "lock" and entry[0] not in {"lock", "unlock"}:
            return
        if action == "power" and entry[0] not in {"up", "down"}:
            return
        result = self._power.make(entry[0])
        logger.info("azione %s (%s): %s", entry[0], entry[1], "ok" if result.ok else result.detail)

    def _on_connect(self, client: Any, _user: Any, _flags: Any, rc: Any, _props: Any = None) -> None:
        # paho 2.x passa il result code (int o enum): 0 = successo.
        try:
            code = int(getattr(rc, "value", rc))
        except (TypeError, ValueError):
            code = 0
        if code != 0:
            logger.warning("MQTT connessione fallita rc=%s", rc)
            return
        client.subscribe(self._topic("lock", "set"), qos=1)
        client.subscribe(self._topic("power", "set"), qos=1)
        self._publish_discovery()
        self._publish(f"{self._prefix}/availability", AVAILABILITY_ONLINE)

    # ----------------------------------------------------------------- start
    async def start(self) -> None:
        self._client.connect(self._s.mqtt_host, self._s.mqtt_port)
        self._client.loop_start()
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning("giro di polling fallito: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._s.mqtt_stats_poll_seconds)
            except asyncio.TimeoutError:
                continue

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._client.loop_stop()
        self._client.disconnect()


def build(settings: Settings, workdir: str) -> HomeAssistantStats | None:
    """Nessun client se ``MQTT_HOST`` non e' impostato (feature disattivata)."""
    if not settings.mqtt_host:
        return None
    power = PowerController(settings, workdir)
    return HomeAssistantStats(settings, power)
