"""Race track geometry -- the smart-car exam field as pure math (SI m).

The 2024 national contest H sheet ("auto-driving smart car"): a white
field at least
220 x 120 cm whose ONLY markings are two symmetric black guide arcs,
radius 40 cm each, ~18 mm wide -- the sheet says the field may carry no
other marks. The four arc endpoints are the nodes A, B, C, D:

  field            220 x 120 cm, arcs centered (20 cm margin all round)
  nodes            A(60,100)  B(160,100)  C(160,20)  D(60,20)
  BC right arc     r=40 cm, center (160,60), B -> C through x=200   [tape]
  DA left arc      r=40 cm, center (60,60), D -> A through x=20     [tape]
  AB / CD straights   100 cm, the top and bottom node gaps       [no tape]
  AC / BD diagonals   sqrt(100^2+80^2) = 128.1 cm                [no tape]

Every figure dimension lands here exactly once: 40 + 40 = the two arc
radii, 100 = the A-B node gap, 60 + 60 = arc centers to the field
edges (half field), 120 / 220 = the field. The straights are NOT
tape: every straight leg of every task (A->B, C->D, A->C, B->D) is a
BLIND dead-reckoning leg across open white -- the exam's core skill.
The bar sees tape only on the arcs, meeting it 63 mm (one bar lead)
before each node. The task-3/4 figure-8 diagonals cross at the field
center (110,60), unmarked. The exam's task routes over these pieces
live in race/tasks.py.

Every projection returns (s, lat, psi): arc length along the segment,
signed lateral offset (+ = left of the direction of travel) and travel
heading (world atan2 frame). Curvature is +1/R for left (CCW) turns.
"""
import math

FIELD = (2.20, 1.20)        # X x Y, m (exam: at least 220 x 120 cm)
TAPE_HALF = 0.009           # m, 18 mm tape (exam spec ~1.8 cm)
TRIGGER_R = 0.05            # m, node trigger radius (exam sheet's 5 cm)

NODES = {
    "A": (0.60, 1.00),
    "B": (1.60, 1.00),
    "C": (1.60, 0.20),
    "D": (0.60, 0.20),
}


def _wrap(a: float) -> float:
    """Angle into [-pi, pi)."""
    a = (a + math.pi) % (2.0 * math.pi) - math.pi
    return a


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


class Straight:
    def __init__(self, name: str, p0: tuple, p1: tuple,
                 taped: bool = False) -> None:
        self.name = name
        self.p0, self.p1 = p0, p1
        self.taped = taped
        self.length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        self._ux = (p1[0] - p0[0]) / self.length
        self._uy = (p1[1] - p0[1]) / self.length
        self._psi = math.atan2(p1[1] - p0[1], p1[0] - p0[0])

    def project(self, x: float, y: float) -> tuple:
        t = (x - self.p0[0]) * self._ux + (y - self.p0[1]) * self._uy
        lat = (x - self.p0[0]) * -self._uy + (y - self.p0[1]) * self._ux
        return _clamp(t, 0.0, self.length), lat, self._psi

    def point(self, s: float) -> tuple:
        return (self.p0[0] + self._ux * s, self.p0[1] + self._uy * s)

    def heading_at(self, s: float) -> float:
        return self._psi

    def curvature_at(self, s: float) -> float:
        return 0.0

    def covers(self, x: float, y: float, half: float) -> bool:
        """Inside this tape piece's black rectangle (square ends)."""
        t = (x - self.p0[0]) * self._ux + (y - self.p0[1]) * self._uy
        lat = (x - self.p0[0]) * -self._uy + (y - self.p0[1]) * self._ux
        return -half <= t <= self.length + half and abs(lat) <= half


