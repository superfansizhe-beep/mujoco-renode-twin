/* Independent watchdog (IWDG) -- the last-resort guard: a control loop
 * that stops cycling for ~300 ms resets the chip with every drive pin
 * at its reset value (TB6612 inputs low = coast). The firmware pairs it
 * with its own faster supervision (IMU starvation -> zero duty), so the
 * watchdog only ever fires on a HUNG loop.
 *
 * Renode 1.17 models it (STM32_IndependentWatchdog at 0x40003000,
 * probed 2026-09-29) -- the gates prove the programming + kick cadence;
 * the reset EFFECT on silicon is the BOARD label in race_status.md.
 */
#ifndef STM32F4_IWDG_H
#define STM32F4_IWDG_H

#include <stdint.h>

void iwdg_start(void);       /* RM sequence: unlock, prescale, reload, run */
void iwdg_kick(void);        /* reload once per control cycle */

#endif /* STM32F4_IWDG_H */
