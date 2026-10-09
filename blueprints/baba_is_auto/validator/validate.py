#!/usr/bin/env python3
"""Validator for baba-is-auto native level files.

Independent of the generator: it takes only the bytes of a level file.
Checks are layered and reported separately (see skill.md, "Verification
levels"):

    1 syntax      header and tokens parse
    2 schema      dimensions, layer count, tile IDs  (level_schema.json)
    3 entities    only tokens the engine gives a meaning to; no unsupported words
    4 loader      the ORIGINAL engine loads the file          (authoritative)
    5 playable    a YOU instance exists; not already won; the rules that are
                  written actually parse the way the engine parses them

    python3 validate.py LEVEL.txt [--json]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from blueprints.baba_is_auto import adapter as A  # noqa: E402

SCHEMA = json.loads((Path(__file__).resolve().parents[1] / "level_schema.json").read_text())
POLICY = SCHEMA["x-forge-policy"]


def check(name, ok, detail=""):
    return {"check": name, "passed": bool(ok), "detail": detail}


def validate_text(text: str, policy=True):
    checks = []
    toks = text.split()
    # 1 syntax ---------------------------------------------------------------
    try:
        w, h = int(toks[0]), int(toks[1])
        syntax_ok = True
    except Exception:
        return {"checks": [check("syntax.header", False, "first two tokens must be integers W H")],
                "schema_valid": False, "loader_accepts": None, "structurally_valid": False}
    body, dirs = toks[2:], []
    if "DIRECTIONS" in body:
        k = body.index("DIRECTIONS")
        body, dirs = body[:k], body[k + 1:]
    try:
        vals = [int(t) for t in body]
        dvals = [int(t) for t in dirs]
        checks.append(check("syntax.tokens", True, f"{len(vals)} integer tile tokens"))
    except ValueError as e:
        checks.append(check("syntax.tokens", False, f"non-integer token: {e}"))
        return {"checks": checks, "schema_valid": False, "loader_accepts": None,
                "structurally_valid": False}
    # 2 schema ---------------------------------------------------------------
    dims_ok = w >= 1 and h >= 1
    checks.append(check("schema.dimensions", dims_ok, f"{w}x{h}"))
    n = w * h if dims_ok else 1
    layers_ok = dims_ok and len(vals) > 0 and len(vals) % n == 0 and len(vals) // n <= A.MAX_LAYERS
    checks.append(check("schema.layers", layers_ok,
                        f"{len(vals)} tiles = {len(vals) / n:g} layer(s) of {n}; allowed 1..{A.MAX_LAYERS}"))
    bad_ids = sorted({v for v in vals if v not in A.NAME})
    checks.append(check("schema.tile_ids", not bad_ids,
                        "all IDs name an engine ObjectType" if not bad_ids else f"invalid IDs {bad_ids}"))
    dirs_ok = (not dirs) or (len(dvals) == len(vals) and all(0 <= d <= 3 for d in dvals))
    checks.append(check("schema.directions", dirs_ok, "no DIRECTIONS block" if not dirs else f"{len(dvals)} values"))
    schema_valid = syntax_ok and dims_ok and layers_ok and not bad_ids and dirs_ok
    out = {"checks": checks, "schema_valid": schema_valid, "loader_accepts": None,
           "structurally_valid": False, "width": w, "height": h}
    if not schema_valid:
        return out
    # 3 entities -------------------------------------------------------------
    names = {A.NAME[v] for v in vals if v != A.EMPTY}
    unsupported = sorted(n_ for n_ in names if A.SUPPORT.get(n_) == "unsupported")
    checks.append(check("entities.no_unsupported_words", not unsupported,
                        "every word has runtime behaviour in this engine" if not unsupported else
                        f"{unsupported} are enum values with no runtime hook (see provenance.json)"))
    if policy:
        checks.append(check("policy.size", w <= POLICY["max_width"] and h <= POLICY["max_height"]
                            and w * h <= POLICY["max_cells"],
                            f"{w}x{h} = {w * h} cells; limit {POLICY['max_width']}x{POLICY['max_height']}, "
                            f"{POLICY['max_cells']} cells"))
    return out


def validate_file(path, policy=True):
    path = Path(path)
    out = validate_text(path.read_text(), policy=policy)
    checks = out["checks"]
    # 4 loader (authoritative) -----------------------------------------------
    rp = A.replay(path, "W")
    out["loader_accepts"] = rp.get("status") == "ok"
    checks.append(check("loader.engine_accepts", out["loader_accepts"],
                        "Game(filename) constructed by the original engine" if out["loader_accepts"]
                        else f"engine error: {rp.get('error')}"))
    py = A.replay_python_binding(path, "")
    if py.get("available"):
        checks.append(check("loader.python_binding_accepts", py.get("loaded", False),
                            "pyBaba.Game(filename)" if py.get("loaded") else str(py.get("error"))))
    if out["loader_accepts"] and out["schema_valid"]:
        f0, f1 = rp["frames"][0], rp["frames"][1]
        out["initial_rules"] = f0["rules"]
        you = [r for r in f0["rules"] if r.endswith(" YOU")]
        you_icons = {"ICON_" + r.split()[0] for r in you}
        has_player = any(c["name"] in you_icons for c in f0["cells"]) or f0["player_icon"] != "ICON_EMPTY"
        checks.append(check("playable.you_instance", has_player,
                            f"controlled: {f0['player_icon']} via {you}" if has_player else
                            "no object is YOU at load: the level cannot be played"))
        checks.append(check("playable.not_won_immediately", f1["state"] != "WON",
                            "not won by an idle first turn" if f1["state"] != "WON"
                            else "level is already won when the first turn is processed"))
        # every noun used as a rule subject should exist as an object, or the rule is dead text
        dead = sorted({r.split()[0] for r in f0["rules"]
                       if A.KIND.get(r.split()[0]) == "noun" and r.split()[0] not in ("TEXT", "ALL", "EMPTY")
                       and not any(c["name"] == "ICON_" + r.split()[0] for c in f0["cells"])})
        out["warnings"] = [f"rule subject {d} has no object on the map" for d in dead]
    out["structurally_valid"] = all(c["passed"] for c in checks)
    return out


if __name__ == "__main__":
    res = validate_file(sys.argv[1])
    if "--json" in sys.argv:
        print(json.dumps(res, indent=1))
    else:
        for c in res["checks"]:
            print(("PASS " if c["passed"] else "FAIL ") + c["check"] + " - " + c["detail"])
        for w_ in res.get("warnings", []):
            print("WARN " + w_)
        print("STRUCTURALLY VALID" if res["structurally_valid"] else "INVALID")
    sys.exit(0 if res["structurally_valid"] else 1)
