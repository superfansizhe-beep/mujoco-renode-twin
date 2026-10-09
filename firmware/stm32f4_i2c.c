#include <stdint.h>

#include "stm32f4_i2c.h"
#include "stm32f4_rcc.h"
#include "timer_monotonic.h"

#define I2C1_BASE 0x40005400u
#define I2C1_CR1  (*(volatile uint32_t *)(I2C1_BASE + 0x00))
#define I2C1_CR2  (*(volatile uint32_t *)(I2C1_BASE + 0x04))
#define I2C1_OAR1 (*(volatile uint32_t *)(I2C1_BASE + 0x08))
#define I2C1_DR   (*(volatile uint32_t *)(I2C1_BASE + 0x10))
#define I2C1_SR1  (*(volatile uint32_t *)(I2C1_BASE + 0x14))
#define I2C1_SR2  (*(volatile uint32_t *)(I2C1_BASE + 0x18))
#define I2C1_CCR  (*(volatile uint32_t *)(I2C1_BASE + 0x1C))
#define I2C1_TRISE (*(volatile uint32_t *)(I2C1_BASE + 0x20))

/* GPIOB: SCL=PB6, SDA=PB7, AF4 */
#define GPIOB_BASE 0x40020400u
#define GPIOB_MODER  (*(volatile uint32_t *)(GPIOB_BASE + 0x00))
#define GPIOB_OTYPER (*(volatile uint32_t *)(GPIOB_BASE + 0x04))
#define GPIOB_OSPEEDR (*(volatile uint32_t *)(GPIOB_BASE + 0x08))
#define GPIOB_PUPDR  (*(volatile uint32_t *)(GPIOB_BASE + 0x0C))
#define GPIOB_AFRL   (*(volatile uint32_t *)(GPIOB_BASE + 0x20))

/* CR1 */
#define CR1_PE    (1u << 0)
#define CR1_START (1u << 8)
#define CR1_STOP  (1u << 9)
#define CR1_ACK   (1u << 10)
#define CR1_POS   (1u << 15)
/* SR1 */
#define SR1_SB    (1u << 0)
#define SR1_ADDR  (1u << 1)
#define SR1_BTF   (1u << 2)
#define SR1_RXNE  (1u << 6)
#define SR1_TXE   (1u << 7)
#define SR1_AF    (1u << 10)
/* CR2 FREQ is the APB1 clock in MHz: the HSI reset tree is 16 MHz */
#define CR2_FREQ_MHZ 16u
/* 100 kHz standard mode: CCR = Fpclk / (2 * 100 kHz) = 80; TRISE = Fpclk/1MHz + 1 */
#define CCR_STANDARD_100K 80u
#define TRISE_16MHZ 17u

static i2c_status_t wait_sr1(uint32_t mask, uint32_t timeout_us)
{
    uint32_t t0 = timer_ticks();
    for (;;) {
        uint32_t sr1 = I2C1_SR1;
        if (sr1 & SR1_AF) {
            I2C1_SR1 = ~SR1_AF;          /* AF clears on a zero write */
            I2C1_CR1 |= CR1_STOP;
            return I2C_ERR_NACK;
        }
        if (sr1 & mask)
            return I2C_OK;
        if (timer_elapsed_us(t0) >= timeout_us)
            return I2C_ERR_TIMEOUT;
    }
}

void i2c1_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOB;
    RCC_APB1ENR |= RCC_APB1ENR_I2C1EN;
    /* PB6/PB7: alternate function, open-drain, pull-up, high speed */
    GPIOB_MODER = (GPIOB_MODER & ~0xF000u) | 0xA000u;   /* 10 AF */
    GPIOB_OTYPER |= (1u << 6) | (1u << 7);
    GPIOB_OSPEEDR |= 0xF000u;
    GPIOB_PUPDR = (GPIOB_PUPDR & ~0xF000u) | 0x5000u;   /* 01 pull-up */
    GPIOB_AFRL = (GPIOB_AFRL & ~0xFF000000u) | 0x44000000u;  /* AF4 both */

    I2C1_CR1 = 0;                        /* stay in reset while timing */
    I2C1_CR2 = CR2_FREQ_MHZ;
    I2C1_OAR1 = 0;
    I2C1_CCR = CCR_STANDARD_100K;
    I2C1_TRISE = TRISE_16MHZ;
    I2C1_CR1 = CR1_PE | CR1_ACK;
}

/* Short first window for the START dead-detection below; silicon
 * raises SB within a few SCL bit times (~30 us at 100 kHz), so this
 * only ever elapses in the simulator. */
#define START_RETRY_WINDOW_US 500u

