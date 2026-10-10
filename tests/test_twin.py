"""Twin regression tests: mailbox contract, domain models, MJCF, loop.

The gates mirror the phase-1 acceptance list in the plan:

- mailbox: pack/unpack round-trip through the exact RAM word image,
  window inside the F407's REAL SRAM top, magic distinct from the radar
  twin (layout collisions across projects must be loud);
- IMU domain: at rest the raw frame must read like a real MPU6050
  (+1 g up on Z at the trim lean, gyro 0) -- the sign conventions the
  firmware will rely on are pinned here, not in prose;
- encoder: counts-per-revolution from the sheet (11 PPR x 4 x 30);
- motor: two-point line (stall / no-load), voltage derating;
- MJCF: compiles, total mass lands in the sheet band, CoM on the
  centerline, and the hover-trim keyframe is a TRUE equilibrium
  (pitch qacc ~ 0 -- the 3x trim bug of the first draft is pinned);
- loop: drive moves forward with counting encoders; balance holds the
  station and survives kicks;
- server: a WebSocket client receives frames and commands land.

Runs standalone (``python -m tests.test_twin``) and is
pytest-collectable without any extra dependency.
"""
import asyncio
import json
import math
import os
import re
import shutil
import struct
import subprocess

import mujoco
import numpy as np

from bot import mjcf, motors, telemetry
from bot.backend import BalanceController
from bot.loop import COUPLING_S
from bot.mailbox import MAGIC_BASE
from bot.sensors import (
    ACCEL_LSB_PER_G, COUNTS_PER_M, COUNTS_PER_REV, WheelEncoder,
    accel_to_raw, accel_to_tilt_rad, gyro_to_raw,
)
from twin import mailbox
from twin.loop import TwinLoop
from twin.mailbox import MAGIC, TWIN_BASE, TWIN_SIZE

TRIM = mjcf.hover_trim_rad()


# ---------------- mailbox contract ----------------
def test_mailbox_roundtrip_through_words():
    frame = mailbox.SensorFrame(
        seq=7, accel=(-111, 222, 16004), gyro=(-131, 0, 262),
        temp_raw=-3920, battery_mv=7400, enc_l=-123456, enc_r=987654)
    words = mailbox.pack_sensors(frame)
    img = mailbox.to_bytes(words)
    assert len(img) == 40 and len(words) == 10
    assert mailbox.from_bytes(img) == words
    sf, mf = mailbox.unpack_words(words)
    assert sf.seq == 7 and sf.accel == (-111, 222, 16004)
    assert sf.gyro == (-131, 0, 262)
    assert sf.temp_raw == -3920 and sf.battery_mv == 7400
    assert sf.enc_l == -123456 and sf.enc_r == 987654
    assert mf.duty_l == 0 and mf.duty_r == 0     # harness never writes motors
    assert mf.fw_seq == 0                        # ...nor the heartbeat


def test_mailbox_motor_word():
    _, mf = mailbox.unpack_words(
        mailbox.pack_sensors(mailbox.SensorFrame())[:8]
        + [mailbox.pack_motor(mailbox.MotorFrame(-600, 250))[0x20], 1234])
    assert mf.duty_l == -600 and mf.duty_r == 250
    assert mf.fw_seq == 1234                     # v2 heartbeat word @ +0x24


def test_mailbox_window_inside_real_f407_sram():
    assert TWIN_BASE >= 0x20000000
    assert TWIN_BASE + TWIN_SIZE <= 0x20020000, \
        "window must end at SRAM2 top (real chip has NO RAM above 0x20020000)"
    assert MAGIC != MAGIC_BASE, "new layout must carry its own magic"


