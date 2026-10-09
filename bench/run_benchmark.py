#!/usr/bin/env python3
"""Reproducible benchmark for the Level-Forge pipeline.

    python3 bench/run_benchmark.py [--trials 200] [--workers 2] [--seed 2026]

Arms (all evaluated by the SAME verifier, after the fact):

  random_tiles      unconstrained generation: tiles drawn at random from the
                    game's vocabulary.  No blueprint knowledge.
  blueprint_only    the blueprint-guided constructor's FIRST candidate, taken
                    on trust (no validation, no solver, no repair).
  full_pipeline     constraint construction + validation + solver + engine
                    replay + skill proofs + bounded repair loop.

The two LLM arms of the original plan (raw LLM, LLM + skill.md) need an API
key and are NOT run here; see forge/llm.py.  The first two arms above are
their no-LLM stand-ins and are labelled as such everywhere.

Everything is measured; nothing is assumed.  Timeouts and unresolved cases
stay in the tables.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import random
import statistics
import subprocess
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from forge import intent, pipeline as PL  # noqa: E402

SKILL_PHRASES = {
    "rule_manipulation": ["rule manipulation", "manipulating rules", "breaking a rule"],
    "object_pushing": ["object pushing", "pushing rocks strategically", "sokoban-style pushing"],
    "win_condition_change": ["a changing win condition", "reasoning about the win condition", "forming IS WIN"],
    "you_change": ["manipulating the IS YOU rule", "changing who IS YOU"],
    "hazard_sink": ["water that sinks things", "a sink hazard"],
    "hazard_defeat": ["deadly skulls", "a defeat hazard"],
}
TEMPLATES = ["Create a {d} level that tests {s}.", "Make a {d} puzzle about {s}.",
             "Design a {d} level combining {s}; it must be solvable.", "I need a {d} level exercising {s}."]
DIFF_WORDS = {"easy": ["easy", "simple", "beginner"], "medium": ["medium", "moderate"],
              "hard": ["hard", "difficult", "challenging"]}
COMBOS = {
    "easy": [["rule_manipulation"], ["object_pushing"], ["win_condition_change"], ["you_change"],
             ["hazard_defeat"], ["hazard_sink"], []],
    "medium": [["rule_manipulation", "object_pushing"], ["win_condition_change", "hazard_defeat"],
               ["object_pushing", "win_condition_change"], ["you_change", "object_pushing"],
               ["rule_manipulation"], ["win_condition_change"], []],
    "hard": [["rule_manipulation", "object_pushing", "win_condition_change"],
             ["object_pushing", "win_condition_change", "hazard_defeat"],
             ["you_change", "object_pushing"], ["rule_manipulation", "object_pushing"],
             ["win_condition_change", "object_pushing"], []],
}
CONTRADICTORY = [
    "Create a hard level where the only rocks are behind the water and the water can only be crossed by sinking a rock in it.",
    "Make a level where the rock is on the far side of the water and you need the rock to cross the water.",
    "Design a medium level where the boxes are locked behind the lava, which you can only pass by pushing a box in.",
    "Hard level about changing the win condition but without any rule manipulation.",
    "A level that requires manipulating the IS YOU rule but no rules may change.",
    "Make a level with teleporters.",
    "Create a level using the PULL rule to drag rocks.",
    "A level built around TELE and SWAP.",
    "Design a puzzle with gravity where rocks FALL.",
    "Create a level with a laser and a pressure plate.",
    "An easy level that needs at least 30 moves and at most 10 moves.",
    "Make a level that uses object pushing but with no pushing at all.",
    "A level with a conveyor belt (SHIFT).",
    "Create a 40x40 hard level about rule manipulation.",
    "Level where the crate is beyond the water and the water needs a crate.",
    "Use the MORE rule so that grass spreads.",
    "A level about SLEEP and waking up Keke.",
    "Make the player jump over walls.",
    "Level with a timer that counts down.",
]
VALID_CONTROL = [
    "Create an easy level about pushing rocks into water.",
    "Make a medium level that tests rule manipulation.",
    "A level that teaches the IS YOU rule.",
    "Create a level with skulls and a changing win condition.",
    "Make a level without any water.",
    "An easy level with no object pushing.",
    "A hard level about object pushing, no skulls.",
    "Medium level, at least 12 moves.",
    "Create a level that avoids teleporters entirely and tests rule manipulation.",
    "Simple level about the win condition.",
]


def make_prompts(n, seed):
    rng = random.Random(seed)
    out = []
    diffs = ["easy", "medium", "hard"]
    i = 0
    while len(out) < n:
        d = diffs[i % 3]
        combo = COMBOS[d][(i // 3) % len(COMBOS[d])]
        if combo:
            s = " and ".join(rng.choice(SKILL_PHRASES[k]) for k in combo)
            text = rng.choice(TEMPLATES).format(d=rng.choice(DIFF_WORDS[d]), s=s)
        else:
            text = f"Create a {rng.choice(DIFF_WORDS[d])} level."
        out.append({"id": i, "prompt": text, "difficulty": d, "skills": combo, "seed": seed * 1000 + i})
        i += 1
    return out


def random_tiles_level(game, spec, rng):
    """Unconstrained baseline: no knowledge of rules, rails, gates or solvability."""
    A = game.A
    w, h = rng.randint(7, 12), rng.randint(6, 8)
    lv = A.Level(w, h)
    texts = ["BABA", "IS", "YOU", "FLAG", "IS", "WIN", "ROCK", "PUSH", "WALL", "STOP", "WATER", "SINK", "IS",
             "SKULL", "DEFEAT", "KEKE"]
    icons = ["baba", "flag", "rock", "wall", "water", "skull", "keke"]
    for y in range(h):
        for x in range(w):
            r = rng.random()
            if r < 0.14:
                lv.put(x, y, rng.choice(texts))
            elif r < 0.34:
                lv.put(x, y, rng.choice(icons))
    return lv


def summarise_report(rep, spec):
    lv = rep.get("levels", {})
    st = lv.get("structural", {})
    checks = {c["check"]: c["passed"] for c in st.get("checks", [])}
    req = spec["skills_required"]
    return {
        "status": rep["status"],
        "schema_valid": bool(checks.get("loader.engine_accepts")),
        "rule_valid": bool(st.get("passed")),
        "solvable": bool(lv.get("solvable", {}).get("passed")),
        "proved_unsolvable": lv.get("solvable", {}).get("established") is True and not lv.get("solvable", {}).get("passed"),
        "unresolved": "solvable" in lv and lv["solvable"].get("established") is False,
        "skills_requested": len(req),
        "skills_covered": sum(1 for s in req if rep.get("skills", {}).get(s, {}).get("passed")),
        "in_band": lv.get("solution_quality", {}).get("in_band"),
        "solution_length": lv.get("solution_quality", {}).get("shortest_length"),
        "difficulty_score": lv.get("solution_quality", {}).get("difficulty_score"),
        "fully_validated": rep["status"] == "FULLY_VALIDATED",
        "dead_state_ratio": lv.get("robustness", {}).get("dead_state_ratio"),
        "states": (rep.get("search") or {}).get("states_explored"),
    }


def run_trial(p):
    game = PL.Game()
    spec = intent.parse_request(p["prompt"], game.spec)
    out = {"id": p["id"], "prompt": p["prompt"], "difficulty": p["difficulty"],
           "skills": spec["skills_required"], "arms": {}}

    # arm 1: random tiles
    t = time.time()
    lv = random_tiles_level(game, spec, random.Random(p["seed"]))
    gen_t = time.time() - t
    rep = PL.verify(game, lv.to_native(), spec, budget_ms=1500, quick=True)
    out["arms"]["random_tiles"] = {**summarise_report(rep, spec), "generation_seconds": round(gen_t, 4),
                                   "attempts": 1, "claimed": "none"}

    # arm 2: blueprint-guided construction, first candidate, no verification
    t = time.time()
    r = PL.generate(p["prompt"], game, seed=p["seed"], max_attempts=1, verify_repair=False, save=False)
    gen_t = time.time() - t
    if r.get("native"):
        rep = PL.verify(game, r["native"], spec, budget_ms=3000, quick=True)
        out["arms"]["blueprint_only"] = {**summarise_report(rep, spec), "generation_seconds": round(gen_t, 4),
                                         "attempts": 1, "claimed": "none"}
    else:
        out["arms"]["blueprint_only"] = {"status": r["status"], "schema_valid": False, "rule_valid": False,
                                         "solvable": False, "skills_requested": len(spec["skills_required"]),
                                         "skills_covered": 0, "fully_validated": False,
                                         "generation_seconds": round(gen_t, 4), "attempts": 1, "claimed": "none"}

    # arm 3: full pipeline
    t = time.time()
    r = PL.generate(p["prompt"], game, seed=p["seed"], max_attempts=8, budget_ms=3000, quick=True, save=False,
                    search_seconds=6)
    gen_t = time.time() - t
    if r.get("native"):
        rep = r["verification"]
        s = summarise_report(rep, spec)
        # independent re-check of the pipeline's own claim, through the game's Python binding
        path = game.A.tempfile.mkstemp(suffix=".txt")[1]
        Path(path).write_text(r["native"])
        claim_solvable = r["status"] in ("PROVEN_SOLVABLE", "FULLY_VALIDATED")
        py = game.A.replay_python_binding(path, r.get("solution") or "")
        os.unlink(path)
        s.update({"generation_seconds": round(gen_t, 3), "attempts": len(r["attempts"]),
                  "claimed": r["status"], "claim_solvable": claim_solvable,
                  "independent_final_state": py.get("final_state"),
                  "false_acceptance": claim_solvable and py.get("final_state") != "WON",
                  "size": f"{r['width']}x{r['height']}", "unmet": r["unmet_requirements"]})
        out["arms"]["full_pipeline"] = s
    else:
        out["arms"]["full_pipeline"] = {"status": r["status"], "schema_valid": False, "rule_valid": False,
                                        "solvable": False, "skills_requested": len(spec["skills_required"]),
                                        "skills_covered": 0, "fully_validated": False,
                                        "generation_seconds": round(gen_t, 3), "attempts": len(r["attempts"]),
                                        "claimed": r["status"], "false_acceptance": False,
                                        "contradictions": r.get("contradictions")}
    return out


def run_sabotage(args):
    """Break an accepted level and check the model's verdict against the real engine."""
    idx, seed = args
    game = PL.Game()
    A = game.A
    rng = random.Random(seed)
    prompt = rng.choice(["Create an easy level that tests object pushing.",
                         "Create an easy level that tests rule manipulation.",
                         "Create an easy level about manipulating the IS YOU rule.",
                         "Create an easy level about forming IS WIN."])
    r = PL.generate(prompt, game, seed=seed, max_attempts=4, budget_ms=1500, quick=True, save=False)
    if not r.get("native"):
        return None
    lv = A.Level.from_native(r["native"])
    cells = [(k, i) for k, st in lv.cells.items() for i in range(len(st))]
    kind = rng.choice(["delete", "delete", "swap", "none"])
    if kind == "delete":
        (k, i) = rng.choice(cells)
        del lv.cells[k][i]
    elif kind == "swap":
        (a, _), (b, _) = rng.sample(cells, 2)
        lv.cells[a], lv.cells[b] = lv.cells[b], lv.cells[a]
    path = A.write_temp(lv)
    m = A.solve(path, max_ms=3000)
    e = json.loads(subprocess.run([str(A.SOLVER), path, "--backend", "engine", "--max-ms", "6000",
                                   "--max-states", "30000"], capture_output=True, text=True).stdout)
    replay_ok = None
    if m["status"] == "solved":
        fr = A.replay(path, m["moves"])
        replay_ok = fr.get("status") == "ok" and fr["frames"][-1]["state"] == "WON"
    os.unlink(path)
    return {"mutation": kind, "model": m["status"], "engine": e["status"], "model_len": m.get("length"),
            "engine_len": e.get("length"), "model_witness_wins_in_engine": replay_ok,
            "comparable": e["status"] in ("solved", "unsolvable") and m["status"] in ("solved", "unsolvable"),
            "agree": e["status"] == m["status"] and (e["status"] != "solved" or e["length"] == m["length"])}


