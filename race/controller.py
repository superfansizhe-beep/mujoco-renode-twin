"""Race controller -- the exam firmware in the twin's backend slot.

Sees ONLY the RAC2 mailbox frame (raw IMU, encoder counts, 8-bit line
mask) -- no MuJoCo ground truth. Firmware-shaped layers:

  estimate   complementary-filtered pitch (twin balance stub's math),
             gyro-Z integrated heading, encoder dead-reckoning position
  mission    route walker over race.track: segment progress by
             projecting the ODOMETRY pose (the rules hand the firmware
             its start box, so the spawn prior is legitimate), node
             trigger inside 5 cm, beep+LED per node, lap count, final
             brake-to-stop with a real stopped check
  follow     on the taped ARCS: a valid contiguous line-bar detection
             + heading error + curvature
             feedforward -> yaw-rate command. On the untaped legs
             (the exam field marks nothing but the two arcs) the same
             law runs as PLANNED blind flight: heading hold on the
             leg's tangent + odometry cross-track, full cruise, no
             search sweep -- the bar meets the next arc's entry tape
             one bar-lead before the node and capture is tangent-smooth
  balance    the twin's LQR on [y - y_ref, ydot - v_ref, th - trim,
             thdot] with the reference integrating the speed plan --
             velocity tracking = station keeping on a moving reference,
             the standard segway trick. Gains imported from bot
             (single source: recompute there after mass edits).
  steering   yaw-rate P -> differential torque about the common mode

Sign chain (derived once, pinned by probe + bring-up):
  travel = chassis -Y (bar-first);   chassis +X = travel-LEFT;
  +lat / +e = tape to the travel-left;  +yaw = world CCW;
  CCW needs +torque on wheel_r (the chassis +X / travel-left wheel);
  encoders/duty stay in the twin's chassis frame (+ = chassis +Y =
  travel BACKWARD, hence the minus signs at the plan/estimate seams).
"""
import math

from bot import motors
from bot.backend import BalanceController
from bot.mjcf import hover_trim_rad
from bot.sensors import (
    COUNTS_PER_M, COUNTS_PER_REV, LINE_PITCH, N_LINE_SENSORS,
    accel_raw_to_mps2, accel_to_tilt_rad, gyro_raw_to_rad_s,
)
from cad_modeling.layout import TRACK_HALF, WHEEL_R
from bot.line_sensor import (LineTracker, LineEndpoint, observe, BAR_AHEAD_M,
                             MASK, END_PROGRESS_MIN)

from . import tasks, track
from .mailbox import RaceMotorFrame, RaceSensorFrame

ARM_S = 0.30                 # settle on the balance loop before moving
A_MAX = 0.25
A_MAX_KINK = 0.12            # m/s^2 ramp after a deep kink: the full ramp
                              # out of the near-stall excites the pitch
                              # past its damping
A_MAX_BRAKE = 0.6            # m/s^2 brake ramp: the accel ramp coasts
                              # half a meter past the final node
# reference governor: y_ref leaks toward y so ramp lag never winds up a
# position error the station-keeping gains would rail duty on.
REF_LEAK = 0.08              # m/s
REF_LEAK_BRAKE = 0.30        # m/s, brake/done: follow the physical coast
                              # so the stop lands at the node, not a
                              # station 0.3 m back
STOP_V = 0.03                # m/s, stopped if below (with STOP_W) for STOP_S
STOP_V_LPF_HZ = 10.0         # stop estimate: suppress encoder-bin chatter;
                              # odometry and balance still use raw deltas
STOP_W = 0.35                # rad/s
STOP_S = 0.45
BEEP_MS = 150
LED_MS = 250

# Straight legs are blind: higher targets consume balance authority
# with less than 0.1 s saved in comparable four-lap host-C trials.
SPEED_BASE = {"straight": 0.28, "r40": 0.155, "node": 0.18}
# Faster arcs retain the node slowdown and the 450-permille traction cap.
# 0.28 arcs failed a full-cycle delay trial; 0.26 with the 40 Hz yaw
# filter passes low voltage, reduced grip, a shove and that same delay.
SPEED_TURBO = {"straight": 0.28, "r40": 0.26, "node": 0.20}

