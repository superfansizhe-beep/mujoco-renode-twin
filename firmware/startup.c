/* Shared F407ZGT6 startup: vector table (16 core + 82 peripheral weak
 * aliases), Reset_Handler, fault reporter, newlib errno landing.
 * Compiled verbatim into every firmware ELF (twin, race, imu_bringup);
 * a build links exactly one copy of this file.
 */

#include <stdint.h>

/* needed by newlib -lm's errno path; this firmware never reads errno, just give it a landing spot */
int *__errno(void);
int *__errno(void) { static int e; return &e; }

extern uint32_t _estack, _sidata, _sdata, _edata, _sbss, _ebss;

int main(void);
void Reset_Handler(void);
void Default_Handler(void);

typedef void (*isr_t)(void);

/* Full F407ZGT6 table: 16 core + 82 peripheral entries. Peripheral handlers
 * are weak aliases -- a real driver overrides by defining the strong name.
 * No interrupt is enabled yet (the mailbox strobe is this firmware's clock),
 * but an unexpected exception must land in the reporter, not in 0xFFFFFFFF. */
#define WEAK_DFLT(n) \
    void n(void) __attribute__((weak, alias("Default_Handler")))

WEAK_DFLT(WWDG_IRQHandler);          WEAK_DFLT(PVD_IRQHandler);
WEAK_DFLT(TAMP_STAMP_IRQHandler);    WEAK_DFLT(RTC_WKUP_IRQHandler);
WEAK_DFLT(FLASH_IRQHandler);         WEAK_DFLT(RCC_IRQHandler);
WEAK_DFLT(EXTI0_IRQHandler);         WEAK_DFLT(EXTI1_IRQHandler);
WEAK_DFLT(EXTI2_IRQHandler);         WEAK_DFLT(EXTI3_IRQHandler);
WEAK_DFLT(EXTI4_IRQHandler);         WEAK_DFLT(DMA1_Stream0_IRQHandler);
WEAK_DFLT(DMA1_Stream1_IRQHandler);  WEAK_DFLT(DMA1_Stream2_IRQHandler);
WEAK_DFLT(DMA1_Stream3_IRQHandler);  WEAK_DFLT(DMA1_Stream4_IRQHandler);
WEAK_DFLT(DMA1_Stream5_IRQHandler);  WEAK_DFLT(DMA1_Stream6_IRQHandler);
WEAK_DFLT(ADC_IRQHandler);           WEAK_DFLT(CAN1_TX_IRQHandler);
WEAK_DFLT(CAN1_RX0_IRQHandler);      WEAK_DFLT(CAN1_RX1_IRQHandler);
WEAK_DFLT(CAN1_SCE_IRQHandler);      WEAK_DFLT(EXTI9_5_IRQHandler);
WEAK_DFLT(TIM1_BRK_TIM9_IRQHandler); WEAK_DFLT(TIM1_UP_TIM10_IRQHandler);
WEAK_DFLT(TIM1_TRG_COM_TIM11_IRQHandler); WEAK_DFLT(TIM1_CC_IRQHandler);
WEAK_DFLT(TIM2_IRQHandler);          WEAK_DFLT(TIM3_IRQHandler);
WEAK_DFLT(TIM4_IRQHandler);          WEAK_DFLT(I2C1_EV_IRQHandler);
WEAK_DFLT(I2C1_ER_IRQHandler);       WEAK_DFLT(I2C2_EV_IRQHandler);
WEAK_DFLT(I2C2_ER_IRQHandler);       WEAK_DFLT(SPI1_IRQHandler);
WEAK_DFLT(SPI2_IRQHandler);          WEAK_DFLT(USART1_IRQHandler);
WEAK_DFLT(USART2_IRQHandler);        WEAK_DFLT(USART3_IRQHandler);
WEAK_DFLT(EXTI15_10_IRQHandler);     WEAK_DFLT(RTC_Alarm_IRQHandler);
WEAK_DFLT(OTG_FS_WKUP_IRQHandler);   WEAK_DFLT(TIM8_BRK_TIM12_IRQHandler);
WEAK_DFLT(TIM8_UP_TIM13_IRQHandler); WEAK_DFLT(TIM8_TRG_COM_TIM14_IRQHandler);
WEAK_DFLT(TIM8_CC_IRQHandler);       WEAK_DFLT(DMA1_Stream7_IRQHandler);
WEAK_DFLT(FSMC_IRQHandler);          WEAK_DFLT(SDIO_IRQHandler);
WEAK_DFLT(TIM5_IRQHandler);          WEAK_DFLT(SPI3_IRQHandler);
WEAK_DFLT(UART4_IRQHandler);         WEAK_DFLT(UART5_IRQHandler);
WEAK_DFLT(TIM6_DAC_IRQHandler);      WEAK_DFLT(TIM7_IRQHandler);
WEAK_DFLT(DMA2_Stream0_IRQHandler);  WEAK_DFLT(DMA2_Stream1_IRQHandler);
WEAK_DFLT(DMA2_Stream2_IRQHandler);  WEAK_DFLT(DMA2_Stream3_IRQHandler);
WEAK_DFLT(DMA2_Stream4_IRQHandler);  WEAK_DFLT(ETH_IRQHandler);
WEAK_DFLT(ETH_WKUP_IRQHandler);      WEAK_DFLT(CAN2_TX_IRQHandler);
WEAK_DFLT(CAN2_RX0_IRQHandler);      WEAK_DFLT(CAN2_RX1_IRQHandler);
WEAK_DFLT(CAN2_SCE_IRQHandler);      WEAK_DFLT(OTG_FS_IRQHandler);
WEAK_DFLT(DMA2_Stream5_IRQHandler);  WEAK_DFLT(DMA2_Stream6_IRQHandler);
WEAK_DFLT(DMA2_Stream7_IRQHandler);  WEAK_DFLT(USART6_IRQHandler);
WEAK_DFLT(I2C3_EV_IRQHandler);       WEAK_DFLT(I2C3_ER_IRQHandler);
WEAK_DFLT(OTG_HS_EP1_OUT_IRQHandler); WEAK_DFLT(OTG_HS_EP1_IN_IRQHandler);
WEAK_DFLT(OTG_HS_WKUP_IRQHandler);   WEAK_DFLT(OTG_HS_IRQHandler);
WEAK_DFLT(DCMI_IRQHandler);          WEAK_DFLT(CRYP_IRQHandler);
WEAK_DFLT(HASH_RNG_IRQHandler);      WEAK_DFLT(FPU_IRQHandler);

