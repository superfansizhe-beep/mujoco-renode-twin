"""The bot's master loop: physics <-> mailbox <-> controller, 200 Hz.

One coupling period (= the declared IMU ODR):

  1. extract MuJoCo sensors -> raw-domain SensorFrame, seq++
  2. controller.step(frame)  -- the firmware slot (Python stub today)
  3. duty -> torque via the sheet motor model, zero-order hold
  4. 5 x 1 ms physics substeps

MuJoCo's accelerometer reports SPECIFIC FORCE in the site frame (0 in
free fall, +1 g up at rest) -- the same semantics as the real MPU6050,
so it maps to raw int16 verbatim (probe-verified, test-pinned).

Sign convention everywhere: + = forward (+Y). Wheel hinge axes are
(-1 0 0) so positive joint angle, joint rate, torque, encoder counts
and duty all mean forward on BOTH sides.
"""
import math
import time

import mujoco

from . import motors
from . import telemetry
from .backend import Controller
from .mailbox import MotorFrame, SensorFrame
from .sensors import ImuLowPass, WheelEncoder, accel_to_raw, gyro_to_raw

G = 9.81   # reference only: MuJoCo's accelerometer already includes it
COUPLING_S = 0.005        # 200 Hz
SUBSTEPS = 5              # x timestep 1 ms
TEMP_RAW_25C = -3920      # MPU6050: raw = (25 - 36.53) * 340

NUDGE_Force_N = 6.0       # horizontal push, applied one coupling period


