/* MPU6050 IMU driver -- register-level, on top of stm32f4_i2c.
 *
 * Data-ready is observed by polling INT_STATUS bit0, the same register
 * a real board can read whether or not the INT pin is routed to EXTI;
 * this keeps one bring-up path for both worlds. The driver never talks
 * to motors -- this milestone proves the acquisition path only.
 *
 * SIM/BOARD status labels live in firmware/imu_status.md; the gate
 * list is tests/test_firmware_imu.py.
 */
#ifndef MPU6050_H
#define MPU6050_H

#include <stdint.h>

#define MPU_ADDR_GND 0x68u      /* AD0 = GND on the breakout */

typedef struct {
    int16_t ax, ay, az;
    int16_t temp_raw;           /* degC = raw/340 + 36.53 */
    int16_t gx, gy, gz;
} mpu_sample_t;

typedef enum {
    MPU_OK = 0,
    MPU_ERR_I2C = 1,            /* transport: NACK or flag timeout */
    MPU_ERR_WHOAMI = 2,         /* identity mismatch (wrong device/address) */
    MPU_ERR_CONFIG = 3,         /* readback disagrees with what was written */
    MPU_ERR_TIMEOUT = 4,        /* data-ready never came */
} mpu_status_t;

/* identification + reset/wake + ranges/DLPF/rate + readback verify;
 * transaction log goes through mpu_trace() */
mpu_status_t mpu6050_init(uint8_t dev_addr);

/* poll data-ready (<= timeout_us), then one coherent 14-byte burst */
mpu_status_t mpu6050_read(uint8_t dev_addr, mpu_sample_t *out,
                          uint32_t timeout_us);

/* weak: apps override to log (op, reg, val) transactions; the bring-up
 * app records the init sequence where the harness (and later, a
 * debugger on the real board) can compare it against the golden list */
void mpu_trace(uint8_t op, uint8_t reg, uint8_t val);

float mpu6050_temp_c(int16_t raw);

#endif /* MPU6050_H */
