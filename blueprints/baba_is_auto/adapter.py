"""Game adapter for baba-is-auto (the game-specific half of a blueprint).

Everything the generic Level-Forge engine needs to know about this game goes
through this module: the level IR, native (de)serialisation, validation,
solving and replay.  The solver and the replay both run the ORIGINAL engine
(engine_build/babasolve links the unmodified game sources); nothing about the
game's rules is re-implemented in Python.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
ENGINE_DIR = ROOT / "engine_build"
SOLVER = ENGINE_DIR / "babasolve"
SPEC = json.loads((HERE / "game_spec.json").read_text())

ID = {e["name"]: e["id"] for e in SPEC["entities"]}
NAME = {e["id"]: e["name"] for e in SPEC["entities"]}
KIND = {e["name"]: e["kind"] for e in SPEC["entities"]}
SUPPORT = {e["name"]: e.get("support", "n/a") for e in SPEC["entities"]}
SENTINELS = set(SPEC["sentinels"].values())
EMPTY = ID["ICON_EMPTY"]
MAX_LAYERS = SPEC["level_format"]["max_layers"]
GEN_VOCAB = set(SPEC["generation_vocabulary"]["text"]) | {
    "ICON_" + n for n in SPEC["generation_vocabulary"]["nouns"]}


# --------------------------------------------------------------------------
# Level IR
# --------------------------------------------------------------------------
def tok_to_name(tok: str) -> str:
    """DSL token -> engine enum name.  UPPER = text tile, lower = icon."""
    if tok.startswith("ICON_"):
        return tok
    return tok if tok.isupper() else "ICON_" + tok.upper()


def name_to_tok(name: str) -> str:
    return name[5:].lower() if name.startswith("ICON_") else name


@dataclass
class Level:
    """Symbolic intermediate representation: a grid of object stacks."""
    width: int
    height: int
    cells: dict = field(default_factory=dict)  # (x, y) -> [engine enum names]
    meta: dict = field(default_factory=dict)

    def put(self, x, y, name):
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError(f"({x},{y}) outside {self.width}x{self.height}")
        self.cells.setdefault((x, y), []).append(tok_to_name(name))

    def at(self, x, y):
        return self.cells.get((x, y), [])

    def free(self, x, y):
        return 0 <= x < self.width and 0 <= y < self.height and not self.cells.get((x, y))

    def copy(self):
        return Level(self.width, self.height, {k: list(v) for k, v in self.cells.items() if v},
                     dict(self.meta))

    # --- DSL (human / LLM friendly) ---
    @staticmethod
    def from_dsl(text: str) -> "Level":
        rows = [r.split() for r in text.strip().splitlines() if r.strip()]
        w = len(rows[0])
        if any(len(r) != w for r in rows):
            raise ValueError("DSL rows have different lengths: " + str([len(r) for r in rows]))
        lv = Level(w, len(rows))
        for y, row in enumerate(rows):
            for x, cell in enumerate(row):
                if cell in (".", "_"):
                    continue
                for tok in cell.split("+"):
                    name = tok_to_name(tok)
                    if name not in ID:
                        raise ValueError(f"unknown entity '{tok}' at ({x},{y})")
                    lv.put(x, y, name)
        return lv

    def to_dsl(self) -> str:
        grid = [["+".join(name_to_tok(n) for n in self.at(x, y)) or "."
                 for x in range(self.width)] for y in range(self.height)]
        wd = max(len(c) for r in grid for c in r)
        return "\n".join(" ".join(c.ljust(wd) for c in r).rstrip() for r in grid)

    # --- native format (see level_schema.json) ---
    def to_native(self) -> str:
        layers = max([len(v) for v in self.cells.values()] + [1])
        if layers > MAX_LAYERS:
            raise ValueError(f"a cell stacks {layers} objects; the loader allows {MAX_LAYERS}")
        out = [f"{self.width} {self.height}"]
        for k in range(layers):
            for y in range(self.height):
                row = []
                for x in range(self.width):
                    st = self.at(x, y)
                    row.append(ID[st[k]] if k < len(st) else EMPTY)
                out.append(" ".join(f"{v:<4}" for v in row).rstrip())
        return "\n".join(out) + "\n"

    @staticmethod
    def from_native(text: str) -> "Level":
        toks = text.split()
        w, h = int(toks[0]), int(toks[1])
        vals = [int(t) for t in toks[2:]]
        lv = Level(w, h)
        for i, v in enumerate(vals):
            if v != EMPTY:
                lv.put((i % (w * h)) % w, (i % (w * h)) // w, NAME[v])
        return lv

    def texts(self):
        return [(x, y, n) for (x, y), st in self.cells.items() for n in st
                if not n.startswith("ICON_")]

    def icons(self):
        return [(x, y, n) for (x, y), st in self.cells.items() for n in st
                if n.startswith("ICON_")]


# --------------------------------------------------------------------------
# Engine access
# --------------------------------------------------------------------------
def engine_available() -> bool:
    return SOLVER.exists()


def _run(args, timeout):
    r = subprocess.run([str(SOLVER)] + [str(a) for a in args], capture_output=True,
                       text=True, timeout=timeout)
    return json.loads(r.stdout)


def solve(path, forbid=(), analyze=False, max_states=200000, max_ms=8000, wait=False):
    """Breadth-first search over engine states.  Returns the solver's JSON.

    status 'solved'      -> 'moves' is a shortest witness (proof: witness)
    status 'unsolvable'  -> the whole reachable state space was exhausted
    status 'unknown'     -> search stopped at the state/time bound
    """
    args = [path, "--max-states", max_states, "--max-ms", max_ms]
    for f in forbid:
        args += ["--forbid", f]
    if analyze:
        args.append("--analyze")
    if wait:
        args.append("--wait")
    try:
        return _run(args, timeout=max_ms / 1000 + 30)
    except subprocess.TimeoutExpired:
        return {"status": "unknown", "proof": "bounded", "moves": "", "length": 0,
                "states_explored": 0, "error": "solver wall-clock timeout"}


def replay(path, moves):
    """Frame-by-frame trace of `moves` in the original engine."""
    d = _run([path, "--replay", moves], timeout=60)
    if d.get("status") != "ok":
        return d
    for f in d["frames"]:
        f["rules"] = [" ".join(NAME[t] for t in r) for r in f["rules"]]
        f["cells"] = [{"x": c[0], "y": c[1], "name": NAME[c[2]], "dir": c[3], "id": c[4]}
                      for c in f["cells"]]
        f["player_icon"] = NAME.get(f["player_icon"], "?")
    return d


def replay_python_binding(path, moves):
    """Independent second check through the game's own Python binding."""
    sys.path.insert(0, str(ENGINE_DIR))
    try:
        import pyBaba  # noqa
    except Exception as e:  # binding not built
        return {"available": False, "error": str(e)}
    d = {"U": pyBaba.Direction.UP, "D": pyBaba.Direction.DOWN, "L": pyBaba.Direction.LEFT,
         "R": pyBaba.Direction.RIGHT, "W": pyBaba.Direction.NONE}
    try:
        g = pyBaba.Game(str(path))
    except RuntimeError as e:
        return {"available": True, "loaded": False, "error": str(e)}
    for m in moves:
        g.MovePlayer(d[m])
    return {"available": True, "loaded": True, "final_state": g.GetPlayState().name}


