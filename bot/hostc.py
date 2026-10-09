"""Host-compiled C control core -- the fast, algorithm-exact backend.

Compiles firmware/core/balance.c -- the one source the ELF links --
into a host DLL and drives it through ctypes behind the Controller
seam: the real C law at native speed, minus the STM32 driver layer.
That layer's gates (I2C/encoder/PWM/UART/watchdog) stay on the Renode
ELF path (--backend renode); this path exists so interactive runs
execute the shipped algorithm, not the Python shadow of it.

Float flags: -O2 -ffp-contract=off keeps the arithmetic order fixed
(no x86 FMA contraction), mirroring the ELF's -O2 hard-float build;
parity with the stub is still tolerance-based because host libm and
newlib differ in ulps (atan2f et al).

Naming: NOT "native" -- in this repo's evidence records native-* means
the ARM ELF executed through Renode; this backend is "hostc".
"""
import ctypes
import os
import shutil
import subprocess

from .backend import Controller
from .mailbox import MotorFrame, SensorFrame

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORE_C = os.path.join(_ROOT, "firmware", "core", "balance.c")
CORE_H = os.path.join(_ROOT, "firmware", "core", "balance.h")
CFG_DIR = os.path.join(_ROOT, "firmware", "twin")   # twin_fwconfig.h
DLL = os.path.join(CFG_DIR, "balance_core.dll")

def _msys2_default() -> str | None:
    if os.name != "nt":
        return None
    drive = os.environ.get("SystemDrive", "C:") + os.sep
    cand = os.path.join(drive, "msys64", "mingw64", "bin", "gcc.exe")
    return cand if os.path.isfile(cand) else None


def find_host_gcc() -> str | None:
    """HOSTCC env wins, then PATH gcc, then the MSYS2 default install
    (the PYRENODE_PATH discovery pattern; an explicit env still wins)."""
    env = os.environ.get("HOSTCC")
    if env:
        return env if os.path.isfile(env) else None
    found = shutil.which("gcc")
    if found:
        return found
    return _msys2_default()


def _gcc_env(gcc: str) -> dict:
    # the discovered gcc carries its toolchain: cc1/as/ld load DLLs from
    # their own bin dir, which is usually NOT on PATH (MSYS2 default
    # install) -- without it the build fails silently (exit 1, no stderr)
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(os.path.abspath(gcc)) + os.pathsep \
        + env.get("PATH", "")
    return env


def build_dll(gcc: str, dll: str, sources, include_dirs, deps) -> None:
    """(Re)build a host DLL from platform-free firmware sources; stale =
    older than any source or watched header. The float flags are the
    contract: -O2 -ffp-contract=off -fno-fast-math, mirroring the ELF's
    -O2 hard-float build (no x86 FMA contraction; parity stays
    tolerance-based because host libm and newlib differ in ulps)."""
    if os.path.isfile(dll) and all(os.path.getmtime(dll) >= os.path.getmtime(d)
                                   for d in (*sources, *deps)):
        return
    cmd = [gcc, "-O2", "-ffp-contract=off", "-fno-fast-math", "-shared"]
    for inc in include_dirs:
        cmd += ["-I", inc]
    cmd += ["-o", dll, *sources]
    res = subprocess.run(cmd, capture_output=True, text=True, env=_gcc_env(gcc))
    if res.returncode != 0:
        raise RuntimeError(
            f"host DLL build failed: {' '.join(cmd)}\n{res.stderr}")


def build_core_dll(gcc: str, verbose: bool = False) -> None:
    """(Re)build the balance core DLL."""
    build_dll(gcc, DLL, [CORE_C], [CFG_DIR],
              [CORE_H, os.path.join(CFG_DIR, "twin_fwconfig.h")])
    if verbose:
        print(f"hostc: built {DLL}")


class _Tilt(ctypes.Structure):
    _fields_ = [("theta", ctypes.c_float), ("have", ctypes.c_uint8)]


class _Hold(ctypes.Structure):
    _fields_ = [("tilt", _Tilt), ("have_enc", ctypes.c_uint8),
                ("last_enc_mean", ctypes.c_float), ("pos_m", ctypes.c_float)]


class _Sample(ctypes.Structure):
    _fields_ = [("ay", ctypes.c_int16), ("az", ctypes.c_int16),
                ("gx", ctypes.c_int16),
                ("enc_l", ctypes.c_int32), ("enc_r", ctypes.c_int32),
                ("batt_mv", ctypes.c_uint16)]


class HostBalanceController(Controller):
    """balance_hold_step in the Controller slot: raw mailbox words in
    (the same frame the stub and the ELF shell see), permille duty out.
    fw_seq counts steps locally -- the heartbeat mirror, one per cycle,
    like TWIN_FW_SEQ in the shell."""

    def __init__(self) -> None:
        gcc = find_host_gcc()
        if gcc is None:
            raise RuntimeError(
                "hostc: no host gcc (set HOSTCC, put gcc on PATH, or "
                "install MSYS2's mingw64 toolchain)")
        self.name = "hostc:balance"
        build_core_dll(gcc)
        self._dll = ctypes.CDLL(DLL)
        self._dll.balance_hold_init.argtypes = [ctypes.POINTER(_Hold)]
        self._dll.balance_hold_step.argtypes = [ctypes.POINTER(_Hold),
                                                ctypes.POINTER(_Sample)]
        self._dll.balance_hold_step.restype = ctypes.c_int
        self._hold = _Hold()
        self.fw_seq = 0
        self.reset()

    def reset(self) -> None:
        self._dll.balance_hold_init(ctypes.byref(self._hold))
        self.fw_seq = 0

    def step(self, s: SensorFrame) -> MotorFrame:
        samp = _Sample(ay=int(s.accel[1]), az=int(s.accel[2]),
                       gx=int(s.gyro[0]),
                       enc_l=int(s.enc_l), enc_r=int(s.enc_r),
                       batt_mv=int(s.battery_mv) & 0xFFFF)
        duty = self._dll.balance_hold_step(ctypes.byref(self._hold),
                                           ctypes.byref(samp))
        self.fw_seq += 1
        return MotorFrame(duty_l=duty, duty_r=duty, fw_seq=self.fw_seq)
