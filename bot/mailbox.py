"""Mailbox word-packing helpers + the base frame payloads -- one impl
shared by every RAM contract.

The layout tables themselves are per-app: twin.mailbox (TWN2, balance
demo) and race.mailbox (RAC2, exam) both pack little-endian 32-bit
words of int16/uint16 pairs, so the packing arithmetic lives here once.
SensorFrame/MotorFrame are the vehicle's base payload types (what the
harness streams the firmware, what a controller answers back); race's
mailbox declares its own extended frames.
"""
from dataclasses import dataclass

MAGIC_BASE = 0x5457494E      # 'TWIN' -- must stay distinct (different project)


def pair32(lo: int, hi: int) -> int:
    """Two int16s into one little-endian u32."""
    return (lo & 0xFFFF) | ((hi & 0xFFFF) << 16)


def lo16(word: int) -> int:
    v = word & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def hi16(word: int) -> int:
    v = (word >> 16) & 0xFFFF
    return v - 0x10000 if v >= 0x8000 else v


def u32_to_i32(word: int) -> int:
    return word - 0x100000000 if word >= 2**31 else word


@dataclass
class SensorFrame:
    """harness -> firmware, one per coupling period (200 Hz)."""
    seq: int = 0
    accel: tuple = (0, 0, 0)        # raw int16
    gyro: tuple = (0, 0, 0)         # raw int16
    temp_raw: int = 0               # ~0 at 25 degC: 25 = raw/340+36.53
    battery_mv: int = 0
    enc_l: int = 0
    enc_r: int = 0


@dataclass
class MotorFrame:
    """firmware -> harness."""
    duty_l: int = 0                 # permille
    duty_r: int = 0
    fw_seq: int = 0                 # heartbeat, one per control cycle
