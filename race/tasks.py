"""Race exam tasks -- the paper's missions, registered over the field.

race.track is the field (nodes, tape pieces, projection math) and knows
nothing about tasks; this module is the exam-paper side and the only
place tasks are defined. Each Task carries its per-lap legs as travel-
oriented field segments plus the sheet's time cap, and route = legs *
laps -- so "task 4 = the crossed route x 4" is data, not code.
"""
from dataclasses import dataclass

from . import track
from .track import Oriented


@dataclass(frozen=True)
class Task:
    id: int
    title: str
    limit_s: float | None       # the sheet's cap; None = timed event
    laps: int
    legs: tuple                 # per-lap oriented segments

    @property
    def route(self) -> list:
        """Full travel-oriented segment list, laps included."""
        return list(self.legs) * self.laps


_LOOP = (Oriented(track.AB), Oriented(track.BC),
         Oriented(track.CD), Oriented(track.DA))
_CROSSED = (Oriented(track.AC), Oriented(track.BC, reverse=True),
            Oriented(track.BD), Oriented(track.DA))

TASKS: dict[int, Task] = {
    1: Task(1, "A->B straight + stop", 15.0, 1,
            (Oriented(track.AB),)),
    2: Task(2, "A->B->C->D->A clockwise loop", 30.0, 1, _LOOP),
    3: Task(3, "A->C->B->D->A crossed loop", 40.0, 1, _CROSSED),
    4: Task(4, "task-3 route, 4 laps, fastest", None, 4, _CROSSED),
}


def task_route(task: int) -> list:
    """Travel-oriented segment list, repeated per lap count."""
    return TASKS[task].route


def task_spec(task: int) -> dict:
    t = TASKS[task]
    route = t.route
    # a beep at the end node of every segment; tasks 2-4 also start on A
    beeps = ["A"] * (0 if task == 1 else 1)
    for o in route:
        end = o.point(o.length)
        beeps.append(track.node_at(end[0], end[1], tol=0.02))
    return {
        "task": task,
        "title": t.title,
        "limit_s": t.limit_s,
        "laps": t.laps,
        "route": route,
        "beeps": beeps,
    }


def route_length(task: int) -> float:
    return sum(o.length for o in task_route(task))


if __name__ == "__main__":
    for n in sorted(TASKS):
        spec = task_spec(n)
        print(f"task {n}: {spec['title']:36s} "
              f"len={route_length(n) * 100:7.2f} cm "
              f"limit={spec['limit_s']} beeps={''.join(spec['beeps'])}")