def write_temp(level: Level) -> str:
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, prefix="lvl_")
    f.write(level.to_native())
    f.close()
    return f.name


# --------------------------------------------------------------------------
# Trace analysis: which mechanics does a move sequence actually exercise?
# --------------------------------------------------------------------------
def analyse_trace(frames):
    ev = {"rule_changes": [], "win_rule_changes": [], "you_changes": [], "object_pushes": [],
          "text_pushes": [], "destroyed": [], "transformed": []}
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        ra, rb = set(a["rules"]), set(b["rules"])
        if ra != rb:
            ev["rule_changes"].append({"step": i, "added": sorted(rb - ra),
                                       "removed": sorted(ra - rb)})
            wa = {r for r in ra if r.endswith(" WIN")}
            wb = {r for r in rb if r.endswith(" WIN")}
            if wa != wb:
                ev["win_rule_changes"].append({"step": i, "before": sorted(wa), "after": sorted(wb)})
            ya = {r for r in ra if r.endswith(" YOU")}
            yb = {r for r in rb if r.endswith(" YOU")}
            if ya != yb:
                ev["you_changes"].append({"step": i, "before": sorted(ya), "after": sorted(yb)})
        you_types = {"ICON_" + r.split()[0] for r in a["rules"] if r.endswith("IS YOU")}
        pa = {c["id"]: c for c in a["cells"]}
        pb = {c["id"]: c for c in b["cells"]}
        gone = [c for oid, c in pa.items() if oid not in pb]
        for oid, c in pa.items():
            n = pb.get(oid)
            if n is None:
                ev["destroyed"].append({"step": i, "name": c["name"], "at": [c["x"], c["y"]]})
                # pushed into a neighbouring cell and destroyed there in the same turn
                if c["name"] not in you_types and any(
                        abs(g["x"] - c["x"]) + abs(g["y"] - c["y"]) == 1 for g in gone if g is not c):
                    key = "object_pushes" if c["name"].startswith("ICON_") else "text_pushes"
                    ev[key].append({"step": i, "name": c["name"], "destroyed": True})
                continue
            if n["name"] != c["name"]:
                ev["transformed"].append({"step": i, "from": c["name"], "to": n["name"]})
            if (n["x"], n["y"]) != (c["x"], c["y"]):
                if not c["name"].startswith("ICON_"):
                    ev["text_pushes"].append({"step": i, "name": c["name"]})
                elif c["name"] not in you_types:
                    ev["object_pushes"].append({"step": i, "name": c["name"]})
    return ev


