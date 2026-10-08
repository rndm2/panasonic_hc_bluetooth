"""Data structures for Panasonic H&C Bluetooth controllers."""

import io
from enum import Enum


class ProtocolError(ValueError):
    """Malformed or unsupported controller packet."""


def _read(fd: io.BytesIO, size: int) -> bytes:
    data = fd.read(size)
    if len(data) != size:
        raise ProtocolError("Truncated packet")
    return data


def _cksum(data):
    cksum = 0
    for i in data:
        cksum = (cksum + i) & 255
    return cksum


def _decode(data):
    if len(data) < 6:
        raise ProtocolError("Truncated parcel")
    data = list(data)
    for x in range(len(data)):
        data[x] = data[x] ^ 105

    for x in range(len(data) - 1, 0, -1):
        data[x] = data[x] ^ data[x - 1]

    data[0] = data[0] ^ 202

    if _cksum(data[1:-1]) != data[-1]:
        raise ProtocolError("Bad checksum")

    return bytes(data)


def _encode(data):
    data = list(data)
    data[-1] = _cksum(data[1:-1])

    data[0] = data[0] ^ 202
    for x in range(1, len(data)):
        data[x] = data[x] ^ data[x - 1]

    for x in range(len(data)):
        data[x] = data[x] ^ 105

    return bytes(data)


class MODE(Enum):
    heat = 1
    cool = 2
    fan_only = 3
    dry = 4
    auto = 5


class FANSPEED(Enum):
    auto = 2
    high = 3
    medium = 4
    low = 5


class PanasonicBLEParcel:
    """A BLE Parcel."""

    idx = 0

    class PanasonicBLEPacket:
        """A BLE Parcel Packet."""

        class PACKET_TYPE(Enum):
            SET_TEMP = 76
            SET_POWER = 65
            SET_MODE = 66
            SET_POWERSAVE = 84

        def __init__(self, ptype, pdata):
            self.ptype = ptype
            self.pdata = pdata

        @staticmethod
        def parse(fd: io.BytesIO):
            """Construct Packet from fd."""

            ptype = _read(fd, 1)[0]
            plen = _read(fd, 1)[0]

            if ptype == 0x69 and plen == 0xFE:
                return PanasonicBLEParcel.PanasonicBLEPacketUARTKeepAlive(ptype, b"")

            pdata = _read(fd, plen)

            if ptype == 129:
                return PanasonicBLEParcel.PanasonicBLEPacketStatus(ptype, pdata)
            if ptype == 33:
                return PanasonicBLEParcel.PanasonicBLEPacketOutdoorTemp(ptype, pdata)

            return PanasonicBLEParcel.PanasonicBLEPacket(ptype, pdata)

        def encode(self):
            return self.ptype.to_bytes() + len(self.pdata).to_bytes() + self.pdata

        def __str__(self):
            return f"{self.ptype}, {list(self.pdata)}"

    class PanasonicBLEPacketStatus(PanasonicBLEPacket):
        def __init__(self, ptype, pdata):
            super().__init__(ptype, pdata)
            if len(pdata) < 5:
                raise ProtocolError("Truncated status")
            self.curtemp = None
            self.power = self.pdata[0] & 1

            raw_mode = (self.pdata[0] >> 5) & 7

            if raw_mode == 6:
                raw_mode = 5  # Some Panasonic devices sent 6 for auto instead of 5

            try:
                self.mode = MODE(raw_mode)
            except ValueError as err:
                raise ProtocolError("Unknown HVAC mode") from err
            self.temp = (self.pdata[4] - 70) / 2
            try:
                self.fanspeed = FANSPEED((self.pdata[1] >> 5) & 7)
            except ValueError as err:
                raise ProtocolError("Unknown fan mode") from err
            self.powersave = None

            if len(self.pdata) >= 6:
                self.curtemp = (self.pdata[5] - 70) / 2

            if len(self.pdata) >= 9:
                self.powersave = self.pdata[8]

        def __str__(self):
            s = super().__str__()
            s += f"\nTemp: {self.temp}"
            if self.curtemp:
                s += f" ({self.curtemp})"
            s += f"\nPower: {'on' if self.power else 'off'}"
            s += f"\nMode: {self.mode.name}"
            s += f"\nFan: {self.fanspeed.name}"
            s += f"\nPowersave: {'on' if self.powersave else 'off'}"
            return s

    class PanasonicBLEPacketOutdoorTemp(PanasonicBLEPacket):
        def __init__(self, ptype, pdata):
            super().__init__(ptype, pdata)
            if len(pdata) < 2:
                raise ProtocolError("Truncated outdoor temperature")
            self.temp = self.pdata[1] / 10

        def __str__(self):
            s = super().__str__()
            s += f"\nOutdoor Temp: {self.temp}"
            return s

    class PanasonicBLEPacketUARTKeepAlive(PanasonicBLEPacket):
        """UART keepalive/empty packet (0x69 0xFE)."""

        pass

    class COMPONENT(Enum):
        I_UNIT1 = 1
        O_UNIT1 = 9
        ALL_UNITS = 247
        APP = 249
        BLE_MODULE_UART = 254

    class OPERATION(Enum):
        SET = 0
        SET_RES = 1
        REQ = 2
        REQ_RES = 3
        NOTIFY = 4

    def __init__(self, src=None, dst=None, op=None, packets=None):
        self.src = self.COMPONENT[src]
        self.dst = self.COMPONENT[dst]
        self.op = self.OPERATION[op]
        self.packets = packets

    @staticmethod
    def parse(data: bytes):
        """Construct PanasonicBLEParcel from fd."""

        data = _decode(data)
        fd = io.BytesIO(data[:-1])

        if _read(fd, 1)[0] != 0x11:
            raise ProtocolError("Bad packet")

        try:
            src = PanasonicBLEParcel.COMPONENT(_read(fd, 1)[0])
            dst = PanasonicBLEParcel.COMPONENT(_read(fd, 1)[0])
            op = PanasonicBLEParcel.OPERATION(_read(fd, 1)[0])
        except ValueError as err:
            raise ProtocolError("Unknown parcel header") from err

        num_packets = _read(fd, 1)[0]
        packets = [PanasonicBLEParcel.PanasonicBLEPacket.parse(fd) for _ in range(num_packets)]

        if fd.read(1):
            raise ProtocolError("Unexpected trailing data")

        return PanasonicBLEParcel(src=src.name, dst=dst.name, op=op.name, packets=packets)

    def encode(self):
        fd = io.BytesIO()
        fd.write(b"\x11")
        fd.write(self.src.value.to_bytes())
        fd.write(self.dst.value.to_bytes())
        fd.write(self.op.value.to_bytes())

        fd.write(len(self.packets).to_bytes())
        for p in self.packets:
            fd.write(p.encode())

        fd.write(b"\x00")  # cksum

        return _encode(fd.getvalue())

    def __str__(self):
        s = f"{self.src.name} => {self.dst.name} {self.op.name}\n"
        for p in self.packets:
            s += f"\t{p}\n"
        return s

    def __iter__(self):
        return iter(self.packets)


