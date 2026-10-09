/* imu_bringup: prove MPU6050 acquisition through the real I2C driver.
 *
 * Boots, configures I2C1 + the MPU6050 through firmware/mpu6050.c,
 * logs the init transactions to a fixed SRAM trace ring, then streams
 * samples: every successful read updates the results block, every
 * failure counts and triggers one re-init attempt (same philosophy as
 * the balance firmware's starvation supervision: degrade to safe,
 * re-acquire, keep going). No motors are touched anywhere -- that is
 * deliberate for this milestone.
 *
 * The results block (firmware/imu_bringup.h) is the contract with the
 * Python gates: same addresses on the board, read back through a
 * debugger there (status labels: firmware/imu_status.md).
 */
#include <stdint.h>

#include "imu_bringup.h"
#include "mpu6050.h"
#include "stm32f4_i2c.h"
#include "timer_monotonic.h"

#define REG32(addr) (*(volatile uint32_t *)(addr))

/* results block (firmware -> harness) */
#define RES_MAGIC    REG32(IMU_RESULT_BASE + 0x00)
#define RES_INIT     REG32(IMU_RESULT_BASE + 0x04)
#define RES_I2C_ERRS REG32(IMU_RESULT_BASE + 0x08)
#define RES_SAMPLES  REG32(IMU_RESULT_BASE + 0x0C)
#define RES_TIMEOUTS REG32(IMU_RESULT_BASE + 0x10)
#define RES_RECOVERS REG32(IMU_RESULT_BASE + 0x14)
#define RES_WHOAMI   REG32(IMU_RESULT_BASE + 0x18)
/* last sample: 7 x int32 raw at +0x1C..+0x38 */
#define RES_SAMPLE(i) REG32(IMU_RESULT_BASE + 0x1C + 4 * (i))

/* trace ring (firmware -> harness): count, dropped, then entries
 * op<<24 | reg<<16 | val; records the FIRST init attempt only */
#define TR_COUNT   REG32(IMU_TRACE_BASE + 0x00)
#define TR_DROPPED REG32(IMU_TRACE_BASE + 0x04)
#define TR_ENTRY(i) REG32(IMU_TRACE_BASE + 0x08 + 4 * ((i) % IMU_TRACE_CAP))

#define RESULT_MAGIC 0x52554D49u        /* "IMUR" little-endian */
#define STREAM_READ_TIMEOUT_US 100000u  /* >> the 5 ms ODR period */

static uint8_t trace_on = 0;

void mpu_trace(uint8_t op, uint8_t reg, uint8_t val)
{
    if (!trace_on)
        return;
    uint32_t n = TR_COUNT;
    if (n - TR_DROPPED >= IMU_TRACE_CAP) {
        TR_DROPPED++;
    }
    TR_ENTRY(n) = ((uint32_t)op << 24) | ((uint32_t)reg << 16) | val;
    TR_COUNT = n + 1;
}

int main(void)
{
    timer_monotonic_start();
    RES_MAGIC = RESULT_MAGIC;
    RES_INIT = 0xFFFFFFFFu;
    RES_I2C_ERRS = 0;
    RES_SAMPLES = 0;
    RES_TIMEOUTS = 0;
    RES_RECOVERS = 0;
    TR_COUNT = 0;
    TR_DROPPED = 0;

    i2c1_init();

    /* first init is the golden transaction trace; retries stay unlogged */
    trace_on = 1;
    mpu_status_t st = mpu6050_init(MPU_ADDR_GND);
    trace_on = 0;

    for (;;) {
        if (st != MPU_OK) {
            RES_INIT = st;
            RES_RECOVERS++;
            st = mpu6050_init(MPU_ADDR_GND);   /* wait out the failure */
            continue;
        }
        RES_INIT = MPU_OK;

        mpu_sample_t s;
        mpu_status_t rst = mpu6050_read(MPU_ADDR_GND, &s,
                                        STREAM_READ_TIMEOUT_US);
        if (rst == MPU_OK) {
            RES_SAMPLES++;
            RES_SAMPLE(0) = s.ax;  RES_SAMPLE(1) = s.ay;
            RES_SAMPLE(2) = s.az;  RES_SAMPLE(3) = s.temp_raw;
            RES_SAMPLE(4) = s.gx;  RES_SAMPLE(5) = s.gy;
            RES_SAMPLE(6) = s.gz;
            continue;
        }
        if (rst == MPU_ERR_TIMEOUT) {
            RES_TIMEOUTS++;
        } else {
            RES_I2C_ERRS++;
        }
        /* degraded: re-acquire, same discipline as the balance
         * firmware's starvation supervision */
        RES_RECOVERS++;
        st = mpu6050_init(MPU_ADDR_GND);
    }
}
