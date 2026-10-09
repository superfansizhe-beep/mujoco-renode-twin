# JGB37-520 vendor reference models

Two independent sources, downloaded 2026-09-27:

1. `../jgb37-520/` (this folder, GitHub files): github.com/hoangwe/Computation-design-fabrication-and-control-of-a-Two-wheel-Balancing-Robot. (trailing dot is part of the repo name), via `gh api` (raw.githubusercontent.com unreachable from this network).
2. `grabcad_encoder/`: GrabCAD "motor JGB37-520 with quadrature encoder" by PENNEL Patrice (uploaded 2026-09-18), downloaded with a logged-in session as one zip.

| file (GitHub set) | what it is |
|---|---|
| dc_motor.step | 520 can shell, Ø33×19.5 (partial — not the full 40 mm can) |
| geared_body.step | gearbox + flange, Ø37×29, flange 3 mm |
| motor_shaft.step | Ø6×21.5 output shaft |
| plastic_cover.step | rear cover, 39.74×33×13 |
| shaft_coupler.step | coupling half, Ø12×6 |
| coupling_bracket.step | coupling bracket, Ø34×4 |
| 37mm_mounting_bracket.step | commercial 37 mm bracket: Ø40 outer arc, Ø13 shaft slot, six Ø3.2 flange holes, four Ø3.4 base holes; 1.5 mm plate |

| file (grabcad_encoder/) | total length incl. shaft (measured) |
|---|---|
| jgb37-520_LR19.step | 73.0 |
| jgb37-520_LR22.step | 76.0 |
| jgb37-520_LR24.step | 77.8 |
| jgb37-520_LR26.5.step | 80.4 |
| jgb37-520_LR29.step | 77.8 (!) — file is 1/4 the size of the others, likely missing parts |
| JGB37-520_size.png | manufacturer-style dimensioned drawing (see below) |

The GrabCAD STEPs are multi-body (21 solids: gears, screws, PCB…) — visual
reference only; collision envelopes come from our constants sheet.
The LR24 STEP output shaft is eccentric by 7 mm; the family drawing says
5.5 mm. The assembly now uses the shaft axis as its datum on both sides,
with the gearbox 7 mm below it. Measure the actual bought variant.

## Flange pattern — SETTLED by three independent sources

The size drawing in `grabcad_encoder/JGB37-520_size.png` states
**6× M3, profondeur 3.5 mm, on a Ø31 bolt circle**; the encoder-side drawing
adds 3×Ø4 through holes. Measured from the STEPs:

- GitHub `geared_body.step`: 6× Ø2.5 (tap drill) on R15.5 at 0/60/…/300°,
  plus 3 counterbored Ø2.6/Ø4.2 at 30°/150°/270°.
- GrabCAD `jgb37-520_LR24.step`: 6× Ø2.52 × 3.1 deep (+0.4 chamfer) on R15.5
  at 0/60/…/300°, plus 3× Ø2.4 through (22.7 deep) with Ø3.4/Ø4 counterbores
  at 30°/150°/270°. Perfect agreement.

**Consequences for our repo (all three sources contradict the old repo values):**
- `MOUNT_HALF = 11` (±11 4-hole square) is WRONG → flange has 6 tapped holes
  on a Ø31 bolt circle, 60° apart (any adjacent 4 are NOT a square; bracket
  must use the 6-hole pattern or a subset aligned to it).
- `MOUNT_HOLE_DEPTH = 6` is WRONG → taps are **3.5 mm deep**; usable thread
  ≈ 3 mm. `BOLT_ENGAGEMENT = 5` is impossible — cap at ~3 mm or go through
  the 3×Ø4 clearance holes with nuts.
- Gearbox length is ratio-tier dependent. The drawing table maps ratios
  6.3/10/19/30/56…270/506–810 → L 19/22/24/26.5/29; column alignment puts
  **1:30 → L24** (to be confirmed against the purchased unit — caliper the
  gearbox barrel, 24 mm ⇒ LR24). Old `GEARBOX_BARREL_L = 22` belongs to the
  1:10 tier.

Other drawing values worth carrying into the constants sheet (caliper to
confirm): total body 70.2±0.4 (L=26.5 tier), shaft Ø6(−0.03)×15±0.2,
Ø12×5 shaft shoulder, encoder collar Ø33.2, rear boss Ø7.5, encoder section
22.7±0.2 / 19.6.

Rule: these files are visual/cross-check references. Mounting features on OUR
parts come from the constants sheet, driven by the caliper.
