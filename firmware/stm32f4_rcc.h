/* RCC register block, RM0090: base 0x40023800 (0x40023C00 is the FLASH
 * controller -- a previous hand-rolled 0x40023Cxx define sent every
 * peripheral's clock enable there, review 2026-09-29). Every driver
 * gates a clock through THIS header; nothing hand-rolls the addresses.
 *
 * The repl attaches the model at the same base (stm32f407zg.repl) and
 * it stores these registers, so the gates read the enables back in sim.
 * rcc_model.cs gates bus accesses and timer clocks for the peripherals
 * these drivers use; see rcc_status.md for the negative SIM gates and
 * the remaining clock-tree/electrical BOARD checks.
 */
#ifndef STM32F4_RCC_H
#define STM32F4_RCC_H

#include <stdint.h>

#define RCC_BASE    0x40023800u
#define RCC_AHB1ENR (*(volatile uint32_t *)(RCC_BASE + 0x30))
#define RCC_APB1ENR (*(volatile uint32_t *)(RCC_BASE + 0x40))
#define RCC_APB2ENR (*(volatile uint32_t *)(RCC_BASE + 0x44))

/* AHB1 */
#define RCC_AHB1ENR_GPIOA (1u << 0)
#define RCC_AHB1ENR_GPIOB (1u << 1)
#define RCC_AHB1ENR_GPIOC (1u << 2)
#define RCC_AHB1ENR_GPIOD (1u << 3)
#define RCC_AHB1ENR_GPIOE (1u << 4)
#define RCC_AHB1ENR_GPIOF (1u << 5)
/* APB1 */
#define RCC_APB1ENR_TIM2EN (1u << 0)
#define RCC_APB1ENR_TIM3EN (1u << 1)
#define RCC_APB1ENR_TIM4EN (1u << 2)
#define RCC_APB1ENR_USART2EN (1u << 17)
#define RCC_APB1ENR_I2C1EN (1u << 21)
/* APB2 */
#define RCC_APB2ENR_TIM1EN  (1u << 0)
#define RCC_APB2ENR_ADC1EN  (1u << 8)

#endif /* STM32F4_RCC_H */
