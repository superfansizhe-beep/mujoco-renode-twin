#include <stdint.h>

#include "stm32f4_encoder.h"
#include "stm32f4_rcc.h"

#define TIM3_BASE 0x40000400u
#define TIM4_BASE 0x40000800u
/* register offsets common to the general timers */
#define TIM_CR1   0x00u
#define TIM_SMCR  0x08u
#define TIM_CCMR1 0x18u
#define TIM_CCER  0x20u
#define TIM_CNT   0x24u
#define TIM_PSC   0x28u
#define TIM_ARR   0x2Cu

#define GPIOC_BASE 0x40020800u
#define GPIOD_BASE 0x40020C00u
#define GPIO_MODER 0x00u
#define GPIO_PUPDR 0x0Cu
#define GPIO_AFRL  0x20u
#define GPIO_AFRH  0x24u

#define REG32(addr) (*(volatile uint32_t *)(addr))

/* CC1S=01 (IC1<-TI1), CC2S=01 (IC2<-TI2) -- CC2S=10 would map IC2 to
 * TI1 as well, feeding both inputs from one pin (review 2026-09-29) */
#define CCMR1_ENCODER ((1u << 0) | (1u << 8))

static uint16_t cnt(uint32_t base)
{
    return (uint16_t)REG32(base + TIM_CNT);
}

int16_t encoder_delta16(uint16_t now, uint16_t last)
{
    /* 16-bit modular subtraction: the narrow cast IS the wrap
     * handling -- 0xFFFC -> 0x0002 reads as +6, no branches */
    return (int16_t)(uint16_t)(now - last);
}

static void encoder_timer(uint32_t base)
{
    REG32(base + TIM_PSC) = 0;
    REG32(base + TIM_ARR) = 0xFFFFu;
    REG32(base + TIM_CCMR1) = CCMR1_ENCODER;
    REG32(base + TIM_CCER) = 0;          /* both polarities rising */
    REG32(base + TIM_SMCR) = 0x3u;       /* SMS=011: encoder mode 3 */
    REG32(base + TIM_CR1) = 1u;          /* CEN */
}

/* AF mode (10) + pull-up (01) + AF2 on two channel pins */
static void encoder_pin(uint32_t gpio, uint8_t pin)
{
    uint32_t pair = 3u << (2 * pin);
    uint32_t moder = REG32(gpio + GPIO_MODER) & ~pair;
    REG32(gpio + GPIO_MODER) = moder | (2u << (2 * pin));
    uint32_t pupdr = REG32(gpio + GPIO_PUPDR) & ~pair;
    REG32(gpio + GPIO_PUPDR) = pupdr | (1u << (2 * pin));
    if (pin < 8u) {
        uint32_t nib = 0xFu << (4 * pin);
        uint32_t afrl = REG32(gpio + GPIO_AFRL) & ~nib;
        REG32(gpio + GPIO_AFRL) = afrl | (2u << (4 * pin));
    } else {
        uint32_t nib = 0xFu << (4 * (pin - 8u));
        uint32_t afrh = REG32(gpio + GPIO_AFRH) & ~nib;
        REG32(gpio + GPIO_AFRH) = afrh | (2u << (4 * (pin - 8u)));
    }
}

void encoder_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOC | RCC_AHB1ENR_GPIOD;
    RCC_APB1ENR |= RCC_APB1ENR_TIM3EN | RCC_APB1ENR_TIM4EN;

    encoder_pin(GPIOC_BASE, 6);
    encoder_pin(GPIOC_BASE, 7);
    encoder_pin(GPIOD_BASE, 12);
    encoder_pin(GPIOD_BASE, 13);

    encoder_timer(TIM3_BASE);
    encoder_timer(TIM4_BASE);
}

uint16_t encoder_cnt_left(void)
{
    return cnt(TIM3_BASE);
}

uint16_t encoder_cnt_right(void)
{
    return cnt(TIM4_BASE);
}
