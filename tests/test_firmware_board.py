"""Board-contract gate: the firmware targets the REAL STM32F407ZGT6 --
not Renode's generous discovery platform (review 2026-09-28, see
output/peripheral-review/review.md).

Pinned here: the linker and the platform repl stay inside the real part
(1 MiB flash, 128 KiB SRAM, CCM separate); the fault words sit directly
below the mailbox; the committed ELFs carry the full 98-entry vector
table and debug symbols; and the firmware's starvation response -- P1:
it used to hold the last motor command forever when the sensor strobe
went silent.
"""
import os
import re
import shutil
import subprocess
import unittest

REPO = os.path.join(os.path.dirname(__file__), "..")
FW = os.path.join(REPO, "firmware")
BALANCE_ELF = os.path.join(FW, "twin", "balance_fw.elf")
ELFS = (os.path.join("twin", "balance_fw.elf"),
        os.path.join("race", "race_fw.elf"))

FAULT_MAGIC_ADDR = 0x2001FFB8
FAULT_SENTINEL = 0xFA17C0DE

# the peripheral firmware's harness side: IMU bench (the Renode MPU6050
# model latches from here) + the encoder origin presets
BENCH = 0xF0000000
BENCH_SEQ = BENCH + 0x04
TIM3_CNT = 0x40000424
TIM4_CNT = 0x40000824


def _read(*parts) -> str:
    with open(os.path.join(*parts)) as f:
        return f.read()


class TestBoardContract(unittest.TestCase):
    """Static sources: no toolchain, no emulator."""

    def test_linker_stays_inside_the_real_part(self):
        text = _read(FW, "stm32f407.ld")
        flash = re.search(r"FLASH \(rx\)\s*: ORIGIN = 0x08000000, LENGTH = (\S+)",
                          text)
        ram = re.search(r"RAM   \(rwx\) : ORIGIN = 0x20000000, LENGTH = (\S+)",
                        text)
        self.assertEqual(flash.group(1), "1024K",
                         "the ZGT6 has 1 MiB flash, not the discovery kit's 2")
        self.assertEqual(ram.group(1).lower(), "0x1ea00",
                         "RAM must end below the bring-up harness blocks "
                         "(battery + pwm + enc + imu) and fault words "
                         "(see ld header)")

    def test_platform_is_the_zgt6_not_the_discovery_kit(self):
        text = _read(FW, "stm32f407zg.repl")
        sram = re.search(r"sram: Memory\.MappedMemory.*?size: (0x[0-9A-Fa-f]+)",
                         text, re.S).group(1)
        flash = re.search(r"flash: Memory\.MappedMemory.*?size: (0x[0-9A-Fa-f]+)",
                          text, re.S).group(1)
        self.assertEqual(int(sram, 16), 0x20000, "128 KiB real SRAM")
        self.assertEqual(int(flash, 16), 0x100000, "1 MiB real flash")
        self.assertIn("ccm: Memory.MappedMemory @ sysbus 0x10000000", text,
                      "CCM modeled as its own region, not extra SRAM")
        self.assertNotIn("gpioPortJ", text, "no Z-package-only ports")

    def test_fault_and_mailbox_words_fit_below_real_sram_top(self):
        mb = int(re.search(r"TWIN_MAILBOX_BASE\s+(0x[0-9A-Fa-f]+)",
                           _read(FW, "twin", "mailbox.h")).group(1), 16)
        self.assertLessEqual(mb + 0x40, 0x20020000,
                             "mailbox window must fit the real 128 KiB SRAM")
        self.assertEqual(mb - 8, FAULT_MAGIC_ADDR,
                         "fault words sit directly below the mailbox")


def _elfs_built():
    return all(os.path.isfile(os.path.join(FW, elf)) for elf in ELFS)


@unittest.skipUnless(shutil.which("arm-none-eabi-readelf"),
                     "arm-none-eabi-readelf not in PATH")