KP_LAT = 16.0                # (rad/s)/m lateral error (on-tape + recovery)
KD_RATE = 0.6                # yaw-rate damping about the feedforward rate
KP_HEAD = 1.2                # (rad/s)/rad heading error
LOST_S = 0.3                 # s without tape before the re-acquire slowdown
SWEEP_AFTER = 1.5            # s lost before the recovery sweeps: the
                              # dead-reckoned path can run parallel to
                              # the tape and never cross it
SWEEP_RAD = 0.9              # rad of heading sweep amplitude
SWEEP_T = 6.0                # s sweep period (at the 0.12 m/s creep,
                              # ~0.17 m of lateral corridor per half-sweep)
PARK_LOST_S = 10.0           # s of lost tape before parking: the sweep
                              # gets ~8 s of search first
E_SLOW = 0.030               # m of lateral error that slows the cruise
E_SLOW_V = 0.22              # m/s cruise cap while off-center
ODO_K = 0.02                 # per-cycle lateral correction gain (200 Hz ->
                              # ~0.25 s time constant)
SCRUB_K = 0.15               # travel discount per rad/s of yaw (arc
                              # overcount calibration, see step())
ENC_SCALE = 1.0              # sphere-tire effective radius runs ~7%
                              # small on the soft floor: raw counts
                              # overread travel by that much
# the finish line is dead-reckoned lead meters early: a tangent-
# continuous final exit never fires the physical tape triggers
FINAL_LEAD = 0.25            # multi-segment routes (brake coast ~0.3 m)
FINAL_LEAD_SHORT = 0.20      # single-segment (task 1): the beep must not
                              # fire further out than the node zone
BLOB_MIN = 6                 # active sensors that read as a junction blob
BLOB_S = 0.04                # s of sustained blob before it counts
ALIGN_MAX_S = 1.5            # post-node heading-align window
K_ALIGN = 3.0                # (rad/s)/rad kink heading servo gain
KINK_STOP = 0.45             # rad of kink -> rotate IN PLACE: the 63 mm
                              # bar lead sweeps a big kink out of capture
                              # range; capture only after the rotation
KINK_GO = 0.12               # rad of kink below which normal following
                              # resumes
W_CMD_CAP = 1.2              # rad/s
W_LPF_HZ = 40.0              # steering-path yaw-rate lowpass: the raw
                              # gyro rides contact ringing and the servo
                              # would relay on its slew limit (~8 Hz);
                              # less phase lag preserves tracking with an
                              # extra 5 ms of actuator delay
K_YAW = 0.5                  # N*m/(rad/s) yaw-rate torque servo on the
                              # FILTERED rate -- the two-wheel-car's
                              # actual steering actuator (wheel-speed
                              # difference detaches from true yaw under
                              # scrub)
TAU_D_CAP = 0.10             # N*m, differential budget
KI_YAW = 0.8                 # N*m/(rad*s) slow integral on the yaw-rate
                              # error: kills the P droop (arcs deliver
                              # ~70% of command); clamped hard
TAU_WI_CAP = 0.06            # N*m, yaw integral clamp
DUTY_D_CAP = 200             # permille, differential budget
DUTY_D_SLEW = 25             # permille/cycle differential slew (200 Hz)
TRACK_M = TRACK_HALF * 2.0 * 1e-3   # wheel track, m (CAD mm)


def _wrap(a: float) -> float:
    return (a + math.pi) % (2.0 * math.pi) - math.pi


def _seg_class(kappa: float) -> str:
    if abs(kappa) < 1e-6:
        return "straight"
    return "r40"          # the field's only taped bends: the two R40 arcs


