"""The IMU bring-up gate: firmware/imu_bringup.elf drives the real I2C
driver (firmware/stm32f4_i2c.c + mpu6050.c) against the Renode MPU6050
device model, and its observable behavior is pinned here:

  init follows the golden transaction trace (identity first),
  streaming decodes the bench samples word-for-word at the ODR,
  wrong identity fails init before anything is written,
  a dead sample stream times out and recovers,
  the clock/pin contract is WRITTEN AT RUNTIME (not annotated).

Board-side gates are NOT here -- they need silicon; the status labels
for both worlds live in firmware/imu_status.md.
"""
import os
import re
import unittest

REPO = os.path.join(os.path.dirname(__file__), "..")
FW = os.path.join(REPO, "firmware")
IMU_ELF = os.path.join(FW, "imu_bringup.elf")


def _layout():
    """Parse the shared C header so the tests cannot drift from it."""
    text = open(os.path.join(FW, "imu_bringup.h")).read()
    vals = {name: int(v, 16) for name, v in re.findall(
        r"#define\s+(IMU_[A-Z_]+)\s+(0x[0-9A-Fa-f]+)u?", text)}
    cap = re.search(r"#define\s+IMU_TRACE_CAP\s+(\d+)u?", text)
    vals["IMU_TRACE_CAP"] = int(cap.group(1))
    return vals


L = _layout()
BENCH = L["IMU_BENCH_BASE"]
RES = L["IMU_RESULT_BASE"]
TRACE = L["IMU_TRACE_BASE"]

RESULT_MAGIC = 0x52554D49
BENCH_MAGIC = 0x494D4231

# init status codes, firmware/mpu6050.h
MPU_OK, MPU_ERR_I2C, MPU_ERR_WHOAMI = 0, 1, 2

# the golden init transaction trace: (op, reg, val) with op 1=WR 2=RD,
# val = data for WR / length for RD
WR, RD = 1, 2
GOLDEN_TRACE = [
    (RD, 0x75, 1),      # identity check first: nothing before it
    (WR, 0x6B, 0x80),   # DEVICE_RESET
    (RD, 0x6B, 1),      # poll the reset bit clear
    (WR, 0x6B, 0x01),   # wake on gyro PLL
    (WR, 0x6C, 0x00),   # all sensors on
    (WR, 0x19, 0x04),   # SMPLRT_DIV: 200 Hz ODR
    (WR, 0x1A, 0x03),   # CONFIG: DLPF 42 Hz
    (WR, 0x1B, 0x00),   # +-250 dps
    (WR, 0x1C, 0x00),   # +-2 g
    (WR, 0x37, 0x00),   # INT pin: push-pull, active high
    (WR, 0x38, 0x01),   # INT_ENABLE: data ready
    (RD, 0x19, 4),      # config readback verify
]


def _renode_ready():
    from bot.renode import DEFAULT_PORTABLE
    os.environ.setdefault("PYRENODE_PATH", DEFAULT_PORTABLE)
    try:
        import pyrenode3  # noqa: F401
    except Exception as exc:
        return None, f"pyrenode3 not importable ({exc.__class__.__name__}: {exc})"
    if not DEFAULT_PORTABLE or not os.path.isdir(DEFAULT_PORTABLE):
        return None, ("Renode portable not configured "
                      f"(set RENODE_PORTABLE): {DEFAULT_PORTABLE}")
    if not os.path.isfile(IMU_ELF):
        return None, f"{IMU_ELF} missing -- bash firmware/build_imu.sh"
    return True, ""


class TestImuLayout(unittest.TestCase):
    """Static: the three places that must agree on the bench region."""

    def test_bench_address_agrees_across_model_repl_and_header(self):
        model = open(os.path.join(FW, "mpu6050_model.cs")).read()
        m = re.search(r"DefaultBenchAddress = (0x[0-9A-Fa-f]+)", model)
        repl = open(os.path.join(FW, "stm32f407zg.repl")).read()
        r = re.search(r"bench: Memory\.MappedMemory @ sysbus (0x[0-9A-Fa-f]+)",
                      repl)
        self.assertEqual(int(m.group(1), 16), BENCH, "model default bench")
        self.assertEqual(int(r.group(1), 16), BENCH, "repl bench region")
        self.assertEqual(L["IMU_BENCH_MAGIC"], BENCH_MAGIC)


