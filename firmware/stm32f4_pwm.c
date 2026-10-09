#include <stdint.h>

#include "stm32f4_pwm.h"
#include "stm32f4_rcc.h"

#define TIM1_BASE 0x40010000u
#define TIM_CR1   0x00u
#define TIM_EGR   0x14u
#define TIM_CCMR1 0x18u
#define TIM_CCER  0x20u
#define TIM_CNT   0x24u
#define TIM_PSC   0x28u
#define TIM_ARR   0x2Cu
#define TIM_CCR1  0x34u
#define TIM_CCR2  0x38u
#define TIM_BDTR  0x44u

#define GPIOE_BASE 0x40021000u
#define GPIO_MODER 0x00u
#define GPIO_ODR   0x14u
#define GPIO_AFRL  0x20u
#define GPIO_AFRH  0x24u

#define REG32(addr) (*(volatile uint32_t *)(addr))

/* 20 kHz from the 16 MHz HSI tree: PSC=0, ARR=799 */
#define PWM_ARR 799u
#define PWM_OC_MODE  ((6u << 4) | (1u << 3) | (6u << 12) | (1u << 11))
/* OC1M=110 PWM1 + OC1PE, OC2M=110 + OC2PE */

/* direction pin numbers on GPIOE */
#define PIN_AIN1 0u
#define PIN_AIN2 1u
#define PIN_BIN1 2u
#define PIN_BIN2 3u
#define PIN_STBY 4u

static void dir_pin(uint8_t pin, uint32_t *word, int value)
{
    if (value)
        *word |= (1u << pin);
    else
        *word &= ~(1u << pin);
}

static uint32_t apply_dir(int32_t d, uint8_t in1, uint8_t in2,
                          uint32_t word)
{
    /* TB6612: 1,0 CW; 0,1 CCW; 0,0 coast */
    dir_pin(in1, &word, d > 0);
    dir_pin(in2, &word, d < 0);
    return word;
}

static uint32_t ccr_of(int32_t d)
{
    /* magnitude -> counts, rounded */
    int32_t m = (d < 0 ? -d : d);
    if (m > 1000)
        m = 1000;
    return (uint32_t)((m * (int32_t)PWM_ARR + 500) / 1000);
}

uint32_t pwm_motor_dir_word(void)
{
    return REG32(GPIOE_BASE + GPIO_ODR) & 0x1Fu;
}

uint32_t pwm_motor_ccr1(void)
{
    return REG32(TIM1_BASE + TIM_CCR1);
}

uint32_t pwm_motor_ccr2(void)
{
    return REG32(TIM1_BASE + TIM_CCR2);
}

void pwm_motor_set(int32_t duty_left_pm, int32_t duty_right_pm)
{
    REG32(TIM1_BASE + TIM_CCR1) = ccr_of(duty_left_pm);
    REG32(TIM1_BASE + TIM_CCR2) = ccr_of(duty_right_pm);
    uint32_t word = REG32(GPIOE_BASE + GPIO_ODR) & 0x1Fu;
    word = apply_dir(duty_left_pm, PIN_AIN1, PIN_AIN2, word);
    word = apply_dir(duty_right_pm, PIN_BIN1, PIN_BIN2, word);
    REG32(GPIOE_BASE + GPIO_ODR) = word | (1u << PIN_STBY);
}

void pwm_motor_init(void)
{
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOE;
    RCC_APB2ENR |= RCC_APB2ENR_TIM1EN;

    /* PE9/PE11: AF1 (TIM1 CH1/CH2) */
    uint32_t moder = REG32(GPIOE_BASE + GPIO_MODER);
    moder &= ~((3u << 18) | (3u << 22));
    moder |= (2u << 18) | (2u << 22);
    REG32(GPIOE_BASE + GPIO_MODER) = moder;
    uint32_t afrh = REG32(GPIOE_BASE + GPIO_AFRH) & ~((0xFu << 4) | (0xFu << 12));
    REG32(GPIOE_BASE + GPIO_AFRH) = afrh | (1u << 4) | (1u << 12);
    /* PE0-PE4: direction outputs, low (coast) */
    uint32_t moder_l = REG32(GPIOE_BASE + GPIO_MODER) & ~0x3FFu;
    REG32(GPIOE_BASE + GPIO_MODER) = moder_l | 0x155u;
    REG32(GPIOE_BASE + GPIO_ODR) &= ~0x1Fu;

    REG32(TIM1_BASE + TIM_PSC) = 0;
    REG32(TIM1_BASE + TIM_ARR) = PWM_ARR;
    REG32(TIM1_BASE + TIM_CCMR1) = PWM_OC_MODE;
    REG32(TIM1_BASE + TIM_CCER) = (1u << 0) | (1u << 4);   /* CC1E, CC2E */
    REG32(TIM1_BASE + TIM_CCR1) = 0;
    REG32(TIM1_BASE + TIM_CCR2) = 0;
    REG32(TIM1_BASE + TIM_EGR) = 1u;      /* UG: latch ARR/CCR, reset counter */
    REG32(TIM1_BASE + TIM_BDTR) = (1u << 15);              /* MOE: TIM1Sim stores
                                                              BDTR; drive decode
                                                              gates on this bit */
    REG32(TIM1_BASE + TIM_CR1) = 0x81u;   /* CEN + ARPE */
}
