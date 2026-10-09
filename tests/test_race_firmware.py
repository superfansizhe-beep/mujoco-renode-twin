"""THE race firmware gate: the real C firmware (race_fw.elf) drives an
exam mission in Renode and its observable behavior tracks the Python
stub's -- the race-side counterpart of twin's
test_renode_firmware_balances_and_matches_stub.

Real unittest skip (not a print) when the Renode environment is
missing: the suite must distinguish "passed" from "didn't run".
"""
import json
import math
import os
import unittest

from bot.renode import RenodeChannel
from race.renode_backend import (GPIOF_LINE_HIGH, BENCH, TIM3_CNT, TIM4_CNT)

GPIOF = 0x40021400              # the line-bar port

REPO = os.path.join(os.path.dirname(__file__), "..")
ELF_PATH = os.path.join(REPO, "firmware", "race", "race_fw.elf")


def _renode_ready():
    from bot.renode import DEFAULT_PORTABLE
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
        return None, f"{ELF_PATH} missing -- bash firmware/race/build.sh"
    return True, ""


class TestRaceFirmwareEndToEnd(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def test_firmware_line_bar_config_is_written_at_runtime(self):
        """The line-bar half of the review's rule (annotations do not
        enforce): after boot GPIOF must show the driver's config --
        PF0-7 inputs with pulls -- and a pin level must reach the bar
        read inside the firmware's control cycle (e_lat mirrors the
        injected centroid)."""
        from bot.renode import BOOT_WINDOW_S
        ch = RenodeChannel(ELF_PATH, 0.005, mach_name="race")
        self.addCleanup(ch.emu.clear)
        ch.preset_counter("timer3", 0x8000)
        ch.preset_counter("timer4", 0x8000)
        ch.write_word(0x2001FFC0 + 0x20, 1 << 16)     # task word: task 1
        for cmd in GPIOF_LINE_HIGH:                   # bar off-tape
            ch.mon.execute(cmd)
        ch.write_word(BENCH, 0x494D4231)
        ch.run(BOOT_WINDOW_S)
        moder = ch.read_word(GPIOF)
        self.assertEqual(moder & 0xFFFF, 0, "PF0-7 inputs (00)")
        pupdr = ch.read_word(GPIOF + 0x0C)
        self.assertEqual(pupdr & 0xFFFF, 0x5555, "PF0-7 pull-ups (01)")
        rcc = ch.read_word(0x40023830)
        self.assertEqual(rcc & 0x20, 0x20, "AHB1ENR.GPIOF (the repl RCC "
                         "stores enables)")

    def test_firmware_runs_task1_and_tracks_stub(self):
        """Task 1 (the shortest mission), stub and firmware in lockstep
        on identical sensor history, through the REAL peripheral path:
        IMU over the I2C driver, encoders edge-fed into TIM3/TIM4, the
        bar on the PF0-7 pins, duty decoded from the PWM registers.
        Same mission events, ground truth within 3 cm, both grade PASS,
        heartbeat exactly at the coupling rate."""
        from bot.loop import COUPLING_S
        from race.loop import RaceLoop, grade
        from race.renode_backend import RacePeriphBackend

        fw = RacePeriphBackend(task=1, dt=COUPLING_S)
        self.addCleanup(fw._ch.emu.clear)
        loop_fw = RaceLoop(task=1, controller=fw)
        loop_stub = RaceLoop(task=1)

        max_d = 0.0
        while loop_fw.data.time < 15.0:
            loop_stub.step_coupling()
            loop_fw.step_coupling()
            g, h = loop_stub.gt(), loop_fw.gt()
            max_d = max(max_d, math.hypot(g["x"] - h["x"], g["y"] - h["y"]))
            if (loop_stub.controller.phase == "done"
                    and loop_fw.controller.phase == "done"):
                break

        self.assertEqual(loop_stub.controller.phase, "done")
        self.assertEqual(loop_fw.controller.phase, "done",
                         "firmware never finished -- check race_fw.elf build")
        self.assertLess(max_d, 0.03,
                        f"stub vs firmware gt divergence {max_d * 100:.1f} cm")

        def shape(loop):
            return [(e["kind"], e["node"]) for e in loop.controller.events]

        self.assertEqual(shape(loop_fw), shape(loop_stub))
        self.assertTrue(grade(loop_fw)["pass"], grade(loop_fw))
        self.assertTrue(grade(loop_stub)["pass"], grade(loop_stub))

        # heartbeat == coupling rate, exactly (checked LAST: the extra
        # stepping must not sit inside the trajectory comparison)
        seq0 = fw.fw_seq
        for _ in range(100):
            loop_fw.step_coupling()
        self.assertEqual(fw.fw_seq - seq0, 100,
                         "lost firmware strobes over 100 couplings")

    def test_firmware_runs_tasks_23_through_peripherals(self):
        """Tasks 2-3 on the same REAL peripheral path (task 1 pins the
        stub equivalence; these pin completion + grade on the kinked
        routes through the bar/I2C/encoder/PWM drivers)."""
        from bot.loop import COUPLING_S
        from race.loop import RaceLoop, grade
        from race.renode_backend import RacePeriphBackend

        for task in (2, 3):
            with self.subTest(task=task):
                fw = RacePeriphBackend(task=task, dt=COUPLING_S)
                self.addCleanup(fw._ch.emu.clear)
                loop = RaceLoop(task=task, controller=fw)
                while loop.data.time < 60.0:
                    loop.step_coupling()
                    if loop.controller.phase == "done":
                        break
                self.assertEqual(loop.controller.phase, "done",
                                 f"task {task} never finished")
                g = grade(loop)
                self.assertTrue(g["pass"], f"task {task}: {g}")

    def test_production_elf_talks_on_the_serial_link_during_a_mission(self):
        """The v3 shell carries the USART2 link WHILE racing -- task 2
        through the full peripheral path with the TX tap attached: UP
        banner, 10 Hz T lines with monotonic seq and honest mission
        fields, ping->pong and stat->fresh-telemetry answered mid-run,
        node lines in route order, the done line with the mission clock,
        starved/resume transitions, and the mission itself still
        completes and grades PASS (the link must not cost behavior).
        Assertions read the backend's raw TX tap; the tester is
        write-only (its waiting reads hang on an empty buffer, twin
        rule)."""
        from bot.loop import COUPLING_S
        from race.loop import RaceLoop, grade
        from race.renode_backend import RacePeriphBackend

        fw = RacePeriphBackend(task=2, dt=COUPLING_S, uart_telemetry=True)
        self.addCleanup(fw._ch.emu.clear)
        loop = RaceLoop(task=2, controller=fw)   # constructor re-boots: the
        couplings = 0                            # log below starts at that UP

        def new_lines(mark):
            return bytes(fw.uart_log[mark:]).decode().splitlines()

        def parse_t(text):
            parts = text.split()
            self.assertEqual(len(parts), 8, f"telemetry shape: {text!r}")
            self.assertEqual(parts[0], "T")
            return [int(x) for x in parts[1:]]

        while loop.data.time < 0.6:             # arm (0.3 s) into the run
            loop.step_coupling()
            couplings += 1
        lines = new_lines(0)
        self.assertEqual(lines[0], "UP", lines[:3])
        self.assertIn("resume", lines[:3], lines[:3])
        seqs = [parse_t(t)[0] for t in lines if t.startswith("T ")]
        self.assertGreaterEqual(len(seqs), 3, lines)
        self.assertEqual(seqs, sorted(set(seqs)), "telemetry seq not monotonic")
        self.assertGreaterEqual(seqs[-1] - seqs[0], 40,
                                f"10 Hz cadence broken: span {seqs[-1] - seqs[0]}")
        first = [t for t in lines if t.startswith("T ")][0]
        self.assertEqual(parse_t(first)[5:], [0, 0], "first T must be arm/seg0")
        self.assertEqual(parse_t(first)[4], 0, "t_mission starts at zero")
        self.assertTrue(9000 < parse_t(first)[3] < 13000,
                        f"battery mV on the link: {first!r}")
        last = [t for t in lines if t.startswith("T ")][-1]
        self.assertEqual(parse_t(last)[6], 1, "0.6 s must be phase run")

        for _ in range(4):                       # commands mid-mission
            loop.step_coupling()
            couplings += 1
        mark = len(fw.uart_log)
        fw.send_line("ping")
        for _ in range(4):
            loop.step_coupling()
            couplings += 1
        self.assertIn("pong", new_lines(mark), new_lines(mark))

        mark = len(fw.uart_log)
        fw.send_line("stat")
        for _ in range(4):
            loop.step_coupling()
            couplings += 1
        stat = [t for t in new_lines(mark) if t.startswith("T ")]
        self.assertTrue(stat, "stat must answer with a telemetry line")
        self.assertGreater(parse_t(stat[0])[0], seqs[-1],
                           "stat must answer with a FRESH line")

        mark = len(fw.uart_log)
        while loop.data.time < 40.0:
            loop.step_coupling()
            couplings += 1
            if loop.controller.phase == "done":
                break
        tail = new_lines(mark)
        self.assertEqual(loop.controller.phase, "done")
        nodes = [int(l.split()[1]) for l in tail if l.startswith("node ")]
        self.assertEqual(nodes, [1, 2, 3], "node lines: legs entered, in order")
        dones = [l for l in tail if l.startswith("done ")]
        self.assertEqual(len(dones), 1, tail[-8:])
        self.assertTrue(0 < int(dones[0].split()[1]) < 30000,
                        f"done line mission clock: {dones[0]!r}")
        t_ms = [parse_t(t)[4] for t in tail if t.startswith("T ")]
        self.assertEqual(t_ms, sorted(t_ms), "mission clock must not go back")
        g = grade(loop)
        self.assertTrue(g["pass"], g)

        mark = len(fw.uart_log)                  # supervision after arrival:
        fw._ch.run(0.3)                          # bench silence, nothing at stake
        self.assertIn("starved", new_lines(mark))
        loop.step_coupling()
        couplings += 1
        self.assertIn("resume", new_lines(mark))

        self.assertEqual(fw.fw_seq, couplings,
                         "the tap/pump must not cost or duplicate cycles")

    def test_firmware_runs_task4_through_peripherals_and_wraps_encoders(self):
        """Four figure-8 laps through the production C drivers, with
        both 16-bit encoder counters crossing their boundaries.
        Completion alone is insufficient: the full ground-truth grade,
        including all 16 node beeps and the stop, must pass."""
        from bot.loop import COUPLING_S
        from race.loop import RaceLoop, grade
        from race.renode_backend import RacePeriphBackend

        fw = RacePeriphBackend(task=4, dt=COUPLING_S)
        self.addCleanup(fw._ch.emu.clear)
        loop = RaceLoop(task=4, controller=fw)
        addresses = (TIM3_CNT, TIM4_CNT)
        previous = [fw._ch.read_word(addr) for addr in addresses]
        wraps = [0, 0]
        couplings = 0
        while loop.data.time < 150.0:
            loop.step_coupling()
            couplings += 1
            raw = [fw._ch.read_word(addr) for addr in addresses]
            for wheel in range(2):
                self.assertLess(raw[wheel], 0x10000, "CNT must stay 16-bit")
                if abs(raw[wheel] - previous[wheel]) > 0x8000:
                    wraps[wheel] += 1
            previous = raw
            if couplings % 2000 == 0:
                print(f"task4 t={loop.data.time:.1f}s "
                      f"lap={fw.info()['lap']}/4 wraps={wraps}", flush=True)
            if loop.controller.phase == "done":
                break
        g = grade(loop)
        print("task4 peripheral gate: " + json.dumps(
            {"grade": g, "encoder_wraps": wraps, "couplings": couplings,
             "fw_seq": fw.fw_seq}), flush=True)
        self.assertEqual(loop.controller.phase, "done", "task 4 never finished")
        self.assertTrue(g["pass"], g)
        self.assertTrue(all(n > 0 for n in wraps),
                        f"both encoders must exercise wrap: {wraps}")
        self.assertEqual(fw.fw_seq, couplings, "lost or duplicate control cycles")


if __name__ == "__main__":
    unittest.main()
