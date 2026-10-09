"""Race mailbox RAC2 -- the exam firmware's RAM contract.

Same window trick as the balance twin: the top 64 B of the F407's REAL
128 K SRAM (0x2001_FFC0..0x2001_FFFF; the linker keeps firmware out via
SRAM LENGTH=0x1FFC0). The race controller sees exactly this word image
and nothing else -- no MuJoCo ground truth, same discipline as
twin.mailbox.

Superset of twin v2 (TWN2): adds the 8-way line-bar mask + the task
select in the sensor direction, and buzzer/LED + the mission status
words in the motor direction. Any layout change bumps the magic.

v2 (RAC2, 2026-09-28): +0x22 reserved -> task (harness->fw, boot-time
route select: byte0 task 1..4, byte1 turbo); +0x30..0x38 reserved ->
fw->harness mission telemetry (phase/seg_i, mission clock, e_lat/v_plan,
odo) -- what the grader/HUD reads off the REAL firmware instead of the
Python stub's internals. v1 (RAC1) had neither; magic bumped with it.

Word map (offsets from RACE_BASE, little-endian u32 words):

  +0x00  u32  magic 'RAC2'
  +0x04  u32  seq          harness increments per sensor update (200 Hz)
  +0x08  i16x3  accel raw (MPU6050 +-2 g domain)
  +0x0E  i16x3  gyro raw (+-250 dps domain)
  +0x14  i16  temp_raw     degC = raw/340 + 36.53
  +0x16  u16  battery_mv
  +0x18  i32  enc_l        accumulated counts, 1320/rev, + = chassis +Y
  +0x1C  i32  enc_r
  +0x20  u16  line_bits    bit i = bar sensor i sees tape (i asc with x)
  +0x22  u16  task         harness->fw: byte0 = task 1..4, bit8 = turbo
  +0x24  i16  duty_l       permille, -1000..1000, + = chassis +Y
  +0x26  i16  duty_r
  +0x28  u16  buzzer_ms    remaining beep time (0 = silent)
  +0x2A  u16  led          bit0 = LED on
  +0x2C  u32  fw_seq       firmware heartbeat, one per control cycle
  +0x30  u32  status       fw->harness: byte0 phase (0arm/1run/2brake/
                           3done), byte1 seg_i; bits16-17 line source
                           (0 odometry, 1 sensor, 2 hold), bits18-19 raw
                           detection (0 lost, 1 track, 2 wide, 3 split),
                           bit20 array centered (heading independent)
  +0x34  u32  t_mission_ms fw->harness: mission clock (t - t_start while
                           running, frozen at t_done; 0 before start)
  +0x38  i16  e_lat_mm     fw->harness applied steering error (+ tape-left)
  +0x3A  u16  v_plan_mm_s  fw->harness telemetry (planned speed)
  +0x3C  u32  odo_cm       fw->harness telemetry: i16 x | i16 y, cm
                           -- 16 words total = the full 64 B window
"""
import struct
from dataclasses import dataclass

from bot.mailbox import (
    MAGIC_BASE, hi16, lo16, pair32, u32_to_i32,   # word helpers: one impl, bot's
)

# 'TWN2' -- the balance twin app's layout magic, pinned here as a literal
# so neither this app nor its tests import the sibling app; if twin ever
# bumps its magic, refresh this literal to keep the assert below honest.
TWIN_MAGIC_TWN2 = 0x54574E32

MAGIC = 0x52414332            # 'RAC2'
assert MAGIC not in (TWIN_MAGIC_TWN2, MAGIC_BASE), \
    "race magic must stay distinct from the other twins"
RACE_BASE = 0x2001FFC0
RACE_SIZE = 0x40
WORD_FMT = "<16I"
assert RACE_BASE + RACE_SIZE == 0x20020000, "window must end at SRAM top"


@dataclass
class RaceSensorFrame:
    """harness -> firmware, one per coupling period (200 Hz)."""
    seq: int = 0
    accel: tuple = (0, 0, 0)        # raw int16
    gyro: tuple = (0, 0, 0)         # raw int16
    temp_raw: int = 0
    battery_mv: int = 0
    enc_l: int = 0
    enc_r: int = 0
    line_bits: int = 0              # bit i = sensor i over tape
    task: int = 0                   # byte0 task 1..4, bit8 turbo (boot-time)


@dataclass
class RaceMotorFrame:
    """firmware -> harness."""
    duty_l: int = 0                 # permille
    duty_r: int = 0
    buzzer_ms: int = 0
    led: int = 0
    fw_seq: int = 0
    status: int = 0                 # phase/segment + line source/observation
    t_mission_ms: int = 0
    e_lat_mm: int = 0
    v_plan_mm_s: int = 0
    odo_cm: tuple = (0, 0)


def pack_sensors(f: RaceSensorFrame, magic: int = MAGIC) -> list[int]:
    """Full 16-word window with firmware-owned words zeroed."""
    return [
        magic,
        f.seq & 0xFFFFFFFF,
        pair32(f.accel[0], f.accel[1]),
        pair32(f.accel[2], f.gyro[0]),
        pair32(f.gyro[1], f.gyro[2]),
        pair32(f.temp_raw, f.battery_mv),
        f.enc_l & 0xFFFFFFFF,
        f.enc_r & 0xFFFFFFFF,
        pair32(f.line_bits, f.task),
        0,                          # word 9  duty pair: firmware-owned
        0,                          # word 10 buzzer/led: firmware-owned
        0,                          # word 11 fw_seq: firmware-owned
        0, 0, 0, 0,                 # words 12-15 status/telemetry: fw-owned
    ]


def unpack_words(words: list[int]):
    """16-word RAM image -> (RaceSensorFrame, RaceMotorFrame)."""
    assert len(words) == 16
    sf = RaceSensorFrame(
        seq=words[1],
        accel=(lo16(words[2]), hi16(words[2]), lo16(words[3])),
        gyro=(hi16(words[3]), lo16(words[4]), hi16(words[4])),
        temp_raw=lo16(words[5]),
        battery_mv=words[5] >> 16,
        enc_l=u32_to_i32(words[6]),
        enc_r=u32_to_i32(words[7]),
        line_bits=words[8] & 0xFFFF,
        task=(words[8] >> 16) & 0xFFFF,
    )
    mf = RaceMotorFrame(duty_l=lo16(words[9]), duty_r=hi16(words[9]),
                        buzzer_ms=words[10] & 0xFFFF,
                        led=(words[10] >> 16) & 0xFFFF,
                        fw_seq=words[11],
                        status=words[12],
                        t_mission_ms=words[13],
                        e_lat_mm=lo16(words[14]),
                        v_plan_mm_s=words[14] >> 16,
                        odo_cm=(lo16(words[15]), hi16(words[15])))
    return sf, mf


def to_bytes(words: list[int]) -> bytes:
    return struct.pack(WORD_FMT, *words)


def from_bytes(buf: bytes) -> list[int]:
    return list(struct.unpack(WORD_FMT, buf))