__attribute__((section(".isr_vector"), used))
isr_t vector_table[16 + 82] = {
    (isr_t)&_estack,   /* 0: initial SP */
    Reset_Handler,     /* 1: reset */
    Default_Handler,   /* 2: NMI */
    Default_Handler,   /* 3: HardFault */
    Default_Handler,   /* 4: MemManage */
    Default_Handler,   /* 5: BusFault */
    Default_Handler,   /* 6: UsageFault */
    0, 0, 0, 0,        /* 7-10: reserved */
    Default_Handler,   /* 11: SVCall */
    Default_Handler,   /* 12: DebugMon */
    0,                 /* 13: reserved */
    Default_Handler,   /* 14: PendSV */
    Default_Handler,   /* 15: SysTick (this firmware polls, no interrupts enabled) */
    WWDG_IRQHandler,
    PVD_IRQHandler,
    TAMP_STAMP_IRQHandler,
    RTC_WKUP_IRQHandler,
    FLASH_IRQHandler,
    RCC_IRQHandler,
    EXTI0_IRQHandler,
    EXTI1_IRQHandler,
    EXTI2_IRQHandler,
    EXTI3_IRQHandler,
    EXTI4_IRQHandler,
    DMA1_Stream0_IRQHandler,
    DMA1_Stream1_IRQHandler,
    DMA1_Stream2_IRQHandler,
    DMA1_Stream3_IRQHandler,
    DMA1_Stream4_IRQHandler,
    DMA1_Stream5_IRQHandler,
    DMA1_Stream6_IRQHandler,
    ADC_IRQHandler,
    CAN1_TX_IRQHandler,
    CAN1_RX0_IRQHandler,
    CAN1_RX1_IRQHandler,
    CAN1_SCE_IRQHandler,
    EXTI9_5_IRQHandler,
    TIM1_BRK_TIM9_IRQHandler,
    TIM1_UP_TIM10_IRQHandler,
    TIM1_TRG_COM_TIM11_IRQHandler,
    TIM1_CC_IRQHandler,
    TIM2_IRQHandler,
    TIM3_IRQHandler,
    TIM4_IRQHandler,
    I2C1_EV_IRQHandler,
    I2C1_ER_IRQHandler,
    I2C2_EV_IRQHandler,
    I2C2_ER_IRQHandler,
    SPI1_IRQHandler,
    SPI2_IRQHandler,
    USART1_IRQHandler,
    USART2_IRQHandler,
    USART3_IRQHandler,
    EXTI15_10_IRQHandler,
    RTC_Alarm_IRQHandler,
    OTG_FS_WKUP_IRQHandler,
    TIM8_BRK_TIM12_IRQHandler,
    TIM8_UP_TIM13_IRQHandler,
    TIM8_TRG_COM_TIM14_IRQHandler,
    TIM8_CC_IRQHandler,
    DMA1_Stream7_IRQHandler,
    FSMC_IRQHandler,
    SDIO_IRQHandler,
    TIM5_IRQHandler,
    SPI3_IRQHandler,
    UART4_IRQHandler,
    UART5_IRQHandler,
    TIM6_DAC_IRQHandler,
    TIM7_IRQHandler,
    DMA2_Stream0_IRQHandler,
    DMA2_Stream1_IRQHandler,
    DMA2_Stream2_IRQHandler,
    DMA2_Stream3_IRQHandler,
    DMA2_Stream4_IRQHandler,
    ETH_IRQHandler,
    ETH_WKUP_IRQHandler,
    CAN2_TX_IRQHandler,
    CAN2_RX0_IRQHandler,
    CAN2_RX1_IRQHandler,
    CAN2_SCE_IRQHandler,
    OTG_FS_IRQHandler,
    DMA2_Stream5_IRQHandler,
    DMA2_Stream6_IRQHandler,
    DMA2_Stream7_IRQHandler,
    USART6_IRQHandler,
    I2C3_EV_IRQHandler,
    I2C3_ER_IRQHandler,
    OTG_HS_EP1_OUT_IRQHandler,
    OTG_HS_EP1_IN_IRQHandler,
    OTG_HS_WKUP_IRQHandler,
    OTG_HS_IRQHandler,
    DCMI_IRQHandler,
    CRYP_IRQHandler,
    HASH_RNG_IRQHandler,
    FPU_IRQHandler,
};