@unittest.skipUnless(_elfs_built(),
                     "firmware ELFs not built -- bash firmware/twin/build.sh "
                     "&& bash firmware/race/build.sh")
class TestCommittedArtifacts(unittest.TestCase):

    def test_isr_vector_is_full_98_entries(self):
        for elf in ELFS:
            out = subprocess.run(
                ["arm-none-eabi-readelf", "-S", os.path.join(FW, elf)],
                capture_output=True, text=True, check=True).stdout
            size = re.search(
                r"\.isr_vector\s+PROGBITS\s+\S+\s+\S+\s+([0-9a-f]+)", out)
            self.assertEqual(int(size.group(1), 16), (16 + 82) * 4,
                             f"{elf}: vector table must carry all 98 entries")

    def test_debug_symbols_are_committed(self):
        for elf in ELFS:
            out = subprocess.run(
                ["arm-none-eabi-readelf", "-S", os.path.join(FW, elf)],
                capture_output=True, text=True, check=True).stdout
            self.assertIn(".debug_info", out,
                          f"{elf}: build with -g, source-level debugging "
                          f"was a review P2")


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
    if not os.path.isfile(BALANCE_ELF):
        return None, f"{BALANCE_ELF} missing -- bash firmware/twin/build.sh"
    return True, ""


class TestFirmwareSelfProtection(unittest.TestCase):
    """The firmware must survive its harness going silent: disable the
    motors on its own deadline, freeze the heartbeat (no phantom cycles),
    resume cleanly, and never fault doing it."""

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()    # singleton: outlive any earlier machine
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(BALANCE_ELF, 0.005)

    def tearDown(self):
        self._ch.emu.clear()

    def _bench_frame(self, seq, accel=(0, 16384, 16384), gyro=(0, 0, 0),
                     temp=-3920, batt=11100):
        """One IMU bench frame: the MPU6050 model latches it, the
        firmware reads it through the real I2C driver (seq write LAST
        = the data-ready latch)."""
        ch = self._ch
        ch.write_word(BENCH, 0x494D4231)          # "IMB1"
        for off, v in zip((0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x20),
                          (*accel, *gyro, temp)):
            ch.write_word(BENCH + off, v & 0xFFFFFFFF)
        ch.write_word(BENCH + 0x24, 0)            # FI: no fault inject
        ch.write_word(BENCH + 0x28, batt)
        ch.write_word(BENCH_SEQ, seq)

    def _boot_leaning(self):
        """Boot the peripheral firmware (encoder counters pre-shifted
        to 0x8000: Renode throws on edge-driven wrap, an origin shift
        the delta16 cannot see), then feed a hard fake lean through the
        bench: the LQR must answer with a clearly nonzero duty --
        decoded from the PWM registers, the truth the plant reads."""
        from bot.renode import BOOT_WINDOW_S
        ch = self._ch
        ch.preset_counter("timer3", 0x8000)
        ch.preset_counter("timer4", 0x8000)
        self._bench_frame(1)
        ch.run(BOOT_WINDOW_S)
        ch.write_word(BENCH_SEQ, 2)
        ch.wait_heartbeat(0x2001FFC0 + 0x24, "balance_fw boot")
        ch.write_word(BENCH_SEQ, 3)
        ch.run_period()
        from bot.periph import decode_duty_pair
        duty_l, _ = decode_duty_pair(ch.read_word)
        self.assertGreater(abs(duty_l), 100,
                           msg="fake lean must produce real drive")

    def test_starvation_disables_motors_and_freezes_heartbeat(self):
        self._boot_leaning()
        ch = self._ch
        seq0 = ch.read_word(0x2001FFC0 + 0x24)
        duty_word = 0x1
        for _ in range(40):            # 2 virtual seconds of silence
            ch.run(0.05)
            duty_word = ch.read_word(0x2001FFC0 + 0x20)
            if duty_word == 0:
                break
        self.assertEqual(duty_word, 0,
                         "firmware must zero duty on its own when the "
                         "strobe goes silent (P1: held -450 forever)")
        self.assertEqual(ch.read_word(0x2001FFC0 + 0x24), seq0,
                         "heartbeat frozen: no phantom control cycles")
        self.assertEqual(ch.read_word(FAULT_MAGIC_ADDR), 0,
                         "starvation path must not trip a fault")
        ch.write_word(BENCH_SEQ, 4)      # a fresh bench frame resumes
        ch.run_period()
        self.assertEqual(ch.read_word(0x2001FFC0 + 0x24), seq0 + 1,
                         "next strobe resumes the control cycle")

    def test_starvation_deadline_is_the_timer_not_a_poll_count(self):
        """The deadline claims wall-time semantics: the shared TIM2 must
        be running once the firmware boots (timer_monotonic.c), and the
        repl clock tree it is calibrated against is the 16 MHz HSI reset
        state both worlds share."""
        self._boot_leaning()
        ch = self._ch
        cr1 = ch.read_word(0x40000000)          # TIM2_CR1
        self.assertEqual(cr1 & 0x1, 0x1,
                         "timer_monotonic must leave TIM2 counting (CEN=1)")
        self.assertEqual(ch.read_word(0x40023840) & 0x1, 0x1,
                         "APB1ENR.TIM2EN must be written BEFORE CEN: on "
                         "silicon the counter is dead without its clock")
        cnt0 = ch.read_word(0x40000024)         # TIM2_CNT
        ch.run(0.01)                            # 10 ms virtual
        cnt1 = ch.read_word(0x40000024)
        delta = (cnt1 - cnt0) & 0xFFFFFFFF
        self.assertAlmostEqual(delta / 16000.0, 10.0, delta=1.0,
                               msg="TIM2 must tick at the pinned 16 MHz "
                                   f"HCLK (got {delta} ticks / 10 ms)")
        repl = _read(FW, "stm32f407zg.repl")
        self.assertNotIn("84000000", repl, "clock tree pinned to 16 MHz")
        self.assertNotIn("168000000", repl, "clock tree pinned to 16 MHz")

    def test_memory_map_matches_the_real_part(self):
        for addr, on_chip in (("0x080FFFFC", True),   # last 1 MiB flash word
                              ("0x08100000", False),  # discovery's extra flash
                              ("0x2001FFBF", True),   # mailbox/fault SRAM top
                              ("0x20020000", False),  # discovery's extra SRAM
                              ("0x10000000", True)):  # CCM
            out, _ = self._ch.mon.execute(
                f"sysbus WhatPeripheralIsAt {addr}")
            self.assertEqual(bool(out.strip()), on_chip, addr)


