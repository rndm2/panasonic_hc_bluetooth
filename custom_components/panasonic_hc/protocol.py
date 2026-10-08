"""Pure Panasonic wire codec. No Bluetooth, clocks or Home Assistant dependencies."""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import IntEnum


class ProtocolError(ValueError):
    """A frame is malformed or contains unsupported status values."""


class Mode(IntEnum):
    heat = 1
    cool = 2
    fan_only = 3
    dry = 4
    auto = 5


class FanSpeed(IntEnum):
    auto = 2
    high = 3
    medium = 4
    low = 5


class Component(IntEnum):
    INDOOR = 1
    OUTDOOR = 9
    ALL = 247
    APP = 249
    UART = 254


class Operation(IntEnum):
    SET = 0
    SET_RESPONSE = 1
    REQUEST = 2
    RESPONSE = 3
    NOTIFY = 4


def _decode(data: bytes) -> bytes:
    if len(data) < 6:
        raise ProtocolError("Truncated frame")
    decoded = bytes([data[0] ^ 0x69 ^ 0xCA]) + bytes(
        current ^ previous for previous, current in zip(data, data[1:], strict=False)
    )
    if sum(decoded[1:-1]) & 255 != decoded[-1]:
        raise ProtocolError("Bad checksum")
    return decoded


def _encode(data: bytes) -> bytes:
    if len(data) < 6:
        raise ProtocolError("Truncated frame")
    raw = data[:-1] + bytes([sum(data[1:-1]) & 255])
    previous = 0xCA
    result = bytearray()
    for value in raw:
        previous ^= value
        result.append(previous ^ 0x69)
    return bytes(result)


@dataclass(frozen=True, slots=True)
class StatusReport:
    power: bool
    mode: Mode
    fanspeed: FanSpeed
    temp: float
    curtemp: float | None
    powersave: bool | None

    @classmethod
    def decode(cls, data: bytes) -> StatusReport:
        if len(data) < 5:
            raise ProtocolError("Truncated status")
        try:
            mode = Mode(5 if (data[0] >> 5) == 6 else data[0] >> 5)
            fan = FanSpeed(data[1] >> 5)
        except ValueError as err:
            raise ProtocolError("Unknown mode or fan speed") from err
        target = (data[4] - 70) / 2
        if not 16 <= target <= 32:
            raise ProtocolError("Invalid target temperature")
        return cls(
            bool(data[0] & 1),
            mode,
            fan,
            target,
            (data[5] - 70) / 2 if len(data) >= 6 else None,
            bool(data[8]) if len(data) >= 9 else None,
        )


@dataclass(frozen=True, slots=True)
class Packet:
    ptype: int
    pdata: bytes
    keepalive: bool = False

    def encode(self) -> bytes:
        if self.keepalive:
            return b"\x69\xfe"
        if not 0 <= self.ptype <= 255 or len(self.pdata) > 255:
            raise ProtocolError("Packet does not fit wire format")
        return bytes([self.ptype, len(self.pdata)]) + self.pdata


@dataclass(frozen=True, slots=True)
class Parcel:
    src: Component
    dst: Component
    op: Operation
    packets: tuple[Packet, ...]

    def __iter__(self) -> Iterator[Packet]:
        return iter(self.packets)

    def encode(self) -> bytes:
        if len(self.packets) > 255:
            raise ProtocolError("Too many packets")
        return _encode(
            bytes([0x11, self.src, self.dst, self.op, len(self.packets)])
            + b"".join(packet.encode() for packet in self.packets)
            + b"\0"
        )

    @classmethod
    def parse(cls, data: bytes) -> Parcel:
        raw = _decode(data)
        if raw[0] != 0x11:
            raise ProtocolError("Invalid frame marker")
        try:
            src, dst, op = Component(raw[1]), Component(raw[2]), Operation(raw[3])
        except ValueError as err:
            raise ProtocolError("Unknown frame header") from err
        pos, end = 5, len(raw) - 1
        packets = []
        for _ in range(raw[4]):
            if pos + 2 > end:
                raise ProtocolError("Truncated packet header")
            ptype, length = raw[pos : pos + 2]
            pos += 2
            if (ptype, length) == (105, 254):
                packets.append(Packet(ptype, b"", keepalive=True))
                continue
            if pos + length > end:
                raise ProtocolError("Truncated packet payload")
            packets.append(Packet(ptype, raw[pos : pos + length]))
            pos += length
        if pos != end:
            raise ProtocolError("Unexpected trailing data")
        return cls(src, dst, op, tuple(packets))

    def status_reports(self) -> tuple[StatusReport, ...]:
        """Only indoor status responses/notifications can confirm climate state.

        Requests and command acknowledgements may share packet identifiers but
        have a different payload. Decode all reports before applying any of them.
        """
        if (
            self.src != Component.INDOOR
            or self.dst != Component.APP
            or self.op not in (Operation.RESPONSE, Operation.NOTIFY)
        ):
            return ()
        return tuple(StatusReport.decode(p.pdata) for p in self if p.ptype == 129)


def _command(*packets: Packet) -> Parcel:
    return Parcel(Component.APP, Component.INDOOR, Operation.SET, packets)


def power(state: bool) -> Parcel:
    return _command(Packet(65, bytes([3 if state else 2])))


def mode(value: str) -> Parcel:
    try:
        wire_value = Mode[value]
    except KeyError as err:
        raise ValueError("Invalid HVAC mode") from err
    return _command(Packet(66, bytes([wire_value])))


def temperature(value: float) -> Parcel:
    if not 16 <= value <= 32 or not float(value * 2).is_integer():
        raise ValueError("Temperature must be 16–32 °C in 0.5 °C steps")
    encoded = int(value * 2 + 70)
    return _command(*(Packet(76, bytes([field, 0, encoded, 0])) for field in (9, 10)))


def fan(value: str) -> Parcel:
    try:
        wire_value = FanSpeed[value]
    except KeyError as err:
        raise ValueError("Invalid fan mode") from err
    return _command(*(Packet(76, bytes([field, wire_value, 0, 0])) for field in range(17, 22)))


def eco(state: bool) -> Parcel:
    return _command(Packet(84, bytes([11 if state else 9])))


def status_request() -> Parcel:
    return Parcel(Component.APP, Component.INDOOR, Operation.REQUEST, (Packet(129, b"\4\0\16"),))
