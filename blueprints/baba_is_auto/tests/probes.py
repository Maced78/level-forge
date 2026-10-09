"""Executable mechanic probes.

Each probe is a tiny level (DSL), a move string and an assertion over the
frame trace produced by the ORIGINAL engine.  provenance.json links every
blueprint claim to one of these probes; a claim is only marked "confirmed"
when its probe passes on the engine build being analysed.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from blueprints.baba_is_auto import adapter as A  # noqa: E402


def run(dsl, moves):
    path = A.write_temp(A.Level.from_dsl(dsl))
    try:
        return A.replay(path, moves)["frames"]
    finally:
        os.unlink(path)


def pos(frame, name):
    return sorted((c["x"], c["y"]) for c in frame["cells"] if c["name"] == A.tok_to_name(name))


def has(frame, name):
    return bool(pos(frame, name))


PROBES = {}


def probe(pid, claim):
    def deco(fn):
        PROBES[pid] = (claim, fn)
        return fn
    return deco


@probe("text_always_push", "Every text tile is pushable without any rule")
def _():
    f = run("BABA IS YOU . .\nbaba ROCK . . .", "R")
    return pos(f[-1], "ROCK") == [(2, 1)] and pos(f[-1], "baba") == [(1, 1)]


@probe("edge_blocks", "The map edge blocks movement; nothing leaves the grid")
def _():
    f = run("BABA IS YOU\nbaba . .", "LLD")
    return pos(f[-1], "baba") == [(0, 1)]


@probe("stop_blocks", "X IS STOP blocks entry into X's cell")
def _():
    f = run("BABA IS YOU . .\nWALL IS STOP . .\nbaba wall . . .", "R")
    return pos(f[-1], "baba") == [(0, 2)]


@probe("no_rule_no_block", "An icon with no property is walked over (shares the cell)")
def _():
    f = run("BABA IS YOU .\nbaba wall . .", "R")
    return pos(f[-1], "baba") == [(1, 1)] and pos(f[-1], "wall") == [(1, 1)]


@probe("push_moves", "X IS PUSH objects are pushed one cell by the mover")
def _():
    f = run("BABA IS YOU . .\nROCK IS PUSH . .\nbaba rock . . .", "R")
    return pos(f[-1], "rock") == [(2, 2)] and pos(f[-1], "baba") == [(1, 2)]


@probe("push_chain", "A line of pushable things moves together")
def _():
    f = run("BABA IS YOU . .\nROCK IS PUSH . .\nbaba rock rock . .", "R")
    return pos(f[-1], "rock") == [(2, 2), (3, 2)]


@probe("push_chain_blocked", "A push chain that hits the edge or STOP blocks the mover")
def _():
    f = run("BABA IS YOU .\nROCK IS PUSH .\n. baba rock rock", "R")
    return pos(f[-1], "baba") == [(1, 2)] and pos(f[-1], "rock") == [(2, 2), (3, 2)]


@probe("push_overrides_stop", "PUSH overrides STOP on the same instance")
def _():
    f = run("BABA IS YOU . .\nROCK IS PUSH . .\nROCK IS STOP . .\nbaba rock . . .", "R")
    return pos(f[-1], "rock") == [(2, 3)]


@probe("win_on_overlap", "The game is WON when a YOU instance shares a cell with a WIN instance")
def _():
    f = run("BABA IS YOU\nFLAG IS WIN\nbaba flag .", "R")
    return f[0]["state"] == "PLAYING" and f[-1]["state"] == "WON"


@probe("win_self", "X IS YOU plus X IS WIN wins as soon as a turn is processed")
def _():
    f = run("BABA IS YOU .\nBABA IS WIN .\nbaba . . .", "R")
    return f[-1]["state"] == "WON"


@probe("load_state_not_evaluated", "Win/lose is evaluated only when a turn is processed, not at load")
def _():
    f = run("BABA IS YOU .\nBABA IS WIN .\nbaba . . .", "")
    return f[0]["state"] == "PLAYING"


@probe("no_you_is_lost", "With no YOU instance left the play state becomes LOST")
def _():
    g = run(". . . .\nBABA IS YOU .\n. baba . .", "U")
    return g[-1]["state"] == "LOST" and not g[-1]["rules"]


@probe("rule_same_turn", "A rule completed by a push is active at the end of that same turn")
def _():
    k = run("BABA IS YOU .\nFLAG IS . .\n. . WIN .\n. . baba .", "U")
    return "FLAG IS WIN" in k[-1]["rules"] and "FLAG IS WIN" not in k[0]["rules"]


@probe("rule_reading_order", "Rules are read left-to-right and top-to-bottom only")
def _():
    f = run("BABA IS YOU . .\nWIN IS FLAG . .\nFLAG . . . .\nIS . baba . .\nWIN . . . .", "")
    return sorted(f[0]["rules"]) == ["BABA IS YOU", "FLAG IS WIN"]


@probe("sink_destroys_both", "SINK removes every instance in an occupied sink cell, including the sinker")
def _():
    f = run("BABA IS YOU . .\nROCK IS PUSH . .\nWATER IS SINK . .\nbaba rock water . .", "R")
    return not has(f[-1], "rock") and not has(f[-1], "water") and pos(f[-1], "baba") == [(1, 3)]


@probe("sink_text", "Text pushed onto a SINK object is destroyed with it")
def _():
    f = run("BABA IS YOU . .\nWATER IS SINK . .\nbaba KEKE water . .", "R")
    return not has(f[-1], "KEKE") and not has(f[-1], "water")


@probe("sink_player", "A YOU instance entering a SINK cell is destroyed (LOST if it was the last)")
def _():
    f = run("BABA IS YOU . .\nWATER IS SINK . .\nbaba water . . .", "R")
    return f[-1]["state"] == "LOST"


@probe("defeat_removes_you", "DEFEAT removes overlapping YOU instances; the DEFEAT object stays")
def _():
    f = run("BABA IS YOU . .\nSKULL IS DEFEAT . .\nbaba skull . . .", "R")
    return f[-1]["state"] == "LOST" and has(f[-1], "skull")


@probe("hot_melt", "A HOT instance removes MELT instances in its cell")
def _():
    f = run("BABA IS YOU . . .\nLAVA IS HOT . . .\nBABA IS MELT . . .\nbaba lava . . . .", "R")
    return f[-1]["state"] == "LOST" and has(f[-1], "lava")


@probe("transform", "X IS Y turns every X into Y when a turn is processed")
def _():
    f = run("BABA IS YOU . .\nROCK IS FLAG . .\nbaba . rock . .", "L")
    return not has(f[-1], "rock") and pos(f[-1], "flag") == [(2, 2)]


@probe("you_swap", "Replacing the subject of 'X IS YOU' hands control to the new noun the same turn")
def _():
    f = run(". baba . . .\n. KEKE . . keke\n. BABA IS YOU .\n. . . . .", "D")
    return f[-1]["rules"] == ["KEKE IS YOU"] and f[-1]["player_icon"] == "ICON_KEKE" \
        and f[-1]["state"] == "PLAYING"


@probe("rail_immovable", "A vertical rule stacked from row 0 in column 0 cannot be moved or broken")
def _():
    lv = "BABA . . .\nIS . . .\nYOU . . .\n. . . .\n. baba . ."
    ok = True
    for moves in ("LU", "ULLL", "UUULLL", "LUUUU", "UUUULDD"):
        f = run(lv, moves)
        ok &= f[-1]["rules"] == ["BABA IS YOU"] and pos(f[-1], "BABA") == [(0, 0)]
    return ok


@probe("unsupported_inert", "Property words with no runtime hook (e.g. PULL, TELE) form rules but do nothing")
def _():
    f = run("BABA IS YOU . .\nROCK IS PULL . .\n. rock baba . .", "R")
    return pos(f[-1], "rock") == [(1, 2)]


@probe("and_chain", "AND chains expand to independent rules")
def _():
    f = run("BABA IS YOU AND WIN\nbaba . . . .", "")
    return sorted(f[0]["rules"]) == ["BABA IS WIN", "BABA IS YOU"]


@probe("stacked_layers", "Extra layers of a level file stack objects in the same cell")
def _():
    lv = A.Level.from_dsl("BABA IS YOU\nbaba+tile . .")
    return lv.to_native().count("\n") == 5 and len(run("BABA IS YOU\nbaba+tile . .", "")[0]["cells"]) == 5


@probe("multi_you", "Every YOU instance moves on each input")
def _():
    f = run("BABA IS YOU .\nbaba . baba .", "R")
    return pos(f[-1], "baba") == [(1, 1), (3, 1)]


def loader_rejects(text):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(text)
    try:
        return A.replay(fh.name, "").get("status") == "load_error"
    finally:
        os.unlink(fh.name)


@probe("loader_rejects_bad_dims", "The loader rejects a missing or zero-sized header")
def _():
    return loader_rejects("0 3\n4 67 77\n") and loader_rejects("x y\n4\n")


@probe("loader_rejects_sentinels", "Category sentinel IDs (0, 66, 76, 110) and out-of-range IDs are rejected")
def _():
    return all(loader_rejects(f"3 1\n4 67 {v}\n") for v in (0, 66, 76, 110, 180, -1))


@probe("loader_rejects_count", "Tile count must be a whole number of WxH layers, at most 3")
def _():
    row = "4 67 77\n"
    return loader_rejects("3 1\n4 67\n") and loader_rejects("3 1\n" + row * 4) \
        and not loader_rejects("3 1\n" + row * 3)


@probe("loader_rejects_nonint", "Non-integer tile tokens are rejected")
def _():
    return loader_rejects("3 1\n4 IS 77\n")


def run_all():
    out = {}
    for pid, (claim, fn) in PROBES.items():
        try:
            ok = bool(fn())
            out[pid] = {"claim": claim, "passed": ok}
        except Exception as e:  # a crashing probe is a failed probe
            out[pid] = {"claim": claim, "passed": False, "error": repr(e)}
    return out


if __name__ == "__main__":
    res = run_all()
    for pid, r in res.items():
        print(("PASS " if r["passed"] else "FAIL ") + pid + " - " + r["claim"] + (" " + r.get("error", "")))
    sys.exit(0 if all(r["passed"] for r in res.values()) else 1)