class RaceController:
    name = "race"

    def __init__(self, task: int, dt: float, v_batt: float,
                 turbo: bool | None = None) -> None:
        self.task = task
        self.dt = dt
        self.v_batt = v_batt
        # Fast mode is the normal exam profile for every task.  Keep an
        # explicit False as a deliberate safe/reference override so the
        # slow table remains available for controlled comparisons.
        self.turbo = (True if turbo is None else bool(turbo)) or task == 4
        self.speeds = SPEED_TURBO if self.turbo else SPEED_BASE
        self.spec = tasks.task_spec(task)
        self.route = self.spec["route"]
        self.theta_ref = hover_trim_rad()

    # ---------------- lifecycle ----------------
    def reset(self, x0: float, y0: float, psi0: float) -> None:
        """(x0, y0, psi0) = spawn axle position and travel heading -- a
        rules-given prior, exactly what real firmware assumes in the
        start box."""
        self.t = 0.0
        self.seq = 0
        self.theta = None
        self._last_enc: tuple | None = None
        # odometry (travel frame: psi = world CCW heading of travel)
        self.psi = psi0
        self.odo_x, self.odo_y = x0, y0
        self.v_cy = 0.0                    # chassis +Y speed (travel = -)
        # LQR moving reference, chassis +Y domain
        self.y = 0.0
        self.y_ref = 0.0
        self.v_plan = 0.0
        self.v_stop = 0.0
        # mission
        self.phase = "arm"                 # arm -> run -> brake -> done
        self.seg_i = 0
        self.t_start = None
        self.t_done = None
        self.stop_hold = 0.0
        self.events: list[dict] = []
        # actuator-side state
        self.buzzer_ms = 0
        self.led_ms = 0
        self._line_tracker = LineTracker()
        self._line_endpoint = LineEndpoint()
        self._line_bits = 0
        self.e_lat = 0.0
        self.w_cmd = 0.0
        self.w_meas = 0.0
        self.tau_d = 0.0
        self.lost_t = 0.0
        self.blob_t = 0.0
        self._prev_bits = 0
        self.align_t0 = -1e9
        self._duty_d_prev = 0
        self._w_integ = 0.0
        self.w_f = 0.0
        self.v_diff = 0.0
        if self.task != 1:
            self._beep("A", kind="start")

    def _beep(self, node: str, kind: str = "node") -> None:
        self.buzzer_ms = BEEP_MS
        self.led_ms = LED_MS
        self.events.append(
            {"kind": kind, "node": node, "t": round(self.t, 3)})

    # ---------------- one control cycle ----------------
    def step(self, s: RaceSensorFrame) -> RaceMotorFrame:
        self.seq += 1
        self.t += self.dt

        # ---- estimate (mailbox domain -> SI) ----
        accel = accel_raw_to_mps2(s.accel)
        gyro = gyro_raw_to_rad_s(s.gyro)
        if self.theta is None:
            self.theta = accel_to_tilt_rad(accel)
        self.theta = (BalanceController.ALPHA
                      * (self.theta + gyro[0] * self.dt)
                      + (1.0 - BalanceController.ALPHA)
                      * accel_to_tilt_rad(accel))

        if self._last_enc is None:
            d_enc = 0.0
            d_enc_l = d_enc_r = 0.0
            self._last_enc = (s.enc_l, s.enc_r)
        else:
            d_enc_l = (s.enc_l - self._last_enc[0]) * ENC_SCALE
            d_enc_r = (s.enc_r - self._last_enc[1]) * ENC_SCALE
            d_enc = (d_enc_l + d_enc_r) / 2.0
            self._last_enc = (s.enc_l, s.enc_r)
        self.v_cy = d_enc / COUNTS_PER_M / self.dt
        v_wheel_l = d_enc_l / COUNTS_PER_M / self.dt
        v_wheel_r = d_enc_r / COUNTS_PER_M / self.dt
        av = self.dt / (self.dt + 1.0 / (2.0 * math.pi * 25.0))
        self.v_diff += ((v_wheel_r - v_wheel_l) - self.v_diff) * av
        # chassis +Y path length (scalar) as the LQR's y -- the standard
        # firmware approximation on arcs
        self.y += self.v_cy * self.dt
        v_travel = -self.v_cy
        # scrub: sphere tires yaw-scrub on arcs and the encoders overcount
        # travel ~15% at w=0.45 rad/s -- discount by yaw rate
        v_travel *= max(0.0, 1.0 - SCRUB_K * abs(gyro[2]))
        # psi_dot in the world frame is omega_z/cos(theta): the body-frame
        # gyro reads ~4.3% short at the cruise trim (~8 deg over an arc)
        self.psi = _wrap(self.psi + gyro[2]
                         / max(0.5, math.cos(self.theta)) * self.dt)
        self.w_meas = gyro[2]
        # the lowpass a real chip's DLPF would do in hardware
        a = self.dt / (self.dt + 1.0 / (2.0 * math.pi * W_LPF_HZ))
        self.w_f += (gyro[2] - self.w_f) * a
        self.odo_x += v_travel * math.cos(self.psi) * self.dt
        self.odo_y += v_travel * math.sin(self.psi) * self.dt

        # ---- mission ----
        # project before _mission: it may advance the segment, and the
        # plan/steering below re-project afterwards
        seg = self.route[min(self.seg_i, len(self.route) - 1)]
        s_seg, _, _ = seg.project(self.odo_x, self.odo_y)
        self._line_bits = s.line_bits & MASK
        line_obs = observe(self._line_bits)
        pop = line_obs.count
        if line_obs.status == "wide" and pop >= BLOB_MIN:
            self.blob_t += self.dt
        else:
            self.blob_t = 0.0
        # Optical node evidence needs the planned arc's endpoint as well
        # as a pattern transition; missing input alone is not an endpoint.
        lead = BAR_AHEAD_M / max(0.5, math.cos(self.theta))
        near_tape_end = (seg.taped
                         and s_seg >= seg.length - lead - track.TRIGGER_R)
        # Confirm a clean-to-white endpoint. Longitudinal odometry drifts
        # on arcs, so use a late-arc window plus persistent white input.
        junction = self.blob_t >= BLOB_S and near_tape_end
        tape_end = self._line_endpoint.update(
            line_obs, seg.taped, s_seg >= END_PROGRESS_MIN * seg.length, self.dt)
        self._prev_bits = self._line_bits
        previous_segment = self.seg_i
        # At 200 Hz one average encoder count is ~0.019 m/s. Raw bins
        # can reset the stopped timer while the chassis is already still.
        # Filter only the stopped-check estimate; preserve raw odometry,
        # speed feedback, the 3 cm/s threshold and the 450 ms hold.
        av_stop = self.dt / (self.dt + 1.0 / (2.0 * math.pi * STOP_V_LPF_HZ))
        self.v_stop += (v_travel - self.v_stop) * av_stop
        self._mission(self.v_stop, gyro[2], junction or tape_end)
        if self.seg_i != previous_segment:
            self._line_endpoint.reset()

        # ---- speed plan (travel frame, applied via chassis -sign) ----
        seg = self.route[min(self.seg_i, len(self.route) - 1)]
        s_seg, lat_odom, _ = seg.project(self.odo_x, self.odo_y)
        blind = not seg.taped          # untaped leg: planned open-white run
        v_target = 0.0 if self.phase in ("brake", "done") else \
            self.speeds[_seg_class(seg.curvature_at(s_seg))]
        # node approach slowdown: the +-47.5 mm capture band survives a
        # kink crossing only while v*sin(kink) is small -- cap the last
        # 15 cm before every node
        if s_seg > seg.length - 0.15:
            v_target = min(v_target, self.speeds["node"])
        kink_err = 9.9
        if self.t - self.align_t0 < ALIGN_MAX_S:
            kink_err = abs(_wrap(seg.heading_at(0.05) - self.psi))
            if kink_err > KINK_GO:
                if kink_err > KINK_STOP:
                    v_target = 0.0
                else:
                    v_target = min(v_target, self.speeds["node"])
        # spawn crawl: differential churn at launch tips the pitch past
        # recovery -- the first 12 cm go gentle
        if self.seg_i == 0 and s_seg < 0.12:
            v_target = min(v_target, 0.16)
        # final approach: balance-braking coasts ~0.2 m, so the last 30
        # cm of the LAST segment crawls into the stop window
        if self.seg_i == len(self.route) - 1 and s_seg > seg.length - 0.30:
            v_target = min(v_target, 0.10)
        # re-acquire slowly after an UNPLANNED loss; on a blind leg a
        # dark bar is the plan and full cruise continues
        if self.lost_t > LOST_S and not blind:
            v_target = min(v_target, 0.12)
        # lateral error slows the cruise: the differential churn of a big
        # correction couples into pitch above ~0.3 m/s
        if abs(self.e_lat) > E_SLOW:
            v_target = min(v_target, E_SLOW_V)
        dv = v_target - self.v_plan
        # full ramp only when tracking is solid: on tape a clean bar, on
        # a blind leg a tight odometry cross-track -- marginal tracking
        # plus the full ramp excites the pitch
        solid = ((line_obs.valid or blind) and abs(self.e_lat) <= 0.025
                 and self.t - self.align_t0 >= 2.5)
        ramp = (A_MAX if solid else A_MAX_KINK) if dv > 0 else A_MAX_BRAKE
        self.v_plan += max(-ramp * self.dt, min(ramp * self.dt, dv))
        v_cy_ref = -self.v_plan
        self.y_ref += v_cy_ref * self.dt
        # leak only the lag side: a symmetric leak also endorses overspeed
        # (v settles at plan + leak rate)
        e0 = self.y - self.y_ref
        if e0 > 0.0:
            self.y_ref += min(REF_LEAK * self.dt, e0)
        elif e0 < 0.0 and self.phase in ("brake", "done"):
            # brake side: the reference walks down to where the car
            # actually stops -- holding the station would reverse it
            # past the node
            self.y_ref -= min(REF_LEAK_BRAKE * self.dt, -e0)

        # ---- line following -> yaw-rate command ----
        # bar centroid + rate damping about the curvature feedforward
        # (damping the ABSOLUTE rate would fight the arc's steady turn);
        # Odometry supplies curvature, node alignment and recovery.
        # Positive error always means tape to travel-left.
        # The reading belongs to the forward sensor bar, not the axle.
        # Project that point using estimated pose only, never ground truth.
        _, lat_bar, psi_bar = seg.project(
            self.odo_x + lead * math.cos(self.psi),
            self.odo_y + lead * math.sin(self.psi))
        cross = math.cos(_wrap(self.psi - psi_bar))
        recovery = -lat_odom if blind else -lat_bar / max(0.5, cross)
        e_lat = self._lateral_error(self._line_bits if not blind else 0,
                                    recovery, allow_hold=not blind)
        self.e_lat = e_lat
        # line-aided dead reckoning: on clean tape the bar measures the
        # lateral offset directly, binning the odometry's lateral drift
        # continuously; longitudinal drift waits for the node re-sync
        if line_obs.valid and not blind and cross >= 0.5:
            lat_err = max(-0.05, min(0.05, lat_bar + line_obs.error_m * cross))
            lx, ly = -math.sin(psi_bar), math.cos(psi_bar)
            self.odo_x -= lx * lat_err * ODO_K
            self.odo_y -= ly * lat_err * ODO_K
        s_look = min(s_seg + 0.08, seg.length)
        psi_path = seg.heading_at(s_look)
        kappa = seg.curvature_at(s_look)
        # feedforward on MEASURED speed: bursts above plan otherwise
        # understeer (w_ff short by 0.125 rad/s at +0.05 m/s on R40)
        v_meas = abs(self.v_cy)
        w_ff = kappa * v_meas
        if line_obs.valid and not blind:
            self.lost_t = 0.0
        else:
            self.lost_t += self.dt
        # Search only after unexpected loss on a taped leg. Untaped legs
        # follow their planned tangent; entry capture gets time to settle.
        psi_aim = psi_path
        if (not blind and self.lost_t > SWEEP_AFTER
                and self.t - self.align_t0 > 4.0):
            psi_aim += SWEEP_RAD * math.sin(
                2.0 * math.pi * (self.lost_t - SWEEP_AFTER) / SWEEP_T)
        w = (w_ff + KP_LAT * e_lat
             + KP_HEAD * _wrap(psi_aim - self.psi)
             - KD_RATE * (self.w_f - w_ff))
        # post-node align servo: the node re-sync just refreshed psi, so
        # a heading servo rotates the car onto the new tangent -- the
        # centroid cannot swallow a 50-deg kink; the plan holds v=0
        # until the kink is small
        if kink_err <= 9.0 and kink_err > KINK_GO * 0.5:
            kink = _wrap(seg.heading_at(0.05) - self.psi)
            w += max(-1.6, min(1.6, K_ALIGN * kink))
        # no steering while braking/done: a rate servo fighting station
        # jitter wags the car and the stopped check never passes; yaw
        # friction is enough at rest
        braking = self.phase in ("brake", "done")
        if braking:
            w = 0.0
        self.w_cmd = max(-W_CMD_CAP, min(W_CMD_CAP, w))

        # ---- balance common mode (twin LQR on a moving reference) ----
        z = (self.y - self.y_ref, self.v_cy - v_cy_ref,
             self.theta - self.theta_ref, gyro[0])
        tau_c = -(BalanceController.K_LQR[0] * z[0]
                  + BalanceController.K_LQR[1] * z[1]
                  + BalanceController.K_LQR[2] * z[2]
                  + BalanceController.K_LQR[3] * z[3])
        # ---- steering differential: yaw-rate torque servo ----
        # duty_d > 0 = more torque on wheel_r = CCW yaw
        if braking:
            self.tau_d = 0.0
            self._w_integ = 0.0
        else:
            self._w_integ = max(-TAU_WI_CAP, min(TAU_WI_CAP,
                self._w_integ + KI_YAW * (self.w_cmd - self.w_f) * self.dt))
            self.tau_d = max(-TAU_D_CAP, min(
                TAU_D_CAP, K_YAW * (self.w_cmd - self.w_f) + self._w_integ))

        duty_c = motors.torque_to_duty(tau_c, self.v_batt)
        duty_d = motors.torque_to_duty(self.tau_d, self.v_batt)
        # differential slew limit: the bar's +-5.5 mm quantization steps
        # the yaw command -- unfiltered, duty_d flips +-150 permille
        # every few cycles
        duty_d = max(self._duty_d_prev - DUTY_D_SLEW,
                     min(self._duty_d_prev + DUTY_D_SLEW, duty_d))
        self._duty_d_prev = duty_d
        cap = BalanceController.DUTY_CAP
        # the differential may not eat the common mode's headroom:
        # balance authority always wins over steering
        headroom = cap - abs(duty_c)
        duty_d = max(-headroom, min(headroom, duty_d))
        duty_l = int(max(-cap, min(cap, duty_c - duty_d)))
        duty_r = int(max(-cap, min(cap, duty_c + duty_d)))

        # ---- sound & light countdown ----
        if self.buzzer_ms > 0:
            self.buzzer_ms = max(0, self.buzzer_ms - int(self.dt * 1000))
        if self.led_ms > 0:
            self.led_ms = max(0, self.led_ms - int(self.dt * 1000))

        return RaceMotorFrame(duty_l=duty_l, duty_r=duty_r,
                              buzzer_ms=int(self.buzzer_ms),
                              led=1 if self.led_ms > 0 else 0,
                              fw_seq=self.seq)

    # ---------------- helpers ----------------
    def _mission(self, v_travel: float, w_meas: float,
                 junction: bool = False) -> None:
        if self.phase == "arm":
            if self.t >= ARM_S:
                self.phase = "run"
                self.t_start = self.t
            return
        if self.phase == "done":
            return
        if self.phase == "run":
            seg = self.route[self.seg_i]
            blind = not seg.taped
            if ((self.lost_t > PARK_LOST_S and not blind)
                    or abs(self.e_lat) > 0.5):
                # hopelessly lost: park so the grader fails the run
                # cleanly (flickering contacts reset the pure timer,
                # hence the e_lat bound; a blind leg's dark bar is the
                # plan -- only its cross-track bound can park it)
                self.phase = "brake"
                return
            ex, ey = seg.point(seg.length)
            s_seg, _, _ = seg.project(self.odo_x, self.odo_y)
            at_node = (math.hypot(self.odo_x - ex, self.odo_y - ey)
                       <= track.TRIGGER_R)
            # s_seg saturates at seg.length by construction (project
            # clamps). Saturation alone over-fires: encoder overcount on
            # the arcs runs odo ~0.3 m ahead -- so the saturated
            # fallback needs the distance bound. The junction blob is
            # the primary, tape-true signal.
            passed_end = (s_seg >= seg.length - 1e-9
                          and math.hypot(self.odo_x - ex,
                                         self.odo_y - ey) <= 0.25)
            lead = FINAL_LEAD_SHORT if len(self.route) == 1 else FINAL_LEAD
            final_line = (self.seg_i == len(self.route) - 1
                          and s_seg >= seg.length - lead)
            # dead-reckoned triggers need fresh odometry ON TAPED LEGS
            # (odo built while the bar has been dark for LONG is
            # fiction); a BLIND leg is dead reckoning by design -- its
            # straights are where the odometry is cleanest -- so there
            # the odo triggers fire ungated. The 2 s window lets an
            # arc's dark TAIL still dead-reckon its finish. The
            # `junction` argument already folds in the tape-end
            # transition -- both bar-measured, always ungated.
            fresh = self.lost_t < 2.0 or blind
            if junction or (fresh and (at_node or passed_end or final_line)):
                self._beep(track.node_at(ex, ey, tol=0.02) or "?")
                # node re-sync: position binned to the node -- what exam
                # firmware does at every marked point. The HEADING
                # integral is kept: snapping it to the sheet tangent
                # lies whenever the car crosses off-tangent (arc-scrub
                # exits run 8-11 deg late), and the lie goes straight
                # down the next leg's dead reckoning.
                self.odo_x, self.odo_y = ex, ey
                self.lost_t = 0.0     # a new leg starts fresh: darkness
                                      # carried across the node from a
                                      # blind leg must not pre-arm the
                                      # next leg's park timer
                self.seg_i += 1
                self.align_t0 = self.t
                if self.seg_i >= len(self.route):
                    self.phase = "brake"
            return
        # brake: the stopped check holds on the controller's own
        # estimates (the filtered yaw rate -- the raw gyro rides contact
        # ringing and never settles below the threshold)
        if (abs(v_travel) < STOP_V and abs(self.w_f) < STOP_W):
            self.stop_hold += self.dt
        else:
            self.stop_hold = 0.0
        if self.stop_hold >= STOP_S:
            self.phase = "done"
            self.t_done = self.t
            self.buzzer_ms = 3 * BEEP_MS      # arrival chirp
            self.led_ms = LED_MS
            self.events.append({"kind": "done", "node": "A",
                                "t": round(self.t, 3)})

    def _lateral_error(self, line_bits: int, recovery_error: float,
                       allow_hold: bool = True) -> float:
        return self._line_tracker.update(line_bits, recovery_error, self.dt,
                                         allow_hold=allow_hold)

    # ---------------- telemetry ----------------
    def diagnostics(self) -> dict:
        """Reference-controller estimates; same units as the C symbol snapshot."""
        return {"available": True, "source": "python_reference", "fw_seq": self.seq,
                "control_time_s": self.t, "pitch_deg": math.degrees(self.theta or 0.0),
                "heading_rad": self.psi, "odometry_m": [self.odo_x, self.odo_y],
                "yaw_rate_rad_s": self.w_f, "yaw_target_rad_s": self.w_cmd,
                "yaw_integral_nm": self._w_integ, "differential_torque_nm": self.tau_d,
                "position_error_m": self.y - self.y_ref,
                "stop_speed_estimate_mps": self.v_stop, "line_lost_s": self.lost_t}

    def info(self) -> dict:
        seg = self.route[min(self.seg_i, len(self.route) - 1)]
        per_lap = len(self.route) // self.spec["laps"]
        return {
            "task": self.task,
            "phase": self.phase,
            "seg": seg.name,
            "seg_i": self.seg_i,
            "lap": min(self.seg_i // per_lap + 1, self.spec["laps"]),
            "laps": self.spec["laps"],
            "v_plan": round(self.v_plan, 3),
            "odo": [round(self.odo_x, 4), round(self.odo_y, 4)],
            "psi": round(self.psi, 4),
            "e_lat_mm": round(self.e_lat * 1000, 1),
            "line_bits": self._line_bits,
            "line_source": self._line_tracker.source,
            "w_meas": round(self.w_meas, 3),
            "w_cmd": round(self.w_cmd, 3),
            "buzzer": self.buzzer_ms > 0,
            "led": self.led_ms > 0,
            "events": list(self.events),
            "t_start": self.t_start,
            "t_done": self.t_done,
            "elapsed": (round(self.t_done - self.t_start, 3)
                        if self.t_done is not None and self.t_start is not None
                        else (round(self.t - self.t_start, 3)
                              if self.t_start is not None else None)),
        }
