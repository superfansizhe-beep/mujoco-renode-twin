"""Race twin regression tests: geometry, tape mask, mailbox, missions.

Unit gates pin the exam sheet's own numbers (node coordinates, segment
lengths, route lengths, the tape-X crossing) and the RAC2 mailbox
round-trip. The mission gates run the real headless loop -- they assert
the STABLE core (mission completes inside the sheet's time limit with
the right node sequence and the car upright); the stop/beep MARGINS are
checked coarsely here (the strict thresholds live in race.loop.grade,
see race/README.md -- tuning is ongoing at freeze time).

Runs standalone: ``python -m tests.test_race``  (pytest-collectable).
Set RACE_SKIP_INT=1 to skip the headless missions (unit gates only).
"""
import math
import os
import re
import shutil
import struct
import subprocess
import unittest

from bot.mailbox import MAGIC_BASE
from race import mailbox, scene, tasks, track
from race.mailbox import MAGIC as RACE_MAGIC
from race.mailbox import TWIN_MAGIC_TWN2


class TestTrackGeometry(unittest.TestCase):
    def test_nodes_match_exam_sheet(self):
        # symmetric layout: the four arc endpoints form a 100 x 80 cm
        # rectangle, 20 cm margins all round in the 220 x 120 field
        self.assertEqual(track.NODES["A"], (0.60, 1.00))
        self.assertEqual(track.NODES["B"], (1.60, 1.00))
        self.assertEqual(track.NODES["C"], (1.60, 0.20))
        self.assertEqual(track.NODES["D"], (0.60, 0.20))

    def test_segment_lengths(self):
        self.assertAlmostEqual(track.AB.length, 1.0, places=9)
        self.assertAlmostEqual(track.BC.length, 0.4 * math.pi, places=9)
        self.assertAlmostEqual(track.CD.length, 1.0, places=9)
        self.assertAlmostEqual(track.DA.length, 0.4 * math.pi, places=9)
        self.assertAlmostEqual(track.AC.length, math.hypot(1.0, 0.8), places=9)
        self.assertAlmostEqual(track.BD.length, math.hypot(1.0, 0.8), places=9)

    def test_route_lengths(self):
        lap2 = (2.0 + 2 * 0.4 * math.pi)
        lap3 = (2 * math.hypot(1.0, 0.8) + 2 * 0.4 * math.pi)
        self.assertAlmostEqual(tasks.route_length(1), 1.0, places=9)
        self.assertAlmostEqual(tasks.route_length(2), lap2, places=9)
        self.assertAlmostEqual(tasks.route_length(3), lap3, places=9)
        self.assertAlmostEqual(tasks.route_length(4), 4 * lap3, places=9)
        # the sheet-derived numbers (451.33 / 507.45 / 2029.8 cm)
        self.assertAlmostEqual(tasks.route_length(2), 4.5133, places=3)
        self.assertAlmostEqual(tasks.route_length(4), 20.298, places=2)

    def test_arcs_pass_through_their_extremes(self):
        self.assertAlmostEqual(track.BC.point(track.BC.length / 2)[0], 2.00)
        self.assertAlmostEqual(track.DA.point(track.DA.length / 2)[0], 0.20)

    def test_only_the_two_arcs_carry_tape(self):
        # the sheet: "no marks besides the two semicircles" -- every
        # straight leg, the crossing included, is open white
        self.assertEqual({seg.name for seg in track.TAPE}, {"BC", "DA"})
        for seg in (track.AB, track.CD, track.AC, track.BD):
            self.assertFalse(seg.taped)

    def test_diagonals_cross_at_the_unmarked_center(self):
        self.assertEqual(track.CROSSING, (1.10, 0.60))
        self.assertFalse(track.over_tape(*track.CROSSING))

    def test_scene_payload_composes_the_field(self):
        # the viewer's track truth rides the --serve scene frame; pin the
        # composition (the geometry itself is pinned by the tests above)
        p = scene.payload()
        self.assertEqual(p["field"], [2.20, 1.20])
        self.assertEqual(p["tape_half"], track.TAPE_HALF)
        self.assertEqual(p["nodes"]["A"], [0.60, 1.00])
        self.assertEqual(p["crossing"], [1.10, 0.60])
        self.assertEqual([t["name"] for t in p["tapes"]], ["BC", "DA"])
        self.assertEqual([g["name"] for g in p["ghosts"]],
                         ["AB", "CD", "AC", "BD"])
        self.assertEqual(sorted(p["tasks"]), ["1", "2", "3", "4"])
        self.assertEqual(p["tasks"]["4"]["laps"], 4)
        self.assertAlmostEqual(p["tasks"]["2"]["length_m"], 4.513, places=2)

    def test_projection_basics(self):
        s, lat, psi = track.AB.project(1.10, 1.00)
        self.assertAlmostEqual(s, 0.5), self.assertAlmostEqual(lat, 0.0)
        self.assertAlmostEqual(psi, 0.0)
        s, lat, psi = track.AB.project(1.10, 1.02)   # 2 cm left of travel
        self.assertAlmostEqual(lat, 0.02, places=9)
        s, lat, psi = track.BC.project(2.00, 0.60)  # arc mid
        self.assertAlmostEqual(s, track.BC.length / 2, places=9)
        self.assertAlmostEqual(lat, 0.0, places=9)
        # curvature sign: CW arcs (B->C and D->A) turn right
        self.assertAlmostEqual(track.BC.curvature_at(0.5), -1 / 0.4, places=9)
        self.assertAlmostEqual(track.DA.curvature_at(0.5), -1 / 0.4, places=9)

    def test_pre_arc_start_clamps_to_start_not_far_end(self):
        # a point 10 cm BEFORE node B (on the AB side, behind the arc's
        # start) must clamp to s=0, not wrap the long way to the far
        # end -- the bring-up bug that fed the follower node C's heading
        # for half a second at every B handoff
        s, _, _ = track.BC.project(1.50, 1.05)
        self.assertAlmostEqual(s, 0.0, places=9)
        # radially past C (beyond the arc's END) clamps to the C end
        s, _, _ = track.BC.project(1.55, 0.05)
        self.assertAlmostEqual(s, track.BC.length, places=9)

    def test_reversed_orientation(self):
        seg = track.Oriented(track.BC, reverse=True)   # C -> B travel
        s, lat, psi = seg.project(1.60, 0.20)          # at C
        self.assertAlmostEqual(s, 0.0, places=9)
        # reversed curvature flips handedness: C->B is a LEFT (CCW) arc
        self.assertAlmostEqual(seg.curvature_at(0.5), +1 / 0.4, places=9)
        self.assertAlmostEqual(seg.heading_at(0.0), 0.0, places=9)


