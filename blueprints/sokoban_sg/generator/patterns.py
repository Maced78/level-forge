"""Level construction for Sokoban: a walled room, inner walls, goals, boxes, player.
Placement is randomised under structural constraints; the solver is the judge."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .. import adapter as A


class PlanError(Exception):
    def __init__(self, explanation, cycle=None, suggestions=(), kind="layout"):
        super().__init__(explanation)
        self.explanation, self.cycle, self.suggestions, self.kind = explanation, cycle or [], list(suggestions), kind


@dataclass
class Plan:
    width: int = 7
    height: int = 6
    boxes: int = 1
    goals: int = 1
    walls: int = 2
    notes: list = field(default_factory=list)

    def describe(self):
        return f"{self.width}x{self.height} room, {self.boxes} box(es), {self.goals} goal(s), {self.walls} inner wall(s)"


def check_plan(plan: Plan):
    if plan.boxes > plan.goals:
        raise PlanError(
            f"{plan.boxes} boxes but only {plan.goals} goal(s): the engine reports a win only when no box is off a "
            f"goal (Game.is_level_complete), and a goal cell holds one box, so this level can never be won.",
            kind="unsatisfiable_counts",
            suggestions=[f"use at least {plan.boxes} goals", f"use at most {plan.goals} box(es)"])
    return True


def build(plan: Plan, rng: random.Random) -> A.Level:
    check_plan(plan)
    W, H = plan.width, plan.height
    grid = [["+" if x in (0, W - 1) or y in (0, H - 1) else "-" for x in range(W)] for y in range(H)]
    inner = [(x, y) for x in range(1, W - 1) for y in range(1, H - 1)]
    rng.shuffle(inner)
    need = plan.walls + plan.goals + plan.boxes + 1
    if need > len(inner) - 2:
        raise PlanError("the room is too small for everything that must be placed in it",
                        suggestions=["increase the level size"])
    for x, y in [inner.pop() for _ in range(plan.walls)]:
        grid[y][x] = "+"
    for x, y in [inner.pop() for _ in range(plan.goals)]:
        grid[y][x] = "X"
    # boxes away from the outer ring's corners is left to the solver; just avoid starting on a goal
    def cornered(x, y):      # a box with walls on two perpendicular sides can never move again
        wall = lambda a, b: grid[b][a] == "+"
        return (wall(x - 1, y) or wall(x + 1, y)) and (wall(x, y - 1) or wall(x, y + 1))
    placed = 0
    while placed < plan.boxes:
        free = [p for p in inner if not cornered(*p)]
        if not free:
            raise PlanError("no cell left where a box could still be pushed", suggestions=["use fewer inner walls"])
        x, y = free[-1]
        inner.remove((x, y))
        grid[y][x] = "@"
        placed += 1
    x, y = inner.pop()
    grid[y][x] = "*"
    lv = A.Level(W, H, grid)
    lv.meta = {"plan": plan.describe(), "notes": plan.notes}
    return lv


def transpose(level: A.Level) -> A.Level:
    g = [list(r) for r in zip(*level.grid)]
    return A.Level(level.height, level.width, g, dict(level.meta))