# ---------------- IMU / encoder domain ----------------
def test_imu_static_frame_at_trim():
    loop = TwinLoop(mode="drive")          # any mode; we only read sensors
    loop.controller.duty = 0
    loop.run(0.5)                           # settle the DLPF + contact transient
    f = loop.read_sensors()
    az_expect = math.cos(TRIM) * ACCEL_LSB_PER_G
    ay_expect = math.sin(TRIM) * ACCEL_LSB_PER_G
    assert abs(f.accel[2] - az_expect) < 150, f.accel
    assert abs(f.accel[1] - ay_expect) < 150, f.accel
    assert abs(f.accel[0]) < 60, f.accel
    assert max(abs(v) for v in f.gyro) < 40, f.gyro
    si = (f.accel[1] / ACCEL_LSB_PER_G * 9.81, f.accel[2] / ACCEL_LSB_PER_G * 9.81)
    assert abs(accel_to_tilt_rad((0.0,) + si) - TRIM) < math.radians(0.5)


def test_gyro_scale_and_saturation():
    raw = gyro_to_raw((1.0, -0.5, 3.0))    # rad/s
    assert abs(raw[0] - 1.0 * 180 / math.pi * 131) < 2
    assert abs(raw[2] - 3.0 * 180 / math.pi * 131) < 2    # 172 deg/s, in range
    assert gyro_to_raw((0.0, 0.0, 5.0))[2] == 32767       # 286 deg/s clamps


def test_encoder_counts_per_revolution():
    enc = WheelEncoder()
    assert enc.update(0.0) == 0
    counts = enc.update(2.5 * 2 * math.pi)
    assert abs(counts - int(round(2.5 * COUNTS_PER_REV))) <= 2
    assert counts == 3300, COUNTS_PER_REV
    neg = WheelEncoder()
    neg.update(0.0)
    assert neg.update(-math.pi) < 0


def test_counts_per_meter_matches_sheet():
    assert abs(COUNTS_PER_M - 5252.1) < 1.0


# ---------------- motor model ----------------
def test_motor_line_endpoints():
    v = motors.BATTERY_NOMINAL["2s"]
    assert abs(motors.torque_nm(1000, 0.0, v) - 0.57 * v / 12.0) < 1e-9
    w_free = motors.torque_nm(1000, 0.0, v) * 0 + motors.OMEGA_FREE * v / 12.0
    assert abs(motors.torque_nm(1000, w_free, v)) < 1e-9
    assert motors.torque_nm(-1000, 0.0, v) < 0
    assert motors.torque_nm(500, 0.0, v) == motors.torque_nm(1000, 0.0, v) / 2


def test_motor_derating_matches_sheet():
    v2 = motors.BATTERY_NOMINAL["2s"]
    stall_2s = motors.max_torque_nm(v2)
    assert 3.5 < stall_2s / 0.0981 < 3.8          # ~3.6 kg*cm at 7.4 V
    v3 = motors.BATTERY_NOMINAL["3s"]
    assert abs(motors.max_torque_nm(v3) - 0.57 * 11.1 / 12.0) < 1e-9


# ---------------- MJCF model ----------------
def test_mjcf_compiles_and_mass_in_sheet_band():
    model = mjcf.load_model()
    assert model.nq == 9 and model.nu == 2
    from bot import mass_properties as mp
    assert abs(model.body_mass.sum() - mp.total_mass()) < 0.02
    assert 0.95 <= model.body_mass.sum() <= 1.15   # expected vehicle band


def test_com_over_wheel_contact_and_trim_is_equilibrium():
    model = mjcf.load_model()
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    mujoco.mj_forward(model, data)
    com = data.subtree_com[1]
    assert abs(com[0]) < 1e-4, "model must be lateral-symmetric"
    # hover = CoM over the tilted WHEEL CONTACT line, not over y=0:
    # the contact follows the axle, y_contact = -AXLE_Z * sin(trim)
    contact_y = -0.04 * math.sin(TRIM)
    assert abs(com[1] - contact_y) < 5e-4, \
        f"CoM y {com[1]*1e3:.2f} mm vs contact y {contact_y*1e3:.2f} mm"
    assert abs(data.qacc[3]) < 1e-3, \
        f"pitch qacc {data.qacc[3]:.4f} at keyframe: trim is not an equilibrium"
    assert abs(np.degrees(TRIM)) < 5, "centered low battery should need little trim"


