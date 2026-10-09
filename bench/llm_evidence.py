#!/usr/bin/env python3
"""Measures what the language model actually contributes (needs a Gemini key in .env).

    python3 bench/llm_evidence.py            # ~10 minutes on a free-tier key (rate limited)

Part 1  Request understanding: keyword parser vs LLM on 24 hand-labelled requests
        (8 literal, 16 paraphrased so that no keyword matches).
Part 2  Level generation, 10 requests, every output scored by the SAME verifier:
          raw_llm        the model writes a native level file directly (one shipped level as example)
          llm_skill      the model reads skill.md and proposes a level
          llm_loop       ... and gets up to two repairs driven by the verifier's findings
          full_pipeline  LLM understands the request, the constraint planner builds, the verifier judges
Part 3  Five free-form showcase requests through the complete system, saved with their transcripts.

Everything is written to bench/llm_results.json and out/showcase/.  Calls are cached in
out/llm_cache.json, so an interrupted run resumes where it stopped.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FORGE_LLM_MIN_INTERVAL", "5")
from forge import llm, pipeline as PL  # noqa: E402

OUT = ROOT / "bench" / "llm_results.json"
SHOW = ROOT / "out" / "showcase"

# text, difficulty, required skills, forbidden skills, must be rejected, literal wording?
INTENT = [
    ("Create a hard level that tests rule manipulation and object pushing.", "hard", ["rule_manipulation", "object_pushing"], [], False, True),
    ("Make an easy level about pushing rocks into water.", "easy", ["object_pushing", "hazard_sink"], [], False, True),
    ("A medium level with skulls where the win condition changes, no object pushing.", "medium", ["win_condition_change", "hazard_defeat"], ["object_pushing"], False, True),
    ("Create a level that teaches the player how to manipulate the IS YOU rule.", "easy", ["you_change"], [], False, True),
    ("Make a level with teleporters and a PULL rule.", None, [], [], True, True),
    ("Hard level about changing the win condition but without any rule manipulation.", None, [], [], True, True),
    ("Create a hard level where the only rocks are behind the water and the water can only be crossed by sinking a rock in it.", None, [], [], True, True),
    ("Create a simple level that tests a sink hazard.", "easy", ["hazard_sink"], [], False, True),
    ("I need a brain-melter for veterans: the exit shouldn't count as an exit until the player makes it one, and they'll have to shove a crate around to get there.", "hard", ["win_condition_change", "object_pushing"], [], False, False),
    ("First stage of the game, for someone who has never played: show them they can stop being Baba and play as the other creature instead.", "easy", ["you_change"], [], False, False),
    ("Something moderately tricky where a moat blocks the way and a boulder has to be sacrificed to get across.", "medium", ["object_pushing", "hazard_sink"], [], False, False),
    ("A gentle intro stage where the barrier only blocks you because a sentence says so - the player should take that sentence apart.", "easy", ["rule_manipulation"], [], False, False),
    ("Give me a nasty one full of things that kill you on touch, where the sentence making them lethal has to be dismantled.", "hard", ["rule_manipulation", "hazard_defeat"], [], False, False),
    ("Mid-game stage: at the start nothing in the level counts as the goal. Keep crates and boulders out of it entirely.", "medium", ["win_condition_change"], ["object_pushing"], False, False),
    ("An expert stage where you must hand control to a different character and then that character has to shift a box into lava.", "hard", ["you_change", "object_pushing"], [], False, False),
    ("Beginner-friendly: just shift one crate out of the way, and please leave every sentence on the board alone.", "easy", ["object_pushing"], ["rule_manipulation"], False, False),
    ("A stage where the hero is yanked toward a magnet across the room.", None, [], [], True, False),
    ("Blocks should drop downward when nothing is under them, like in a platformer.", None, [], [], True, False),
    ("I want a stage with a beam emitter and mirrors to redirect the beam.", None, [], [], True, False),
    ("The player must redefine what counts as winning, but none of the sentences on the board may ever be altered.", None, [], [], True, False),
    ("Put the single crate on the far bank of the river; the river can only be crossed by dropping that crate into it.", None, [], [], True, False),
    ("A fiendish stage: the creature you start as is not the one who finishes, and what counts as the exit has to be assembled by the player.", "hard", ["you_change", "win_condition_change"], [], False, False),
    ("Nothing fancy, a relaxed stage for kids.", "easy", [], [], False, False),
    ("Tough stage, but please no rivers, lava or anything that swallows objects.", "hard", [], ["hazard_sink"], False, False),
]

GEN = [
    "Make an easy level about pushing a rock into water to reach the flag.",
    "A gentle intro stage where a wall only blocks you because a sentence says so; the player should break that sentence.",
    "Create an easy level where nothing counts as the goal until the player completes the sentence that makes the flag the goal.",
    "First level for a new player: show them they can stop being Baba and play as Keke instead.",
    "A medium level: a column of deadly skulls blocks the way and the player has to dismantle the rule that makes them deadly.",
    "Medium difficulty: a moat of water, one rock, and the win rule has to be assembled by the player.",
    "Something moderately tricky that combines breaking a rule with pushing a box into lava.",
    "A hard level that tests rule manipulation, strategic object pushing and a changing win condition.",
    "A hard puzzle where the player must sacrifice a rule word as well as a rock to cross a wide river.",
    "An expert stage: hand control to a different character, who then has to push a box into lava to reach the goal.",
]

SHOWCASE = [
    "I need a brain-melter for veterans: the exit shouldn't count as an exit until the player makes it one, and they'll have to shove a crate around to get there.",
    "First stage of the game, for someone who has never played: show them they can stop being Baba and play as the other creature instead.",
    "Something moderately tricky where a moat blocks the way and a boulder has to be sacrificed to get across.",
    "Give me a nasty one full of things that kill you on touch, where the sentence making them lethal has to be dismantled.",
    "Put the single crate on the far bank of the river; the river can only be crossed by dropping that crate into it.",
]

RAW_SYSTEM = """You write level files for the open-source puzzle game baba-is-auto (a Baba Is You simulator).
A level file is plain text: the first line is "W H", followed by W*H whitespace-separated integer tile
IDs in row order. Here is one of the game's own levels (Resources/Maps/baba_is_you.txt) as a reference:

