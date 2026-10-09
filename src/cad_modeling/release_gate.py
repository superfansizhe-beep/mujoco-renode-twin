"""Physical-release audit for the balance-bot CAD model.

The geometry tests answer whether the current model is internally coherent.
They cannot answer whether a particular bought part, material, connector, or
fastener matches the model. This module keeps those evidence gaps explicit
and provides a deterministic command that can gate a fabrication release.

Run it with::

    python -m cad_modeling.release_gate

The command exits non-zero while any release blocker remains. It is
intentionally separate from the geometry test suite: a provisional model is
useful for layout and twin work, but must not be mistaken for cut-ready CAD.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ReleaseItem:
    """One evidence item that must be closed before cutting or assembly."""

    key: str
    status: str
    source: str
    action: str


# Keep this registry small and tied to an actionable source location. A
# status is deliberately not inferred from a comment scan: changing prose
# must not silently turn a physical blocker into a release approval.
RELEASE_ITEMS: tuple[ReleaseItem, ...] = (
    ReleaseItem(
        "motor_shaft_eccentricity",
        "CONFLICT",
        "src/cad_modeling/jgb37_520.py:20-24",
        "Caliper the bought motor and resolve the 7 mm STEP versus 5.5 mm drawing offset.",
    ),
    ReleaseItem(
        "motor_rear_length",
        "SHEET",
        "src/cad_modeling/jgb37_520.py:58-62",
        "Measure the encoder/rear section of the bought motor before fixing the housing length.",
    ),
    ReleaseItem(
        "wheel_size_and_hub",
        "GUESS",
        "src/cad_modeling/wheel.py:10-21",
        "Measure wheel diameter, width, bore, D-flat engagement, hub width, and setscrew layout.",
    ),
    ReleaseItem(
        "battery_envelope",
        "PROVISIONAL",
        "src/cad_modeling/deck.py:165-170",
        "Measure the pack, leads, connector, and buckle as installed.",
    ),
    ReleaseItem(
        "pcb_mounting_patterns",
        "PROVISIONAL",
        "src/cad_modeling/deck.py:34-40",
        "Measure the purchased driver and controller boards or use a measured carrier plate.",
    ),
    ReleaseItem(
        "sonar_bracket",
        "GUESS",
        "src/cad_modeling/sensors.py:32-38",
        "Caliper the actual bracket and confirm the sensor mounting side and tab pattern.",
    ),
    ReleaseItem(
        "line_bar_interface",
        "PROVISIONAL",
        "src/cad_modeling/sensors.py:41-48",
        "Caliper the line bar and confirm its hole pattern, height, and sensor pitch.",
    ),
    ReleaseItem(
        "connectors_and_harness",
        "MISSING",
        "src/cad_modeling/ASSEMBLY.md:50-66",
        "Add connector envelopes, bend radii, strain relief, and a serviceable cable route.",
    ),
    ReleaseItem(
        "plate_strength_and_material",
        "DESIGN_REVIEW",
        "src/cad_modeling/ASSEMBLY.md:118-123",
        "Choose the final plate material and verify bracket loads, fastener torque, and impact margin.",
    ),
    ReleaseItem(
        "motor_driver_thermal",
        "UNRESOLVED",
        "src/cad_modeling/ASSEMBLY.md:173-182",
        "Select a driver that survives stall current and model its footprint and heat path.",
    ),
    ReleaseItem(
        "mass_measurements",
        "WEIGH_PENDING",
        "bot/mass_properties.py:24-42",
        "Weigh the wheels, line bar, hardware, pack, and boards, then refresh CoM and trim inputs.",
    ),
    ReleaseItem(
        "physics_inertia",
        "APPROXIMATE",
        "bot/mjcf.py:12-20",
        "Export measured/CAD mass properties and replace primitive inertias and placeholder wheel contact.",
    ),
)


def release_blockers() -> tuple[ReleaseItem, ...]:
    """Return the items that currently prevent a physical release."""

    return RELEASE_ITEMS


def is_releasable() -> bool:
    """Return whether the registry has no open physical-release items."""

    return not release_blockers()


def render_report() -> str:
    """Render a stable human-readable audit report."""

    blockers = release_blockers()
    lines = [
        "CAD physical-release audit: "
        + ("READY" if not blockers else f"BLOCKED ({len(blockers)} items)"),
    ]
    for item in blockers:
        lines.append(f"- [{item.status}] {item.key}: {item.action} ({item.source})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        action="store_true",
        help="write the release registry as machine-readable JSON",
    )
    args = parser.parse_args(argv)
    if args.json:
        print(json.dumps([asdict(item) for item in RELEASE_ITEMS], indent=2))
    else:
        print(render_report())
    return 0 if is_releasable() else 1


if __name__ == "__main__":
    raise SystemExit(main())
