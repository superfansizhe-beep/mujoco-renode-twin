#include <stdint.h>

#include "mpu6050.h"
#include "stm32f4_i2c.h"
#include "timer_monotonic.h"

/* register map, InvenSense RM-MPU-6000A */
#define SMPLRT_DIV  0x19u
#define CONFIG      0x1Au
#define GYRO_CONFIG 0x1Bu
#define ACCEL_CONFIG 0x1Cu
#define INT_PIN_CFG 0x37u
#define INT_ENABLE  0x38u
#define INT_STATUS  0x3Au
#define ACCEL_XOUT0 0x3Bu          /* 14 bytes: accel xyz, temp, gyro xyz */
#define PWR_MGMT_1  0x6Bu          /* bit7 reset, bit6 sleep, bits2:0 clksel */
#define PWR_MGMT_2  0x6Cu
#define WHO_AM_I    0x75u
#define WHO_AM_I_68 0x68u

/* bring-up configuration: 200 Hz ODR (1 kHz / (div+1)), DLPF 42 Hz,
 * +-2 g / +-250 dps */
#define CFG_SMPLRT_DIV   0x04u
#define CFG_DLPF_42HZ    0x03u
#define CFG_RANGE_250    0x00u
#define CFG_RANGE_2G     0x00u
#define CFG_WAKE_PLL     0x01u
#define CFG_INT_DATA_READY 0x01u

#define FLAG_WAIT_US 10000u         /* per-flag transport deadline */
#define RESET_POLL_US 1000u         /* DEVICE_RESET clears in ~100 ms on silicon */

/* trace ops */
#define MPU_TR_WR 1u                /* register write: val = data */
#define MPU_TR_RD 2u                /* read start: reg, val = length */

__attribute__((weak))
void mpu_trace(uint8_t op, uint8_t reg, uint8_t val)
{
    (void)op; (void)reg; (void)val;
}

static mpu_status_t write_reg(uint8_t dev_addr, uint8_t reg, uint8_t val)
{
    i2c_status_t st = i2c1_write_regs(dev_addr, reg, &val, 1, FLAG_WAIT_US);
    mpu_trace(MPU_TR_WR, reg, val);
    if (st) return MPU_ERR_I2C;
    return MPU_OK;
}

static mpu_status_t read_regs(uint8_t dev_addr, uint8_t reg,
                              uint8_t *out, uint32_t len)
{
    i2c_status_t st = i2c1_read_regs(dev_addr, reg, out, len, FLAG_WAIT_US);
    mpu_trace(MPU_TR_RD, reg, (uint8_t)len);
    if (st) return MPU_ERR_I2C;
    return MPU_OK;
}

mpu_status_t mpu6050_init(uint8_t dev_addr)
{
    /* identity first: a wrong device must not be reset by us */
    uint8_t who = 0;
    mpu_status_t st = read_regs(dev_addr, WHO_AM_I, &who, 1);
    if (st) return st;
    if (who != WHO_AM_I_68) return MPU_ERR_WHOAMI;

    /* reset, then wait for the bit to self-clear (immediate in sim) */
    st = write_reg(dev_addr, PWR_MGMT_1, 0x80u);
    if (st) return st;
    uint32_t t0 = timer_ticks();
    for (;;) {
        st = read_regs(dev_addr, PWR_MGMT_1, &who, 1);
        if (st) return st;
        if ((who & 0x80u) == 0) break;
        if (timer_elapsed_us(t0) >= 200000u) return MPU_ERR_TIMEOUT;
    }

    /* wake on the gyro PLL, all sensors on */
    st = write_reg(dev_addr, PWR_MGMT_1, CFG_WAKE_PLL);
    if (st) return st;
    st = write_reg(dev_addr, PWR_MGMT_2, 0x00u);
    if (st) return st;

    /* sample plan + ranges + data-ready interrupt status */
    st = write_reg(dev_addr, SMPLRT_DIV, CFG_SMPLRT_DIV);
    if (st) return st;
    st = write_reg(dev_addr, CONFIG, CFG_DLPF_42HZ);
    if (st) return st;
    st = write_reg(dev_addr, GYRO_CONFIG, CFG_RANGE_250);
    if (st) return st;
    st = write_reg(dev_addr, ACCEL_CONFIG, CFG_RANGE_2G);
    if (st) return st;
    st = write_reg(dev_addr, INT_PIN_CFG, 0x00u);
    if (st) return st;
    st = write_reg(dev_addr, INT_ENABLE, CFG_INT_DATA_READY);
    if (st) return st;

    /* readback: the config must be on the device, not just on the bus */
    uint8_t rb[4];
    st = read_regs(dev_addr, SMPLRT_DIV, rb, 4);
    if (st) return st;
    if (rb[0] != CFG_SMPLRT_DIV || rb[1] != CFG_DLPF_42HZ
            || rb[2] != CFG_RANGE_250 || rb[3] != CFG_RANGE_2G)
        return MPU_ERR_CONFIG;
    return MPU_OK;
}

mpu_status_t mpu6050_read(uint8_t dev_addr, mpu_sample_t *out,
                          uint32_t timeout_us)
{
    /* data-ready by polling INT_STATUS: a fresh sample sets bit0 (when
     * INT_ENABLE has it armed); the bit clears on read */
    uint32_t t0 = timer_ticks();
    for (;;) {
        uint8_t st_reg = 0;
        mpu_status_t st = read_regs(dev_addr, INT_STATUS, &st_reg, 1);
        if (st) return st;
        if (st_reg & 0x01u) break;
        if (timer_elapsed_us(t0) >= timeout_us) return MPU_ERR_TIMEOUT;
    }

    uint8_t raw[14];
    mpu_status_t st = read_regs(dev_addr, ACCEL_XOUT0, raw, 14);
    if (st) return st;
    uint8_t *p = raw;
    out->ax = (int16_t)((p[0] << 8) | p[1]);
    out->ay = (int16_t)((p[2] << 8) | p[3]);
    out->az = (int16_t)((p[4] << 8) | p[5]);
    out->temp_raw = (int16_t)((p[6] << 8) | p[7]);
    out->gx = (int16_t)((p[8] << 8) | p[9]);
    out->gy = (int16_t)((p[10] << 8) | p[11]);
    out->gz = (int16_t)((p[12] << 8) | p[13]);
    return MPU_OK;
}

float mpu6050_temp_c(int16_t raw)
{
    return (float)raw / 340.0f + 36.53f;
}