def test_chassis_pitch_positive_is_nose_up():
    loop = TwinLoop(mode="drive")
    loop.controller.duty = 0
    loop.data.qpos[3:7] = [math.cos(math.radians(5) / 2), math.sin(math.radians(5) / 2), 0, 0]
    mujoco.mj_forward(loop.model, loop.data)
    assert abs(loop.tilt_deg() - 5.0) < 0.05


# ---------------- loop behavior ----------------
def test_drive_moves_forward_and_counts():
    loop = TwinLoop(mode="drive", drive_duty=300)
    loop.run(2.0)
    st = loop.state()
    assert st["pos"][1] > 0.10, "drive must move forward (+Y)"
    assert st["enc"][0] > 1500 and st["enc"][1] > 1500
    assert st["speed_mps"] > 0.10
    assert not any(np.isnan(v) for v in loop.data.qpos)


def test_balance_holds_station_five_seconds():
    loop = TwinLoop(mode="balance")
    worst = 0.0
    for i in range(5):
        loop.run(1.0)
        if i >= 1:   # first second = boot: DLPF settle + saddle escape
            worst = max(worst, abs(loop.tilt_deg() - np.degrees(TRIM)))
    st = loop.state()
    assert not st["fallen"]
    assert worst < 5.0, f"max deviation from trim {worst:.2f} deg"
    assert abs(st["pos"][1]) < 0.10, "station drift"
    assert abs(st["speed_mps"]) < 0.05


def test_balance_survives_kick():
    loop = TwinLoop(mode="balance")
    loop.run(2.0)
    loop.nudge(tx=3.5)
    peak = 0.0
    for _ in range(600):
        loop.step_coupling()
        peak = max(peak, abs(loop.tilt_deg() - np.degrees(TRIM)))
    loop.run(2.0)
    st = loop.state()
    assert not st["fallen"], f"kick peak {peak:.1f} deg -> fell"
    assert peak > 8.0, "kick must exceed the 5-degree station-keeping band"
    assert abs(st["tilt_deg"] - np.degrees(TRIM)) < 5.0


def test_fall_detection_cuts_motors():
    loop = TwinLoop(mode="balance")
    loop.run(1.0)
    loop.nudge(tx=-40.0)             # brutal kick
    for _ in range(400):
        loop.step_coupling()
    st = loop.state()
    if st["fallen"]:
        assert st["duty"] == [0, 0]


# ---------------- state-frame schema ----------------
def test_state_base_schema_pinned():
    """state() = telemetry.BASE_FIELDS + the twin's identity field. The
    schema lives in bot.telemetry, not in each loop's hand-written
    dict -- this is the pin against the twin/race drift."""
    assert telemetry.BASE_FIELDS == (
        "type", "t", "pos", "quat_xyzw", "wheel_deg", "tilt_deg",
        "speed_mps", "duty", "enc", "batt_v", "fw_seq", "paused", "fallen")
    st = TwinLoop(mode="balance").state()
    assert set(telemetry.BASE_FIELDS) <= set(st)
    assert set(st) - set(telemetry.BASE_FIELDS) == {"mode"}
    assert st["fw_seq"] is None            # stub backend: no heartbeat


def test_speed_is_travel_axis_projected_not_world_y():
    """Yawed 90 deg, world velocity -X: the old world-Y sensor readout
    reported 0.0 here; the travel projection reads the full speed with
    the sign of the app's travel axis (twin leads chassis +Y, race runs
    bar-first = chassis -Y, race/spawn.py)."""
    model = mjcf.load_model()
    d = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, d, 0)
    half = math.radians(90) / 2
    d.qpos[3:7] = (math.cos(half), 0.0, 0.0, math.sin(half))   # yaw +90
    d.qvel[0:3] = (-0.3, 0.0, 0.0)
    st = telemetry.pose_fields(d, duty=[0, 0], enc=[0, 0],
                               batt_v=11.1, paused=False)
    assert abs(st["speed_mps"] - 0.3) < 1e-6      # -X is chassis +Y-first
    st_bar_first = telemetry.pose_fields(d, duty=[0, 0], enc=[0, 0],
                                         batt_v=11.1, paused=False,
                                         travel_y=-1.0)
    assert abs(st_bar_first["speed_mps"] + 0.3) < 1e-6


