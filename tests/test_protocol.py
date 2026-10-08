import random

import pytest
from conftest import parcel, status_packet

from custom_components.panasonic_hc.config_flow import validate_mac
from custom_components.panasonic_hc.protocol import (
    Parcel,
    ProtocolError,
    _encode,
    fan,
    power,
    temperature,
)


@pytest.mark.parametrize(
    "mac",
    [
        "GG:11:22:33:44:55",
        "A:001:22:33:44:55",
        "",
        "AA:BB:CC:DD:EE",
        "AA:BB:CC:DD:EE:FFF",
        "AA:BB:CC:DD:EE:-1",
    ],
)
def test_invalid_mac(mac):
    assert not validate_mac(mac)


@pytest.mark.parametrize("mac", ["AA:BB:CC:DD:EE:FF", "aa:bb:cc:dd:ee:ff"])
def test_valid_mac(mac):
    assert validate_mac(mac)


@pytest.mark.parametrize(
    "data", [b"", b"\0", b"\0" * 6, _encode(bytes([17, 1, 249, 3, 1, 129, 15, 0]))]
)
def test_bad_parcel(data):
    with pytest.raises(ProtocolError):
        Parcel.parse(data)


def test_short_status_and_auto_alias():
    packet = Parcel.parse(status_packet(mode=6, short=True)).status_reports()[0]
    assert packet.mode.name == "auto"
    assert packet.powersave is None
    assert packet.curtemp == 23


def test_minimum_status():
    packet = Parcel.parse(parcel(bytes([64, 64, 0, 0, 114]))).status_reports()[0]
    assert packet.curtemp is None
    assert packet.powersave is None


@pytest.mark.parametrize(
    "payload", [b"", b"\0" * 4, bytes([224, 64, 0, 0, 114]), bytes([64, 224, 0, 0, 114])]
)
def test_invalid_status(payload):
    with pytest.raises(ProtocolError):
        Parcel.parse(parcel(payload)).status_reports()


def test_outdoor_packet_is_structurally_decoded():
    packet = Parcel.parse(parcel(bytes([0, 100]), 33)).packets[0]
    assert packet.pdata == bytes([0, 100])


def test_uart_keepalive():
    wire = _encode(bytes([17, 1, 249, 3, 1, 105, 254, 0]))
    parsed = Parcel.parse(wire)
    assert parsed.packets[0].keepalive
    assert parsed.encode() == wire


@pytest.mark.parametrize("temp", [15, 33, 22.1, float("nan"), float("inf")])
def test_invalid_temperature(temp):
    with pytest.raises(ValueError):
        temperature(temp)


def test_wire_compatibility():
    # Literal golden frames generated from the original protocol, not round trips.
    assert power(1).encode().hex() == "b24b4a4a4b0a0b0848"
    assert temperature(22).encode().hex() == "b24b4a4a48040009097b7b373339394b4bd8"


def test_fan_all_modes():
    p = Parcel.parse(fan("high").encode())
    assert [x.pdata[0] for x in p] == [17, 18, 19, 20, 21]


def test_random_malformed_inputs_fail_cleanly():
    rng = random.Random(42)
    for _ in range(500):
        data = rng.randbytes(rng.randrange(0, 80))
        try:
            Parcel.parse(data)
        except ProtocolError:
            pass


def test_nested_iteration_independent():
    p = Parcel.parse(temperature(22).encode())
    assert len([(a, b) for a in p for b in p]) == 4


def test_random_framed_inputs_fail_cleanly():
    rng = random.Random(88)
    for _ in range(500):
        payload = rng.randbytes(rng.randrange(0, 20))
        ptype = rng.choice([129, 33, 105])
        try:
            Parcel.parse(parcel(payload, ptype))
        except ProtocolError:
            pass


def test_request_is_not_decoded_as_status():
    from custom_components.panasonic_hc.protocol import status_request

    assert Parcel.parse(status_request().encode()).status_reports() == ()


@pytest.mark.parametrize("src,dst,op", [(9, 249, 3), (1, 9, 3), (1, 249, 1), (249, 1, 0)])
def test_wrong_header_cannot_confirm_status(src, dst, op):
    from custom_components.panasonic_hc.protocol import _decode

    raw = bytearray(_decode(status_packet()))
    raw[1:4] = bytes([src, dst, op])
    assert Parcel.parse(_encode(bytes(raw))).status_reports() == ()


def test_invalid_target_temperature_rejected():
    with pytest.raises(ProtocolError, match="target"):
        Parcel.parse(status_packet(temp=0)).status_reports()


@pytest.mark.parametrize(
    "builder,args,expected",
    [
        ("power", (False,), "b24b4a4a4b0a0b0936"),
        ("mode", ("heat",), "b24b4a4a4b09080936"),
        ("mode", ("auto",), "b24b4a4a4b09080d4e"),
        (
            "fan",
            ("high",),
            "b24b4a4a4f030716151515595d4f4c4c4c000417141414585c484b4b4b070316151515e8",
        ),
        ("eco", (False,), "b24b4a4a4b1f1e174e"),
        ("eco", (True,), "b24b4a4a4b1f1e154e"),
        ("status_request", (), "b24b4a4849c8cbcfcfc152"),
    ],
)
def test_all_command_families_match_pre_rewrite_frames(builder, args, expected):
    # Captured from the released 0.1.2 implementation, not the new encoder.
    from custom_components.panasonic_hc import protocol

    assert getattr(protocol, builder)(*args).encode().hex() == expected
