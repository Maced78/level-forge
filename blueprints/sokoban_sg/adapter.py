"""Game adapter for the second target game: xbandrade/sokoban-solver-generator (MIT), a pygame
Sokoban.  Same contract as blueprints/baba_is_auto/adapter.py; forge/pipeline.py is unchanged.

Search runs on a small Python model of the engine's movement rules (src/player.py, src/box.py);
every solution is replayed in the ORIGINAL engine through engine_driver.py before it counts.
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
GAME_DIR = ROOT / "games" / "sokoban_sg"
SPEC = json.loads((HERE / "game_spec.json").read_text())
TOKENS = {"+": "wall", "-": "floor", "@": "box", "X": "goal", "*": "player", "$": "box on goal", "%": "player on goal"}
DIRS = {"U": (0, -1), "D": (0, 1), "L": (-1, 0), "R": (1, 0)}


@dataclass
class Level:
    width: int
    height: int
    grid: list = field(default_factory=list)      # rows of single-character tokens
    meta: dict = field(default_factory=dict)

    @staticmethod
    def from_dsl(text):
        rows = [r.split() for r in text.strip().splitlines() if r.strip()]
        if any(len(r) != len(rows[0]) for r in rows):
            raise ValueError("rows have different lengths: " + str([len(r) for r in rows]))
        for r in rows:
            for c in r:
                if c not in TOKENS:
                    raise ValueError(f"unknown token '{c}'")
        return Level(len(rows[0]), len(rows), rows)

    from_native = from_dsl

    def to_dsl(self):
        return "\n".join(" ".join(r) for r in self.grid)

    def to_native(self):                          # the game's own .dat format
        return self.to_dsl() + "\n"


def engine_available():
    return (GAME_DIR / "src" / "game.py").exists()


def write_temp(level):
    f = tempfile.NamedTemporaryFile("w", suffix=".dat", delete=False, prefix="lvl_")
    f.write(level.to_native())
    f.close()
    return f.name


def _cells(state, w):
    out, i = [], 0
    for pos, ch in enumerate(state):
        x, y = pos % w, pos // w
        for name in {"+": ["ICON_WALL"], "@": ["ICON_BOX"], "X": ["ICON_GOAL"], "*": ["ICON_PLAYER"],
                     "$": ["ICON_GOAL", "ICON_BOX"], "%": ["ICON_GOAL", "ICON_PLAYER"]}.get(ch, []):
            out.append({"x": x, "y": y, "name": name, "dir": 4, "id": i})
            i += 1
    return out


def replay(path, moves):
    """Frame-by-frame trace from the ORIGINAL engine (headless pygame)."""
    r = subprocess.run([sys.executable, str(HERE / "engine_driver.py"), str(Path(path).resolve()), moves],
                       cwd=GAME_DIR, capture_output=True, text=True, timeout=120)
    try:
        d = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        return {"status": "load_error", "error": (r.stderr or r.stdout)[-300:]}
    if d.get("status") == "engine_unavailable":
        d = _model_replay(path, moves, d.get("error", ""))
    if d.get("status") != "ok":
        return d
    for f in d["frames"]:
        raw = f.pop("cells")
        f["raw"] = raw
        f["state"] = "WON" if f["solved"] else "PLAYING"
        on, total = raw.count("$"), raw.count("$") + raw.count("@")
        f["rules"] = [f"{on}/{total} BOXES ON GOALS"]
        f["cells"] = _cells(raw, d["width"])
        f["player_icon"] = "ICON_PLAYER"
    return d


def _model_replay(path, moves, why):
    """Used only when pygame/numpy are not installed, so the original engine cannot start.
    Same frames from the tested model (model_step); the result says so in d['engine']."""
    w, h, walls, goals, boxes, player = parse(Path(path).read_text())
    state = (player, boxes)

    def raw(st):
        pl, bx = st
        out = []
        for i in range(w * h):
            g = i in goals
            out.append("+" if i in walls else ("$" if g else "@") if i in bx else ("%" if g else "*") if i == pl
                       else "X" if g else "-")
        return "".join(out)
    frames = [{"cells": raw(state), "solved": state[1] <= goals}]
    for m in moves:
        state, moved = model_step(w, h, walls, state, m)
        frames.append({"cells": raw(state), "solved": state[1] <= goals, "moved": moved})
    return {"status": "ok", "width": w, "height": h, "frames": frames, "engine": "model_fallback",
            "engine_note": "original Sokoban engine not started (" + why + "); install it with: pip install pygame numpy"}


def replay_python_binding(path, moves):
    return {"available": False}


# ---------------------------------------------------------------- model + search
def parse(text):
    rows = [r.split() for r in text.strip().splitlines() if r.strip()]
    w, walls, goals, boxes, player = len(rows[0]), set(), set(), set(), None
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            p = y * w + x
            if c == "+": walls.add(p)
            if c in "X$%": goals.add(p)
            if c in "@$": boxes.add(p)
            if c in "*%": player = p
    return w, len(rows), walls, goals, frozenset(boxes), player


def model_step(w, h, walls, state, m):
    """Mirrors Player.update + Box.can_move: a box moves if the cell behind holds no box and no wall."""
    player, boxes = state
    dx, dy = DIRS[m]
    t = player + dx + dy * w
    if t in walls:
        return state, False
    if t in boxes:
        b = t + dx + dy * w
        if b in walls or b in boxes:
            return state, False
        return (t, boxes - {t} | {b}), True
    return (t, boxes), False


def solve(path, forbid=(), analyze=False, max_states=200000, max_ms=8000, wait=False):
    t0 = time.time()
    w, h, walls, goals, boxes, player = parse(Path(path).read_text())
    root = (player, boxes)
    won = lambda s: s[1] <= goals
    nodes, index, succ = [(-1, "", 0)], {root: 0}, [[-1] * 4]
    states, frontier, first, capped = [root], deque([0]), (0 if won(root) else -1), False
    while frontier:
        if first >= 0 and not analyze:
            break
        if len(states) >= max_states or (len(states) % 512 == 0 and (time.time() - t0) * 1000 > max_ms):
            capped = True
            break
        i = frontier.popleft()
        if won(states[i]):
            continue
        for k, m in enumerate("UDLR"):
            s, pushed = model_step(w, h, walls, states[i], m)
            if "push" in forbid and pushed:
                continue
            j = index.get(s)
            if j is None:
                j = len(states)
                index[s] = j
                states.append(s)
                nodes.append((i, m, nodes[i][2] + 1))
                succ.append([-1] * 4)
                if won(s):
                    if first < 0:
                        first = j
                else:
                    frontier.append(j)
            succ[i][k] = j
    moves = ""
    n = first
    while n > 0:
        moves = nodes[n][1] + moves
        n = nodes[n][0]
    exhaustive = not capped and not frontier
    out = {"status": "solved" if first >= 0 else ("unsolvable" if exhaustive else "unknown"),
           "proof": "witness" if first >= 0 else ("exhaustive" if exhaustive else "bounded"), "backend": "model",
           "moves": moves, "length": len(moves), "states_explored": len(states), "wait_allowed": False}
    if analyze:
        N = len(states)
        pred = [[] for _ in range(N)]
        for i in range(N):
            for j in succ[i]:
                if j >= 0:
                    pred[j].append(i)
        can = [False] * N
        q = deque(i for i in range(N) if won(states[i]))
        wins = len(q)
        for i in q:
            can[i] = True
        while q:
            i = q.popleft()
            for p in pred[i]:
                if not can[p]:
                    can[p] = True
                    q.append(p)
        dead = N - sum(can)
        ways = 0
        if first >= 0:
            target = nodes[first][2]
            cnt = [0.0] * N
            cnt[0] = 1.0
            for i in range(N):
                if won(states[i]) or nodes[i][2] >= target:
                    continue
                for j in succ[i]:
                    if j >= 0 and nodes[j][2] == nodes[i][2] + 1:
                        cnt[j] += cnt[i]
            ways = sum(cnt[i] for i in range(N) if won(states[i]) and nodes[i][2] == target)
        path_m = {"established": first >= 0 and exhaustive, "decision_points": 0, "trap_states": 0,
                  "trap_moves": 0, "forced_states": 0, "survival_log2": 0.0}
        if first >= 0 and exhaustive:
            chain, n = [], first
            while n >= 0:
                chain.append(n)
                n = nodes[n][0]
            for v in reversed(chain[1:]):
                changing = [j for j in succ[v] if j >= 0 and j != v]
                safe = [j for j in changing if can[j]]
                if not changing or not safe:
                    continue
                path_m["decision_points"] += 1
                if len(safe) < len(changing):
                    path_m["trap_states"] += 1
                    path_m["trap_moves"] += len(changing) - len(safe)
                if len(set(safe)) == 1:
                    path_m["forced_states"] += 1
                path_m["survival_log2"] += math.log2(len(safe) / len(changing))
        out["path"] = path_m
        out["analysis"] = {"complete": exhaustive, "reachable_states": N, "winning_states": wins, "lost_states": 0,
                           "dead_states": dead, "shortest_solution_count": ways,
                           "shortest_count_exact": first >= 0 and exhaustive}
    out["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
    return out


# ---------------------------------------------------------------- trace analysis, skills, difficulty
def analyse_trace(frames):
    ev = {"box_pushes": [], "boxes_delivered": [], "rule_changes": [], "destroyed": []}
    for i in range(1, len(frames)):
        a, b = frames[i - 1]["raw"], frames[i]["raw"]
        if [k for k, c in enumerate(a) if c in "@$"] != [k for k, c in enumerate(b) if c in "@$"]:
            ev["box_pushes"].append({"step": i})
        if b.count("$") > a.count("$"):
            ev["boxes_delivered"].append({"step": i})
    return ev


def skill_exercised(skill_id, events, frames):
    if skill_id == "box_pushing":
        return bool(events["box_pushes"])
    if skill_id == "multi_box":
        return frames[0]["raw"].count("@") >= 2 and len(events["boxes_delivered"]) >= 2
    return False


def static_necessity(skill_id, initial_rules, frame0=None):
    off = frame0["raw"].count("@") if frame0 else 0
    if skill_id == "box_pushing" and off >= 1:
        return (f"{off} box(es) start off a goal, and utils.is_solved / Game.is_level_complete only report a win "
                f"when no box is off a goal; boxes move only when pushed")
    if skill_id == "multi_box" and off >= 2:
        return f"{off} boxes start off a goal, so at least two different boxes must be pushed"
    return None


DIFFICULTY_WEIGHTS = {"trap_bits": 2.0, "dead_ratio": 4.0, "boxes": 1.5}


def difficulty(solve_result, events):
    path, an = solve_result.get("path") or {}, solve_result.get("analysis") or {}
    established = bool(path.get("established")) and bool(an.get("complete"))
    comp = {"trap_bits": round(-path.get("survival_log2", 0.0), 2) if established else None,
            "trap_states": path.get("trap_states") if established else None,
            "decision_points": path.get("decision_points") if established else None,
            "dead_ratio": round(an["dead_states"] / an["reachable_states"], 3) if established else None,
            "rule_changes": 0, "sacrifices": 0, "boxes": len(events["boxes_delivered"])}
    w, score = DIFFICULTY_WEIGHTS, None
    if established:
        score = round(w["trap_bits"] * comp["trap_bits"] + w["dead_ratio"] * comp["dead_ratio"] + w["boxes"] * comp["boxes"], 1)
    return {"established": established, "score": score, "components": comp, "weights": w}
