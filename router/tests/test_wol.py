import pytest

from app.wol import magic_packet


def test_magic_packet():
    packet = magic_packet("AA:BB:CC:DD:EE:FF")
    assert len(packet) == 102
    assert packet[:6] == b"\xff" * 6
    assert packet[6:12] == bytes.fromhex("AABBCCDDEEFF")


def test_invalid_mac():
    with pytest.raises(ValueError):
        magic_packet("not-a-mac")