_Static_assert(sizeof vector_table == (16 + 82) * sizeof(isr_t),
               "vector table must carry all 98 F407ZGT6 entries");

__attribute__((naked))
void Reset_Handler(void)
{
    /* set SP explicitly: do not depend on how Renode reads vector table entry 0 (same as the radar repo) */
    __asm volatile ("ldr r0, =_estack\n\t"
                    "mov sp, r0\n\t"
                    : : : "r0");
    /* .data: flash -> ram */
    for (uint32_t *p = &_sdata, *s = &_sidata; p < &_edata;)
        *p++ = *s++;
    /* zero .bss */
    for (uint32_t *p = &_sbss; p < &_ebss;)
        *p++ = 0;
    /* M4F FPU enable must precede any FPU instruction — including the vpush
     * the compiler inserts into the main prologue (measured: later than here
     * = UsageFault on the first FPU instruction, PC dumped into
     * Default_Handler). Same placement as ARM's official startup. */
    __asm volatile (
        "ldr r1, =0xE000ED88\n\t"   /* SCB->CPACR */
        "ldr r0, [r1]\n\t"
        "orr r0, r0, #0x00F00000\n\t"
        "str r0, [r1]\n\t"
        "dsb\n\t"
        "isb\n\t"
        : : : "r0", "r1", "memory");
    (void)main();
    for (;;)
        ;
}

/* Fault landing: park the magic + exception number in the fault words
 * (0x2001FFB8/BC, carved in stm32f407.ld) where the harness can read
 * them, then hang. Naked + hand asm with no literal pool: valid even
 * when the fault IS a broken stack. */
__attribute__((naked))
void Default_Handler(void)
{
    __asm volatile ("movw r1, #0xC0DE\n\t"
                    "movt r1, #0xFA17\n\t"
                    "movw r2, #0xFFB8\n\t"
                    "movt r2, #0x2001\n\t"
                    "str r1, [r2], #4\n\t"
                    "mrs r0, ipsr\n\t"
                    "str r0, [r2]\n\t"
                    "1: b 1b\n\t");
}
