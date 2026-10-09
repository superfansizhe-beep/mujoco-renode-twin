# Battery bring-up status -- SIM vs BOARD

One driver (firmware/stm32f4_adc.c), one bring-up ELF
(firmware/battery_bringup.c). Pin contract: VBAT_SENSE = PC0
(ADC123_IN10) behind a 30k:10k divider (VBAT = 4 x pin), 3S drone
battery 9.9-12.6 V -> 2.48-3.15 V at the pin; CURRENT_SENSE = PC1
(ADC123_IN11) reserved for the current sensor module (1:1 in the
model until that module is chosen).

## SIM -- verified (tests/test_firmware_battery.py, Renode 1.17.0)

| gate | test |
| --- | --- |
| ADC config contract (PC0/PC1 analog nibble + no pulls, ADON, SQR3=ch10, 480-cycle SMPR1, RCC GPIOCEN/ADC1EN readback) at runtime | `test_adc_config_contract_is_written_at_runtime` |
| 3S nominal 11.1 V reads back within quantization (+-10 mV) | `test_3s_nominal_reads_back_within_quantization` |
| full 12.6 V and empty 9.9 V span; deep-under 1 V quantizes | `test_full_and_empty_spans_of_the_3s_battery` |
| over-range saturates at the VREF rail (4095 / 13200 marker) | `test_over_range_saturates_at_the_vref_rail` |
| a valid zero conversion publishes zero, no false timeouts, recovers | `test_valid_zero_voltage_publishes_zero_then_recovers` |
| the ~268 s TIM2 wrap is EXECUTED: park CNT 1 us under the wrap pre-boot, pacing + data must survive (free-run 32-bit crossing does not throw in Renode, unlike the edge-injected encoder counters) | `test_deadline_clock_survives_the_32_bit_wrap` |
| modeled divider == firmware VBAT_DIVIDER; bench words disjoint | `TestBatteryLayout` |
| missing GPIOC/ADC1 clock cannot configure/convert; restoring ADC1 clock recovers | [rcc_status.md](rcc_status.md), `tests.test_firmware_rcc` |
| conversion pays its sample time: 3-cycle vs 480-cycle SMPR1 differ ~1.9 vs ~61.5 us (RM0090 ch. 13 TCONV), value unchanged | `TestAdcLatency.test_conversion_pays_its_sample_time` |
| a wrong ADCPRE stretches the conversion (/2 vs /8); SWSTART during a conversion is ignored | `TestAdcLatency.test_wrong_adcpre_stretches_the_conversion`, `TestAdcLatency.test_swstart_during_a_conversion_is_ignored` |

## BOARD -- pending hardware (procedure for the on-arrival day)

| gate | procedure |
| --- | --- |
| divider resistors | measure the actual top/bottom divider values; if not 30k:10k, change VBAT_DIVIDER in stm32f4_adc.h AND DefaultBatteryDivider in adc_model.cs together (the layout test pins them equal) |
| VREF rail | meter the 3.3 V rail feeding VREF+; adjust ADC_VREF_MV; a mV-scale error here is a mV-scale battery error |
| ADC clock | ADCPRE (common block, /2 -> 8 MHz) is unmodeled; verify no ADON-before-clock surprises at the debugger |
| current sensor | when the module lands: wire to PC1, set its mV-per-A in the driver, extend the bench feed to +0x2C |
| battery correlation | meter each cell vs the reported total; the OCV-SOC table in the memory notes becomes the SOC estimator input |