class Arc:
    """Circular arc from angle a0 to a1 (atan2 frame about `center`);
    a1 < a0 means the sweep runs clockwise."""

    def __init__(self, name: str, center: tuple, radius: float,
                 a0: float, a1: float, taped: bool = True) -> None:
        self.name = name
        self.c = center
        self.r = radius
        self.a0 = a0
        self.dir = 1.0 if a1 > a0 else -1.0
        self.span = abs(a1 - a0)
        self.length = radius * self.span
        self.taped = taped

    def _theta(self, s: float) -> float:
        return self.a0 + self.dir * (s / self.r)

    def project(self, x: float, y: float) -> tuple:
        dx, dy = x - self.c[0], y - self.c[1]
        r_pt = math.hypot(dx, dy)
        th = math.atan2(dy, dx)
        d = _wrap(th - self.a0) * self.dir
        if d < 0:
            d += 2.0 * math.pi
        if d <= self.span:
            s = self.r * d
        else:
            # outside the sweep: clamp to whichever END is angularly
            # nearer. The naive min(d, span) clamp sends points just
            # BEFORE the arc start (e.g. still on the previous segment
            # behind a node) the long way round to the far end -- on a
            # semicircle that fed the follower the far node's heading
            # and curvature for half a second at every node handoff
            s = 0.0 if (2.0 * math.pi - d) < (d - self.span) else self.length
        # +lat = left of travel: for a CCW sweep left points at the
        # center, for a CW sweep it points outward -- both are dir*(r-r_pt)
        lat = self.dir * (self.r - r_pt)
        return s, lat, self._theta(s) + self.dir * math.pi / 2.0

    def point(self, s: float) -> tuple:
        th = self._theta(s)
        return (self.c[0] + self.r * math.cos(th),
                self.c[1] + self.r * math.sin(th))

    def heading_at(self, s: float) -> float:
        return self._theta(s) + self.dir * math.pi / 2.0

    def curvature_at(self, s: float) -> float:
        return self.dir / self.r

    def covers(self, x: float, y: float, half: float) -> bool:
        dx, dy = x - self.c[0], y - self.c[1]
        r_pt = math.hypot(dx, dy)
        if abs(r_pt - self.r) > half:
            return False
        d = _wrap(math.atan2(dy, dx) - self.a0) * self.dir
        if d < 0:
            d += 2.0 * math.pi
        return d <= self.span


class Oriented:
    """A segment viewed in travel direction -- `reverse` flips s/lat/psi."""

    def __init__(self, seg, reverse: bool = False) -> None:
        self.seg = seg
        self.reverse = reverse
        self.length = seg.length
        self.taped = seg.taped
        self.name = seg.name + ("-" if reverse else "")

    def project(self, x: float, y: float) -> tuple:
        s, lat, psi = self.seg.project(x, y)
        if self.reverse:
            return self.length - s, -lat, _wrap(psi + math.pi)
        return s, lat, psi

    def point(self, s: float) -> tuple:
        return self.seg.point(self.length - s if self.reverse else s)

    def heading_at(self, s: float) -> float:
        psi = self.seg.heading_at(self.length - s if self.reverse else s)
        return _wrap(psi + math.pi) if self.reverse else psi

    def curvature_at(self, s: float) -> float:
        k = self.seg.curvature_at(s)
        return -k if self.reverse else k


# ---------------- the six route pieces (tape: the two arcs only) ----------------
AB = Straight("AB", NODES["A"], NODES["B"])
BC = Arc("BC", (1.60, 0.60), 0.40, math.pi / 2, -math.pi / 2)   # through x=2.00
CD = Straight("CD", NODES["C"], NODES["D"])
DA = Arc("DA", (0.60, 0.60), 0.40, -math.pi / 2, math.pi / 2 - 2 * math.pi)
AC = Straight("AC", NODES["A"], NODES["C"])
BD = Straight("BD", NODES["B"], NODES["D"])

TAPE = (BC, DA)              # the field's entire marking: two arcs

CROSSING = (1.10, 0.60)      # AC x BD intersection -- open white, no tape


def over_tape(x: float, y: float, half: float = TAPE_HALF) -> bool:
    """Tape-mask sample: True if the point sits on any arc's black."""
    return any(seg.covers(x, y, half) for seg in TAPE)


def node_at(x: float, y: float, tol: float = 0.01) -> str | None:
    for name, p in NODES.items():
        if math.hypot(x - p[0], y - p[1]) <= tol:
            return name
    return None


def polyline(seg, step: float = 0.02) -> list:
    """Sampled centerline for drawing (canvas/MJCF visuals)."""
    n = max(2, int(math.ceil(seg.length / step)) + 1)
    return [seg.point(seg.length * i / (n - 1)) for i in range(n)]


def tape_polylines(step: float = 0.02) -> list:
    """The taped arcs -- what the field actually shows."""
    return [(seg.name, polyline(seg, step)) for seg in TAPE]


def ghost_polylines(step: float = 0.02) -> list:
    """The untaped legs, for viewers only -- open white on the field."""
    return [(seg.name, polyline(seg, step))
            for seg in (AB, CD, AC, BD)]


if __name__ == "__main__":
    s, lat, psi = BC.project(2.00, 0.60)
    print(f"BC probe s={s:.3f} lat={lat:+.4f} psi={psi:.3f}")