# ---------------- controller internals ----------------
def test_balance_trim_from_mass_table():
    bc = BalanceController()
    assert abs(np.degrees(bc.theta_ref) - np.degrees(TRIM)) < 1e-6


# ---------------- firmware phase 2: the Renode takeover ----------------
FIRMWARE_DIR = os.path.join(os.path.dirname(__file__), "..", "firmware", "twin")
ELF_PATH = os.path.join(FIRMWARE_DIR, "balance_fw.elf")


def test_fwconfig_header_in_sync():
    from twin import fwconfig
    ok, msg = fwconfig.check()
    assert ok, msg


def test_firmware_mailbox_header_matches_python_layout():
    """Byte-level cross-check: a Python-packed frame must decode, field
    by field, at the offsets firmware/twin/mailbox.h declares."""
    with open(os.path.join(FIRMWARE_DIR, "mailbox.h"), encoding="utf-8") as fp:
        hdr = fp.read()
    magic = re.search(r"#define TWIN_MAILBOX_MAGIC (0x[0-9A-Fa-f]+)", hdr)
    base = re.search(r"#define TWIN_MAILBOX_BASE  (0x[0-9A-Fa-f]+)", hdr)
    assert magic and int(magic.group(1), 16) == MAGIC
    assert base and int(base.group(1), 16) == TWIN_BASE

    accessors = {name: (int(addr, 16), kind) for name, kind, addr
                 in re.findall(r"#define (TWIN_\w+)\s+TWIN_MB(16|U16|32|32S)"
                               r"\((0x[0-9A-Fa-f]+)", hdr)}
    frame = mailbox.SensorFrame(
        seq=7, accel=(-111, 222, 16004), gyro=(-131, 0, 262),
        temp_raw=-3920, battery_mv=7400, enc_l=-123456, enc_r=987654)
    words = mailbox.pack_sensors(frame)
    words[8] = mailbox.pack_motor(mailbox.MotorFrame(-600, 250))[0x20]
    words[9] = 0xDEADBEEF
    img = mailbox.to_bytes(words)
    expected = {          # name -> (struct fmt, value)
        "TWIN_SEQ": ("<I", 7), "TWIN_ACCEL_X": ("<h", -111),
        "TWIN_ACCEL_Y": ("<h", 222), "TWIN_ACCEL_Z": ("<h", 16004),
        "TWIN_GYRO_X": ("<h", -131), "TWIN_GYRO_Y": ("<h", 0),
        "TWIN_GYRO_Z": ("<h", 262), "TWIN_TEMP": ("<h", -3920),
        "TWIN_BATT_MV": ("<H", 7400), "TWIN_ENC_L": ("<i", -123456),
        "TWIN_ENC_R": ("<i", 987654), "TWIN_DUTY_L": ("<h", -600),
        "TWIN_DUTY_R": ("<h", 250), "TWIN_FW_SEQ": ("<I", 0xDEADBEEF),
    }
    assert set(expected) <= set(accessors), \
        f"mailbox.h lost accessors: {set(expected) - set(accessors)}"
    for name, (fmt, val) in expected.items():
        addr, _kind = accessors[name]
        got, = struct.unpack_from(fmt, img, addr)
        assert got == val, f"{name} @ +{addr:#x}: C header says {got}, Python packed {val}"


def test_firmware_builds():
    if shutil.which("arm-none-eabi-gcc") is None:
        print("SKIP: arm-none-eabi-gcc not in PATH")
        return
    repo_root = os.path.join(os.path.dirname(__file__), "..")
    r = subprocess.run([shutil.which("bash") or "bash", "firmware/twin/build.sh"], cwd=repo_root,
                       capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=120)
    assert r.returncode == 0, f"build.sh failed:\n{r.stdout}\n{r.stderr}"