class TestWatchdogContract(unittest.TestCase):
    """The IWDG is the last-resort guard (firmware/stm32f4_iwdg.c,
    race_status.md): both production mains program it at boot and kick
    every loop slice. Renode 1.17's stock model stores the registers but
    a driven counter NEVER resets the machine (probed 2026-09-29: bare
    KR/PR/RLR drive past the window with machine time flowing -- zero
    MachineReset events, output/fidelity/probe3.log), so the platform
    carries firmware/iwdg_model.cs whose expiry calls
    machine.RequestReset()."""

    def test_both_mains_program_and_kick_the_watchdog(self):
        for name in (os.path.join("twin", "main.c"),
                     os.path.join("race", "main.c")):
            src = _read(FW, name)
            self.assertIn("iwdg_start();", src,
                          f"{name}: IWDG programmed at boot")
            self.assertIn("iwdg_kick();", src,
                          f"{name}: the loop kicks the watchdog")

    def test_expired_watchdog_resets_and_lands_motor_safe(self):
        """A hung loop takes the reset: the CPU is nailed into
        Default_Handler's self-branch (a real hang still EXECUTES, so
        the machine scheduler keeps draining -- cpu Pause would freeze
        the scheduled expiry event with it, probed), the un-kicked
        ~300 ms window expires, the machine resets (MachineReset
        event), and the reboot lands with the drive chain dead --
        decode 0/0."""
        from bot.renode import BOOT_WINDOW_S
        from bot.renode import RenodeChannel
        from pyrenode3.wrappers import Emulation
        from System import Action
        from Antmicro.Renode.Core import IMachine
        from bot.periph import decode_duty_pair
        Emulation().clear()
        ch = RenodeChannel(BALANCE_ELF, 0.005)
        self.addCleanup(ch.emu.clear)
        ch.preset_counter("timer3", 0x8000)
        ch.preset_counter("timer4", 0x8000)
        ch.write_word(BENCH, 0x494D4231)
        ch.write_word(BENCH + 0x04, 1)
        ch.run(BOOT_WINDOW_S)
        ch.write_word(BENCH + 0x04, 2)
        ch.wait_heartbeat(0x2001FFC0 + 0x24, "balance_fw boot")
        for i in range(3, 12):       # a living, kicking loop to hang
            ch.write_word(BENCH + 0x04, i)
            ch.run_period()
        self.assertGreaterEqual(ch.read_word(0x2001FFC0 + 0x24), 5,
                                "boot phase: the loop runs and kicks")

        resets = []
        ch.mach.internal.add_MachineReset(
            Action[IMachine](lambda m: resets.append(1)))
        nm = subprocess.run(["arm-none-eabi-nm", BALANCE_ELF],
                            capture_output=True, text=True).stdout
        spin = next(l.split()[0] for l in nm.splitlines()
                    if l.endswith(" Default_Handler"))
        ch.mon.execute(f"cpu PC 0x{spin}")
        ch.run(0.5)                  # 1.7x the window, nobody kicks
        self.assertGreaterEqual(len(resets), 1,
                                "an un-kicked watchdog must reset the machine")
        ch.run(0.3)                  # the reboot re-runs its inits
        self.assertEqual(decode_duty_pair(ch.read_word), (0, 0),
                         "the rebooted machine lands motor-safe (chain dead)")
        self.assertEqual(ch.read_word(0x2001FFC0), 0x54574E32,
                         "the rebooted firmware restored its status mirror")

    def test_heartbeat_crosses_a_full_watchdog_window(self):
        """KR is write-only in the model (reads 0), so the observable
        gate is survival: run past the ~300 ms IWDG window with the
        sensor stream silent -- a firmware that starved its kicks would
        take the reset and the heartbeat would never reappear."""
        from bot.renode import BOOT_WINDOW_S
        from bot.renode import RenodeChannel
        from pyrenode3.wrappers import Emulation
        Emulation().clear()
        ch = RenodeChannel(BALANCE_ELF, 0.005)
        self.addCleanup(ch.emu.clear)
        ch.preset_counter("timer3", 0x8000)
        ch.preset_counter("timer4", 0x8000)
        ch.write_word(BENCH, 0x494D4231)
        ch.write_word(BENCH + 0x04, 1)
        ch.run(BOOT_WINDOW_S)
        ch.write_word(BENCH + 0x04, 2)
        ch.wait_heartbeat(0x2001FFC0 + 0x24, "balance_fw boot")
        seq0 = ch.read_word(0x2001FFC0 + 0x24)
        ch.run(0.5)                  # 1.7x the IWDG window, no bench data
        self.assertEqual(ch.read_word(0x2001FFC0 + 0x24), seq0,
                         "no watchdog reset across the window: the "
                         "heartbeat is starve-frozen by the firmware's "
                         "own supervision, not zeroed by a reboot "
                         "(probe: output/race-integration/"
                         "iwdg-behavior-probe.log)")
        self.assertEqual(ch.read_word(0x2001FFC0), 0x54574E32,
                         "the status mirror magic survived: the machine "
                         "never rebooted under the programmed IWDG")


