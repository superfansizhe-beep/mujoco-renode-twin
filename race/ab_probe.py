"""A/B probe: stub vs firmware, per-cycle duty diff on task 1.

Not a test -- a bring-up instrument. Steps BOTH controller slots against
their own MuJoCo loops (identical spawn, identical harness), logging the
first cycles where |duty diff| crosses 1/3/10 permille and the gt drift
at 0.5 s marks. Gradual growth = float precision amplification (the
brake transient is a marginal hunt); a discrete jump = porting bug.
"""
import sys

from bot.loop import COUPLING_S

from .loop import RaceLoop
from .renode_backend import RacePeriphBackend


def main() -> int:
    task = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0

    fw = RacePeriphBackend(task=task, dt=COUPLING_S)
    loop_fw = RaceLoop(task=task, controller=fw)
    loop_stub = RaceLoop(task=task)
    print(f"task {task}: stub vs {fw.name}")

    marks = {"gt1": 0.0}
    thresholds = (1, 3, 10, 30)
    crossed = set()
    max_dx = 0.0
    n = int(seconds / COUPLING_S)
    for i in range(n):
        loop_stub.step_coupling()
        loop_fw.step_coupling()
        dl = abs(loop_stub.last_motor.duty_l - loop_fw.last_motor.duty_l)
        dr = abs(loop_stub.last_motor.duty_r - loop_fw.last_motor.duty_r)
        d = max(dl, dr)
        for th in thresholds:
            if th not in crossed and d > th:
                crossed.add(th)
                t = (i + 1) * COUPLING_S
                print(f"  first |dduty|>{th:2d} @ t={t:6.3f}s  "
                      f"stub=({loop_stub.last_motor.duty_l:+d},"
                      f"{loop_stub.last_motor.duty_r:+d}) "
                      f"fw=({loop_fw.last_motor.duty_l:+d},"
                      f"{loop_fw.last_motor.duty_r:+d})")
        if (i + 1) % 100 == 0:
            t = (i + 1) * COUPLING_S
            g1, g2 = loop_stub.gt(), loop_fw.gt()
            dx = abs(g1["x"] - g2["x"]) + abs(g1["y"] - g2["y"])
            max_dx = max(max_dx, dx)
            print(f"  t={t:5.2f}  gt_stub=({g1['x']:.3f},{g1['y']:.3f}) "
                  f"gt_fw=({g2['x']:.3f},{g2['y']:.3f}) "
                  f"tilt {loop_stub.tilt_deg():+6.2f}/"
                  f"{loop_fw.tilt_deg():+6.2f}  d={d}")
    print(f"max |gt drift| over run: {max_dx * 100:.1f} cm")
    print("stub events:", [(e["kind"], e["node"], e["t"]) for e in
                           loop_stub.controller.events])
    print("fw   events:", [(e["kind"], e["node"], e["t"]) for e in
                           loop_fw.controller.events])
    return 0


if __name__ == "__main__":
    sys.exit(main())
