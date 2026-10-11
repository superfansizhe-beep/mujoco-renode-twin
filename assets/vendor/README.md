# Vendor reference models — fetch guide

Third-party CAD for the bought modules. **Not redistributed with this
repository** — the STEP/STP/PNG files under this tree are `gitignored`;
fetch them from the sources below into the same layout. Everything the
twin needs runs without them: collision envelopes and mounting features
come from the constants sheet, and `python -m cad_modeling.balance_bot`
falls back to the envelope assembly (with a notice) when they are
absent, so the viewer model exports vendor-free.

## What to fetch, from where

| family | files to place | source |
|---|---|---|
| JGB37-520 motor set | `jgb37-520/*.step` (dc_motor, geared_body, motor_shaft, plastic_cover, shaft_coupler, coupling_bracket, 37mm_mounting_bracket) | github.com/hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. (trailing dot is part of the repo name) |
| JGB37-520 with encoder | `jgb37-520/grabcad_encoder/jgb37-520_LR{19,22,24,26.5,29}.step` + `JGB37-520_size.png` | GrabCAD "motor JGB37-520 with quadrature encoder" by PENNEL Patrice — <https://www.grabcad.com/library/motor-jgb37-520-with-quadrature-encoder-1> (login required) |
| GY-521 (MPU6050) board | `mpu6050-gy521/gy521_module.step` | github.com/adam-kabbara/RSX-CANSAT-2026 |
| GY-521 cross-check | `mpu6050-gy521/grabcad_gy521/GY-521_MPU6050 Accelerometer.step` | GrabCAD (with components) |
| AMS1117 SOT-223 chip | `ams1117/ams1117_chip_sot223_only.step` | github.com/xhivo97/esp-garage-hardware |
| AMS1117 module variants (reference only — NOT the Taobao board) | `ams1117/grabcad_module/*`, `ams1117/grabcad_ldo_3pin/*` | GrabCAD |
| TCRT5000L sensor head | `tcrt5000/tcrt5000l.step` | github.com/alientanya/line-follower-PCB |

No public model exists for the Taobao AMS1117 module board, the JY61P or
the Yahboom 8-way line bar — those are self-modeled from the caliper.

GrabCAD items are user-uploaded models under GrabCAD's terms — fetch
them yourself, do not commit them back. The GitHub-sourced items follow
their repositories' terms; none ships an OSI license mark, which is why
this project's route is fetch-not-ship for all of it.

## The one manual step: GrabCAD

GrabCAD serves downloads only to a logged-in session, so this one file cannot
be scripted. Everything else `tools/fetch_vendor.sh` handles.

1. Open <https://www.grabcad.com/library/motor-jgb37-520-with-quadrature-encoder-1>
   and log in (a free account is enough).
2. Download the archive. It carries every gearbox-length variant —
   `jgb37-520_LR19.step`, `LR22`, `LR24`, `LR26.5`, `LR29` — plus the
   dimensioned drawing `JGB37-520_size.png`.
3. Unzip it into `assets/vendor/jgb37-520/grabcad_encoder/`, file names unchanged.
4. Confirm it landed:

   ```bash
   uv run python -m pytest tests/test_assembly.py -q -rs
   ```

   Missing the file, six geometry gates skip and name it as the reason; with
   it, they run. Only `jgb37-520_LR24.step` is on the code path
   (`cad_modeling/jgb37_520.py`); the other four are cross-check references.

## Rules that hold regardless

These are visual/cross-check references. The collision envelopes and
every mounting feature on OUR parts come from the constants sheet,
driven by the caliper — not from these files. Measured bboxes, variant
notes and the flange-pattern settlement live in
[jgb37-520/README.md](jgb37-520/README.md). The geometry tests that
compare against vendor BREPs skip cleanly when the files are absent
(`tests/test_assembly.py`).