def static_necessity(skill_id, initial_rules):
    """Source-level arguments that make a skill necessary without any search."""
    if skill_id == "win_condition_change" and not any(r.endswith(" WIN") for r in initial_rules):
        return ("no 'X IS WIN' rule is active in the initial state, and Game::CheckPlayState only reports "
                "WON for a YOU instance sharing a cell with a WIN instance: every winning play must first "
                "create a WIN rule")
    if skill_id == "rule_manipulation" and not any(r.endswith(" WIN") for r in initial_rules):
        return "no WIN rule is active initially, so at least one rule must be formed before any win"
    return None


DIFFICULTY_WEIGHTS = {"trap_bits": 2.0, "dead_ratio": 4.0, "rule_changes": 2.0, "sacrifices": 3.0}


def difficulty(solve_result, events):
    """Difficulty estimate that deliberately ignores solution length.

    trap_bits     -log2 of the chance that a player who, at every step of the shortest
                  solution, picks uniformly among the moves that change the board never makes
                  the level unwinnable.  5 bits = 1 chance in 32.
    dead_ratio    share of all reachable states from which the level can no longer be won.
    rule_changes  times the active rule set changes along the solution (ideas needed).
    sacrifices    rule words destroyed along the solution (a word used up as a resource).

    Only 'established' when the whole reachable state space was enumerated; otherwise the
    first two terms are unknown and no difficulty claim is made.
    """
    path, an = solve_result.get("path") or {}, solve_result.get("analysis") or {}
    established = bool(path.get("established")) and bool(an.get("complete"))
    sacrifices = sum(1 for d in events["destroyed"] if not d["name"].startswith("ICON_"))
    comp = {"trap_bits": round(-path.get("survival_log2", 0.0), 2) if established else None,
            "trap_states": path.get("trap_states") if established else None,
            "decision_points": path.get("decision_points") if established else None,
            "dead_ratio": round(an["dead_states"] / an["reachable_states"], 3) if established else None,
            "rule_changes": len(events["rule_changes"]), "sacrifices": sacrifices}
    w = DIFFICULTY_WEIGHTS
    score = None
    if established:
        score = round(w["trap_bits"] * comp["trap_bits"] + w["dead_ratio"] * comp["dead_ratio"]
                      + w["rule_changes"] * comp["rule_changes"] + w["sacrifices"] * comp["sacrifices"], 1)
    return {"established": established, "score": score, "components": comp, "weights": w}


def skill_exercised(skill_id, events, frames):
    """Was this skill used in the replayed solution? (game-specific reading of the trace)"""
    if skill_id == "hazard_defeat":
        return any(any(r.endswith(" DEFEAT") for r in f["rules"]) for f in frames)
    if skill_id == "hazard_sink":
        return any(any(r.endswith(" SINK") for r in f["rules"]) for f in frames) and bool(events["destroyed"])
    key = {"rule_manipulation": "rule_changes", "object_pushing": "object_pushes",
           "win_condition_change": "win_rule_changes", "you_change": "you_changes"}[skill_id]
    return bool(events[key])
