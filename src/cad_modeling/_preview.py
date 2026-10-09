"""Quick multi-view render of the assembly for visual verification.

Known limitation: svgpathtools raises AssertionError while projecting a
degenerate full-circle edge, which currently hits the wheels, motors and
brackets in every view. Those children are skipped with a warning instead
of failing the whole export -- each SVG's console line names exactly what
is missing, so the renders can never silently lie.
"""
import os

from build123d import Axis
from build123d.exporters import ExportSVG

from .balance_bot import build_assembly

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "output")

# (name, ((axis, degrees), ...)) -- rotations applied in order
VIEWS = [
    ("top", ()),
    ("front", ((Axis.X, 90),)),   # look along Y -> XZ plane
    ("side", ((Axis.Y, 90),)),    # look along X -> YZ plane
]


def export_views(assembly) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, rotations in VIEWS:
        view = assembly
        for axis, degrees in rotations:
            view = view.rotate(axis, degrees)
        svg = ExportSVG()
        skipped = []
        for child in view.children:
            try:
                svg.add_shape(child)
            except AssertionError:
                skipped.append(child.label or type(child).__name__)
        svg.write(os.path.join(OUT_DIR, f"balance_bot_{name}.svg"))
        note = f" (skipped: {', '.join(skipped)})" if skipped else ""
        print(f"wrote balance_bot_{name}.svg{note}")


if __name__ == "__main__":
    export_views(build_assembly())
