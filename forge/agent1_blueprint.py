#!/usr/bin/env python3
"""Agent 1 - Game Intelligence & Blueprint Engineer (machine-checkable half).

Reads the game's source tree and (re)builds the blueprint package:

    game_spec.json     entities, support status, turn pipeline, skills
    level_schema.json  native level-file format
    provenance.json    every claim -> source line(s) + executable probe result
    tests/example_levels.json   regression over the game's own shipped levels

The narrative files (skill.md, mechanics.md) are written by the LLM half of
Agent 1.  In this proof of concept they were authored by Claude acting as
Agent 1 during the build session; this script fingerprints them and refuses to
call a claim "confirmed" unless its source anchor still resolves AND its probe
passes on the engine built from that same source.

    python3 forge/agent1_blueprint.py            # rebuild blueprint
    python3 forge/agent1_blueprint.py --check    # detect a stale blueprint
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "game_src"
BP = ROOT / "blueprints" / "baba_is_auto"
ENUMS = "Includes/baba-is-auto/Enums"
GAME_CPP = "Sources/baba-is-auto/Games/Game.cpp"
MAP_CPP = "Sources/baba-is-auto/Games/Map.cpp"
DOC = "Documents/rule-language.md"

# Files the blueprint depends on, and which blueprint sections each one feeds.
ANALYSED = {
    f"{ENUMS}/NounType.def": ["game_spec.entities", "level_schema.tile_ids"],
    f"{ENUMS}/OpType.def": ["game_spec.entities", "level_schema.tile_ids"],
    f"{ENUMS}/PropertyType.def": ["game_spec.entities", "level_schema.tile_ids"],
    f"{ENUMS}/IconType.def": ["game_spec.entities", "level_schema.tile_ids"],
    f"{ENUMS}/GameEnums.hpp": ["game_spec.entities", "level_schema.tile_ids"],
    GAME_CPP: ["game_spec.turn_pipeline", "game_spec.support", "mechanics.md", "provenance",
               "solver (re-link)", "tests/probes.py"],
    MAP_CPP: ["level_schema.json", "validator", "provenance"],
    "Sources/baba-is-auto/Games/Object.cpp": ["solver (re-link)"],
    "Sources/baba-is-auto/Rules/RuleManager.cpp": ["solver (re-link)"],
    DOC: ["game_spec.support (cross-check only)"],
}

# ---------------------------------------------------------------------------
# Claims: statement, the source line that implements it (regex anchor), and
# the probe in tests/probes.py that demonstrates it on the running engine.
# ---------------------------------------------------------------------------
CLAIMS = [
    ("text_always_push", GAME_CPP, r"\(IsTextType\(instance\.type\) \|\|", "mechanics.push"),
    ("edge_blocks", GAME_CPP, r"// Check boundary", "mechanics.movement"),
    ("stop_blocks", GAME_CPP, r"// Check the icon has property 'STOP'", "mechanics.stop"),
    ("no_rule_no_block", GAME_CPP, r"bool Game::CanMove\(", "mechanics.movement"),
    ("push_moves", GAME_CPP, r"void Game::ProcessPush\(", "mechanics.push"),
    ("push_chain", GAME_CPP, r"if \(!CanMove\(_x, _y, dir, pushedIDs\)\)", "mechanics.push"),
    ("push_chain_blocked", GAME_CPP, r"if \(!CanMove\(_x, _y, dir, pushedIDs\)\)", "mechanics.push"),
    ("push_overrides_stop", GAME_CPP, r"ObjectType::STOP\) &&", "mechanics.stop"),
    ("win_on_overlap", GAME_CPP, r"m_playState = PlayState::WON;", "mechanics.win"),
    ("win_self", GAME_CPP, r"if \(HasPropertyAt\(x, y, ObjectType::WIN\)\)", "mechanics.win"),
    ("load_state_not_evaluated", GAME_CPP, r"^Game::Game\(std::string_view filename\)", "mechanics.win"),
    ("no_you_is_lost", GAME_CPP, r"m_playState = PlayState::LOST;", "mechanics.lose"),
    ("rule_same_turn", GAME_CPP, r"^void Game::MovePlayer\(Direction dir\)", "mechanics.rules"),
    ("rule_reading_order", GAME_CPP, r"ParseRule\(x, y, RuleDirection::VERTICAL\);", "mechanics.rules"),
    ("sink_destroys_both", GAME_CPP, r"^void Game::ProcessSink\(\)", "mechanics.sink"),
    ("sink_text", GAME_CPP, r"instances\.size\(\) < 2 \|\| !HasPropertyAt\(x, y, ObjectType::SINK\)", "mechanics.sink"),
    ("sink_player", GAME_CPP, r"^void Game::ProcessSink\(\)", "mechanics.sink"),
    ("defeat_removes_you", GAME_CPP, r"^void Game::ProcessDefeat\(\)", "mechanics.defeat"),
    ("hot_melt", GAME_CPP, r"^void Game::ProcessHotMelt\(\)", "mechanics.hot_melt"),
    ("transform", GAME_CPP, r"^void Game::ProcessTransformations\(\)", "mechanics.transform"),
    ("you_swap", GAME_CPP, r"^std::vector<ObjectID> Game::GetPlayerIDsAt", "mechanics.you"),
    ("multi_you", GAME_CPP, r"^void Game::ProcessPlayerMove\(Direction dir\)", "mechanics.you"),
    ("rail_immovable", GAME_CPP, r"// Check boundary", "patterns.rule_rail"),
    ("unsupported_inert", f"{ENUMS}/PropertyType.def", r"X\(PULL\)", "game_spec.support"),
    ("and_chain", GAME_CPP, r"^void AddRuleCombinations\(", "mechanics.rules"),
    ("stacked_layers", MAP_CPP, r"constexpr std::size_t MAX_MAP_LAYERS = 3;", "level_schema.layers"),
    ("loader_rejects_bad_dims", MAP_CPP, r'throw std::runtime_error\("Invalid map dimensions"\)', "level_schema.header"),
    ("loader_rejects_sentinels", MAP_CPP, r"^bool IsValidMapTile\(int value\)", "level_schema.tile_ids"),
    ("loader_rejects_count", MAP_CPP, r"values\.size\(\) / tileCount > MAX_MAP_LAYERS", "level_schema.layers"),
    ("loader_rejects_nonint", MAP_CPP, r"^std::optional<int> ParseInt\(", "level_schema.tokens"),
]

# Claims that are NOT established by a probe: stated honestly as such.
SOFT_CLAIMS = [
    {"id": "state_abstraction_ignores_ids", "status": "inferred",
     "statement": "The solver identifies states by the multiset of (type[, facing]) per cell; "
                  "object IDs and in-cell stacking order are ignored.",
     "basis": "IDs only order simultaneous updates (PlayerStackComesFirst, MOVE rounds); no rule in "
              "the generation vocabulary can observe them.  No counter-example found, not proven.",
     "consequence": "A witness solution is still certified by replay in the real engine. Only "
                    "'unsolvable' and dead-state counts rest on this abstraction."},
    {"id": "empty_move_random", "status": "confirmed-by-source",
     "statement": "A directionless EMPTY under 'EMPTY IS MOVE' picks a random direction "
                  "(std::mt19937 seeded from std::random_device).",
     "source": {"file": "Includes/baba-is-auto/Games/Game.hpp", "anchor": r"std::mt19937 m_randomEngine"},
     "consequence": "EMPTY is excluded from the generation vocabulary so every generated level is deterministic."},
    {"id": "wait_input", "status": "unresolved",
     "statement": "Whether a 'wait' input is available to the player.",
     "basis": "Game::MovePlayer(Direction::NONE) processes a turn, but the shipped pygame GUI was not "
              "confirmed to bind a wait key.",
     "consequence": "The solver searches the four directional inputs only (pass --wait to include "
                    "waiting). 'Unsolvable' therefore means 'unsolvable with U/D/L/R'."},
    {"id": "facing_in_state", "status": "inferred",
     "statement": "Facing direction is left out of the state key unless MOVE, FACING, a direction "
                  "property or a LOCKED_* tile is present in the level.",
     "basis": "Those are the only places Game.cpp reads ObjectInstance::direction.",
     "consequence": "Same as state_abstraction_ignores_ids."},
    {"id": "float_safe_weak_open_shut_move", "status": "out-of-scope",
     "statement": "MOVE, OPEN/SHUT, WEAK, FLOAT, SAFE, HAS, conditions (ON/NEAR/FACING/LONELY), NOT and "
                  "the special nouns are implemented by the engine (and the solver handles them, since "
                  "it runs the engine) but have no probe in this blueprint yet.",
     "consequence": "They are accepted in hand-written levels and verified by the solver, but the "
                    "generator will not emit them."},
]

SKILLS = [
    {"id": "rule_manipulation", "label": "Rule manipulation",
     "definition": "The set of active rules changes during the solution.",
     "keywords": ["rule manipulation", "manipulate rules", "manipulating rules", "break a rule", "break rule",
                  "form a rule", "rewrite rule", "rule", "rules"],
     "exercised_if": "trace event rule_changes", "necessity_ablation": "rules"},
    {"id": "object_pushing", "label": "Strategic object pushing",
     "definition": "A non-text, non-player object is pushed during the solution.",
     "keywords": ["object pushing", "push", "pushing", "sokoban", "rock", "crate", "box"],
     "exercised_if": "trace event object_pushes", "necessity_ablation": "push"},
    {"id": "win_condition_change", "label": "Changing win condition",
     "definition": "The set of 'X IS WIN' rules changes during the solution.",
     "keywords": ["win condition", "win conditions", "changing win", "is win", "goal changes", "retarget"],
     "exercised_if": "trace event win_rule_changes", "necessity_ablation": "win"},
    {"id": "you_change", "label": "IS YOU manipulation",
     "definition": "The set of 'X IS YOU' rules changes during the solution.",
     "keywords": ["is you", "you rule", "change who", "control", "become", "identity", "swap character"],
     "exercised_if": "trace event you_changes", "necessity_ablation": "you"},
    {"id": "hazard_sink", "label": "SINK hazard",
     "definition": "A SINK object is present and something is destroyed on it during the solution.",
     "keywords": ["sink", "water", "drown"], "exercised_if": "trace event destroyed", "necessity_ablation": None},
    {"id": "hazard_defeat", "label": "DEFEAT hazard",
     "definition": "A DEFEAT object is present on the map.",
     "keywords": ["defeat", "skull", "danger", "enemy", "hazard", "deadly"],
     "exercised_if": "DEFEAT rule active in some frame", "necessity_ablation": None},
]

GEN_VOCAB = {
    "text": ["IS", "YOU", "WIN", "STOP", "PUSH", "SINK", "DEFEAT"],
    "nouns": ["BABA", "KEKE", "ROCK", "WALL", "FLAG", "WATER", "SKULL", "KEY", "DOOR", "LAVA",
              "TILE", "GRASS", "STAR", "BOX", "CRAB", "HEDGE", "LOVE"],
    "note": "Only tokens whose behaviour has a passing probe. Everything else the engine implements is "
            "accepted by the validator but never emitted by the generator.",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fingerprint():
    return {rel: sha(SRC / rel) for rel in ANALYSED}


def find_line(rel, pattern):
    for i, line in enumerate((SRC / rel).read_text().splitlines(), 1):
        if re.search(pattern, line):
            return i, line.strip()
    return None, None


def entities():
    order = [("NOUN_TYPE", "NounType.def", "noun"), ("OP_TYPE", "OpType.def", "operator"),
             ("PROPERTY_TYPE", "PropertyType.def", "property"), ("ICON_TYPE", "IconType.def", "icon")]
    ents, sentinels, i = [], {}, 0
    for sentinel, fname, kind in order:
        sentinels[sentinel] = i
        i += 1
        for n in re.findall(r"X\((\w+)\)", (SRC / ENUMS / fname).read_text()):
            ents.append({"name": n, "id": i, "kind": kind, "source": f"{ENUMS}/{fname}"})
            i += 1
    for n in ("LOCKED_UP", "LOCKED_DOWN", "LOCKED_LEFT", "LOCKED_RIGHT"):
        ents.append({"name": n, "id": i, "kind": "synthetic_property", "source": f"{ENUMS}/GameEnums.hpp"})
        i += 1
    return ents, sentinels


def support_status(ents):
    """Static analysis: does the runtime ever read this word?  Cross-checked
    against the repository's own capability matrix."""
    game = (SRC / GAME_CPP).read_text()
    doc = (SRC / DOC).read_text()
    doc_status = {}
    for row in doc.splitlines():
        cells = [c.strip() for c in row.split("|")]
        if len(cells) > 3 and cells[2] in ("Implemented", "Partial", "Unsupported"):
            for tok in re.findall(r"`([A-Z_]+)`", cells[1]):
                doc_status.setdefault(tok, cells[2].lower())
    conflicts = []
    for e in ents:
        if e["kind"] == "icon":
            continue
        refs = len(re.findall(rf"ObjectType::{e['name']}\b", game))
        e["runtime_refs"] = refs
        d = doc_status.get(e["name"])
        if e["kind"] == "noun" and d is None:
            e["support"] = "implemented"  # ordinary noun: generic SubjectMatches path
        elif d is not None:
            e["support"] = d
            if d == "implemented" and refs == 0 and e["kind"] in ("property", "synthetic_property"):
                conflicts.append(e["name"])
                e["support"] = "unresolved"
        else:
            e["support"] = "implemented" if refs else "unsupported"
        if refs == 0 and e["kind"] == "property":
            e["support"] = "unsupported"
        e["support_evidence"] = (f"{refs} reference(s) to ObjectType::{e['name']} in {GAME_CPP}"
                                 + (f"; capability matrix says {d}" if d else ""))
    return conflicts


