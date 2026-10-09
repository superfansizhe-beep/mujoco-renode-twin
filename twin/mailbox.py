"""Twin mailbox v2 -- the firmware-facing RAM contract (balance bot).

Address window: 0x2001_FFC0..0x2001_FFFF, the top 64 B of the F407's
REAL 128 K SRAM. The radar twin's 0x2003FFF0 does NOT exist on real
silicon (only in Renode's generous sysbus map) -- this layout must run
on the bought board, so it stays inside real RAM. The firmware linker
keeps out: SRAM LENGTH = 0x1FFC0 from 0x20000000 (see the radar
firmware's stm32f407.ld for the same trick).

Two directions, one window (little-endian 32-bit words):

  harness -> firmware (sensors):  magic, seq, accel, gyro, temp, batt, enc
  firmware -> harness (motors):   duty_l, duty_r, fw_seq

Word map (offsets from TWIN_BASE):

  +0x00  u32  magic 'TWN2' -- layout version; ANY layout change changes it
  +0x04  u32  seq          harness increments per sensor update; firmware
                           waits for a change == data-ready (mimics the
                           IMU ODR strobe; 200 Hz = the declared ODR)
  +0x08  i16 x3  accel raw (MPU6050 +-2g domain)
  +0x0E  i16 x3  gyro raw (+-250 dps domain)
  +0x14  i16  temp_raw     degC = raw/340 + 36.53 (chip formula)
  +0x16  u16  battery_mv
  +0x18  i32  enc_l        accumulated counts, 1320/rev, + = forward
  +0x1C  i32  enc_r
  +0x20  i16  duty_l       permille, -1000..1000, + = forward
  +0x22  i16  duty_r
  +0x24  u32  fw_seq       firmware increments per control cycle --
                           the heartbeat: harness reads it to tell
                           "firmware alive" from "mailbox untouched"

v2 (2026-09-28): +0x24 reserved -> fw_seq, magic 'TWNB' -> 'TWN2'.
The Python stub backend passes frames as dataclasses; the Renode
backend produces the same word image via pyrenode3 sysbus calls.
"""
import struct

from bot.mailbox import (
    MotorFrame, SensorFrame, hi16, lo16, pair32, u32_to_i32,
)

MAGIC = 0x54574E32            # 'TWN2'
TWIN_BASE = 0x2001FFC0
TWIN_SIZE = 0x40
WORD_FMT = "<10I"             # 10 words = 40 B of the 64 B window
assert TWIN_BASE + TWIN_SIZE == 0x20020000, "window must end at SRAM2 top"


def pack_sensors(f: SensorFrame, magic: int = MAGIC) -> list[int]:
    """The full 10-word window with firmware-owned words (duty, fw_seq)
    zeroed (harness never writes them on the wire; they live in the same
    packed image so the round-trip tests see exactly what RAM will hold).
    All words are unsigned u32 two's-complement images -- struct '<10I'
    rejects negatives, and the sysbus WriteDoubleWord wants that image."""
    return [
        magic,
        f.seq & 0xFFFFFFFF,
        pair32(f.accel[0], f.accel[1]),
        pair32(f.accel[2], f.gyro[0]),
        pair32(f.gyro[1], f.gyro[2]),
        pair32(f.temp_raw, f.battery_mv),
        f.enc_l & 0xFFFFFFFF,
        f.enc_r & 0xFFFFFFFF,
        0,
        0,
    ]


def pack_motor(m: MotorFrame) -> dict[int, int]:
    """Motor word as address offset -> u32 (harness reads it back)."""
    return {0x20: pair32(m.duty_l, m.duty_r)}


def decode_motor(duty_word: int, fw_seq_word: int) -> MotorFrame:
    """RAM word pair (+0x20, +0x24) -> MotorFrame -- what the Renode
    backend reads back after each RunFor."""
    return MotorFrame(duty_l=lo16(duty_word), duty_r=hi16(duty_word),
                      fw_seq=fw_seq_word)


def unpack_words(words: list[int]):
    """10-word RAM image -> (SensorFrame, MotorFrame); the Renode backend
    will decode read-back words through this same function."""
    assert len(words) == 10
    sf = SensorFrame(
        seq=words[1],
        accel=(lo16(words[2]), hi16(words[2]), lo16(words[3])),
        gyro=(hi16(words[3]), lo16(words[4]), hi16(words[4])),
        temp_raw=lo16(words[5]),
        battery_mv=words[5] >> 16,
        enc_l=u32_to_i32(words[6]),
        enc_r=u32_to_i32(words[7]),
    )
    mf = MotorFrame(duty_l=lo16(words[8]), duty_r=hi16(words[8]),
                    fw_seq=words[9])
    return sf, mf


def to_bytes(words: list[int]) -> bytes:
    return struct.pack(WORD_FMT, *words)


def from_bytes(buf: bytes) -> list[int]:
    return list(struct.unpack(WORD_FMT, buf))
