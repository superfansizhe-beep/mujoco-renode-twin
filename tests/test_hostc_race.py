"""Host-C race law gates: frame-level duty parity vs the Python stub on
identical sensor frames (same spawn prior both sides -- the law derives
it from the route table, the stub from reset(x0, y0, psi0)), and
closed-loop mission parity on task 2 (arcs + line law + nodes). The
Renode ELF gates (tests.test_race_firmware, tests.test_line_tracking)
stay on the ELF -- they pinned the extraction itself; these pin the
host port of the same single source.

Renode is not needed; the only external dependency is a host gcc
(skipped with a reason when none exists).
"""
import math
import unittest

from bot import mjcf
from bot.hostc import find_host_gcc
from bot.loop import COUPLING_S

from race.controller import RaceController
from race.hostc_backend import RaceHostcController
from race.loop import RaceLoop, grade
from race.spawn import spawn_for_task

TASK = 2


def _record_stub_frames(task: int, cap_s: float) -> list:
    """One stub-driven mission; returns every sensor frame in order."""
    record = []

    class Tap(RaceController):
        def step(self, s):
            record.append(s)
            return super().step(s)

    loop = RaceLoop(task=task, controller=Tap(task, COUPLING_S, 11.1))
    loop.run_until_done(cap_s)
    return record


class HostCRace(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if find_host_gcc() is None:
            raise unittest.SkipTest(
                "no host gcc (HOSTCC env, PATH gcc, or MSYS2 mingw64 "
                "default)")
        cls.hostc = RaceHostcController(task=TASK)

    def test_hostc_default_uses_fast_profile(self):
        self.assertTrue(self.hostc.turbo)

    def test_duty_series_matches_stub_on_identical_frames(self):
        """Same frames in, duty series out. float64 stub vs float32 law:
        integrator drift over a whole mission, not structure. The bound
        covers it with margin (measured worst 7 permille)."""
        record = _record_stub_frames(TASK, 30.0)
        # The default profile is now fast for every task; task 2 completes
        # sooner than the former slow-table threshold while still covering
        # the full route and both taped arcs.
        self.assertGreater(len(record), 3000)
        _, spawn = spawn_for_task(mjcf.load_model(), TASK)
        stub = RaceController(TASK, COUPLING_S, 11.1)
        stub.reset(spawn["x"], spawn["y"], spawn["psi"])
        core = RaceHostcController(task=TASK)
        worst = 0
        for s in record:
            a = stub.step(s)
            b = core.step(s)
            worst = max(worst, abs(a.duty_l - b.duty_l),
                        abs(a.duty_r - b.duty_r))
        self.assertLessEqual(worst, 10,
                             f"stub vs host-C duty divergence {worst} "
                             f"permille over {len(record)} frames")

    def test_task2_mission_matches_stub_closed_loop(self):
        """Both controllers drive the same mission from their own spawn
        priors; verdicts must both pass with matching node order and
        close elapsed/stop, and the sampled ground-truth trajectories
        must stay near each other (float32 integrator drift only)."""

        def mission(loop, samples):
            mark = 0.0
            while loop.controller.phase != "done" and loop.data.time < 30.0:
                loop.run(0.5)
                if loop.data.time - mark >= 0.5:
                    mark = loop.data.time
                    samples.append((loop.data.time, loop.tilt_deg(),
                                    float(loop.data.qpos[0]),
                                    float(loop.data.qpos[1])))
            samples.append((loop.data.time, loop.tilt_deg(),
                            float(loop.data.qpos[0]),
                            float(loop.data.qpos[1])))
            return grade(loop)

        samples_h, samples_s = [], []
        host_ctl = RaceHostcController(task=TASK)
        v_h = mission(RaceLoop(task=TASK, controller=host_ctl), samples_h)
        v_s = mission(RaceLoop(task=TASK), samples_s)

        self.assertTrue(v_s["pass"], v_s)
        self.assertTrue(v_h["pass"], v_h)
        self.assertEqual(v_h["nodes"], v_s["nodes"])
        self.assertLess(abs(v_h["elapsed_s"] - v_s["elapsed_s"]), 0.6,
                        (v_h["elapsed_s"], v_s["elapsed_s"]))
        self.assertLess(abs(v_h["stop_dist_m"] - v_s["stop_dist_m"]), 0.15,
                        (v_h["stop_dist_m"], v_s["stop_dist_m"]))
        d_tilt = max(abs(a[1] - b[1]) for a, b in zip(samples_h, samples_s))
        d_pos = max(math.hypot(a[2] - b[2], a[3] - b[3])
                    for a, b in zip(samples_h, samples_s))
        self.assertLess(d_tilt, 2.0, f"tilt divergence {d_tilt:.2f} deg")
        self.assertLess(d_pos, 0.12, f"position divergence {d_pos*100:.1f} cm")

        # the observable-mission surface the loop/viewer/grader read
        info_dict = host_ctl.info()
        stub_info = RaceLoop(task=TASK).controller.info()
        self.assertEqual(set(info_dict), set(stub_info))
        kinds = [e["kind"] for e in host_ctl.events]
        self.assertIn("done", kinds)
        self.assertTrue(any(k == "node" for k in kinds))


if __name__ == "__main__":
    unittest.main()
