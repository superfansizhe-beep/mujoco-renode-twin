"""Sensor peripherals: IMU raw-domain conversion + wheel encoders.

The mailbox carries RAW MPU6050-domain int16 values, not SI floats, so the
future firmware's scaling path (raw -> g -> m/s^2, raw -> dps -> rad/s)
runs identically in the twin. Full-scale selection lives here once and
must match the firmware's MPU6050 config registers:

  accel +-2 g   -> 16384 LSB/g
  gyro  +-250 dps -> 131 LSB/(deg/s)

Sign conventions (pinned by tests against a pitched model):
  +Z up, +X out the right side, +Y forward (the CAD frame);
  at rest upright the accelerometer reads (0, 0, +1 g) -- specific force,
  exactly like the real chip; gyro is the body-frame rate about +X = pitch
  rate, positive = nose up.
"""
import math

from cad_modeling.layout import WHEEL_R

G_MPS2 = 9.81
ACCEL_LSB_PER_G = 16384.0
GYRO_LSB_PER_DPS = 131.0

COUNTS_PER_REV = 1320       # 11 PPR x 4 (quadrature) x 30 (gear), sheet
# encoder counts per meter of travel (5252 counts/m on the D80 guess
# wheel); WHEEL_R arrives from cad_modeling.layout in MILLIMETERS
COUNTS_PER_M = COUNTS_PER_REV / (2.0 * math.pi * (WHEEL_R / 1000.0))
INT16_MIN, INT16_MAX = -32768, 32767

# ---- 8-way line-follow bar (sample sites live in bot.mjcf) ----
N_LINE_SENSORS = 8
LINE_PITCH = 0.011            # m, bar sensor spacing (GUESS, caliper
                              # pending; the CAD fixes only the 91.11 mm
                              # envelope, vendor drawing)


def _clamp16(v: float) -> int:
    return max(INT16_MIN, min(INT16_MAX, int(round(v))))


def accel_to_raw(accel_mps2) -> tuple[int, int, int]:
    return tuple(_clamp16(a / G_MPS2 * ACCEL_LSB_PER_G) for a in accel_mps2)


def gyro_to_raw(gyro_rad_s) -> tuple[int, int, int]:
    return tuple(
        _clamp16(w * 180.0 / math.pi * GYRO_LSB_PER_DPS) for w in gyro_rad_s)


# ---- firmware-direction decoding (what the C side will do) ----
def accel_raw_to_mps2(raw) -> tuple[float, float, float]:
    return tuple(r / ACCEL_LSB_PER_G * G_MPS2 for r in raw)


def gyro_raw_to_rad_s(raw) -> tuple[float, float, float]:
    return tuple(r / GYRO_LSB_PER_DPS * math.pi / 180.0 for r in raw)


def accel_to_tilt_rad(accel_mps2) -> float:
    """Pitch from a gravity-only accel reading: atan2(ay, az).

    Valid when linear acceleration is small (the classic accel-only tilt
    limitiation the complementary filter exists to fix).
    """
    return math.atan2(accel_mps2[1], accel_mps2[2])


class ImuLowPass:
    """One-pole lowpass standing in for the MPU6050's hardware DLPF.

    MuJoCo's soft contacts ring at the solref frequency with ~1 g
    amplitude at the site; the real chip never sees that because its
    DLPF (10-42 Hz taps) removes it before the register. Without this
    filter the complementary filter's gravity correction eats the
    ringing and the fused tilt drifts degrees off the truth.
    """

    def __init__(self, cutoff_hz: float = 25.0, dt: float = 1.0 / 200.0) -> None:
        rc = 1.0 / (2.0 * math.pi * cutoff_hz)
        self.alpha = dt / (dt + rc)
        self.state: tuple | None = None

    def __call__(self, v):
        import numpy as _np
        if self.state is None:
            self.state = _np.array(v, dtype=float)
        else:
            self.state += self.alpha * (_np.asarray(v, dtype=float) - self.state)
        return tuple(float(x) for x in self.state)

    def reset(self) -> None:
        self.state = None


class WheelEncoder:
    """Quadrature counter fed by the wheel hinge angle (1320 counts/rev).

    The twin reads the exact joint angle, so counts are derived, never
    integrated -- no drift by construction. int32 wrap like the timer
    counter the firmware will read.
    """

    def __init__(self) -> None:
        self._last_angle = 0.0
        self.counts = 0

    def update(self, angle_rad: float) -> int:
        self.counts += int(round(
            (angle_rad - self._last_angle) / (2.0 * math.pi) * COUNTS_PER_REV))
        self._last_angle = angle_rad
        self.counts = ((self.counts + 2**31) % 2**32) - 2**31   # int32 wrap
        return self.counts

    def reset(self) -> None:
        self._last_angle = 0.0
        self.counts = 0