class TestTapeMask(unittest.TestCase):
    def test_on_and_off_tape(self):
        self.assertTrue(track.over_tape(2.005, 0.60))        # just inside arc
        self.assertFalse(track.over_tape(2.02, 0.60))       # just outside
        self.assertTrue(track.over_tape(0.20, 0.60))        # arc extreme
        # the field's open white: the top A-B gap, the bottom C-D gap
        # and the dead center are all BLIND ground -- the whole point
        # of the sheet's "no other marks" rule
        self.assertFalse(track.over_tape(1.10, 1.00))
        self.assertFalse(track.over_tape(1.10, 0.20))
        self.assertFalse(track.over_tape(1.10, 0.60))

    def test_task_beep_sequences(self):
        self.assertEqual(tasks.task_spec(1)["beeps"], ["B"])
        self.assertEqual(tasks.task_spec(2)["beeps"],
                         ["A", "B", "C", "D", "A"])
        self.assertEqual(tasks.task_spec(3)["beeps"],
                         ["A", "C", "B", "D", "A"])
        self.assertEqual(tasks.task_spec(4)["beeps"], ["A"] + ["C", "B", "D", "A"] * 4)

    def test_task_registry_pins(self):
        # the registry IS the exam paper: four tasks, and task 4 is the
        # crossed route x 4 laps expressed as data, not an alias in code
        self.assertEqual(set(tasks.TASKS), {1, 2, 3, 4})
        t3, t4 = tasks.TASKS[3], tasks.TASKS[4]
        self.assertEqual(t4.legs, t3.legs)
        self.assertEqual(t4.laps, 4)
        self.assertEqual(len(t4.route), 4 * len(t3.route))



