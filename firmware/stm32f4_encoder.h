/* Quadrature encoder interface on the general timers, x4 (count on
 * both A and B edges, SMS=011).
 *
 * Pin contract (our allocation; motor PWM keeps off these pins):
 *   left  TIM3 CH1/CH2 = PC6/PC7   (AF2, pull-ups)
 *   right TIM4 CH1/CH2 = PD12/PD13 (AF2, pull-ups)
 * (PB6/PB7 stay with I2C1; TIM8's PWM pins are chosen elsewhere.)
 *
 * The 16-bit counters wrap by design; positions integrate through
 * encoder_delta16, whose modular subtraction is wrap-correct by
 * construction. The crossing itself is only exercisable on silicon:
 * Renode 1.17's LimitTimer throws on ANY counter wrap (probed
 * 2026-09-29, encprobe.log) -- the BOARD label in enc_status.md owns
 * that gate, and the sim tests stop one step short of the boundary.
 */
#ifndef STM32F4_ENCODER_H
#define STM32F4_ENCODER_H

#include <stdint.h>

void encoder_init(void);

uint16_t encoder_cnt_left(void);
uint16_t encoder_cnt_right(void);

/* signed distance from `last` to `now`, correct across wrap */
int16_t encoder_delta16(uint16_t now, uint16_t last);

#endif /* STM32F4_ENCODER_H */
