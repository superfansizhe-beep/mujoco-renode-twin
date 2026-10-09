"""Controllers -- the firmware slot of the bot.

Phase 1: a Python stub. It sees EXACTLY what the C firmware will see --
the raw int16 mailbox frame, no MuJoCo ground truth -- and emits the
same motor permille command. When the F407 firmware exists, a
RenodeFirmwareBackend drops in behind this same interface:

    step():  write SensorFrame words into Renode SRAM via monitor
             WriteDoubleWord (one command_batch), RunFor(coupling_s),
             read the motor word back -- the radar twin's twin_step
             pattern, one round-trip per slice.

The balance stub is deliberately firmware-shaped: decode raw -> SI,
complementary-filter the pitch, PD + wheel-speed damping, map the
desired torque back to duty. It is environment validation, not the
"real" control design -- gains live here until the C takes over.
"""
from abc import ABC, abstractmethod
import math

from cad_modeling.layout import WHEEL_R

from . import motors
from .mailbox import MotorFrame, SensorFrame
from .sensors import (
    COUNTS_PER_M, COUNTS_PER_REV, accel_raw_to_mps2, accel_to_tilt_rad,
    gyro_raw_to_rad_s,
)


class Controller(ABC):
    name = "controller"

    @abstractmethod
    def reset(self) -> None: ...

    @abstractmethod
    def step(self, s: SensorFrame) -> MotorFrame: ...


class BalanceController(Controller):
    """Cascade balance: position/velocity outer loop -> commanded lean,
    complementary-filtered pitch PD inner loop -> torque.

    Structure is production-firmware-shaped: a bare tilt PD has NO
    stationary equilibrium on a wheeled inverted pendulum (constant lean
    -> constant wheel torque -> constant acceleration -- the bot drifts
    forever); the outer loop steers the commanded lean so the station
    is kept. The trim constant (the lean that parks the CoM over the
    contact line) is hand-calibrated on real firmware; the stub derives
    it from the bot's own mass table so it tracks mass-table edits.

    Signs (pinned by tests): theta > 0 = nose up; gyro_x > 0 = nose-up
    rate; positive duty = forward wheel torque.

    DUTY_CAP is traction authority, not motor limit: the grip budget is
    mu*N_wheel*R ~= 1.2 * 5.3 N * 0.04 m ~= 0.25 N*m per wheel, while
    stall at the 3S pack is 0.53 N*m -- an uncapped command just burns
    rubber. 450 permille ~= 0.24 N*m stays inside the friction cone.
    """

    ALPHA = 0.98           # filter weight on the gyro integration
    DUTY_CAP = 450         # permille; traction-limited, see class docstring
    # LQR gains over z = [y, ydot, theta-theta_ref, thetadot], derived from
    # the twin itself (bot.lqr, Q=(40,1,200,2), r=8, sphere-tire contacts,
    # lowered 2026-09-29 housing / 3S LiPo mass table).
    # Recompute after mass-table edits.
    K_LQR = (-0.8435, -1.3297, 1.9785, 0.2107)

    def __init__(self, dt: float = 0.005, v_batt: float = 11.1) -> None:
        self.name = "balance"
        self.dt = dt
        self.v_batt = v_batt
        self.theta = None
        self._last_enc = None
        self.pos_m = 0.0
        # Firmware-style trim: the lean that parks the CoM over the WHEEL
        # CONTACT line -- mjcf.hover_trim_rad() is the single derivation
        # (the keyframe starts there too). Real firmware hand-calibrates
        # this constant; the stub derives it from the bot's own mass
        # table so it tracks mass-table edits.
        from .mjcf import hover_trim_rad    # deferred: pulls cad_modeling
        self.theta_ref = hover_trim_rad()

    def reset(self) -> None:
        self.theta = None
        self._last_enc = None
        self.pos_m = 0.0

    def step(self, s: SensorFrame) -> MotorFrame:
        accel = accel_raw_to_mps2(s.accel)
        gyro = gyro_raw_to_rad_s(s.gyro)
        if self.theta is None:                       # first sample: trust gravity
            self.theta = accel_to_tilt_rad(accel)
        self.theta = (self.ALPHA * (self.theta + gyro[0] * self.dt)
                      + (1.0 - self.ALPHA) * accel_to_tilt_rad(accel))

        if self._last_enc is None:
            self._last_enc = (s.enc_l + s.enc_r) / 2.0
            wheel_rate = 0.0
        else:
            enc_mean = (s.enc_l + s.enc_r) / 2.0
            d_counts = enc_mean - self._last_enc
            wheel_rate = d_counts / COUNTS_PER_REV * 2.0 * math.pi / self.dt
            self.pos_m += d_counts / COUNTS_PER_M
            self._last_enc = enc_mean
        speed_mps = wheel_rate * (WHEEL_R / 1000.0)

        # LQR state feedback on [y, ydot, theta - theta_ref, thetadot],
        # every term mailbox-sourced (encoders, filtered IMU, gyro)
        z = (self.pos_m, speed_mps, self.theta - self.theta_ref, gyro[0])
        tau = -(self.K_LQR[0] * z[0] + self.K_LQR[1] * z[1]
                + self.K_LQR[2] * z[2] + self.K_LQR[3] * z[3])
        duty = motors.torque_to_duty(tau, self.v_batt)
        duty = max(-self.DUTY_CAP, min(self.DUTY_CAP, duty))
        return MotorFrame(duty_l=duty, duty_r=duty)