FIRMWARE_DIR = os.path.join(os.path.dirname(__file__), "..", "firmware", "race")


class TestFirmwareContract(unittest.TestCase):
    """Phase 2: the RAC2 contract and constants are pinned to the C side
    (mirrors tests/test_twin.py's twin gates)."""

    def test_race_fwconfig_header_in_sync(self):
        from race import fwconfig
        ok, msg = fwconfig.check()
        assert ok, msg

    def test_race_mailbox_header_matches_python_layout(self):
        """Byte-level cross-check: a Python-packed frame must decode,
        field by field, at the offsets firmware/race/mailbox.h declares."""
        with open(os.path.join(FIRMWARE_DIR, "mailbox.h"),
                  encoding="utf-8") as fp:
            hdr = fp.read()
        magic = re.search(r"#define RACE_MAILBOX_MAGIC (0x[0-9A-Fa-f]+)", hdr)
        base = re.search(r"#define RACE_MAILBOX_BASE  (0x[0-9A-Fa-f]+)", hdr)
        assert magic and int(magic.group(1), 16) == RACE_MAGIC
        assert base and int(base.group(1), 16) == mailbox.RACE_BASE

        accessors = {name: (int(addr, 16), kind) for name, kind, addr
                     in re.findall(r"#define (RACE_\w+)\s+RACE_MB(16|U16|32|32S)"
                                   r"\((0x[0-9A-Fa-f]+)", hdr)}
        f = mailbox.RaceSensorFrame(
            seq=7, accel=(-111, 222, 16004), gyro=(-131, 0, 262),
            temp_raw=-3920, battery_mv=11100, enc_l=-123456, enc_r=987654,
            line_bits=0b00011000, task=0x105)
        words = mailbox.pack_sensors(f)
        words[9] = mailbox.pair32(-600, 250)          # duty pair
        words[10] = mailbox.pair32(145, 1)            # buzzer/led
        words[11] = 0xDEADBEEF                       # fw_seq
        img = mailbox.to_bytes(words)
        expected = {
            "RACE_SEQ": ("<I", 7), "RACE_ACCEL_X": ("<h", -111),
            "RACE_ACCEL_Y": ("<h", 222), "RACE_ACCEL_Z": ("<h", 16004),
            "RACE_GYRO_X": ("<h", -131), "RACE_GYRO_Y": ("<h", 0),
            "RACE_GYRO_Z": ("<h", 262), "RACE_TEMP": ("<h", -3920),
            "RACE_BATT_MV": ("<H", 11100), "RACE_ENC_L": ("<i", -123456),
            "RACE_ENC_R": ("<i", 987654), "RACE_LINE_BITS": ("<H", 0b00011000),
            "RACE_TASK_WORD": ("<H", 0x105), "RACE_DUTY_L": ("<h", -600),
            "RACE_DUTY_R": ("<h", 250), "RACE_BUZZER_MS": ("<H", 145),
            "RACE_LED": ("<H", 1), "RACE_FW_SEQ": ("<I", 0xDEADBEEF),
        }
        assert set(expected) <= set(accessors),             f"race/mailbox.h lost accessors: {set(expected) - set(accessors)}"
        for name, (fmt, val) in expected.items():
            addr, _kind = accessors[name]
            got, = struct.unpack_from(fmt, img, addr)
            assert got == val,                 f"{name} @ +{addr:#x}: C header says {got}, Python packed {val}"

    def test_race_firmware_builds(self):
        if shutil.which("arm-none-eabi-gcc") is None:
            print("SKIP: arm-none-eabi-gcc not in PATH")
            return
        repo_root = os.path.join(os.path.dirname(__file__), "..")
        # Pass the resolved executable: Windows otherwise prefers its
        # System32 WSL launcher over Git Bash earlier in PATH.
        r = subprocess.run([shutil.which("bash") or "bash", "firmware/race/build.sh"], cwd=repo_root,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=120)
        assert r.returncode == 0, \
            f"build_race.sh failed:\n{r.stdout}\n{r.stderr}"


