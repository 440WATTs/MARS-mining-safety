"""20-byte wearable telemetry frame, shared with firmware/mars_core/mars_packet.h.

offset size field
  0     1   version (0xA1)
  1     1   type (1 telemetry, 2 SOS, 3 heartbeat)
  2     2   worker id            uint16 LE
  4     2   sequence             uint16 LE
  6     4   device uptime (s)    uint32 LE
 10     1   zone code            (see zones.zone_code)
 11     1   heart rate (bpm)     0 = invalid
 12     1   SpO2 (%)             0xFF = invalid
 13     2   body temp x10 (degC) int16 LE
 15     1   flags                bit0 fall, bit1 inactivity, bit2 SOS,
                                 bit3 low battery, bit4 ECG lead-off, bit5 sensor fault
 16     1   battery (%)
 17     1   hop count            0 = direct to gateway, +1 per mesh/rover relay
 18     2   CRC-16/CCITT-FALSE over bytes 0..17, LE
"""

import struct
from dataclasses import dataclass

VERSION = 0xA1
TYPE_TELEMETRY, TYPE_SOS, TYPE_HEARTBEAT = 1, 2, 3
FLAG_FALL, FLAG_INACTIVE, FLAG_SOS, FLAG_LOW_BATT, FLAG_LEAD_OFF, FLAG_SENSOR_FAULT = (1 << i for i in range(6))
SPO2_INVALID = 0xFF

_BODY = struct.Struct("<BBHHIBBBhBBB")
FRAME_LEN = _BODY.size + 2


def crc16_ccitt(data: bytes, crc: int = 0xFFFF) -> int:
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return crc


@dataclass
class Telemetry:
    worker_id: int
    seq: int
    uptime_s: int
    zone_code: int
    hr_bpm: int
    spo2: int
    temp_c: float
    flags: int = 0
    battery_pct: int = 100
    hops: int = 0
    msg_type: int = TYPE_TELEMETRY

    def encode(self) -> bytes:
        body = _BODY.pack(VERSION, self.msg_type, self.worker_id, self.seq & 0xFFFF,
                          self.uptime_s, self.zone_code, self.hr_bpm, self.spo2,
                          int(round(self.temp_c * 10)), self.flags, self.battery_pct, self.hops)
        return body + struct.pack("<H", crc16_ccitt(body))


class FrameError(ValueError):
    pass


def decode(frame: bytes) -> Telemetry:
    if len(frame) != FRAME_LEN:
        raise FrameError(f"expected {FRAME_LEN} bytes, got {len(frame)}")
    body, (crc,) = frame[:-2], struct.unpack("<H", frame[-2:])
    if crc16_ccitt(body) != crc:
        raise FrameError("CRC mismatch")
    ver, mtype, wid, seq, up, zc, hr, spo2, t10, flags, batt, hops = _BODY.unpack(body)
    if ver != VERSION:
        raise FrameError(f"unknown version 0x{ver:02X}")
    return Telemetry(wid, seq, up, zc, hr, spo2, t10 / 10.0, flags, batt, hops, mtype)
