"""The encoder bring-up gate: firmware/enc_bringup.elf reads quadrature
through the real timer encoder interface (firmware/stm32f4_encoder.c)
and integrates positions through the wrap-correct modular delta.

TIM3/TIM4 use firmware/enc_model.cs: Renode 1.17's stock encoder path
throws on wrap/underflow. These gates cross both boundaries through
quadrature edges and verify the real C driver's signed integration.
Edges enter through the encoder PORT pins (gpio_model.cs gates them on
MODER/AFRL like silicon); tests.test_firmware_rcc also gates their
RCC clocks. Physical AF routing remains a board check.
"""
import os
import re
import unittest

from bot.mailbox import u32_to_i32

REPO = os.path.join(os.path.dirname(__file__), "..")
FW = os.path.join(REPO, "firmware")
ENC_ELF = os.path.join(FW, "enc_bringup.elf")

TIM3 = 0x40000400          # left wheel
TIM4 = 0x40000800          # right wheel
GPIOC = 0x40020800
GPIOD = 0x40020C00

SEQ = ((0, 0), (1, 0), (1, 1), (0, 1))   # forward quadrature cycle

# the injection path: the port pins the firmware maps to the timer
# inputs (PC6/7 -> TIM3 ch1/ch2, PD12/13 -> TIM4), AF2
PORT_PINS = {"timer3": ("gpioPortC", 6, 7), "timer4": ("gpioPortD", 12, 13)}


def _layout():
    text = open(os.path.join(FW, "enc_bringup.h")).read()
    base = int(re.search(r"#define\s+ENC_RESULT_BASE\s+(0x[0-9A-Fa-f]+)",
                         text).group(1), 16)
    return base


ENC_BASE = _layout()


class TestEncoderLayout(unittest.TestCase):

    def test_results_block_sits_in_the_ld_carve(self):
        ld = open(os.path.join(FW, "stm32f407.ld")).read()
        ram = re.search(r"RAM   \(rwx\) : ORIGIN = 0x20000000, LENGTH = (\S+)",
                        ld).group(1)
        ram_end = 0x20000000 + int(ram, 16)
        self.assertLessEqual(ram_end, ENC_BASE,
                             "usable RAM must end at the enc results block "
                             "(see the ld header carve map)")
        self.assertEqual(ENC_BASE, 0x2001EE00)
        self.assertLess(ENC_BASE + 0x200, 0x2001FFB8,
                        "the enc block must stay below the fault words")


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
    if not os.path.isfile(ENC_ELF):
        return None, f"{ENC_ELF} missing -- bash firmware/build_enc.sh"
    return True, ""


