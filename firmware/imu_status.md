# IMU bring-up status -- SIM vs BOARD

One driver pair (firmware/stm32f4_i2c.c + firmware/mpu6050.c), one
bring-up ELF (firmware/imu_bringup.c), two verification worlds. The
labels below are the milestone contract: nothing may move from
PENDING to verified except through its named gate.

## SIM -- verified (tests/test_firmware_imu.py, Renode 1.17.0)

| gate | test |
| --- | --- |
| init matches the golden RM sequence, identity read first | `test_init_matches_the_golden_transaction_trace` |
| streaming decodes accel/temp/gyro word-for-word at 200 Hz | `test_streaming_decodes_the_bench_word_for_word` |
| wrong identity (0x72) fails init before any config write | `test_wrong_identity_fails_init_before_anything_is_written` |
| identity recovery once the right device appears | `test_identity_recovery_once_the_right_device_appears` |
| data-ready outage -> timeout + re-init -> self-recovery | `test_data_ready_timeout_and_recovery` |
| GYRO_CONFIG FS_SEL rescales the latched sample (wrong range -> wrong physicals; RM-MPU-6000A 4.1) | `test_gyro_range_registers_rescale_latched_samples` |
| ACCEL_CONFIG AFS_SEL rescales accel only; temp unscaled (4.2) | `test_accel_range_registers_rescale_latched_samples` |
| DEVICE_RESET restores the default ranges via the config registers | `test_device_reset_restores_default_scaling` |
| address NACK (SR1.AF, armed on the controller wrapper -- Unregister does not reroute and SR1 writes are ignored, output/i2c-nack/probe.log) aborts the driver, reports MPU_ERR_I2C, freezes sampling, recovers when disarmed | `test_address_nack_fails_the_driver_and_recovers` |
| GPIO mode/pull/AF4, I2C CR2/PE, and the RCC clock enables (GPIOBEN, I2C1EN, TIM2EN at 0x400238xx) read back at runtime | `test_clock_and_pin_contract_is_written_at_runtime` |

## BOARD -- pending hardware (procedure for the on-arrival day)

| gate | procedure |
| --- | --- |
| clock gating effect | [rcc_status.md](rcc_status.md) covers missing GPIOB/I2C1/TIM2 enables in SIM; on the board verify a from-reset boot streams samples, including enable propagation delay and real clock timing |
| open-drain SCL/SDA | GPIOB OTYPER bits 6/7 read back as set -- Renode's GPIO port does not store OTYPER (probed 2026-09-29) |
| identity | AD0=GND breakout at 0x68 answers WHO_AM_I=0x68; init reports OK in the results block |
| init trace identical to the sim golden | flash imu_bringup.elf, halt, dump the trace ring at 0x2001F080 (SWD); byte-diff vs GOLDEN_TRACE in tests/test_firmware_imu.py |
| streaming decode | known orientation (flat: az=+1 g, temp ~ambient) matches the results block; CCR=80/TRISE=17 read back (Renode does not model them) |
| wrong-address/NACK path | SIM gates the driver/firmware AF branches (above) through the controller wrapper; the physical layer -- a pulled SDA, a dead module, real line capacitance -- stays board: unplug SDA, init must report ERR_I2C within the deadline, recover on replug |
| electrical pin contract | SCL=PB6, SDA=PB7 AF4 open-drain pull-up, 3.3 V -- confirm against the breakout pinout when it arrives |

Sim limits this milestone accepted (probes in output/imu-milestone/):
Renode commits writes at STOP, needs I2CReadCount up front (harness
pins a 32-byte over-fetch), keeps STOP readable-set after receiver
transactions, and can swallow the first START after a receiver -- the
driver carries exactly one bounded re-issue for the last one, which
silicon never triggers (SB latency there is microseconds).
