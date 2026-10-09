#include <stdint.h>

#include "stm32f4_adc.h"
#include "stm32f4_rcc.h"
#include "timer_monotonic.h"

#define ADC1_BASE 0x40012000u
#define ADC_SR    0x00u
#define ADC_CR2   0x08u
#define ADC_SMPR1 0x0Cu   /* sample times for channels 10-18 */
#define ADC_SQR1  0x2Cu
#define ADC_SQR3  0x34u
#define ADC_DR    0x4Cu

#define GPIOC_BASE 0x40020800u
#define GPIO_MODER 0x00u
#define GPIO_PUPDR 0x0Cu

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define SR_EOC     (1u << 1)
#define CR2_ADON   (1u << 0)
#define CR2_SWSTART (1u << 30)

/* 480-cycle sample time (SMP=0b111) for the sense channels: slow and
 * quiet is what a battery divider wants. SMPR1 covers ch10-18, its
 * first field is ch10. */
#define SMPR1_CH(ch) (7u << (3u * ((ch) - 10u)))
#define EOC_TIMEOUT_US 1000u

void adc1_init(void)
{
    RCC_APB2ENR |= RCC_APB2ENR_ADC1EN;
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOC;
    /* PC0/PC1: analog mode (11), no pull resistors. The LOW nibble is
     * PC0/PC1 (two MODER bits each); 0xF0 would be PC2/PC3
     * (review 2026-09-29, finding 6). */
    uint32_t moder = REG32(GPIOC_BASE + GPIO_MODER) & ~0x0Fu;
    REG32(GPIOC_BASE + GPIO_MODER) = moder | 0x0Fu;
    uint32_t pupdr = REG32(GPIOC_BASE + GPIO_PUPDR) & ~0x0Fu;
    REG32(GPIOC_BASE + GPIO_PUPDR) = pupdr;

    REG32(ADC1_BASE + ADC_CR2) = CR2_ADON;
    REG32(ADC1_BASE + ADC_SQR1) = 0;          /* L=0: one conversion */
    REG32(ADC1_BASE + ADC_SMPR1) =
        SMPR1_CH(ADC_CH_VBAT) | SMPR1_CH(ADC_CH_CURRENT);
}

int adc1_read(uint8_t channel, uint16_t *out)
{
    REG32(ADC1_BASE + ADC_SQR3) = channel & 0x1Fu;
    REG32(ADC1_BASE + ADC_CR2) |= CR2_SWSTART;
    uint32_t t0 = timer_ticks();
    for (;;) {
        if (REG32(ADC1_BASE + ADC_SR) & SR_EOC)
            break;
        if (timer_elapsed_us(t0) >= EOC_TIMEOUT_US)
            return -1;                        /* conversion lost this tick */
    }
    *out = (uint16_t)REG32(ADC1_BASE + ADC_DR); /* reading DR clears EOC */
    return 0;
}

int adc1_read_mv(uint8_t channel, uint32_t *out_mv)
{
    uint16_t raw;
    if (adc1_read(channel, &raw))
        return -1;
    *out_mv = (uint32_t)raw * ADC_VREF_MV / 4095u;
    return 0;
}

int battery_read_mv(uint32_t *out_mv)
{
    uint32_t pin_mv;
    if (adc1_read_mv(ADC_CH_VBAT, &pin_mv))
        return -1;
    *out_mv = pin_mv * VBAT_DIVIDER;
    return 0;
}
