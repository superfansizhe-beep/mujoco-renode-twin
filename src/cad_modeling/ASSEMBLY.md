# Lowered disc assembly — 2026-09-29

The housing now sits lower around the wheels, with dedicated side recesses.
The battery lies lengthwise between the motor bracket bases, the main control
PCB occupies the top tier, and the MPU6050 has a defined underside mount.
This is a verified CAD arrangement with provisional bought-part envelopes;
actual component measurements are still required before releasing the cuts.

## Frame and principal dimensions

All coordinates below are millimeters in the upright assembly: X is width,
+Y is forward and +Z is up. The floor is Z=0; both output shafts are at Z=40.

| Item | Revised arrangement | Original reference |
|---|---|---|
| Lower disc midplane | Z=58; faces 56.5 / 59.5 | Z=69.5 |
| Upper disc midplane | Z=89; faces 87.5 / 90.5 | Z=110.5 |
| Tier spacers | Four 28 mm columns, X=±60, Y=±45 | 38 mm columns |
| Disc stock | D190 × 3; two identical recessed profiles | D160.4 × 3 circular discs |
| Wheel axle spacing | 200.4; wheel centers X=±100.2 | Shoulder seating now included |
| Wheel envelopes | D80 × 25, inner faces X=±87.7 | Purchased wheel still to measure |
| Overall modeled envelope | 225.4 wide × 190 long × 96.5 high | Excludes unmodeled connectors |

The larger circular blank lets the housing extend into the wheel band while
retaining mounting material. Both side pockets start at |X|=84.7, span Y=±43,
and have R2 inner corners. Direct shape-distance checks establish at least
3 mm between either disc and either wheel. Separate bracket relief starts
at |X|=81.7, spans Y=±21 and uses R1 corners; it clears the vertical plate
and bend while leaving the base-bolt seats intact.

The motor datum is its output shaft, rather than the gearbox center. The
supplied LR24 STEP has 7 mm eccentricity: gearbox centers are at Z=33 on
both sides, with output shafts at Z=40. The left assembly rotates around Z,
so its eccentricity and bracket base stay in the same vertical orientation.
The separate family drawing gives 5.5 mm; measure the bought variant.

## Modules and their mounts

| Module | Location and mounting |
|---|---|
| Battery | Center (0, +1, 71.5), mounted footprint 34 X × 106 Y × 22 Z. Bottom 60.5, top 82.5. |
| Main control PCB | Center (0, 0, 95), above the upper disc on 3 mm spacers. Modeled top 96.5 is the assembly's highest point. |
| Motor driver | Center (0, −66, 64), lower rear, on 3 mm spacers. Footprint 21 × 16. |
| MPU6050 / GY-521 | Board centered at X=Y=0 under the lower disc. Board bottom 50.5, component-envelope top 53.0. Component face upward; choose a low-profile right-angle connector exiting toward −Y. |
| Sonar | Lower front, bracket face at Y=+67. Compact 25 mm bracket, feet at (±20, +64). |
| Line sensor | Under the lower disc at Y=−42, two 28 mm posts at X=±21.025. Sensor face Z=15. |

The battery's long axis is along Y to clear the bracket bases and their
fasteners. Its rear edge is Y=−52; the driver begins at Y=−58, leaving a
6 mm nominal gap. Keep battery connectors and their bend radius in the
open side corridors rather than projecting toward the driver. The model
does not yet include the actual battery leads, connector or buckle.

A 1 mm anti-slip pad supports the pack. Two 10 mm straps pass across its
short axis, at Y=−27 and +29. The four through slots are centered at
(±21, −27) and (±21, +29), each 3 mm wide along X and 22 mm long along Y.
Each slot leaves 2.5 mm to the pack footprint. The retained pack reaches
Z=83.5, leaving 4 mm below the upper disc. Select flat straps and keep the
buckle beside the pack to preserve that clearance. Do not compress the
pack into the upper plate.

The loom slot is at (−40, +32), 22 × 8 with its long axis along X. Both
discs carry it, providing a route to the top PCB beside the battery.
Strain-relieve the battery and motor harnesses to the structure; route
motor power wiring around the central IMU and keep the IMU connector
unloaded by the harness. A measured connector envelope must be added to
the next fabrication check.

The driver and main PCB footprints and mounting patterns remain
provisional. Their four M2.5 mounting axes are respectively (±8, −66±5)
and (±15, ±10). Measure the purchased boards before machining those holes,
or use a carrier with the correct pattern. Do not drill a populated PCB to
match a placeholder pattern.

## Dedicated MPU6050 attachment

The supplied GY-521 STEP establishes a 20.35 × 15.65 mm outline, 1 mm PCB,
and two D3 mounting holes at (−8.175, +5.825) and (+8.175, +5.825).
The corresponding disc holes are D2.9. Two OD4 × 5 mm double-female M2.5
spacers bear between the PCB top at Z=51.5 and disc underside at Z=56.5.

