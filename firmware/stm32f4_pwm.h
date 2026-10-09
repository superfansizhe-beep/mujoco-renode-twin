/* Motor PWM on the advanced timer TIM1 + direction GPIOs for the
 * TB6612-style bridge.
 *
 * Pin contract (our allocation, pending the motor-driver module's
 * arrival -- it is a #define table here, swap freely):
 *   PWMA (left)  TIM1 CH1 = PE9  (AF1)
 *   PWMB (right) TIM1 CH2 = PE11 (AF1)
 *   AIN1/AIN2 = PE0/PE1, BIN1/BIN2 = PE2/PE3, STBY = PE4
 * (PC6/PC7 + PD12/PD13 stay with the encoders, PB6/PB7 with I2C1,
 * PC0/PC1 reserved for the battery/current ADC.)
 *
 * 20 kHz, 800-count period (ARR=799 @ 16 MHz HSI tree), CCR preloaded
 * (writes latch at the next update event -- glitch-free on silicon).
 *
 * TB6612 truth table per half-bridge: IN1=1,IN2=0 CW; 0,1 CCW;
 * 1,1 short-brake; 0,0 coast. pwm_motor_set() maps a signed permille
 * duty: sign -> direction pins, magnitude -> CCR, 0 -> coast.
 *
 * Sim limits: TIM1Sim stores BDTR for read-back; the plant decoder
 * gates motor drive on MOE, STBY and the timer/channel enables. The
 * PWM pin-waveform layer does not gate on MOE or faithfully reproduce
 * within-period phase. Duty gates measure averages; verify electrical
 * waveform shape and switching on the board.
 */
#ifndef STM32F4_PWM_H
#define STM32F4_PWM_H

#include <stdint.h>

void pwm_motor_init(void);

/* signed permille (-1000..1000, + selects IN1=1/IN2=0); clamps outside */
void pwm_motor_set(int32_t duty_left_pm, int32_t duty_right_pm);

/* snapshot of the direction-pin word: bit0 AIN1, 1 AIN2, 2 BIN1,
 * 3 BIN2, 4 STBY */
uint32_t pwm_motor_dir_word(void);

/* applied compare values, for echoes */
uint32_t pwm_motor_ccr1(void);
uint32_t pwm_motor_ccr2(void);

#endif /* STM32F4_PWM_H */