class TestMailbox(unittest.TestCase):
    def test_roundtrip_through_words(self):
        f = mailbox.RaceSensorFrame(
            seq=9, accel=(-111, 222, 16004), gyro=(10, -20, 131),
            temp_raw=-3920, battery_mv=11100, enc_l=-999, enc_r=123456,
            line_bits=0b10100001)
        words = mailbox.pack_sensors(f)
        img = mailbox.to_bytes(words)
        self.assertEqual(len(img), 64)
        self.assertEqual(mailbox.from_bytes(img), words)
        sf, mf = mailbox.unpack_words(words)
        self.assertEqual(sf.seq, 9)
        self.assertEqual(sf.accel, (-111, 222, 16004))
        self.assertEqual(sf.gyro, (10, -20, 131))
        self.assertEqual(sf.enc_l, -999)
        self.assertEqual(sf.enc_r, 123456)
        self.assertEqual(sf.line_bits, 0b10100001)
        self.assertEqual(mf.duty_l, 0)

    def test_magic_and_window(self):
        self.assertNotIn(RACE_MAGIC, (TWIN_MAGIC_TWN2, MAGIC_BASE))
        self.assertEqual(mailbox.RACE_BASE + mailbox.RACE_SIZE, 0x20020000)


class TestVehicle(unittest.TestCase):
    def test_model_and_sites(self):
        import mujoco
        from bot import mjcf, sensors
        from race import spawn
        model = mjcf.load_model()        # race model == bot model
        self.assertEqual(model.nq, 9)     # twin chassis verbatim
        ids = mjcf.line_site_ids(model)
        self.assertEqual(len(ids), sensors.N_LINE_SENSORS)
        self.assertNotIn(-1, ids)
        qpos, pose = spawn.spawn_for_task(model, 1)
        self.assertAlmostEqual(pose["x"], 0.60, places=6)
        self.assertAlmostEqual(pose["y"], 1.00, places=6)
        data = mujoco.MjData(model)
        data.qpos[:] = qpos
        mujoco.mj_forward(model, data)
        # the bar rides 63 mm ahead of the axle: at spawn on the blind
        # AB leg it hangs past node A over open white -- the run opens
        # in dead reckoning, dark bar and all
        from race import track as T
        bits = 0
        for sid in ids:
            if T.over_tape(data.site_xpos[sid][0], data.site_xpos[sid][1]):
                bits |= 1 << ids.index(sid)
        self.assertEqual(bits, 0)

    def test_spawn_heading_task3(self):
        from bot import mjcf
        from race import spawn
        model = mjcf.load_model()
        _, pose = spawn.spawn_for_task(model, 3)
        self.assertAlmostEqual(pose["psi"], math.atan2(-0.8, 1.0), places=6)

    def test_set_task_respawns(self):
        # the loop's task switch must rebuild the controller AND re-spawn
        # on the new route (this seam is what --serve's task buttons drive)
        from race.loop import RaceLoop
        loop = RaceLoop(task=1)
        loop.set_task(3, turbo=True)
        self.assertEqual(loop.controller.task, 3)
        self.assertTrue(loop.controller.turbo)
        self.assertAlmostEqual(loop.spawn["psi"], math.atan2(-0.8, 1.0),
                               places=6)


