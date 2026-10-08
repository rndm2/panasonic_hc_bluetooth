"""No tests contact a Bluetooth adapter or physical controller."""

from unittest.mock import AsyncMock, Mock

import pytest
from bleak.backends.device import BLEDevice

from custom_components.panasonic_hc.panasonic_hc import PanasonicHC
from custom_components.panasonic_hc.protocol import _decode, _encode


@pytest.fixture
def device():
    return BLEDevice("AA:BB:CC:DD:EE:FF", "CZ-RTC6BLW", {})


@pytest.fixture
def thermostat(device):
    return PanasonicHC(device, device.address)


def parcel(payload: bytes, ptype: int = 129) -> bytes:
    return _encode(bytes([0x11, 1, 249, 3, 1, ptype, len(payload)]) + payload + b"\0")


def status_packet(power=True, mode=2, fan=2, temp=22, current=23, eco=0, short=False):
    payload = bytes(
        [
            (mode << 5) | int(power),
            fan << 5,
            0,
            0,
            int(temp * 2 + 70),
            int(current * 2 + 70),
            0,
            0,
            eco,
        ]
    )
    return parcel(payload[:6] if short else payload)


def notify(thermostat, packet):
    thermostat.on_notification(packet)


@pytest.fixture
def connected(thermostat):
    conn = Mock()
    conn.is_connected = True
    conn.disconnect = AsyncMock()
    conn.start_notify = AsyncMock()

    async def write(uuid, data):
        # Decode outgoing framing directly; requests are not inbound status packets.
        raw = _decode(data)
        pos = 5
        for _ in range(raw[4]):
            ptype, length = raw[pos : pos + 2]
            pos += 2 + length
            if ptype == 129:
                notify(thermostat, status_packet())

    conn.write_gatt_char = AsyncMock(side_effect=write)
    thermostat.transport.client = conn
    notify(thermostat, status_packet())
    return conn


@pytest.fixture(autouse=True)
def skip_hardware_settle_delays(monkeypatch):
    monkeypatch.setattr("custom_components.panasonic_hc.transport.NOTIFY_SETTLE_DELAY", 0)
    monkeypatch.setattr("custom_components.panasonic_hc.panasonic_hc.COMMAND_CONFIRM_TIMEOUT", 0.05)
    monkeypatch.setattr(
        "custom_components.panasonic_hc.panasonic_hc.COMMAND_CONFIRM_INTERVAL", 0.001
    )
