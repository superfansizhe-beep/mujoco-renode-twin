#include <stdint.h>

#include "stm32f4_uart.h"
#include "stm32f4_rcc.h"
#include "timer_monotonic.h"

#define USART2_BASE 0x40004400u
#define USART_SR   0x00u
#define USART_DR   0x04u
#define USART_BRR  0x08u
#define USART_CR1  0x0Cu

#define GPIOA_BASE 0x40020000u
#define GPIO_MODER 0x00u
#define GPIO_OSPEEDR 0x08u
#define GPIO_PUPDR 0x0Cu
#define GPIO_AFRL 0x20u

#define REG32(addr) (*(volatile uint32_t *)(addr))

#define SR_TXE  (1u << 7)
#define SR_TC   (1u << 6)
#define SR_RXNE (1u << 5)

#define CR1_UE (1u << 13)
#define CR1_TE (1u << 3)
#define CR1_RE (1u << 2)

void uart2_init(void)
{
    RCC_APB1ENR |= RCC_APB1ENR_USART2EN;
    RCC_AHB1ENR |= RCC_AHB1ENR_GPIOA;
    /* PA2/PA3 nibble = MODER bits 4-7, PUPDR bits 4-7, AFRL bits 8-15 */
    uint32_t moder = REG32(GPIOA_BASE + GPIO_MODER) & ~0xF0u;
    REG32(GPIOA_BASE + GPIO_MODER) = moder | 0xA0u;   /* both AF (10) */
    REG32(GPIOA_BASE + GPIO_OSPEEDR) |= 0xF0u;        /* 115200: high speed */
    uint32_t pupdr = REG32(GPIOA_BASE + GPIO_PUPDR) & ~0xF0u;
    REG32(GPIOA_BASE + GPIO_PUPDR) = pupdr | 0x40u;   /* PA3 pull-up only */
    uint32_t afrl = REG32(GPIOA_BASE + GPIO_AFRL) & ~0xFF00u;
    REG32(GPIOA_BASE + GPIO_AFRL) = afrl | 0x7700u;   /* AF7 both */

    REG32(USART2_BASE + USART_BRR) = UART2_BRR;
    REG32(USART2_BASE + USART_CR1) = CR1_UE | CR1_TE | CR1_RE;
}

int uart2_putc(char c, uint32_t timeout_us)
{
    uint32_t t0 = timer_ticks();
    for (;;) {
        if (REG32(USART2_BASE + USART_SR) & SR_TXE)
            break;
        if (timer_elapsed_us(t0) >= timeout_us)
            return -1;
    }
    REG32(USART2_BASE + USART_DR) = (uint8_t)c;
    return 0;
}

int uart2_write(const char *buf, uint32_t len, uint32_t timeout_us)
{
    for (uint32_t i = 0; i < len; i++)
        if (uart2_putc(buf[i], timeout_us))
            return -1;
    return 0;
}

int uart2_getc(char *out, uint32_t timeout_us)
{
    uint32_t t0 = timer_ticks();
    for (;;) {
        if (REG32(USART2_BASE + USART_SR) & SR_RXNE) {
            *out = (char)(REG32(USART2_BASE + USART_DR) & 0xFFu);
            return 0;
        }
        if (timer_elapsed_us(t0) >= timeout_us)
            return -1;
    }
}

int uart2_flush(uint32_t timeout_us)
{
    uint32_t t0 = timer_ticks();
    for (;;) {
        if (REG32(USART2_BASE + USART_SR) & SR_TC)
            return 0;
        if (timer_elapsed_us(t0) >= timeout_us)
            return -1;
    }
}
