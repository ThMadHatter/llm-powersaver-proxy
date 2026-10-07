import re
import socket


def magic_packet(mac: str) -> bytes:
    clean = re.sub(r"[^0-9A-Fa-f]", "", mac)
    if len(clean) != 12:
        raise ValueError("MAC address non valido")
    return bytes.fromhex("FF" * 6 + clean * 16)


def send_wol(mac: str, broadcast: str, port: int = 9) -> None:
    packet = magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