class TestEncoderBringup(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()    # singleton: outlive any earlier machine
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(ENC_ELF, 0.005)
        self.sb = self._ch.sysbus

    def tearDown(self):
        self._ch.emu.clear()

    # ---- helpers ----
    def _step(self, timer, a, b):
        port, pin_a, pin_b = PORT_PINS[timer]
        self._ch.mon.execute(
            f"{port} OnGPIO {pin_a} {'true' if a else 'false'}")
        self._ch.mon.execute(
            f"{port} OnGPIO {pin_b} {'true' if b else 'false'}")
        self._ch.run(0.00002)

    def _drive(self, timer, n, start_state=0):
        """n quadrature counts (+/-) from SEQ state index start_state."""
        idx = start_state
        for _ in range(abs(n)):
            nxt = (idx + (1 if n > 0 else -1)) % 4
            a, b = SEQ[nxt]
            self._step(timer, a, b)
            idx = nxt

    def _res(self, i):
        return self.sb.ReadDoubleWord(ENC_BASE + 4 * i)

    # ---- the gates ----
    def test_encoder_mode_contract_is_written_at_runtime(self):
        self._ch.run(0.05)
        for name, base in (("TIM3", TIM3), ("TIM4", TIM4)):
            self.assertEqual(self.sb.ReadDoubleWord(base + 0x08) & 0x7, 0x3,
                             f"{name} SMCR.SMS=011 encoder mode x4")
            self.assertEqual(self.sb.ReadDoubleWord(base + 0x18), 0x101,
                             f"{name} CCMR1: CC1S=01, CC2S=01 "
                             "(TI1->IC1, TI2->IC2)")
            self.assertEqual(self.sb.ReadDoubleWord(base + 0x20) & 0xF, 0x0,
                             f"{name} CCER: both channels rising")
            self.assertEqual(self.sb.ReadDoubleWord(base) & 0x1, 0x1,
                             f"{name} CR1.PE... CEN: counting")
        moder_c = self.sb.ReadDoubleWord(GPIOC)
        self.assertEqual((moder_c >> 12) & 0xF, 0xA, "PC6/PC7 AF mode")
        afrl_c = self.sb.ReadDoubleWord(GPIOC + 0x20)
        self.assertEqual((afrl_c >> 24) & 0xFF, 0x22, "PC6/PC7 AF2")
        moder_d = self.sb.ReadDoubleWord(GPIOD)
        self.assertEqual((moder_d >> 24) & 0xF, 0xA, "PD12/PD13 AF mode")
        afrh_d = self.sb.ReadDoubleWord(GPIOD + 0x24)
        self.assertEqual((afrh_d >> 16) & 0xFF, 0x22, "PD12/PD13 AF2")
        # The repl's RCC model at 0x40023800 STORES the enables (the
        # 2026-09-29 review round corrected the old "stores nothing"
        # probe -- it had hit the FLASH block at 0x40023Cxx), so the
        # clock contract is sim-gated; only the gating EFFECT is board
        # (enc_status.md)
        rcc = 0x40023800
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x30) & 0xC, 0xC,
                         "AHB1ENR: GPIOC + GPIOD clocks")
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x40) & 0x6, 0x6,
                         "APB1ENR: TIM3 + TIM4 clocks")

    def test_forward_counts_integrate_to_position(self):
        self._ch.run(0.05)
        self._drive("timer3", 40)
        self._ch.run(0.01)
        self.assertEqual(self._res(0), 0x52434E45, "ENCR magic")
        self.assertGreater(self._res(1), 0, "the 1 ms poll loop runs")
        self.assertEqual(self._res(2), 40, "left position = +40 counts")
        self.assertEqual(self._res(4), 0x28, "left raw CNT")
        self.assertEqual(self._res(3), 0, "right wheel untouched")
        self.assertEqual(self.sb.ReadDoubleWord(0x2001FFB8), 0, "no fault")

    def test_reverse_counts_negative_after_a_forward_primer(self):
        """Changing direction preserves the quadrature phase."""
        self._ch.run(0.05)
        self._drive("timer4", 30)
        self._drive("timer4", -10, start_state=30 % 4)
        self._ch.run(0.01)
        self.assertEqual(self._res(3), 20, "right position = 30 - 10")
        self.assertEqual(self._res(2), 0, "left wheel untouched")

    def test_bench_counter_preset_integrates_as_a_modular_jump(self):
        """A bench preset mid-run is a real counter jump: the firmware
        must integrate it through the same modular delta it will use
        across real wrap (here: 0 -> 100 reads as +100)."""
        self._ch.run(0.05)
        self.sb.WriteDoubleWord(TIM4 + 0x24, 100)
        self._drive("timer4", -24, start_state=0)
        self._ch.run(0.01)
        self.assertEqual(self._res(3), 76, "position = +100 preset - 24")
        self.assertEqual(self._res(5), 0x4C, "raw CNT = 76")

    def test_forward_wrap_integrates_without_losing_counts(self):
        """0xFFFE -> 0x0004 is six forward edges, including the wrap."""
        self._ch.run(0.05)
        self.sb.WriteDoubleWord(TIM3 + 0x24, 0xFFFE)
        self._ch.run(0.01)                 # the firmware absorbs the jump
        pos_before = u32_to_i32(self._res(2))
        self._drive("timer3", 6)
        self._ch.run(0.01)
        self.assertEqual(self._res(4), 4, "CNT wraps to 16 bits")
        self.assertEqual(u32_to_i32(self._res(2)) - pos_before, 6,
                         "all six edges integrate through the wrap")
        self.assertEqual(self.sb.ReadDoubleWord(0x2001FFB8), 0, "no fault")

    def test_reverse_from_zero_integrates_negative_position(self):
        self._ch.run(0.05)
        self._drive("timer4", -40)
        self._ch.run(0.01)
        self.assertEqual(u32_to_i32(self._res(3)), -40)
        self.assertEqual(self._res(5), 0xFFD8, "underflow wraps to 16 bits")
        self.assertEqual(self._res(2), 0, "left wheel untouched")

    def test_reverse_underflow_integrates_without_losing_counts(self):
        self._ch.run(0.05)
        self.sb.WriteDoubleWord(TIM4 + 0x24, 2)
        self._ch.run(0.01)
        pos_before = u32_to_i32(self._res(3))
        self._drive("timer4", -6)
        self._ch.run(0.01)
        self.assertEqual(self._res(5), 0xFFFC)
        self.assertEqual(u32_to_i32(self._res(3)) - pos_before, -6)
        self.assertEqual(self.sb.ReadDoubleWord(TIM4) & 0x10, 0x10,
                         "DIR reports down-counting")

    def test_repeated_pin_levels_do_not_duplicate_edges(self):
        self._ch.run(0.05)
        self._step("timer3", 1, 0)
        for _ in range(8):
            self._step("timer3", 1, 0)
        self._ch.run(0.01)
        self.assertEqual(self._res(2), 1)
        self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), 1)

    def test_disabled_counter_tracks_pins_without_counting(self):
        self._ch.run(0.05)
        self.sb.WriteDoubleWord(TIM3, 0)     # CEN=0
        self._drive("timer3", 3)
        self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), 0)
        self.sb.WriteDoubleWord(TIM3, 1)
        self._drive("timer3", 1, start_state=3)
        self._ch.run(0.01)
        self.assertEqual(self._res(2), 1, "only the enabled edge counts")

    def test_unsupported_encoder_configurations_do_not_count(self):
        self._ch.run(0.05)
        for offset, unsupported in ((0x08, 0), (0x18, 0), (0x20, 2),
                                    (0x28, 1), (0x2C, 1000)):
            with self.subTest(offset=offset):
                saved = self.sb.ReadDoubleWord(TIM3 + offset)
                before = self.sb.ReadDoubleWord(TIM3 + 0x24)
                self.sb.WriteDoubleWord(TIM3 + offset, unsupported)
                self._drive("timer3", 4)
                self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), before)
                self.sb.WriteDoubleWord(TIM3 + offset, saved)
                self._drive("timer3", 4)
                self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), before + 4)

    def test_wrong_pin_map_stops_the_counts(self):
        """PC6/PC7 outside AF2 -> the timer inputs never see the edges
        (gpio_model.cs; the stock port forwarded unconditionally, probed
        2026-09-29). A wrong AFRL on the board is a silently dead
        encoder -- here it must be a visibly dead one. A full ring
        cycle (4 counts) returns the pins to the same absolute levels,
        so the phase stays consistent across the poke."""
        self._ch.run(0.05)
        cases = ((GPIOC, (3 << 12) | (3 << 14), "clear", "MODER -> input"),
                 (GPIOC + 0x20, (3 << 24) | (3 << 28), "set", "AFRL -> AF3"))
        for addr, bits, op, name in cases:
            with self.subTest(mis_map=name):
                before = self.sb.ReadDoubleWord(TIM3 + 0x24)
                saved = self.sb.ReadDoubleWord(addr)
                self.sb.WriteDoubleWord(
                    addr, (saved & ~bits) if op == "clear" else (saved | bits))
                self._drive("timer3", 4)
                self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), before,
                                 "edges with a wrong pin map must not count")
                self.sb.WriteDoubleWord(addr, saved)
                self._drive("timer3", 4, start_state=0)
                self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), before + 4,
                                 "restored pin map counts again")

    def test_reset_clears_pin_state_and_configuration(self):
        self._ch.run(0.05)
        self._step("timer3", 1, 0)          # leave A high at reset
        _, err = self._ch.mon.execute("timer3 Reset")
        self.assertFalse(err, err)
        self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), 0)
        self.assertEqual(self.sb.ReadDoubleWord(TIM3), 0)
        for offset, value in ((0x08, 3), (0x18, 0x101), (0x20, 0),
                              (0x28, 0), (0x2C, 0xFFFF), (0x00, 1)):
            self.sb.WriteDoubleWord(TIM3 + offset, value)
        # the pin level survives the TIMER reset (the port owns it, like
        # the wire on the board) -- a real low->high edge is needed to
        # count, and the reset-clear must keep it at exactly one
        self._step("timer3", 0, 0)
        self._step("timer3", 1, 0)
        self.assertEqual(self.sb.ReadDoubleWord(TIM3 + 0x24), 1,
                         "reset must clear the old A-high state")


if __name__ == "__main__":
    unittest.main()
