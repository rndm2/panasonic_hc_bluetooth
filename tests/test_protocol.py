import io
import random

import pytest
from conftest import parcel, status_packet

from custom_components.panasonic_hc.config_flow import validate_mac
from custom_components.panasonic_hc.panasonic_hc_proto import (
    PanasonicBLEFanMode,
    PanasonicBLEParcel,
    PanasonicBLEPower,
    PanasonicBLETemp,
    ProtocolError,
    _encode,
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
        PanasonicBLEParcel.parse(data)


def test_short_status_and_auto_alias():
    packet = next(iter(PanasonicBLEParcel.parse(status_packet(mode=6, short=True))))
    assert packet.mode.name == "auto"
    assert packet.powersave is None
    assert packet.curtemp == 23


def test_minimum_status():
    packet = next(iter(PanasonicBLEParcel.parse(parcel(bytes([64, 64, 0, 0, 114])))))
    assert packet.curtemp is None
    assert packet.powersave is None


@pytest.mark.parametrize(
    "payload", [b"", b"\0" * 4, bytes([224, 64, 0, 0, 114]), bytes([64, 224, 0, 0, 114])]
)
def test_invalid_status(payload):
    with pytest.raises(ProtocolError):
        PanasonicBLEParcel.parse(parcel(payload))


def test_outdoor_packet():
    packet = PanasonicBLEParcel.PanasonicBLEPacket.parse(io.BytesIO(bytes([33, 2, 0, 100])))
    assert packet.temp == 10


def test_uart_keepalive():
    wire = _encode(bytes([17, 1, 249, 3, 1, 105, 254, 0]))
    assert isinstance(
        next(iter(PanasonicBLEParcel.parse(wire))),
        PanasonicBLEParcel.PanasonicBLEPacketUARTKeepAlive,
    )


@pytest.mark.parametrize("temp", [15, 33, 22.1, float("nan"), float("inf")])
def test_invalid_temperature(temp):
    with pytest.raises(ValueError):
        PanasonicBLETemp(temp)


def test_wire_compatibility():
    # Literal golden frames generated from the original protocol, not round trips.
    assert PanasonicBLEPower(1).encode().hex() == "b24b4a4a4b0a0b0848"
    assert PanasonicBLETemp(22).encode().hex() == "b24b4a4a48040009097b7b373339394b4bd8"


def test_fan_all_modes():
    p = PanasonicBLEParcel.parse(PanasonicBLEFanMode(3).encode())
    assert [x.pdata[0] for x in p] == [17, 18, 19, 20, 21]


def test_random_malformed_inputs_fail_cleanly():
    rng = random.Random(42)
    for _ in range(500):
        data = rng.randbytes(rng.randrange(0, 80))
        try:
            PanasonicBLEParcel.parse(data)
        except ProtocolError:
            pass


def test_nested_iteration_independent():
    p = PanasonicBLEParcel.parse(PanasonicBLETemp(22).encode())
    assert len([(a, b) for a in p for b in p]) == 4


def test_random_framed_inputs_fail_cleanly():
    rng = random.Random(88)
    for _ in range(500):
        payload = rng.randbytes(rng.randrange(0, 20))
        ptype = rng.choice([129, 33, 105])
        try:
            PanasonicBLEParcel.parse(parcel(payload, ptype))
        except ProtocolError:
            pass
