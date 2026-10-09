/* STM32F407ZGT6 bare-metal linker script (board repl: stm32f407zg.repl)
 *
 * Sizes are the real part's: 1 MiB flash, 128 KiB SRAM -- no discovery
 * platform's 2 MiB / 256 KiB generosity. RAM is truncated to 0x1EA00 and
 * the top carved, all inside the real chip's SRAM:
 *
 *   0x2001EA00  battery_bringup results (firmware/battery_bringup.h)
 *   0x2001EC00  pwm_bringup command + results (firmware/pwm_bringup.h)
 *   0x2001ED00  line_bringup results + command (firmware/line_bringup.h)
 *   0x2001EE00  enc_bringup results (firmware/enc_bringup.h)
 *   0x2001F000  imu_bringup results + init trace (firmware/imu_bringup.h)
 *               (trace ends at 0x2001F080 + 0x808)
 *   0x2001FA00  uart_bringup results (firmware/uart_bringup.h)
 *   0x2001FFB8  fault magic (Default_Handler writes 0xFA17C0DE; 0 = clean)
 *   0x2001FFBC  fault IPSR
 *   0x2001FFC0  twin/race mailbox, top 64 B (see twin/mailbox.py)
 *   0x20020000  end of the real 128 KiB SRAM
 *
 * _estack = 0x2001FFB8: full-descending stack grows down below the fault
 * words and never touches them, the harness blocks, or the mailbox. Same
 * trick as the radar repo.
 */

ENTRY(Reset_Handler)

MEMORY
{
    FLASH (rx)  : ORIGIN = 0x08000000, LENGTH = 1024K
    RAM   (rwx) : ORIGIN = 0x20000000, LENGTH = 0x1EA00
}

SECTIONS
{
    .isr_vector ORIGIN(FLASH) :
    {
        KEEP(*(.isr_vector))
    } > FLASH

    .text :
    {
        *(.text*)
        *(.rodata*)
        . = ALIGN(4);
    } > FLASH

    _sidata = LOADADDR(.data);

    .data :
    {
        . = ALIGN(4);
        _sdata = .;
        *(.data*)
        . = ALIGN(4);
        _edata = .;
    } > RAM AT > FLASH

    .bss (NOLOAD) :
    {
        . = ALIGN(4);
        _sbss = .;
        *(.bss*)
        *(COMMON)
        . = ALIGN(4);
        _ebss = .;
    } > RAM

    /DISCARD/ :
    {
        *(.ARM.exidx*)
        *(.ARM.attributes)
        *(.comment)
    }

    _estack = ORIGIN(RAM) + LENGTH(RAM);
}
