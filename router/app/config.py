import os
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def get_env_files():
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return (env_file,)
    return (".env", "/opt/litellm-router/.env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=get_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    listen_host: str = "0.0.0.0"
    listen_port: int = 8080
    log_level: str = "INFO"

    router_api_key: str = Field(min_length=16)
    upstream_base_url: str = "http://192.168.1.50:4000"
    upstream_authorization: str = ""
    upstream_health_path: str = "/health/liveliness"
    upstream_connect_timeout: float = 3.0
    upstream_write_timeout: float = 60.0
    upstream_pool_timeout: float = 5.0

    proxmox_base_url: str = "https://192.168.1.10:8006"
    proxmox_node: str = "pve"
    proxmox_vm_type: str = "qemu"
    proxmox_vmid: int = 101
    proxmox_token_id: str
    proxmox_token_secret: str
    proxmox_verify_tls: bool = False
    proxmox_ca_file: str = ""
    proxmox_timeout: float = 10.0

    startup_timeout: float = 180.0
    startup_poll_initial: float = 0.5
    startup_poll_max: float = 3.0

    gaming_mac: str = ""
    gaming_broadcast: str = "255.255.255.255"
    gaming_wol_port: int = 9
    agent_base_url: str = ""
    agent_token: str = ""
    agent_heartbeat_path: str = "/activity/llm"
    agent_heartbeat_interval: float = 60.0
    agent_timeout: float = 5.0

    # Power Agent (Workstation) via ssh, used by app/mqtt_stats.py
    power_host: str = ""
    power_ssh_user: str = "root"
    power_ssh_port: int = 22
    ssh_home: str = "/root"
    ssh_known_hosts: str = "/root/.ssh/known_hosts"
    power_workdir: str = "/opt/llm-powersaver-proxy"
    agent_port: int = 8765

    # Home Assistant MQTT discovery (stats + wakelock). Empty MQTT_HOST disables it.
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_stats_topic_prefix: str = "home/llm_router"
    mqtt_stats_entity_prefix: str = "llm_router"
    mqtt_stats_poll_seconds: float = 15.0

    @property
    def agent_heartbeat_url(self) -> str:
        return f"{self.agent_base_url.rstrip(chr(47))}{self.agent_heartbeat_path}" if self.agent_base_url else ""

    @field_validator("upstream_base_url", "proxmox_base_url")
    @classmethod
    def strip_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("proxmox_vm_type")
    @classmethod
    def validate_vm_type(cls, value: str) -> str:
        if value not in {"qemu", "lxc"}:
            raise ValueError("PROXMOX_VM_TYPE deve essere qemu oppure lxc")
        return value

    @property
    def proxmox_verify(self) -> bool | str:
        return self.proxmox_ca_file or self.proxmox_verify_tls


@lru_cache
def get_settings() -> Settings:
    return Settings()