class PanasonicBLEMode(PanasonicBLEParcel):
    def __init__(self, mode):
        super().__init__(
            src="APP",
            dst="I_UNIT1",
            op="SET",
            packets=[PanasonicBLEParcel.PanasonicBLEPacket(66, bytes([mode]))],
        )


class PanasonicBLEFanMode(PanasonicBLEParcel):
    def __init__(self, mode):
        super().__init__(
            src="APP",
            dst="I_UNIT1",
            op="SET",
            packets=[
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([17, mode, 0, 0])),
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([18, mode, 0, 0])),
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([19, mode, 0, 0])),
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([20, mode, 0, 0])),
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([21, mode, 0, 0])),
            ],
        )


class PanasonicBLEEnergySaving(PanasonicBLEParcel):
    def __init__(self, state):
        state = 11 if state else 9
        super().__init__(
            src="APP",
            dst="I_UNIT1",
            op="SET",
            packets=[PanasonicBLEParcel.PanasonicBLEPacket(84, bytes([state]))],
        )


class PanasonicBLEPower(PanasonicBLEParcel):
    def __init__(self, state):
        state += 2  # 2==OFF, 3==ON
        super().__init__(
            src="APP",
            dst="I_UNIT1",
            op="SET",
            packets=[PanasonicBLEParcel.PanasonicBLEPacket(65, bytes([state]))],
        )


class PanasonicBLEStatusReq(PanasonicBLEParcel):
    def __init__(self):
        super().__init__(
            src="APP",
            dst="I_UNIT1",
            op="REQ",
            packets=[PanasonicBLEParcel.PanasonicBLEPacket(129, bytes([4, 0, 14]))],
        )


class PanasonicBLETemp(PanasonicBLEParcel):
    def __init__(self, temp):
        if not 16 <= temp <= 32 or not float(temp * 2).is_integer():
            raise ValueError("Temperature must be 16–32 °C in 0.5 °C steps")
        temp = int(temp * 2 + 70)
        super().__init__(
            src="APP",
            dst="I_UNIT1",
            op="SET",
            packets=[
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([9, 0, temp, 0])),
                PanasonicBLEParcel.PanasonicBLEPacket(76, bytes([10, 0, temp, 0])),
            ],
        )


class PanasonicBLEOuting(PanasonicBLEParcel):
    def __init__(self, state):
        super().__init__(
            src="APP",
            dst="BLE_MODULE_UART",
            op="SET",
            packets=[PanasonicBLEParcel.PanasonicBLEPacket(105, bytes([0, 0, 17, 2, state]))],
        )
