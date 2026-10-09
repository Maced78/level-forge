#!/usr/bin/env python3
"""Second-game benchmark: the SAME forge/pipeline.py, pointed at the Sokoban blueprint.
    python3 bench/run_benchmark_sokoban.py [--trials 60]
"""
import argparse, json, os, random, statistics, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FORGE_LLM"] = "off"
from forge import pipeline as PL

PROMPTS = {"easy": ["Make an easy sokoban level.", "A simple level about pushing one box.", "Beginner level with a crate."],
           "medium": ["A medium level with two boxes.", "Create a moderate level about pushing several boxes.", "Medium sokoban level."],
           "hard": ["Create a hard level that needs careful planning with several boxes.", "A difficult level with three boxes.", "Hard sokoban puzzle."]}
BAD = ["Make a level with three boxes and two goals.", "A level with teleporters.", "Create a level with 4 crates and 1 target.",
       "A sokoban level with a laser.", "Level where boxes fall with gravity."]
GOOD = ["Make an easy sokoban level.", "A medium level with two boxes.", "A level with two boxes and three goals.", "Hard level with three crates."]

ap = argparse.ArgumentParser(); ap.add_argument("--trials", type=int, default=60); a = ap.parse_args()
game = PL.Game("sokoban_sg"); rng = random.Random(7); rows = []; t0 = time.time()
for i in range(a.trials):
    d = ["easy", "medium", "hard"][i % 3]
    prompt = PROMPTS[d][(i // 3) % 3]
    t = time.time()
    r = PL.generate(prompt, game, seed=9000 + i, save=False, quick=True, budget_ms=3000, search_seconds=5, use_llm=False)
    v = r.get("verification") or {}
    replay_ok = None
    if r.get("solution") is not None and r.get("native"):
        p = game.A.tempfile.mkstemp(suffix=".dat")[1]; Path(p).write_text(r["native"])
        fr = game.A.replay(p, r["solution"]); os.unlink(p)
        replay_ok = fr.get("status") == "ok" and fr["frames"][-1]["solved"]
    rows.append({"difficulty": d, "prompt": prompt, "status": r["status"], "seconds": round(time.time() - t, 2),
                 "attempts": len(r["attempts"]), "solution_length": len(r.get("solution") or ""),
                 "score": (v.get("difficulty") or {}).get("score"), "engine_replay_won": replay_ok})
    if (i + 1) % 15 == 0: print(f"[{time.time() - t0:4.0f}s] {i + 1}/{a.trials}", flush=True)
def rej(p): return PL.generate(p, game, seed=1, max_attempts=1, verify_repair=False, save=False, use_llm=False)["status"] == "REJECTED_CONTRADICTION"
by = {}
for d in ("easy", "medium", "hard"):
    x = [r for r in rows if r["difficulty"] == d]
    by[d] = {"n": len(x), "fully_validated_pct": round(100 * sum(r["status"] == "FULLY_VALIDATED" for r in x) / len(x), 1),
             "solvable_pct": round(100 * sum(r["status"] in ("FULLY_VALIDATED", "PROVEN_SOLVABLE") for r in x) / len(x), 1),
             "median_score": statistics.median([r["score"] for r in x if r["score"] is not None] or [0]),
             "median_solution_length": statistics.median([r["solution_length"] for r in x]),
             "median_seconds": statistics.median(r["seconds"] for r in x)}
labelled = [r for r in rows if r["status"] in ("FULLY_VALIDATED", "PROVEN_SOLVABLE")]
summary = {"game": game.spec["game"], "trials": len(rows),
           "solvable_pct": round(100 * len(labelled) / len(rows), 1),
           "fully_validated_pct": round(100 * sum(r["status"] == "FULLY_VALIDATED" for r in rows) / len(rows), 1),
           "labelled_solvable": len(labelled), "false_acceptances": sum(1 for r in labelled if not r["engine_replay_won"]),
           "by_difficulty": by, "contradictory_rejected": f"{sum(rej(p) for p in BAD)}/{len(BAD)}",
           "valid_controls_wrongly_rejected": f"{sum(rej(p) for p in GOOD)}/{len(GOOD)}",
           "median_seconds": statistics.median(r["seconds"] for r in rows), "wall_clock_seconds": round(time.time() - t0, 1),
           "pipeline_lines_changed_for_this_game": 0}
(ROOT / "bench" / "results_sokoban.json").write_text(json.dumps({"summary": summary, "trials": rows}, indent=1))
print(json.dumps(summary, indent=1))