class TestImuBringup(unittest.TestCase):
    """Renode gates for the acquisition path (SIM status labels)."""

    @classmethod
    def setUpClass(cls):
        ready, why = _renode_ready()
        if not ready:
            raise unittest.SkipTest(why)

    def setUp(self):
        from pyrenode3.wrappers import Emulation
        Emulation().clear()    # singleton: outlive any earlier machine
        from bot.renode import RenodeChannel
        self._ch = RenodeChannel(IMU_ELF, 0.005)
        self.sb = self._ch.sysbus

    def tearDown(self):
        self._ch.emu.clear()

    # ---- helpers ----
    def _bench(self, seq, ax=0, ay=16384, az=16384, gx=512, gy=0, gz=0,
               temp=-3920, fi=0):
        self.sb.WriteDoubleWord(BENCH + 0x00, BENCH_MAGIC)
        self.sb.WriteDoubleWord(BENCH + 0x04, seq)
        for i, v in enumerate((ax, ay, az, gx, gy, gz, temp)):
            self.sb.WriteDoubleWord(BENCH + 0x08 + 4 * i, v & 0xFFFFFFFF)
        self.sb.WriteDoubleWord(BENCH + 0x24, fi)

    def _mpu_write(self, reg, val):
        """Inject a device-register write behind the driver's back, the
        master's own II2CPeripheral.Write path."""
        from System import Array, Byte
        mpu = (self._ch.mach.sysbus.get_child("i2c1")
               .get_child("mpu").internal)
        mpu.Write(Array[Byte](bytes([reg, val])))

    def _decoded(self):
        """The last decoded sample (ax ay az temp gx gy gz) as int16s."""
        words = [self.sb.ReadDoubleWord(RES + 0x1C + 4 * i) & 0xFFFF
                 for i in range(7)]
        return [w - 0x10000 if w & 0x8000 else w for w in words]

    def _res(self, i):
        return self.sb.ReadDoubleWord(RES + 4 * i)

    def _stream(self, seq0, n=100):
        for i in range(seq0, seq0 + n):
            self.sb.WriteDoubleWord(BENCH + 0x04, i)
            self._ch.run(0.005)      # 5 ms coupling = the 200 Hz ODR

    def _trace(self):
        count = self.sb.ReadDoubleWord(TRACE)
        entries = []
        for i in range(count):
            e = self.sb.ReadDoubleWord(TRACE + 8 + 4 * i)
            entries.append(((e >> 24) & 0xFF, (e >> 16) & 0xFF, e & 0xFFFF))
        return entries

    # ---- the gates ----
    def test_init_matches_the_golden_transaction_trace(self):
        self._bench(1)
        self._ch.run(0.1)
        self.assertEqual(self._res(0), RESULT_MAGIC, "results magic")
        self.assertEqual(self._res(1), MPU_OK,
                         "clean bench must bring the device up")
        self.assertEqual(self._trace(), GOLDEN_TRACE,
                         "init transactions must match the RM sequence")

    def test_streaming_decodes_the_bench_word_for_word(self):
        self._bench(1)
        self._stream(2, 100)
        self.assertGreater(self._res(3), 50, "streaming at ~200 Hz")
        self.assertEqual(self._res(4), 0, "no data-ready timeouts")
        self.assertEqual(self._res(2), 0, "no i2c errors")
        self.assertEqual(self._res(5), 0, "no recoveries needed")
        expected = [0, 16384, 16384, (-3920) & 0xFFFFFFFF, 512, 0, 0]
        got = [self.sb.ReadDoubleWord(RES + 0x1C + 4 * i) for i in range(7)]
        self.assertEqual(got, expected,
                         "decoded accel/temp/gyro must equal the bench "
                         "(coherent burst, big-endian pairs)")
        self.assertEqual(self.sb.ReadDoubleWord(0x2001FFB8), 0,
                         "no fault along the way")

    def test_wrong_identity_fails_init_before_anything_is_written(self):
        self._bench(1, fi=0x72)     # a device answering 0x72 (MPU9250)
        self._ch.run(0.1)
        self.assertEqual(self._res(1), MPU_ERR_WHOAMI,
                         "identity mismatch must be reported")
        self.assertEqual(self._res(3), 0, "no samples from a wrong device")
        trace = self._trace()
        self.assertEqual(trace, [(RD, 0x75, 1)],
                         "identity check first: the trace must hold ONLY "
                         "the WHO_AM_I read")

    def test_identity_recovery_once_the_right_device_appears(self):
        self._bench(1, fi=0x72)
        self._ch.run(0.1)
        self.assertEqual(self._res(1), MPU_ERR_WHOAMI)
        self._bench(2, fi=0)        # the right device appears
        self._stream(3, 60)
        self.assertEqual(self._res(1), MPU_OK,
                         "the retry loop must acquire the device")
        self.assertGreater(self._res(3), 30, "streaming after recovery")

    def test_data_ready_timeout_and_recovery(self):
        self._bench(1)
        self._stream(2, 80)
        base_samples = self._res(3)
        self.assertGreater(base_samples, 40)
        # the sensor stops updating: data-ready never comes
        self.sb.WriteDoubleWord(BENCH + 0x24, 0x100)
        self._ch.run(0.5)
        self.assertGreater(self._res(4), 0, "data-ready timeout counted")
        self.assertGreater(self._res(5), 0, "recovery re-inits attempted")
        # updates resume: the stream must come back on its own
        self.sb.WriteDoubleWord(BENCH + 0x24, 0)
        self._stream(500, 60)
        self.assertGreater(self._res(3), base_samples,
                           "streaming resumes after the outage")

    def test_gyro_range_registers_rescale_latched_samples(self):
        """A wrong FS_SEL must yield wrong physicals, not silent luck:
        the bench speaks the +-250 dps domain, the latched sample carries
        the full-scale GYRO_CONFIG selects (RM-MPU-6000A section 4.1),
        and the driver still converts with its own +-250 constant -- the
        mismatch shrinks the reading, exactly like silicon."""
        self._bench(1, gx=-1024)
        self._stream(2, 30)
        self.assertEqual(self._decoded()[4], -1024,
                         "matching config round-trips the bench word")
        self._mpu_write(0x1B, 0x18)          # FS_SEL=3: +-2000 dps
        self._stream(100, 30)
        dec = self._decoded()
        self.assertEqual(dec[4], -128,
                         "FS_SEL=3 divides the gyro sample by 8, sign kept")
        self.assertEqual(dec[1], 16384,
                         "a gyro range must not touch the accel axes")
        self._mpu_write(0x1B, 0x00)          # back to +-250 dps
        self._stream(200, 30)
        self.assertEqual(self._decoded()[4], -1024)

    def test_accel_range_registers_rescale_latched_samples(self):
        """Same contract on AFS_SEL (RM-MPU-6000A section 4.2); the
        temperature register is not a scaled axis."""
        self._bench(1)
        self._stream(2, 30)
        self.assertEqual(self._decoded()[1], 16384)
        self._mpu_write(0x1C, 0x10)          # AFS_SEL=2: +-8 g
        self._stream(100, 30)
        dec = self._decoded()
        self.assertEqual(dec[1], 4096, "AFS_SEL=2 divides the accel by 4")
        self.assertEqual(dec[4], 512,
                         "an accel range must not touch the gyro axes")
        self.assertEqual(dec[3], -3920, "temp is not scaled")

    def test_device_reset_restores_default_scaling(self):
        """DEVICE_RESET clears the config registers to power-up defaults,
        so the rescale factor is register-sourced, never sticky: after a
        reset behind the driver's back the data-ready source dies, the
        recovery loop re-inits, and the sample is whole again."""
        self._bench(1, gx=-1024)
        self._stream(2, 30)
        self._mpu_write(0x1B, 0x18)          # FS_SEL=3
        self._stream(100, 30)
        self.assertEqual(self._decoded()[4], -128)
        self._mpu_write(0x6B, 0x80)          # DEVICE_RESET
        self._ch.run(0.5)          # data-ready timeout -> recovery re-init
        self._stream(500, 60)
        self.assertGreater(self._res(5), 0, "the recovery loop re-inited")
        self.assertEqual(self._decoded()[4], -1024,
                         "default range restored by the reset")

    def test_address_nack_fails_the_driver_and_recovers(self):
        """The controller NACKs (SR1.AF, 0x400) an address with no
        device -- probed 2026-09-29 on the stock controller. Renode's
        Unregister does not reroute an attached device and SR1 writes
        are ignored (output/i2c-nack/probe.log), so the harness arms
        the same AF through the controller wrapper: the driver must
        abort with NACK, the firmware must report MPU_ERR_I2C and stop
        sampling, and both must recover once the bus is healthy."""
        self._bench(1)
        self._stream(2, 30)
        base = self._res(3)
        self.assertGreater(base, 0, "streaming must be established")
        i2c = self._ch.mach.sysbus.get_child("i2c1").internal
        i2c.NackArmed = True
        self._stream(100, 20)
        self.assertEqual(self._res(1), MPU_ERR_I2C,
                         "init must report the bus failure")
        self.assertGreater(self._res(2), 0,
                           "the in-flight sample read counted an I2C error")
        self.assertEqual(self._res(3), base, "no samples from a dead bus")
        self.assertGreater(self._res(5), 0, "recovery attempts counted")
        i2c.NackArmed = False
        self._stream(300, 60)
        self.assertEqual(self._res(1), MPU_OK, "a healthy bus re-inits")
        self.assertGreater(self._res(3), base, "streaming resumes")

    def test_clock_and_pin_contract_is_written_at_runtime(self):
        """The review's rule: annotations do not enforce -- after boot the
        GPIO/I2C registers must SHOW the driver's configuration, and the
        RCC enables must sit in the model at the real 0x400238xx base
        (the 2026-09-29 review round corrected the old "RCC stores
        nothing" probe, which had hit the FLASH controller block).
        What stays board-only: the gating EFFECT and the unmodeled
        fields -- OTYPER, CCR/TRISE -- per firmware/imu_status.md."""
        self._bench(1)
        self._ch.run(0.1)
        rcc = 0x40023800
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x30) & 0x2, 0x2,
                         "AHB1ENR.GPIOBEN")
        self.assertEqual(self.sb.ReadDoubleWord(rcc + 0x40) & 0x200001,
                         0x200001,
                         "APB1ENR.I2C1EN + TIM2EN (the deadline clock)")
        gpiob = 0x40020400
        moder = self.sb.ReadDoubleWord(gpiob)
        self.assertEqual((moder >> 12) & 0xF, 0xA, "PB6/PB7 alternate mode")
        pupdr = self.sb.ReadDoubleWord(gpiob + 0xC)
        self.assertEqual((pupdr >> 12) & 0xF, 0x5, "pull-ups on SCL/SDA")
        afrl = self.sb.ReadDoubleWord(gpiob + 0x20)
        self.assertEqual((afrl >> 24) & 0xFF, 0x44, "AF4 on PB6/PB7")
        # OTYPER (open-drain) is board-only too: Renode's GPIO port does
        # not store it (probed 2026-09-29, gpioprobe)
        i2c1 = 0x40005400
        self.assertEqual(self.sb.ReadDoubleWord(i2c1 + 0x04) & 0x3F, 16,
                         "CR2.FREQ = the 16 MHz HSI tree")
        self.assertEqual(self.sb.ReadDoubleWord(i2c1) & 0x1, 0x1,
                         "CR1.PE: peripheral enabled")
        # Renode's STM32F1_I2C has no CCR/TRISE registers (reads return 0;
        # probed 2026-09-29) -- the timing contract is asserted on the
        # board, see firmware/imu_status.md


if __name__ == "__main__":
    unittest.main()
