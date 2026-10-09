"""Long encoder probe through the production peripheral backend.

Run: .venv/Scripts/python.exe -u -m tests.encoder_wrap_probe
Inject +70000 left / -70000 right counts at 7 counts per 5 ms coupling.
No post-boot CNT writes: the backend checks every edge batch modulo
65536, while real C firmware consumes IMU samples and polls the timers.
"""
import json
import os
import time

from bot.loop import COUPLING_S
from bot.renode import DEFAULT_PORTABLE
from race.mailbox import RaceSensorFrame
from race.renode_backend import RacePeriphBackend, TIM3_CNT, TIM4_CNT


def main():
    os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)
    fw = RacePeriphBackend(task=1, dt=COUPLING_S)
    ch = fw._ch
    started = time.monotonic()
    previous = [ch.read_word(TIM3_CNT), ch.read_word(TIM4_CNT)]
    crossings = [0, 0]
    try:
        for coupling in range(1, 10001):
            target = coupling * 7
            fw.step(RaceSensorFrame(seq=coupling + 1, accel=(0, 0, 16384),
                                   battery_mv=11100,
                                   enc_l=target, enc_r=-target))
            raw = [ch.read_word(TIM3_CNT), ch.read_word(TIM4_CNT)]
            expected = [(0x8000 + target) & 0xFFFF,
                        (0x8000 - target) & 0xFFFF]
            if raw != expected or fw.fw_seq != coupling:
                raise AssertionError(f"coupling {coupling}: CNT={raw}, "
                                     f"expected={expected}, fw_seq={fw.fw_seq}")
            for wheel in range(2):
                if abs(raw[wheel] - previous[wheel]) > 0x8000:
                    crossings[wheel] += 1
                    print(f"wrap wheel={wheel} counts={target} "
                          f"CNT=0x{previous[wheel]:04X}->0x{raw[wheel]:04X}",
                          flush=True)
            previous = raw
            if coupling % 1000 == 0:
                print(f"counts=+/-{target} couplings={coupling} "
                      f"CNT={[hex(v) for v in raw]} "
                      f"wall_s={time.monotonic() - started:.1f}", flush=True)
        fault = ch.read_word(0x2001FFB8)
        if crossings != [1, 1] or fault != 0:
            raise AssertionError(f"crossings={crossings}, fault=0x{fault:X}")
        print(json.dumps({"pass": True, "counts": [70000, -70000],
                          "couplings": fw.fw_seq, "wraps": crossings,
                          "raw_cnt": previous, "fault": fault,
                          "wall_s": round(time.monotonic() - started, 2)}),
              flush=True)
    finally:
        ch.emu.clear()


if __name__ == "__main__":
    main()
