"""RaceHostcController -- the mission law compiled for the host.

Channel: firmware/race/race_law.c (+ track.c + core/balance.c) built
into a DLL by bot.hostc's toolchain discovery, driven through ctypes
behind the Controller seam. The observable-mission adapter is
RaceMissionCore (race/mission.py), shared with the Renode backends:
events and info() are synthesized from the same output fields the RAC2
mirror carries, so the loop, the viewer and the grader cannot tell the
backends apart except by name and speed. The law here is the shipped
algorithm at host speed -- the driver/peripheral layer's gates stay on
the Renode ELF path.
"""
import ctypes
import os

from bot.backend import Controller
from bot.hostc import build_dll, find_host_gcc
from .mailbox import RaceMotorFrame, RaceSensorFrame
from .mission import RaceMissionCore

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FW = os.path.join(_ROOT, "firmware")
RACE_DIR = os.path.join(_FW, "race")
DLL = os.path.join(RACE_DIR, "race_core.dll")
_SOURCES = [os.path.join(RACE_DIR, "race_law.c"),
            os.path.join(RACE_DIR, "track.c"),
            os.path.join(_FW, "core", "balance.c")]
_INCLUDES = [RACE_DIR, os.path.join(_FW, "twin"), _FW]
_DEPS = [os.path.join(RACE_DIR, p) for p in
         ("race_law.h", "track.h", "race_fwconfig.h")] + [
    os.path.join(_FW, "core", p) for p in ("balance.h", "line.h")] + [
    os.path.join(_FW, "line_config.h"),
    os.path.join(_FW, "twin", "twin_fwconfig.h")]


class _LawOut(ctypes.Structure):
    """race_law_out_t -- one cycle's observable outputs."""
    _fields_ = [
        ("duty_l", ctypes.c_int16), ("duty_r", ctypes.c_int16),
        ("buzzer_ms", ctypes.c_uint16), ("led_ms", ctypes.c_uint16),
        ("line_bits", ctypes.c_uint16),
        ("status", ctypes.c_uint32),
        ("t_mission_ms", ctypes.c_uint32),
        ("e_lat_mm", ctypes.c_int16),
        ("v_plan_mm_s", ctypes.c_uint16),
        ("odo_x_cm", ctypes.c_int16), ("odo_y_cm", ctypes.c_int16),
        ("fw_seq", ctypes.c_uint32),
        ("node_edge", ctypes.c_uint8), ("done_edge", ctypes.c_uint8),
    ]


class RaceHostcController(RaceMissionCore, Controller):
    """The controller surface (task/turbo/phase/events/step/reset/info)
    backed by the C mission law in a host DLL instead of Renode."""

    name = "hostc:race"

    def __init__(self, task: int = 2, dt: float = 0.005,
                 v_batt: float = 11.1, turbo: bool | None = None) -> None:
        gcc = find_host_gcc()
        if gcc is None:
            raise RuntimeError(
                "hostc: no host gcc (set HOSTCC, put gcc on PATH, or "
                "install MSYS2's mingw64 toolchain)")
        super().__init__(task, dt, turbo)
        self.v_batt = v_batt          # the law derates by the sample's mV
        self.name = "hostc:race"
        build_dll(gcc, DLL, _SOURCES, _INCLUDES, _DEPS)
        self._dll = ctypes.CDLL(DLL)
        self._dll.race_law_configure.argtypes = [ctypes.c_uint8,
                                                 ctypes.c_uint8]
        self._dll.race_law_init.argtypes = []
        self._dll.race_law_cycle.argtypes = [
            ctypes.POINTER(_LawOut),
            ctypes.c_int16, ctypes.c_int16, ctypes.c_int16, ctypes.c_int16,
            ctypes.c_int32, ctypes.c_int32, ctypes.c_uint16, ctypes.c_uint16]
        from .diagnostics import CEstimates
        self._estimates = CEstimates(DLL, dll=self._dll)
        self._out = _LawOut()
        self.reset()

    # ---------------- lifecycle ----------------
    def reset(self, x0: float = 0.0, y0: float = 0.0,
              psi0: float = 0.0) -> None:
        """Fresh mission. (x0, y0, psi0) -- the spawn prior the stub
        gets -- is IGNORED: the law derives the identical triple from
        its own route table (both are 'node A + first-segment tangent',
        race.spawn.spawn_for_task)."""
        del x0, y0, psi0                 # the harness passes them; law owns them
        self._reset_mission()
        self._dll.race_law_configure(self.task, 1 if self.turbo else 0)
        self._dll.race_law_init()
        self._estimates.clear_cache()

    def diagnostics(self) -> dict:
        return self._estimates.snapshot(self.fw_seq, self.phase)

    # ---------------- the controller slot ----------------
    def step(self, s: RaceSensorFrame) -> RaceMotorFrame:
        self._dll.race_law_cycle(
            ctypes.byref(self._out),
            int(s.accel[1]), int(s.accel[2]), int(s.gyro[0]), int(s.gyro[2]),
            int(s.enc_l), int(s.enc_r),
            int(s.line_bits) & 0xFFFF, int(s.battery_mv) & 0xFFFF)
        o = self._out
        m = RaceMotorFrame(
            duty_l=o.duty_l, duty_r=o.duty_r,
            buzzer_ms=o.buzzer_ms, led=o.led_ms,
            fw_seq=o.fw_seq, status=o.status,
            t_mission_ms=o.t_mission_ms,
            e_lat_mm=o.e_lat_mm, v_plan_mm_s=o.v_plan_mm_s,
            odo_cm=(o.odo_x_cm, o.odo_y_cm))
        self._absorb_outputs(m)
        self._consumed_line_bits = o.line_bits & 0xFF
        return m