def _renode_ready():
    from twin.renode_backend import DEFAULT_PORTABLE
    if DEFAULT_PORTABLE:  # None until RENODE_PORTABLE/PYRENODE_PATH is set
        os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)
    try:
        import pyrenode3  # noqa: F401
    except Exception as exc:
        return None, f"pyrenode3 not importable ({exc.__class__.__name__}: {exc})"
    if not DEFAULT_PORTABLE or not os.path.isdir(DEFAULT_PORTABLE):
        return None, ("Renode portable not configured "
                      f"(set RENODE_PORTABLE): {DEFAULT_PORTABLE}")
    if not os.path.isfile(ELF_PATH):
        return None, f"{ELF_PATH} missing -- bash firmware/twin/build.sh"
    return True, ""


def _kick_scenario(loop):
    """Settle 1 s, kick, ride it out 3 s; return (peak, 0.5 s samples)."""
    samples = []

    def snap():
        samples.append((loop.data.time, loop.tilt_deg(),
                        float(loop.data.qpos[1])))

    snap()
    loop.run(1.0)
    snap()
    loop.nudge(tx=3.5)                 # same kick as the stub tests
    peak = 0.0
    for i in range(600):
        loop.step_coupling()
        peak = max(peak, abs(loop.tilt_deg() - np.degrees(TRIM)))
        if (i + 1) % 100 == 0:
            snap()
    loop.run(2.0)
    snap()
    return peak, samples


def test_renode_firmware_balances_and_matches_stub():
    """THE phase-2 gate, now through the REAL peripheral path: the C
    firmware reads the IMU through the I2C driver, the encoders through
    the TIM3/TIM4 interface (edge-fed) and the battery through ADC1,
    and drives TIM1/TB6612 -- the plant torque is decoded from the PWM
    registers, never from a commanded word. It must balance in Renode,
    keep the heartbeat at exactly the coupling rate, survive the kick,
    and track the Python stub (port-correctness by A/B)."""
    ready, why = _renode_ready()
    if not ready:
        print(f"SKIP: {why}")
        return
    from twin.renode_backend import RenodePeriphBackend

    # BOTH sides run the identical scenario from a fresh keyframe state --
    # any phase offset (an extra settle second on one side) shifts the
    # kick to a different system state and the comparison diverges for
    # reasons that are NOT porting errors (first draft: +6.8 deg from
    # exactly that). Measured symmetric: 0.00 deg / 0.0 cm.
    fw = RenodePeriphBackend(elf_path=ELF_PATH, dt=COUPLING_S)
    loop = TwinLoop(controller=fw)
    peak, samples_fw = _kick_scenario(loop)
    st = loop.state()
    assert not st["fallen"], f"kick peak {peak:.1f} deg -> fell"
    assert peak > 8.0, "kick must exceed the 5-degree station-keeping band"
    assert abs(st["tilt_deg"] - np.degrees(TRIM)) < 5.0
    assert st["fw_seq"] and st["fw_seq"] > 0

    stub = TwinLoop(mode="balance")
    peak_stub, samples_stub = _kick_scenario(stub)
    assert peak_stub > 8.0            # deviation from trim, not absolute lean
    max_dtilt = max(abs(a[1] - b[1]) for a, b in zip(samples_fw, samples_stub))
    max_dy = max(abs(a[2] - b[2]) for a, b in zip(samples_fw, samples_stub))
    assert max_dtilt < 1.0, f"stub vs firmware tilt divergence {max_dtilt:.2f} deg"
    assert max_dy < 0.03, f"stub vs firmware position divergence {max_dy * 100:.1f} cm"

    # heartbeat LAST -- it offsets the firmware side's phase, and nothing
    # compares trajectories after this point
    seq0 = fw.fw_seq                    # heartbeat == coupling rate, exactly
    for _ in range(200):
        loop.step_coupling()
    assert fw.fw_seq - seq0 == 200, \
        f"lost strobes: {fw.fw_seq - seq0} cycles in 200 couplings"


