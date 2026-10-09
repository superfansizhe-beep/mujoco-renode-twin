/* I2C1 master, polled -- the F4 peripheral is the same IP block as F1,
 * which is exactly what Renode models (I2C.STM32F1_I2C). One code path
 * for the twin and the board.
 *
 * Pin contract (our allocation, board layout pending the motor-driver
 * module): SCL=PB6, SDA=PB7, both AF4 open-drain with pull-ups,
 * 100 kHz standard mode from the 16 MHz HSI tree.
 *
 * Sim limits (kept visible, from the probes in
 * output/imu-milestone/): Renode's controller delivers a WRITE
 * transaction to the device when it sees STOP, serves the RECEIVER
 * from a pre-fetched count (the harness pins I2CReadCount), and sets
 * SB/ADDR/RXNE/AF on virtual time -- which the polling waits below
 * consume anyway. An address with no device sets AF like the real
 * peripheral, so NACK paths are testable in sim.
 */
#ifndef STM32F4_I2C_H
#define STM32F4_I2C_H

#include <stdint.h>

typedef enum {
    I2C_OK = 0,
    I2C_ERR_TIMEOUT = 1,   /* a polled flag never came within the deadline */
    I2C_ERR_NACK = 2,      /* AF: address not acknowledged (no device) */
} i2c_status_t;

/* RCC enables + PB6/PB7 AF4 + 100 kHz timing from the 16 MHz tree */
void i2c1_init(void);

i2c_status_t i2c1_write_regs(uint8_t dev_addr, uint8_t reg,
                             const uint8_t *vals, uint32_t len,
                             uint32_t timeout_us);
i2c_status_t i2c1_read_regs(uint8_t dev_addr, uint8_t reg,
                            uint8_t *out, uint32_t len, uint32_t timeout_us);

#endif /* STM32F4_I2C_H */
