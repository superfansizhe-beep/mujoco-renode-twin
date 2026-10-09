# PWM bring-up status -- SIM vs BOARD

One driver (firmware/stm32f4_pwm.c), one bring-up ELF
(firmware/pwm_bringup.c). Pin contract: PWMA=PE9/PWMB=PE11 (TIM1
CH1/CH2 AF1, 20 kHz), AIN1/AIN2/BIN1/BIN2/STBY = PE0..PE4. The
TB6612-style signed-permille mapping (sign -> direction pins,
magnitude -> CCR, 0 -> coast) is register-proven in sim; everything
electrical is the BOARD label. Motors stay unconnected until the
integration milestone -- this ELF would command them if wired, so the
on-arrival procedure uses it deliberately.

## SIM -- verified (tests/test_firmware_pwm.py, Renode 1.17.0)

| gate | test |
| --- | --- |
| TIM1 20 kHz config (PSC/ARR/OCxM+preload/CCxE/CEN) + GPIO AF/output + RCC enables (GPIOE, TIM1) at runtime | `test_pwm_config_contract_is_written_at_runtime` |
| harness command -> duty echo + CCR + direction word | `test_command_echoes_through_ccr_and_direction` |
| pin waveform average duty matches the command (0.50 / 0.25) | `test_waveform_average_duty_matches_the_command` |
| zero duty coasts; |duty| clamps to the rail | `test_duty_zero_coasts_and_clamps_at_the_rail` |

## BOARD -- pending the motor-driver module + hardware

| gate | procedure |
| --- | --- |
| BDTR.MOE / STBY gating | `TIM1Sim` stores BDTR for register read-back, and the plant decoder enforces clock/CEN/CCxE/MOE/STBY (inactive MOE or STBY suppresses modeled motor drive). Renode's pin-waveform layer still does not gate its PWM trace on MOE or reproduce within-period phase. On the board, scope that PWMA/PWMB toggle only after init sets MOE=1 and STBY high |
| waveform shape | scope PWMA at 20 kHz: clean 800-count sawtooth PWM, phase within a period; Renode's IDR readback is duty-exact but phase-unfaithful (probed 2026-09-29) |
| TB6612 electrical truth table | per phase: IN1=1,IN2=0 -> CW; 0,1 -> CCW; 1,1 -> brake; 0,0 -> coast, at 3.3 V logic with VMOT present; the driver's signed mapping must match the actual motor +w direction (swap IN pins if a wheel runs backward) |
| electrical pins | PWMA/PWMB + PE0..PE4 against the module silkscreen when it arrives; the pin table in stm32f4_pwm.h is the swap point |
| clock gating effect | [rcc_status.md](rcc_status.md) covers missing GPIOE/TIM1 enables and pauses the PWM clock entries in SIM; on the board verify PWMA/PWMB toggle only after pwm_motor_init from a reset boot and scope the final output level when the clock is removed |