def test_production_elf_talks_on_the_serial_link():
    """The v3 shell streams telemetry and answers commands on USART2
    WHILE balancing -- the same driver path the bring-up gate proved,
    now under the full control loop, including the supervision event
    lines (starved/resume) that the 2 ms-sliced loop makes timely.

    Assertions read the backend's raw TX tap (fw.uart_log); the tester
    is used only to WRITE command lines -- its waiting reads can hang
    forever on an empty buffer (virtual-time timeout, nobody advancing
    virtual time), probed 2026-09-29."""
    ready, why = _renode_ready()
    if not ready:
        print(f"SKIP: {why}")
        return
    from twin.renode_backend import RenodePeriphBackend

    # uart_telemetry=True attaches the taps INSIDE reset(), before the
    # machine's first execution -- attaching a UART receiver after any
    # run crashes Renode (see renode_backend.py)
    fw = RenodePeriphBackend(elf_path=ELF_PATH, dt=COUPLING_S,
                             uart_telemetry=True)

    def new_lines(mark):
        return bytes(fw.uart_log[mark:]).decode().splitlines()

    def parse_t(text):
        parts = text.split()
        assert parts[0] == "T" and len(parts) == 5, f"telemetry shape: {text!r}"
        return [int(x) for x in parts[1:]]

    loop = TwinLoop(controller=fw)
    loop.run(0.5)                        # settle -> UP + resume + T lines
    lines = new_lines(0)
    assert lines[0] == "UP", lines[:3]
    assert "resume" in lines[:3], lines[:3]

    seqs = [parse_t(t)[0] for t in lines if t.startswith("T ")]
    assert len(seqs) >= 3, f"expected 10 Hz telemetry, got {lines}"
    assert seqs == sorted(set(seqs)), f"telemetry seq not monotonic: {seqs}"
    assert seqs[-1] - seqs[0] >= 40, \
        f"10 Hz cadence broken: 3 lines spanned {seqs[-1] - seqs[0]} cycles"

    for _ in range(4):                   # commands mid-balance
        loop.step_coupling()
    mark = len(fw.uart_log)
    fw.send_line("ping")
    for _ in range(4):
        loop.step_coupling()
    assert "pong" in new_lines(mark), new_lines(mark)

    mark = len(fw.uart_log)
    fw.send_line("stat")
    for _ in range(4):
        loop.step_coupling()
    stat = [t for t in new_lines(mark) if t.startswith("T ")]
    assert stat and parse_t(stat[0])[0] > seqs[-1], \
        "stat must answer with a FRESH telemetry line"

    # supervision over the link: bench silence -> starved line + duty 0
    mark = len(fw.uart_log)
    fw._ch.run(0.3)                      # no bench writes: no fresh samples
    assert "starved" in new_lines(mark), new_lines(mark)
    assert fw._ch.read_word(TWIN_BASE + 0x20) == 0, "duty mirror must be 0"
    mark = len(fw.uart_log)
    loop.step_coupling()                 # the next fresh sample resumes
    assert "resume" in new_lines(mark), new_lines(mark)


# ---------------- WebSocket server ----------------
def test_server_streams_and_takes_commands():
    import websockets
    from bot.server import BotServer

    scene = {"type": "scene", "app": "twin", "title": "Balance Twin"}

    async def scenario():
        # port=0 lets the OS pick; wait_ready() reports the real port instead
        # of probing for a free one first, which races under a parallel run.
        server = BotServer(port=0, scene=scene)
        server.start()
        try:
            port = await server.wait_ready()
            async with websockets.connect(
                    f"ws://127.0.0.1:{port}") as ws:
                # the connection's FIRST message is the scene frame --
                # the app declaring itself before any state flows
                frame = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert frame == scene
                server.push_state({"type": "state", "t": 0.0, "tilt_deg": -12.4})
                frame = json.loads(await asyncio.wait_for(ws.recv(), 5))
                assert frame["type"] == "state"
                await ws.send(json.dumps({"type": "pause"}))
                for _ in range(50):
                    cmd = server.poll_command()
                    if cmd is not None:
                        assert cmd == {"type": "pause"}
                        return
                    await asyncio.sleep(0.02)
                raise AssertionError("command never arrived")
        finally:
            server.stop()

    asyncio.run(asyncio.wait_for(scenario(), 15))


# ---------------- harness ----------------
def main() -> int:
    import traceback

    tests = [
        (name, fn)
        for name, fn in sorted(globals().items())
        if name.startswith("test_") and callable(fn)
    ]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