class BotLoop:
    MOTOR_FRAME = MotorFrame     # the zero motor frame's type (race swaps it)

    def __init__(self, controller: Controller, battery: str = "3s") -> None:
        self.model = self._load_model()
        self.data = mujoco.MjData(self.model)
        self.v_batt = motors.BATTERY_NOMINAL[battery]
        # the controller slot: a caller-injected controller (the
        # RenodeFirmwareBackend) replaces the app's default stub; the
        # app subclass (twin.loop, race.loop) builds that default
        self.controller: Controller = controller
        self.paused = False
        self._seq = 0
        self._enc_l = WheelEncoder()
        self._enc_r = WheelEncoder()
        self._acc_lpf = ImuLowPass(cutoff_hz=25.0, dt=COUPLING_S)
        self._nudge_pending: tuple[float, float] | None = None
        self._sid = {name: mujoco.mj_name2id(
            self.model, mujoco.mjtObj.mjOBJ_SENSOR, name)
            for name in ("imu_accel", "imu_gyro",
                         "wheel_l_vel", "wheel_r_vel")}
        self.reset()

    # ---------------- model plumbing ----------------
    @staticmethod
    def _load_model() -> mujoco.MjModel:
        from . import mjcf              # deferred: pulls cad_modeling
        return mjcf.load_model()

    def reset(self) -> None:
        mujoco.mj_resetDataKeyframe(self.model, self.data, 0)
        self._seq = 0
        self._enc_l.reset()
        self._enc_r.reset()
        self._acc_lpf.reset()
        self.controller.reset()
        self.paused = False
        self.last_sensor = None
        self.last_motor = self.MOTOR_FRAME()

    def nudge(self, fx: float = 0.0, fy: float = NUDGE_Force_N,
              tx: float = 0.0) -> None:
        """Disturbance for the next coupling period: a Cartesian force at
        the chassis CoM (translation shove) and/or a torque about +X
        (pitch kick -- the visually obvious one)."""
        self._nudge_pending = (fx, fy, tx)

    # ---------------- sensor path ----------------
    def _sensor_adr(self, name: str) -> int:
        return self.model.sensor_adr[self._sid[name]]

    def read_sensors(self) -> SensorFrame:
        return SensorFrame(seq=self._seq, **self._imu_enc_fields())

    def _imu_enc_fields(self) -> dict:
        """Shared sensor path: IMU (LPF'd) + encoders, raw mailbox domain
        -- the fields every backend's sensor frame carries verbatim."""
        d = self.data
        # MuJoCo's accelerometer already reports SPECIFIC FORCE in the site
        # frame (0 in free fall, +1 g up at rest -- verified by probe and
        # pinned by test): identical semantics to the real MPU6050, so it
        # feeds the raw conversion directly. The first draft added gravity
        # on top (2 g magnitude, angle ratios coincidentally unaffected).
        a_sensor = d.sensordata[self._sensor_adr("imu_accel"):
                                self._sensor_adr("imu_accel") + 3]
        g_sensor = d.sensordata[self._sensor_adr("imu_gyro"):
                                self._sensor_adr("imu_gyro") + 3]
        accel_si = self._acc_lpf(a_sensor)
        return {
            "accel": accel_to_raw(accel_si),
            "gyro": gyro_to_raw(g_sensor),
            "temp_raw": TEMP_RAW_25C,
            "battery_mv": int(round(self.v_batt * 1000)),
            "enc_l": self._enc_l.update(d.qpos[7]),
            "enc_r": self._enc_r.update(d.qpos[8]),
        }

    # ---------------- actuator path ----------------
    def apply_motors(self, m: MotorFrame) -> None:
        d = self.data
        wl = d.sensordata[self._sensor_adr("wheel_l_vel")]
        wr = d.sensordata[self._sensor_adr("wheel_r_vel")]
        d.ctrl[0] = motors.torque_nm(m.duty_l, wl, self.v_batt)
        d.ctrl[1] = motors.torque_nm(m.duty_r, wr, self.v_batt)

    # ---------------- one coupling period ----------------
    def step_coupling(self) -> SensorFrame:
        if self.paused:
            # Desktop inspection pause freezes plant and firmware together.
            # Cutting torque while advancing physics made the parked view fall.
            if self.last_sensor is None:
                self.last_sensor = self.read_sensors()
            return self.last_sensor
        frame = self.read_sensors()
        self.last_sensor = frame
        self._seq += 1
        if not self.paused and abs(self.tilt_deg()) <= 55.0:
            motor = self.controller.step(frame)
            self._annotate(motor)
        else:
            motor = self.MOTOR_FRAME()   # paused or tipped over
        self.apply_motors(motor)
        if self._nudge_pending is not None:
            fx, fy, tx = self._nudge_pending
            self.data.xfrc_applied[1, :3] = (fx, fy, 0.0)   # body 1 = chassis
            self.data.xfrc_applied[1, 3:6] = (tx, 0.0, 0.0)
        for _ in range(SUBSTEPS):
            mujoco.mj_step(self.model, self.data)
        if self._nudge_pending is not None:
            self.data.xfrc_applied[1, :] = 0.0
            self._nudge_pending = None
        self.last_motor = motor
        return frame

    def _annotate(self, motor) -> None:
        """Hook after a live controller step (default: nothing to do)."""
        pass

    # ---------------- telemetry ----------------
    def tilt_deg(self) -> float:
        return telemetry.tilt_deg(self.data)

    def state(self) -> dict:
        m = getattr(self, "last_motor", MotorFrame())
        st = telemetry.pose_fields(
            self.data,
            duty=[m.duty_l, m.duty_r],
            enc=[self._enc_l.counts, self._enc_r.counts],
            batt_v=self.v_batt,
            paused=self.paused,
            fw_seq=getattr(self.controller, "fw_seq", None))  # fw heartbeat
        st["mode"] = self.controller.name
        return st

    # ---------------- drivers ----------------
    def run(self, seconds: float, realtime: bool = False,
            on_state=None, state_hz: float = 30.0, on_step=None) -> None:
        """Coupling loop for a virtual duration; on_state(state) fires at
        roughly state_hz of WALL time with the latest telemetry;
        on_step() fires at every coupling boundary BEFORE the step, so a
        command lands on the very next period -- a chunk-level pump held
        pauses ~300 ms behind 0.1 s chunks at 0.33x realtime (measured
        2026-10-01, output/performance-20261001/live.json). The firmware
        backend runs slower than realtime (Renode coupling), and a
        virtual-step cadence there throttles a realtime viewer to a few
        fps -- measured 4.8 fps at 0.17x realtime, 2026-10-01."""
        n = int(round(seconds / COUPLING_S))
        wall_start = time.perf_counter()
        next_state = wall_start
        for i in range(n):
            if on_step is not None:
                on_step()
            self.step_coupling()
            now = time.perf_counter()
            if on_state is not None and now >= next_state:
                on_state(self.state())
                next_state = now + 1.0 / state_hz
            if realtime:
                target = wall_start + (i + 1) * COUPLING_S
                delay = target - time.perf_counter()
                if delay > 0:
                    time.sleep(delay)
            elif self.paused:
                time.sleep(COUPLING_S)
