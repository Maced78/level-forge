#!/usr/bin/env python3
"""Validator for sokoban-solver-generator level files (levels/*.dat).  Standalone:
    python3 validate.py LEVEL.dat
Each rule cites the engine code it comes from (see provenance.json)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from blueprints.sokoban_sg import adapter as A  # noqa: E402

POLICY = {"max_width": 12, "max_height": 9, "engine_max_width": 17, "engine_max_height": 10}


def check(name, ok, detail=""):
    return {"check": name, "passed": bool(ok), "detail": detail}


def validate_file(path, policy=True):
    text = Path(path).read_text()
    rows = [r.split() for r in text.splitlines() if r.strip()]
    checks = []
    ok_shape = bool(rows) and all(len(r) == len(rows[0]) for r in rows)
    checks.append(check("syntax.rectangular", ok_shape, f"{len(rows)} rows"))
    bad = sorted({c for r in rows for c in r if c not in A.TOKENS})
    checks.append(check("syntax.tokens", not bad, "all tokens are in the engine's alphabet + - @ X * $ %" if not bad
                        else f"unknown tokens {bad} (Game.load_puzzle raises ValueError and clears the level)"))
    out = {"checks": checks, "schema_valid": ok_shape and not bad, "loader_accepts": None, "structurally_valid": False}
    if not out["schema_valid"]:
        return out
    w, h = len(rows[0]), len(rows)
    flat = [c for r in rows for c in r]
    checks.append(check("schema.size", w <= POLICY["engine_max_width"] and h <= POLICY["engine_max_height"]
                        and (not policy or (w <= POLICY["max_width"] and h <= POLICY["max_height"])),
                        f"{w}x{h}; the engine's 1216x640 window holds 17x10 cells of puzzle"))
    players = sum(c in "*%" for c in flat)
    checks.append(check("playable.one_player", players == 1, f"{players} player token(s)"))
    border = all(c == "+" for c in rows[0] + rows[-1]) and all(r[0] == "+" and r[-1] == "+" for r in rows)
    checks.append(check("invariant.closed_border", border,
                        "outer ring is all walls" if border else
                        "open border: Player.update indexes game.puzzle outside the level and fails on None"))
    boxes, goals = sum(c in "@$" for c in flat), sum(c in "X$%" for c in flat)
    checks.append(check("invariant.boxes_not_more_than_goals", boxes <= goals,
                        f"{boxes} boxes, {goals} goals; the engine wins only when no box is off a goal"))
    checks.append(check("playable.not_solved_at_start", flat.count("@") >= 1,
                        "at least one box starts off a goal" if flat.count("@") else "already solved at load"))
    rp = A.replay(path, "")
    out["loader_accepts"] = rp.get("status") == "ok"
    checks.append(check("loader.engine_accepts", out["loader_accepts"],
                        ("original engine not installed; checked by the model only" if rp.get("engine") == "model_fallback"
                         else "Game(path=...) built by the original engine, headless") if out["loader_accepts"]
                        else f"engine: {rp.get('error')}"))
    out["initial_rules"] = [f"{boxes} boxes", f"{goals} goals"]
    out["warnings"] = []
    out["structurally_valid"] = all(c["passed"] for c in checks)
    return out


if __name__ == "__main__":
    r = validate_file(sys.argv[1])
    for c in r["checks"]:
        print(("PASS " if c["passed"] else "FAIL ") + c["check"] + " - " + c["detail"])
    sys.exit(0 if r["structurally_valid"] else 1)