class TestReviewRegisterContracts(unittest.TestCase):
    """Static pins for the 2026-09-29 register-contract review
    (output/peripheral-review-20260929/): seven findings against the
    RM0090/cmsis ground truth. The runtime halves live in the peripheral
    suites (RCC readback at 0x400238xx, CC2S=01, the PC0/PC1 nibble,
    valid-zero samples, TIM2EN before CEN)."""

    def test_clock_enables_come_from_the_shared_rcc_header(self):
        for name in ("stm32f4_i2c.c", "stm32f4_encoder.c",
                     "stm32f4_pwm.c", "stm32f4_adc.c"):
            src = _read(FW, name)
            self.assertNotIn("0x40023C", src,
                             f"{name}: 0x40023Cxx is the FLASH controller "
                             "block, not RCC (review finding 1)")
            self.assertIn('include "stm32f4_rcc.h"', src,
                          f"{name}: clock enables must come from the "
                          "shared RCC header, never hand-rolled")

    def test_deadline_clock_enables_tim2_before_counting(self):
        src = _read(FW, "timer_monotonic.c")
        self.assertIn("RCC_APB1ENR |= RCC_APB1ENR_TIM2EN", src,
                      "review finding 2: TIM2 is dead on silicon without "
                      "its APB1 clock enable")
        self.assertLess(src.index("RCC_APB1ENR"),
                        src.index("TIM2_CR1 = 1u"),
                        "the enable must precede CEN")

    def test_elapsed_subtracts_raw_ticks_before_scaling(self):
        src = _read(FW, "timer_monotonic.c")
        self.assertRegex(
            src, r"\(TIM2_CNT - since_ticks\) / TIMER_TICKS_PER_US",
            "review finding 5: scale AFTER the modular subtraction -- "
            "pre-divided operands wrap at 2^28 us instead of 2^32 ticks "
            "(32 us read ~4.0e9 us across the 268 s wrap)")
        self.assertNotIn("timer_us(", src,
                         "no absolute-us API may survive to invite "
                         "pre-divided operands back")

    def test_encoder_maps_ic2_to_ti2(self):
        src = _read(FW, "stm32f4_encoder.c")
        self.assertNotIn("(2u << 8)", src,
                         "review finding 3: CC2S=10 maps IC2 to TI1 too")
        self.assertRegex(src,
                         r"CCMR1_ENCODER \(\(1u << 0\) \| \(1u << 8\)\)",
                         "CC1S=01 + CC2S=01: TI1->IC1, TI2->IC2")

    def test_adc_nibble_belongs_to_pc0_pc1(self):
        src = _read(FW, "stm32f4_adc.c")
        self.assertNotIn("0xF0u", src,
                         "review finding 6: 0xF0 in MODER is PC2/PC3")
        self.assertIn("0x0Fu", src, "PC0/PC1 are the low nibble")
        self.assertIn("RCC_AHB1ENR_GPIOC", src,
                      "GPIOC's own clock enable (was missing)")

    def test_i2c_read_tail_synchronizes_on_btf(self):
        body = _read(FW, "stm32f4_i2c.c").split("i2c1_read_regs", 1)[1]
        self.assertEqual(body.count("SR1_BTF"), 3,
                         "review finding 4: the >=3-byte tail waits BTF "
                         "twice and the 2-byte shape once -- RXNE alone "
                         "can stop one byte early")
        self.assertEqual(body.count("CR1_POS"), 3,
                         "the 2-byte shape moves the NACK via POS per "
                         "the RM sequence, restored on success and in "
                         "the fail cleanup")

    def test_battery_zero_sample_is_not_a_timeout(self):
        self.assertIn("int adc1_read(uint8_t channel, uint16_t *out)",
                      _read(FW, "stm32f4_adc.c"),
                      "review finding 7: conversion status separate "
                      "from the value")
        self.assertNotIn("if (raw == 0)", _read(FW, "battery_bringup.c"),
                         "raw 0 is a valid conversion, not a transport "
                         "failure")


if __name__ == "__main__":
    unittest.main()