def turn_pipeline():
    lines = (SRC / GAME_CPP).read_text().splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("void Game::MovePlayer("))
    phases = []
    for i in range(start, start + 40):
        if lines[i].startswith("}"):
            break
        m = re.search(r"\b(ProcessPlayerMove|ParseRules|Process\w+|CheckPlayState)\(", lines[i])
        if m:
            phases.append({"phase": m.group(1), "source": f"{GAME_CPP}:{i + 1}"})
    return phases


def level_schema():
    ln = lambda pat: find_line(MAP_CPP, pat)[0]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "baba-is-auto native level file (text)",
        "description": "Whitespace-separated integers. Header 'W H', then 1-3 layers of W*H tile IDs in "
                       "row-major order (y outer, x inner). Layer k holds the k-th object of each cell; "
                       "ICON_EMPTY (132) pads. Optional trailing 'DIRECTIONS' block with one 0-3 value per tile.",
        "type": "object",
        "required": ["width", "height", "layers"],
        "properties": {
            "width": {"type": "integer", "minimum": 1, "x-source": f"{MAP_CPP}:{ln('Invalid map dimensions')}"},
            "height": {"type": "integer", "minimum": 1, "x-source": f"{MAP_CPP}:{ln('Invalid map dimensions')}"},
            "layers": {"type": "array", "minItems": 1, "maxItems": 3,
                       "x-source": f"{MAP_CPP}:{ln('MAX_MAP_LAYERS = 3')}",
                       "items": {"type": "array", "description": "W*H tile IDs",
                                 "items": {"type": "integer", "minimum": 1, "maximum": 179,
                                           "not": {"enum": [66, 76, 110]},
                                           "x-source": f"{MAP_CPP}:{ln('bool IsValidMapTile')}"}}},
            "directions": {"type": "array", "items": {"enum": [0, 1, 2, 3]},
                           "description": "0=RIGHT 1=UP 2=LEFT 3=DOWN; if present, exactly one per tile value",
                           "x-source": f"{MAP_CPP}:{ln('ParseDirection')}"},
        },
        "x-conventions": {
            "coordinates": "zero-based (x, y), origin top-left, y grows downward",
            "empty_cell": 132,
            "default_facing": "RIGHT",
            "icon_id": "noun text id + 110  (ConvertTextToIcon)",
            "object_ids": "assigned column-major at load (AssignObjectIDs); not stored in the file",
        },
        "x-forge-policy": {
            "comment": "Stricter limits applied by this blueprint so the exhaustive solver stays tractable",
            "max_width": 20, "max_height": 20, "max_cells": 250, "must_have_you_instance": True,
            "must_not_be_won_by_first_wait": True,
        },
    }