def pct(a, b):
    return None if not b else round(100 * a / b, 1)


def summarise(trials, contra, sabotage, meta):
    arms = {}
    for arm in ("random_tiles", "blueprint_only", "full_pipeline"):
        rows = [t["arms"][arm] for t in trials]
        n = len(rows)
        req = sum(r["skills_requested"] for r in rows)
        times = [r["generation_seconds"] for r in rows]
        claimed = [r for r in rows if r.get("claim_solvable")]
        arms[arm] = {
            "n": n,
            "schema_validity_pct": pct(sum(r["schema_valid"] for r in rows), n),
            "rule_validity_pct": pct(sum(r["rule_valid"] for r in rows), n),
            "solvability_established_pct": pct(sum(r["solvable"] for r in rows), n),
            "proved_unsolvable": sum(bool(r.get("proved_unsolvable")) for r in rows),
            "unresolved_within_bound": sum(bool(r.get("unresolved")) for r in rows),
            "mechanic_coverage_pct": pct(sum(r["skills_covered"] for r in rows), req),
            "difficulty_alignment_pct": pct(sum(bool(r.get("in_band")) for r in rows), n),
            "fully_validated_pct": pct(sum(r["fully_validated"] for r in rows), n),
            "latency_seconds": {"median": round(statistics.median(times), 3),
                                "p90": round(sorted(times)[int(0.9 * (n - 1))], 3), "max": round(max(times), 3)},
            "mean_attempts": round(statistics.mean(r["attempts"] for r in rows), 2),
        }
        if arm == "full_pipeline":
            arms[arm]["levels_labelled_solvable"] = len(claimed)
            arms[arm]["false_acceptances"] = sum(bool(r.get("false_acceptance")) for r in claimed)
            arms[arm]["false_acceptance_rate_pct"] = pct(sum(bool(r.get("false_acceptance")) for r in claimed),
                                                         len(claimed))
            arms[arm]["by_difficulty"] = {
                d: {"n": len(x), "fully_validated_pct": pct(sum(r["fully_validated"] for r in x), len(x)),
                    "solvable_pct": pct(sum(r["solvable"] for r in x), len(x)),
                    "median_solution_length": statistics.median([r["solution_length"] for r in x
                                                                 if r.get("solution_length")] or [0]),
                    "median_difficulty_score": statistics.median([r["difficulty_score"] for r in x
                                                                  if r.get("difficulty_score") is not None] or [0]),
                    "median_latency_s": round(statistics.median(r["generation_seconds"] for r in x), 2)}
                for d in ("easy", "medium", "hard")
                for x in [[t["arms"][arm] for t in trials if t["difficulty"] == d]] if x}
    sab = [s for s in sabotage if s]
    comp = [s for s in sab if s["comparable"]]
    summary = {
        "meta": meta, "arms": arms,
        "contradiction_handling": {
            "contradictory_prompts": len(contra["bad"]),
            "correctly_rejected": sum(c["rejected"] for c in contra["bad"]),
            "rejected_with_suggestion": sum(c["rejected"] and c["has_suggestion"] for c in contra["bad"]),
            "valid_control_prompts": len(contra["good"]),
            "wrongly_rejected_controls": sum(c["rejected"] for c in contra["good"]),
            "missed": [c["prompt"] for c in contra["bad"] if not c["rejected"]],
            "false_alarms": [c["prompt"] for c in contra["good"] if c["rejected"]],
        },
        "model_vs_engine_on_sabotaged_levels": {
            "levels": len(sab), "comparable_verdicts": len(comp),
            "agree": sum(s["agree"] for s in comp), "disagree": sum(not s["agree"] for s in comp),
            "engine_bound_reached": len(sab) - len(comp),
            "model_says_solved": sum(s["model"] == "solved" for s in sab),
            "of_which_witness_wins_in_real_engine": sum(bool(s["model_witness_wins_in_engine"]) for s in sab),
            "model_says_unsolvable": sum(s["model"] == "unsolvable" for s in sab),
        },
        "not_measured": {
            "raw_llm_arm": "requires an API key (forge/llm.py); random_tiles is the no-LLM stand-in",
            "llm_plus_skill_md_arm": "requires an API key; blueprint_only is the no-LLM stand-in",
            "cross_version_reliability": "only one game version analysed; `agent1_blueprint.py --check` "
                                         "detects source drift but no second version was benchmarked",
            "difficulty_vs_human_playtest": "no playtesting; difficulty is the blueprint's own score (trap "
                                            "pressure, dead-state ratio, rule changes, sacrificed words), "
                                            "which has not been compared with human ratings",
        },
    }
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--sabotage", type=int, default=120)
    a = ap.parse_args()
    t0 = time.time()
    prompts = make_prompts(a.trials, a.seed)
    out_dir = ROOT / "bench"
    with Pool(a.workers) as pool:
        trials = []
        for i, r in enumerate(pool.imap_unordered(run_trial, prompts), 1):
            trials.append(r)
            if i % 10 == 0:
                print(f"[{time.time() - t0:6.0f}s] {i}/{len(prompts)} trials", flush=True)
        sabotage = pool.map(run_sabotage, [(i, a.seed * 7 + i) for i in range(a.sabotage)])
    trials.sort(key=lambda t: t["id"])
    game = PL.Game()
    contra = {"bad": [], "good": []}
    for key, plist in (("bad", CONTRADICTORY), ("good", VALID_CONTROL)):
        for p in plist:
            r = PL.generate(p, game, seed=1, max_attempts=1, verify_repair=False, save=False)
            cs = r.get("contradictions") or []
            contra[key].append({"prompt": p, "rejected": r["status"] == "REJECTED_CONTRADICTION",
                                "kinds": [c["kind"] for c in cs],
                                "has_suggestion": all(c.get("suggestions") for c in cs) if cs else False})
    meta = {"trials": a.trials, "seed": a.seed, "workers": a.workers,
            "python": platform.python_version(), "machine": platform.machine(),
            "cpu_count": os.cpu_count(), "platform": platform.platform(),
            "limits": {"analysis_ms": 3000, "ablation_ms": 2000, "max_attempts": 8, "hard_search_seconds": 6,
                       "analysis_max_states": 3_000_000},
            "verifier": "model search + replay of every witness in the original engine; "
                        "independent re-check through the pyBaba binding",
            "wall_clock_seconds": round(time.time() - t0, 1),
            "blueprint_version": game.spec["blueprint_version"], "game_commit": game.spec["game"]["commit"]}
    summary = summarise(trials, contra, sabotage, meta)
    (out_dir / "results.json").write_text(json.dumps(
        {"summary": summary, "contradiction_prompts": contra, "sabotage": sabotage, "trials": trials}, indent=1))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