class TestStateProtocol(unittest.TestCase):
    """state() must carry the twin-viewer pose fields (web/src/main.ts
    drives the 3D bot from pos/quat_xyzw/wheel_deg, same as bot.loop)."""

    def test_state_has_twin_pose_fields(self):
        from race.loop import RaceLoop
        st = RaceLoop(task=1).state()
        self.assertEqual(st["type"], "state")
        self.assertEqual(len(st["pos"]), 3)
        self.assertEqual(len(st["quat_xyzw"]), 4)
        self.assertEqual(len(st["wheel_deg"]), 2)
        self.assertEqual(len(st["enc"]), 2)
        self.assertIsInstance(st["batt_v"], float)
        # spawn sanity: axle starts on node A, wheels not yet turned
        self.assertAlmostEqual(st["pos"][0], 0.60, places=3)
        self.assertAlmostEqual(st["pos"][1], 1.00, places=3)
        self.assertEqual(st["wheel_deg"], [0.0, 0.0])
        # xyzw order: spawn is yaw-90 (chassis -Y = travel +X) plus the
        # hover trim, so w and z dominate at ~cos45 and x/y carry trim
        q = st["quat_xyzw"]
        self.assertAlmostEqual(math.hypot(*q), 1.0, places=3)
        self.assertGreater(q[3], 0.5)
        self.assertGreater(q[2], 0.5)

    def test_state_schema_and_speed_pinned(self):
        """state() = telemetry.BASE_FIELDS + the race identity field
        (mission), and speed_mps is gt().v under the unified name -- the
        schema pin mirroring tests/test_twin.py's."""
        from race.loop import RaceLoop
        from bot import telemetry
        loop = RaceLoop(task=1)
        st = loop.state()
        self.assertEqual(set(st) - set(telemetry.BASE_FIELDS), {"mission", "line"})
        self.assertAlmostEqual(st["speed_mps"], loop.gt()["v"], places=4)


@unittest.skipIf(os.environ.get("RACE_SKIP_INT"), "RACE_SKIP_INT set")
class TestMissions(unittest.TestCase):
    """Headless mission runs against the CURRENT controller state.

    Asserts the stable core: completes inside the sheet's limit, right
    node order, car upright. Stop/beep margins are asserted coarsely
    (the strict grader thresholds are race.loop.grade's business;
    see race/README.md -- margins were still being tuned at freeze).
    """

    def _run(self, task, timeout):
        from race.loop import RaceLoop, grade
        loop = RaceLoop(task=task)
        v = loop.run_until_done(timeout)
        return loop, v

    def test_task1_straight_and_stop(self):
        loop, v = self._run(1, 40.0)
        self.assertTrue(v["done"], v)
        self.assertTrue(v["within_limit"], v)
        self.assertEqual(v["nodes"], ["B"])
        self.assertFalse(v["fallen"])
        self.assertLessEqual(v["stop_dist_m"], 0.5, v)
        self.assertLessEqual(
            max((e.get("gt_dist", 9) for e in loop.controller.events
                 if e["kind"] == "node"), default=0), 0.5)

    def test_task2_clockwise_loop(self):
        loop, v = self._run(2, 60.0)
        self.assertTrue(v["done"], v)
        self.assertTrue(v["within_limit"], v)
        self.assertEqual(v["nodes"], ["B", "C", "D", "A"])
        self.assertFalse(v["fallen"])
        self.assertLessEqual(v["stop_dist_m"], 0.5, v)

    def test_task3_crossed_loop(self):
        loop, v = self._run(3, 60.0)
        self.assertTrue(v["done"], v)
        self.assertTrue(v["within_limit"], v)
        self.assertEqual(v["nodes"], ["C", "B", "D", "A"])
        self.assertFalse(v["fallen"])
        self.assertLessEqual(v["stop_dist_m"], 0.6, v)

    def test_task4_runs_four_laps_and_passes(self):
        # task 4 is the speed event: 4 full laps, every node beeped in
        # order, stopped at A -- the same grade() contract as tasks 1-3.
        # (bring-up 2026-09-29: the 10 Hz yaw-rate lowpass fed the
        # steering servo's ~8 Hz relay and its phase with the tilt filter
        # leaked ~3 deg/lap into psi -- W_LPF_HZ 10->16 fixed lap 4)
        from race.loop import RaceLoop, grade
        loop = RaceLoop(task=4, turbo=True)
        loop.run_until_done(180.0)
        v = grade(loop)
        self.assertTrue(v["pass"], v)
        self.assertEqual(v["nodes"], ["C", "B", "D", "A"] * 4, v)


if __name__ == "__main__":
    unittest.main(verbosity=2)