def build(args):
    sys.path.insert(0, str(ROOT))
    ents, sentinels = entities()
    conflicts = support_status(ents)
    spec = {
        "blueprint_version": "0.1.0",
        "game": {"name": "baba-is-auto", "upstream": "https://github.com/utilForever/baba-is-auto",
                 "commit": "24cefb48d47ae6a6f5c0d936310d8bceb9c4279d", "license": "MIT",
                 "description": "Open-source C++17 Baba Is You simulator with pybind11 binding and pygame GUI"},
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_fingerprint": fingerprint(),
        "sentinels": sentinels,
        "level_format": {"max_layers": 3, "empty_id": 132, "icon_offset": 110,
                         "direction_codes": {"0": "RIGHT", "1": "UP", "2": "LEFT", "3": "DOWN"}},
        "inputs": ["U", "D", "L", "R"],
        "turn_pipeline": turn_pipeline(),
        "generation_vocabulary": GEN_VOCAB,
        "skills": SKILLS,
        "support_conflicts": conflicts,
        "entities": ents,
    }
    (BP / "game_spec.json").write_text(json.dumps(spec, indent=1))
    (BP / "level_schema.json").write_text(json.dumps(level_schema(), indent=1))

    # --- probes -> provenance ---
    from blueprints.baba_is_auto.tests import probes
    import importlib
    importlib.reload(probes.A)
    results = probes.run_all()
    claims = []
    for pid, rel, pattern, section in CLAIMS:
        line, text = find_line(rel, pattern)
        res = results.get(pid, {"passed": False, "claim": "?"})
        status = "confirmed" if (line and res["passed"]) else ("unresolved" if not line else "refuted")
        claims.append({"id": pid, "statement": res["claim"], "section": section, "status": status,
                       "source": {"file": rel, "line": line, "text": text, "anchor": pattern},
                       "evidence": {"probe": f"tests/probes.py::{pid}", "passed": res["passed"]}})
    for sc in SOFT_CLAIMS:
        sc = dict(sc)
        if "source" in sc:
            line, text = find_line(sc["source"]["file"], sc["source"]["anchor"])
            sc["source"]["line"], sc["source"]["text"] = line, text
        claims.append(sc)
    unsupported = [e["name"] for e in ents if e.get("support") == "unsupported"]
    prov = {
        "blueprint_version": spec["blueprint_version"], "game_commit": spec["game"]["commit"],
        "source_fingerprint": spec["source_fingerprint"],
        "depends_on": ANALYSED,
        "narrative_fingerprint": {f: sha(BP / f) for f in ("skill.md", "mechanics.md") if (BP / f).exists()},
        "summary": {s: sum(1 for c in claims if c["status"] == s)
                    for s in sorted({c["status"] for c in claims})},
        "unsupported_tokens": {"tokens": unsupported,
                               "evidence": f"zero references in {GAME_CPP} and/or 'Unsupported' in {DOC}"},
        "claims": claims,
    }
    (BP / "provenance.json").write_text(json.dumps(prov, indent=1))

    # --- regression over the game's own levels ---
    if not args.skip_examples:
        from blueprints.baba_is_auto import adapter as A
        importlib.reload(A)
        from blueprints.baba_is_auto.validator import validate as V
        ex = []
        for p in sorted((SRC / "Resources/Maps").glob("*.txt")):
            v = V.validate_file(p, policy=False)
            s = A.solve(p, max_ms=1500) if v["loader_accepts"] else {"status": "n/a"}
            ex.append({"level": p.name, "loader_accepts": v["loader_accepts"],
                       "schema_valid": v["schema_valid"], "solver": s.get("status"),
                       "proof": s.get("proof"), "solution_length": s.get("length"),
                       "states_explored": s.get("states_explored")})
        (BP / "tests" / "example_levels.json").write_text(json.dumps(
            {"note": "The game's shipped maps, most of which are unit-test fixtures rather than puzzles. "
                     "'unknown' = search bound (1.5 s) reached, not a failure.",
             "levels": ex}, indent=1))
        agree = sum(1 for e in ex if e["loader_accepts"] == e["schema_valid"])
        print(f"example levels: {len(ex)} checked, validator agrees with the real loader on {agree}/{len(ex)}; "
              f"solved {sum(1 for e in ex if e['solver'] == 'solved')}")
    print(f"entities: {len(ents)}  unsupported tokens: {len(unsupported)}  claims: {prov['summary']}")
    print("turn pipeline:", " > ".join(p["phase"] for p in spec["turn_pipeline"]))
    bad = [c["id"] for c in claims if c["status"] in ("refuted",)]
    if bad:
        print("REFUTED claims (blueprint must be corrected):", bad)
        return 1
    return 0


def check(_args):
    spec = json.loads((BP / "game_spec.json").read_text())
    old, new = spec["source_fingerprint"], fingerprint()
    changed = [f for f in new if old.get(f) != new[f]]
    if not changed:
        print("blueprint is current: all", len(new), "analysed source files match their fingerprints")
        return 0
    print("STALE blueprint - analysed source changed:")
    stale = set()
    for f in changed:
        print("  ", f, "->", ", ".join(ANALYSED[f]))
        stale.update(ANALYSED[f])
    print("sections to regenerate / revalidate:", ", ".join(sorted(stale)))
    return 3


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--skip-examples", action="store_true")
    a = ap.parse_args()
    sys.exit(check(a) if a.check else build(a))