{example}

Write a NEW level file for the request. Return ONLY JSON: {{"level_file": "<the file contents, rows separated by \\n>"}}"""


def stat(rep):
    lv = rep.get("levels", {})
    checks = {c["check"]: c["passed"] for c in lv.get("structural", {}).get("checks", [])}
    return {"loader_accepts": bool(checks.get("loader.engine_accepts")),
            "structurally_valid": bool(lv.get("structural", {}).get("passed")),
            "solvable": bool(lv.get("solvable", {}).get("passed")),
            "fully_validated": rep["status"] == "FULLY_VALIDATED", "status": rep["status"],
            "reasons": rep.get("reasons", [])[:4]}


def main():
    if llm.mode() != "live":
        print("No Gemini key found. Put GEMINI_API_KEY=... in", ROOT / ".env")
        return 1
    if llm.selftest() != 0:
        print("\nThe key does not work, so nothing was measured. Fix the key and run this script again.")
        return 1
    game = PL.Game()
    skill_md = (ROOT / "blueprints" / game.name / "skill.md").read_text()
    res = {}
    res["model"] = llm.pick_model()
    res["started"] = res.get("started") or time.strftime("%Y-%m-%d %H:%M:%S")
    print("model:", res["model"])
    save = lambda: OUT.write_text(json.dumps(res, indent=1))
    t0 = time.time()

    # ---- Part 1: request understanding ------------------------------------
    rows = []
    for i, (text, diff, req, forb, reject, literal) in enumerate(INTENT):
        row = {"request": text, "literal_wording": literal,
               "label": {"difficulty": diff, "required": sorted(req), "forbidden": sorted(forb), "reject": reject}}
        for name, use in (("keyword", False), ("llm", True)):
            try:
                r = PL.generate(text, game, seed=1, max_attempts=1, verify_repair=False, save=False,
                                use_llm=use, llm_proposals=0)
                sp = r["spec"]
                got = {"difficulty": sp["difficulty"], "required": sorted(sp["skills_required"]),
                       "forbidden": sorted(sp["skills_forbidden"]),
                       "reject": r["status"] == "REJECTED_CONTRADICTION",
                       "source": r["ai"]["intent_source"], "errors": r["ai"]["errors"]}
            except Exception as e:
                got = {"error": str(e)}
            if name == "llm" and "error" not in got and "LLM" not in got["source"]:
                got = {"error": "LLM call failed, fell back to keyword parser: " + "; ".join(got["errors"])[:200]}
            if "error" not in got:
                if reject:
                    got["correct"] = got["reject"]
                else:
                    got["correct"] = (not got["reject"] and got["difficulty"] == diff
                                      and set(req) <= set(got["required"]) and set(forb) <= set(got["forbidden"])
                                      and not (set(got["required"]) & set(forb)))
                    got["exact"] = got["correct"] and got["required"] == sorted(req) and got["forbidden"] == sorted(forb)
            row[name] = got
        rows.append(row)
        res["intent_rows"] = rows
        save()
        print(f"[{time.time() - t0:5.0f}s] intent {i + 1}/{len(INTENT)}  keyword={rows[-1]['keyword'].get('correct')} "
              f"llm={rows[-1]['llm'].get('correct')}", flush=True)

    def acc(name, subset):
        ok = [r for r in subset if r[name].get("correct")]
        return {"correct": len(ok), "of": len(subset)}
    lit = [r for r in rows if r["literal_wording"]]
    par = [r for r in rows if not r["literal_wording"]]
    res["intent_summary"] = {
        "keyword": {"all": acc("keyword", rows), "literal": acc("keyword", lit), "paraphrased": acc("keyword", par)},
        "llm": {"all": acc("llm", rows), "literal": acc("llm", lit), "paraphrased": acc("llm", par)},
        "llm_fell_back_to_keyword": sum(1 for r in rows if "keyword" in str(r["llm"].get("source", "")))}
    save()

    # ---- Part 2: generation arms --------------------------------------------
    example = (ROOT / "game_src" / "Resources" / "Maps" / "baba_is_you.txt").read_text()
    gens = []
    for i, text in enumerate(GEN):
        row = {"request": text, "arms": {}}
        try:
            spec, _ = llm.parse_request(text, game.spec)
        except Exception as e:
            row["error"] = f"intent failed: {e}"
            gens.append(row)
            continue
        row["spec"] = {k: spec[k] for k in ("difficulty", "skills_required", "skills_forbidden")}
        # raw
        try:
            out, _ = llm.call(RAW_SYSTEM.format(example=example), "REQUEST: " + text, tag="raw_level")
            native = str(out.get("level_file", "")).replace("\\n", "\n")
            row["arms"]["raw_llm"] = stat(PL.verify(game, native, spec, budget_ms=3000, quick=True))
        except Exception as e:
            row["arms"]["raw_llm"] = {"loader_accepts": False, "structurally_valid": False, "solvable": False,
                                      "fully_validated": False, "status": "ERROR", "reasons": [str(e)[:200]]}
        # skill.md, then repair loop
        try:
            cands, _ = llm.propose_levels(text, spec, skill_md, n=1)
            dsl, rounds, st, rep = cands[0]["dsl"], 0, None, None
            for rounds in range(3):
                try:
                    native = game.A.Level.from_dsl(dsl).to_native()
                    rep = PL.verify(game, native, spec, budget_ms=3000, quick=True)
                    if not rep["reasons"] and rep["status"] != "FULLY_VALIDATED":
                        rep["reasons"].append("did not pass verification")
                    st = stat(rep)
                except Exception as e:
                    rep = {"status": "UNVERIFIED", "reasons": [f"malformed level text: {e}"], "initial_rules": []}
                    st = {"loader_accepts": False, "structurally_valid": False, "solvable": False,
                          "fully_validated": False, "status": "MALFORMED", "reasons": rep["reasons"]}
                if rounds == 0:
                    row["arms"]["llm_skill"] = dict(st)
                if st["fully_validated"] or rounds == 2:
                    break
                fixed, _ = llm.repair_level(text, dsl, rep["reasons"], rep.get("initial_rules", []), skill_md)
                dsl = fixed["dsl"]
            row["arms"]["llm_loop"] = dict(st, repair_rounds=rounds)
        except Exception as e:
            for k in ("llm_skill", "llm_loop"):
                row["arms"].setdefault(k, {"loader_accepts": False, "structurally_valid": False, "solvable": False,
                                           "fully_validated": False, "status": "ERROR", "reasons": [str(e)[:200]]})
        # full pipeline (LLM understands, planner builds, verifier judges)
        r = PL.generate(text, game, seed=100 + i, save=False, quick=True, budget_ms=3000, search_seconds=6,
                        use_llm=True, llm_proposals=0)
        if r.get("verification"):
            row["arms"]["full_pipeline"] = dict(stat(r["verification"]), seconds=r["elapsed_seconds"],
                                                difficulty_score=(r["verification"].get("difficulty") or {}).get("score"))
        else:
            row["arms"]["full_pipeline"] = {"loader_accepts": False, "structurally_valid": False, "solvable": False,
                                            "fully_validated": False, "status": r["status"], "reasons": []}
        gens.append(row)
        res["generation_rows"] = gens
        save()
        print(f"[{time.time() - t0:5.0f}s] generation {i + 1}/{len(GEN)}  " +
              "  ".join(f"{k}={v['status']}" for k, v in row["arms"].items()), flush=True)
    arms = {}
    for arm in ("raw_llm", "llm_skill", "llm_loop", "full_pipeline"):
        got = [g["arms"][arm] for g in gens if arm in g.get("arms", {})]
        arms[arm] = {"n": len(got), **{k: sum(1 for a in got if a.get(k))
                                       for k in ("loader_accepts", "structurally_valid", "solvable", "fully_validated")}}
    res["generation_summary"] = arms
    save()

    # ---- Part 3: showcase ----------------------------------------------------
    SHOW.mkdir(parents=True, exist_ok=True)
    shows = []
    for i, text in enumerate(SHOWCASE):
        r = PL.generate(text, game, seed=500 + i, save=False, use_llm=True, llm_proposals=2, search_seconds=10)
        (SHOW / f"llm_{i + 1}.json").write_text(json.dumps(r))
        shows.append({"request": text, "status": r["status"], "delivered_from": r.get("delivered_from"),
                      "title": (r.get("presentation") or {}).get("title"),
                      "proposals": [{"by": p["by"], "status": p["status"], "reasons": p["reasons"][:3]}
                                    for p in r["ai"]["proposals"]],
                      "usage": r["ai"].get("usage")})
        res["showcase"] = shows
        save()
        print(f"[{time.time() - t0:5.0f}s] showcase {i + 1}/{len(SHOWCASE)}  {r['status']}  "
              f"from: {r.get('delivered_from')}", flush=True)

    log = llm._cache()
    res["totals"] = {"cached_answers": len(log),
                     "tokens": sum((e["meta"].get("total_tokens") or 0) for e in log.values()),
                     "llm_seconds": round(sum((e["meta"].get("seconds") or 0) for e in log.values()), 1),
                     "wall_clock_seconds": round(time.time() - t0, 1)}
    res["finished"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save()
    print(json.dumps({k: res[k] for k in ("model", "intent_summary", "generation_summary", "totals")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