static i2c_status_t start_addr(uint8_t dev_addr, uint8_t rw, uint32_t timeout_us)
{
    /* No STOP-pending wait here, even though the F1 reference manual
     * advises it: Renode's controller keeps CR1.STOP readable-set after
     * a receiver transaction forever (probed 2026-09-29, sticky.log),
     * while back-to-back transactions work on both targets. Single
     * master + polled pacing makes the race the manual warns about
     * unreachable. */
    I2C1_CR1 |= CR1_START;
    i2c_status_t st = wait_sr1(SR1_SB, START_RETRY_WINDOW_US);
    if (st == I2C_ERR_TIMEOUT) {
        /* Renode 1.17's controller can swallow the first START after a
         * receiver transaction's STOP (probed 2026-09-29, seq.log):
         * CR1 shows START set but SB never comes until START is
         * re-issued. Silicon generates SB immediately, so this path is
         * simulation-only; one re-issue, then the full deadline. */
        I2C1_CR1 &= ~CR1_START;
        I2C1_CR1 |= CR1_START;
        st = wait_sr1(SR1_SB, timeout_us);
    }
    if (st) return st;
    I2C1_DR = (uint32_t)(dev_addr << 1) | rw;
    st = wait_sr1(SR1_ADDR, timeout_us);
    if (st) return st;
    (void)I2C1_SR1; (void)I2C1_SR2;      /* ADDR clears on the SR1+SR2 read */
    return I2C_OK;
}

i2c_status_t i2c1_write_regs(uint8_t dev_addr, uint8_t reg,
                             const uint8_t *vals, uint32_t len,
                             uint32_t timeout_us)
{
    i2c_status_t st = start_addr(dev_addr, 0, timeout_us);
    if (st) return st;
    I2C1_DR = reg;
    st = wait_sr1(SR1_TXE, timeout_us);
    if (st) return st;
    for (uint32_t i = 0; i < len; i++) {
        I2C1_DR = vals[i];
        if (i + 1 < len) {
            st = wait_sr1(SR1_TXE, timeout_us);
            if (st) return st;
        }
    }
    st = wait_sr1(SR1_BTF, timeout_us);  /* last byte fully shifted out */
    if (st) return st;
    I2C1_CR1 |= CR1_STOP;
    return I2C_OK;
}

i2c_status_t i2c1_read_regs(uint8_t dev_addr, uint8_t reg,
                            uint8_t *out, uint32_t len, uint32_t timeout_us)
{
    /* pointer set + STOP: Renode commits a write transaction on STOP,
     * and stop-between is legal on the real bus too (no repeated start
     * needed for a single-master poller) */
    i2c_status_t st = i2c1_write_regs(dev_addr, reg, out, 0, timeout_us);
    if (st) return st;

    /* RM0090 master receiver: the NACK/STOP choreography differs by
     * length. Deciding on RXNE alone in the tail can stop one byte
     * early and truncate the transfer (review 2026-09-29, finding 4);
     * the last stretch is gated on BTF (DR + shift register both full)
     * exactly as the RM flowchart and ST's HAL sequence it. */
    if (len == 1) {
        I2C1_CR1 &= ~CR1_ACK;            /* NACK the only byte before ADDR */
        st = start_addr(dev_addr, 1, timeout_us);
        if (st) goto fail;
        st = wait_sr1(SR1_RXNE, timeout_us);
        if (st) goto fail;
        I2C1_CR1 |= CR1_STOP;
        out[0] = (uint8_t)I2C1_DR;
        return I2C_OK;
    }
    if (len == 2) {
        /* POS moves the NACK one byte earlier: clearing ACK after ADDR
         * now NACKs the FIRST byte of the pair */
        I2C1_CR1 |= CR1_POS | CR1_ACK;
        st = start_addr(dev_addr, 1, timeout_us);
        if (st) goto fail;
        I2C1_CR1 &= ~CR1_ACK;
        st = wait_sr1(SR1_BTF, timeout_us);
        if (st) goto fail;
        I2C1_CR1 |= CR1_STOP;
        out[0] = (uint8_t)I2C1_DR;
        out[1] = (uint8_t)I2C1_DR;
        I2C1_CR1 &= ~CR1_POS;
        return I2C_OK;
    }
    I2C1_CR1 |= CR1_ACK;
    st = start_addr(dev_addr, 1, timeout_us);
    if (st) goto fail;
    for (uint32_t i = 0; i + 3 < len; i++) {
        st = wait_sr1(SR1_RXNE, timeout_us);
        if (st) goto fail;
        out[i] = (uint8_t)I2C1_DR;
    }
    st = wait_sr1(SR1_BTF, timeout_us);  /* N-2 in DR, N-1 in shift */
    if (st) goto fail;
    I2C1_CR1 &= ~CR1_ACK;                /* NACK the final byte */
    out[len - 3] = (uint8_t)I2C1_DR;
    st = wait_sr1(SR1_BTF, timeout_us);  /* N-1 in DR, N in shift */
    if (st) goto fail;
    I2C1_CR1 |= CR1_STOP;
    out[len - 2] = (uint8_t)I2C1_DR;
    out[len - 1] = (uint8_t)I2C1_DR;
    return I2C_OK;

fail:
    I2C1_CR1 &= ~CR1_POS;                /* bounded cleanup: free the bus,
                                          * leave ACK armed for next time */
    I2C1_CR1 |= CR1_STOP;
    return st;
}
