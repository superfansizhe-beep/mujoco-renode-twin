"""Shared Renode channel: machine boot + word I/O + heartbeat wait.

Both firmware backends (twin.renode_backend, race.renode_backend) boot
the same STM32F407ZGT6 machine (firmware/stm32f407zg.repl -- the real
part's memory map, not the discovery kit's) over pyrenode3 -- Renode
loaded in-process as a .NET assembly (coreclr) -- and wait for the
mailbox heartbeat under the same wall-clock cap. What deliberately
stays per-backend is the boot STROBE policy: the balance twin strobes a
zeros frame at boot, the race backend's first REAL frame is the
strobe; each choice is measured and documented in its reset().

Spike-measured 2026-09-28 on the survey's renode_1.17.0-portable:
direct .NET RunFor(5 ms) ~= 6 ms wall (0.84x realtime at 200 Hz
coupling), sysbus Write/ReadDoubleWord ~0.01 ms -- vs ~0.2 s/call
over the TCP monitor in the radar days.

Environment: RENODE_PORTABLE (or pyrenode3's own PYRENODE_PATH) must
point at a .NET (coreclr) Renode package/portable; nothing is guessed
about the host. pyrenode3 imports lazily so the rest of the twin works
without it (it lives in the optional [renode] dependency group).
"""
import os
import time

# Default the path at import time: both backends import bot.renode
# BEFORE they lazily import pyrenode3, so setting either variable makes
# the CLIs (`python -m race --backend renode` / `python -m twin --fw`)
# work with no further setup; RENODE_PORTABLE wins.
DEFAULT_PORTABLE = (os.environ.get("RENODE_PORTABLE")
                    or os.environ.get("PYRENODE_PATH"))
if DEFAULT_PORTABLE:
    os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)

# Renode-side heartbeat handshake: virtual boot window + wall-clock cap
BOOT_WINDOW_S = 0.05      # virtual seconds of firmware boot + first cycle
BOOT_TIMEOUT_WALL_S = 30.0


class RenodeChannel:
    """One booted Renode machine: ELF loaded, period pinned, word I/O."""

    def __init__(self, elf_path: str, dt: float, mips: int = 4,
                 mach_name: str = "twin",
                 renode_path: str | None = None) -> None:
        resolved = os.environ.setdefault(
            "PYRENODE_PATH", renode_path or DEFAULT_PORTABLE)
        if not os.path.isdir(resolved):
            raise FileNotFoundError(
                f"portable Renode not found at {resolved} -- point "
                f"PYRENODE_PATH at a .NET (coreclr) Renode package/portable")
        if not os.path.isfile(elf_path):
            raise FileNotFoundError(
                f"{elf_path} missing -- build the firmware first "
                f"(bash firmware/twin/build.sh or firmware/race/build.sh)")
        import pyrenode3                       # loads Renode (coreclr)
        from pyrenode3.wrappers import Emulation, Monitor
        from Antmicro.Renode.Time import TimeInterval

        repl = os.path.join(os.path.dirname(__file__), "..", "firmware",
                            "stm32f407zg.repl")
        self.emu = Emulation()
        self.mach = self.emu.add_mach(mach_name)
        mon = Monitor()
        self.mon = mon          # tests introspect the platform via monitor
        # the MPU6050 device model must exist before the repl attaches it
        for name in ("mpu6050_model.cs", "adc_model.cs", "enc_model.cs",
                     "timer1_model.cs", "iwdg_model.cs", "gpio_model.cs",
                     "rcc_model.cs", "uart_model.cs", "i2c_model.cs"):
            model_cs = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "firmware", name))
            out, err = mon.execute(f'include "{model_cs.replace(os.sep, "/")}"')
            if err:
                raise RuntimeError(f"{name} failed to compile: {err!r}")
        self.mach.load_repl(repl)
        # Renode's I2C master needs the receiver length up front (the real
        # peripheral paces reads with ACK/STOP instead); pin an over-fetch
        # the driver never observes -- every driver read asks for <= 14
        # bytes and stops when it has them.
        mon.execute("i2c1 I2CReadCount 32")
        out, err = mon.execute(f"cpu PerformanceInMips {mips}")
        if err:
            raise RuntimeError(f"PerformanceInMips failed: {err!r}")
        self.mach.load_elf(elf_path)
        try:  # vector table at flash base; skip if the property is missing (older Renode, same as the radar repo)
            mon.execute("cpu VectorTableOffset 0x08000000")
        except Exception:  # noqa: BLE001 -- optional knob
            pass
        self.sysbus = self.mach.sysbus.internal
        self.TI = TimeInterval
        self.period = TimeInterval.FromMilliseconds(dt * 1000.0)
        self._has_run = False

    def preset_counter(self, timer: str, value: int) -> None:
        """Harness-only initial CNT state, before the CPU executes.

        Bus writes with RCC disabled are discarded. Set the initial
        model state directly without enabling a firmware-owned clock.
        Runtime motion must still arrive through quadrature edges.
        """
        if self._has_run or timer not in ("timer2", "timer3", "timer4"):
            raise ValueError("counter presets are restricted to pre-boot TIM2/3/4")
        self.mach.sysbus.get_child(timer).internal.WriteDoubleWord(0x24, value)

    # ---- running ----
    def run(self, seconds: float) -> None:
        self._has_run = True
        self.emu.internal.RunFor(
            self.TI.FromMilliseconds(seconds * 1000.0))

    def run_period(self) -> None:
        self._has_run = True
        self.emu.internal.RunFor(self.period)

    # ---- mailbox word I/O ----
    def read_word(self, addr: int) -> int:
        return int(self.sysbus.ReadDoubleWord(addr))

    def write_word(self, addr: int, word: int) -> None:
        self.sysbus.WriteDoubleWord(addr, word)

    def wait_heartbeat(self, hb_addr: int, what: str) -> int:
        """Run periods until the fw_seq word at hb_addr goes positive
        (firmware alive), wall-clock capped at BOOT_TIMEOUT_WALL_S."""
        deadline = time.monotonic() + BOOT_TIMEOUT_WALL_S
        while self.read_word(hb_addr) < 1:
            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"firmware heartbeat never started -- boot hang? {what}")
            self.run_period()
        return self.read_word(hb_addr)