Use separate M2.5 × 4 upper and M2.5 × 3 lower screws. The modeled button
heads are D4.7 × 1.5, consistent with the [Accu specification](https://www.accu.co.uk/socket-button-screws/8265-SSB-M2-5-3-A4).
The upper heads sit in D5 × 1.8 deep counterbores machined from the disc's
top face. Their tops finish 0.3 mm below the deck and cannot press into
the battery pad. The counterbores leave 1.2 mm of plate; avoid excessive
preload and verify this attachment in the chosen plate material.

Upper engagement is 2.8 mm, lower engagement 2 mm, and the screw tips
remain 0.2 mm apart. Use spacers with compatible continuous internal
threads and verify tip clearance against actual screw tolerances.
The board is mounted rigidly near the axle; it is not placed on loose foam.
Confirm the printed sensor axes and firmware mounting rotation with a
bench tilt test. The twin's representative IMU site is (0, 0, 51.75);
this is the board envelope center, not a measured silicon die location.

## Assembly and manufacturing

1. Measure the motors, brackets, wheel hubs, pack, both control PCBs,
   connectors and sonar bracket. Update their CAD constants first.
2. Cut the two identical through profiles in 3 mm stock. Machine the two
   upper-face MPU6050 counterbores separately, retaining the same XY origin.
3. Install the underside IMU and its recessed upper screws before laying
   down the pad and battery. Fit the line carrier and lower-tier harness.
4. Seat the lower disc **under** both bracket bases. Their eight base-hole
   axes are X=±51.2 and ±75.2, Y=±15. Use load-spreading hardware compatible
   with the plate, rather than relying on friction against a perforated rim.
5. Install motors and shaft hubs. The flange has six M3 positions on D31;
   usable thread engagement is capped at 3 mm. Check the entire screw,
   washer and head stack against the 5 mm shoulder-to-wheel seating space.
   A tall socket head can consume that space even when the disc clears.
6. Fit the rear driver, front sonar, four tier columns and top control PCB.
   Route cables through the side slot, then check pack access and wiring
   clearance with the upper disc installed.
7. Turn the wheels by hand through a full revolution, check runout and hub
   retention, and tilt the assembled chassis through its intended range.

The existing PMMA assumption remains in the mass calculation. For repeated
impacts, evaluate a tougher plate material and local load spreading around
the bracket bases. Changing thickness or material requires a new mass and
counterbore review; a 1.8 mm counterbore must not be reused blindly in thinner
stock. Plate strength, fastener torque and hub torque capacity are not
proved by the geometric tests.

Generated files (into the gitignored `output/`, regenerate via the
command below):

- `output/balance_bot.step` (assembly) and `output/balance_bot.glb` (binary GLB).
- `output/fabricated_parts.step` (disc, cut two).
- `output/deck_disc_cut.dxf`: millimeters; 121 D3.4 and ten D2.9 through holes, plus slots and perimeter.
- `output/deck_disc_top_counterbores.dxf`: two D5 circles only; depth 1.8 from the top. **These are not D5 through holes.**
- [Interactive review](http://127.0.0.1:8127/output/low_cog/index.html) with assembly, battery, underside, top and front views. Its local server is bound to 127.0.0.1.

Regenerate the CAD and web model from the workspace in PowerShell:

```powershell
& '.\.venv\Scripts\python.exe' -m cad_modeling.balance_bot
& '.\.venv\Scripts\python.exe' -m tests.test_assembly
& '.\.venv\Scripts\python.exe' -m cad_modeling.release_gate
```

The geometry test is allowed to pass with provisional envelopes so layout and
twin work can continue. The release audit is a separate physical gate and
returns a non-zero status while any bought-part measurement, harness,
structure, driver, or mass-property item remains open.

## Estimated balance and verification

The updated CAD-derived mass table estimates total mass at 1.057 kg and
whole-vehicle CoM at (0.043, 0.145, 51.848) mm. The original audit estimated
Z=58.685 mm: the new estimate is lower by 6.837 mm, roughly 12%. This
comparison includes corrected motor/bracket datums and revised mass
estimates, so it is not a measurement isolating deck lowering alone.
Weigh the purchased parts and check the assembled balance point.

The calculated trim changes from −16.74° to approximately +0.70°. The
Python controller gains were recomputed for the revised lumped plant,
and the generated twin firmware header was refreshed. A lower CoM does
not eliminate the need to tune and validate a balancing controller.

CAD verification: **35/35 checks pass**, including actual vendor shaft axes,
flange/base-hole alignment, mounting support, wheel distance, battery and
strap clearance, recessed IMU hardware, both assembly modes, and at least
3 mm clearance to the floor through ±12° pitch. Pairwise geometry tests
use placed OCCT shapes directly. The supplied motor's M2 screw-head lobes
protrude 0.0669 mm beyond its flange, producing 0.0506 mm³ reference-model
overlap per bracket; the specific flange check permits up to 0.1 mm³.
The general assembly check rejects overlaps greater than 1 mm³.

The GLB header and length were checked, and both DXFs were read back to
verify units, hole diameters and the separate counterbore coordinates.
Assembly, battery, underside IMU and front views were inspected in the
browser against the new export.

The current standalone validation runs report **35/35 assembly checks** and
**25/25 twin checks**. The earlier revision called out an 8/8 focused subset;
the full-suite count is recorded here so the validation scope is unambiguous.
The measured kick reaches about 11.5° deviation from trim and recovers without
falling. The kick gate now measures deviation from trim, so the old large
resting lean cannot count as an excitation. These are CAD/software gates:
Renode firmware, physical wiring, thermal behavior and a built assembly have
not been validated in this mechanical revision.

The physical-release audit is machine-readable with
`python -m cad_modeling.release_gate --json`. It keeps unresolved interfaces
explicit instead of treating a passing geometry test as approval to cut
material.

One particularly important component-selection issue affects practical use: the motor's
[manufacturer specifications](https://www.hiwonder.com/products/hall-encoder-dc-geared-motor)
give approximately 3.2 A stall current, while the
[TB6612FNG datasheet](https://toshiba.semicon-storage.com/info/TB6612FNG_datasheet_en_20141001.pdf?did=10660&prodName=TB6612FNG)
lists 1 A in its operating range without PWM, 1.2 A average as an absolute
limit, and 3.2 A only for a 10 ms single pulse. Confirm current limiting and the real
driver's thermal capability, or select a suitable driver and update its
reserved mounting footprint. The CAD's small driver block is not proof
that the electrical system can sustain a stalled motor.
