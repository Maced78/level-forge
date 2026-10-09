"""Mechanic probes for the Sokoban blueprint: tiny levels run on the ORIGINAL engine."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from blueprints.sokoban_sg import adapter as A  # noqa: E402

PROBES = {}


def run(dsl, moves):
    p = A.write_temp(A.Level.from_dsl(dsl))
    try:
        return A.replay(p, moves)
    finally:
        os.unlink(p)


def probe(pid, claim, source):
    def deco(fn):
        PROBES[pid] = (claim, source, fn)
        return fn
    return deco


ROOM = "+ + + + + +\n+ * - - - +\n+ - @ - X +\n+ - - - - +\n+ + + + + +"


@probe("walk", "The player moves one cell onto floor", ("src/player.py", r"def update\(self, key=None\)"))
def _():
    f = run(ROOM, "R")["frames"]
    return f[1]["raw"][8] == "*" and f[1]["moved"] == 1


@probe("wall_blocks", "A wall blocks the player", ("src/player.py", r"isinstance\(target_elem\.obj, Obstacle\)"))
def _():
    f = run(ROOM, "U")["frames"]
    return f[1]["raw"] == f[0]["raw"] and f[1]["moved"] == 0


@probe("push", "Walking into a box pushes it one cell", ("src/box.py", r"def can_move\(self, move\)"))
def _():
    f = run(ROOM, "DR")["frames"]
    return f[2]["raw"][13:16] == "-*@"


@probe("box_blocked_by_wall", "A box against a wall cannot be pushed into it (walls are a Box subclass)",
       ("src/box.py", r"class Obstacle\(Box\)"))
def _():
    f = run("+ + + + +\n+ * @ + +\n+ - - X +\n+ + + + +", "R")["frames"]
    return f[1]["raw"] == f[0]["raw"]


@probe("box_blocked_by_box", "Two boxes in a line cannot be pushed together",
       ("src/box.py", r"if not isinstance\(target_elem\.obj, Box\)"))
def _():
    f = run("+ + + + + +\n+ * @ @ - +\n+ X - X - +\n+ + + + + +", "R")["frames"]
    return f[1]["raw"] == f[0]["raw"]


@probe("goal_marks_box", "A box pushed onto a goal becomes '$' and counts as delivered",
       ("src/box.py", r"target_elem\.char = '@' if not target_elem\.ground else '\$'"))
def _():
    f = run("+ + + + + +\n+ * @ X - +\n+ + + + + +", "R")["frames"]
    return "$" in f[1]["raw"] and "@" not in f[1]["raw"]


@probe("win_when_no_box_off_goal", "The level is complete exactly when no box is off a goal",
       ("src/game.py", r"def is_level_complete\(self\)"))
def _():
    f = run("+ + + + + +\n+ * @ X X +\n+ + + + + +", "R")["frames"]
    return f[0]["solved"] is False and f[1]["solved"] is True


@probe("box_leaves_goal", "A delivered box can be pushed off its goal again, un-solving the level",
       ("src/box.py", r"curr_elem\.char = '-' if not curr_elem\.ground else 'X'"))
def _():
    f = run("+ + + + + + +\n+ * @ X - - +\n+ + + + + + +", "RR")["frames"]
    return f[1]["solved"] and not f[2]["solved"]


@probe("bad_token_rejected", "An unknown token makes the loader abandon the level",
       ("src/game.py", r"raise ValueError\("))
def _():
    p = A.write_temp(A.Level(3, 3, [list("+++"), ["+", "*", "+"], list("+++")]))
    open(p, "w").write("+ + +\n+ ? +\n+ + +\n")
    try:
        return A.replay(p, "").get("status") == "load_error"
    finally:
        os.unlink(p)


def run_all():
    out = {}
    for pid, (claim, source, fn) in PROBES.items():
        try:
            out[pid] = {"claim": claim, "source": source, "passed": bool(fn())}
        except Exception as e:
            out[pid] = {"claim": claim, "source": source, "passed": False, "error": repr(e)}
    return out


if __name__ == "__main__":
    res = run_all()
    for pid, r in res.items():
        print(("PASS " if r["passed"] else "FAIL ") + pid + " - " + r["claim"] + " " + r.get("error", ""))
    sys.exit(0 if all(r["passed"] for r in res.values()) else 1)
