#!/usr/bin/env python3
"""Builds docs/data.js (the hosted demo's data) from REAL pipeline runs.

    python3 docs/build_site.py           # needs ./build_engine.sh first

Gallery entries are produced by forge.pipeline.generate on this machine and verified against the
original engine; the hosted page only replays them.  Also writes docs/engine_traces.json, frames
recorded from the original engine, which docs/test_model.js uses to check the JavaScript model.
"""
import json, os, random, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FORGE_LLM"] = "off"
from forge import pipeline as PL
game = PL.Game(); A = game.A
REQUESTS = [
 ("Create a difficult level that tests the player's ability to manipulate rules, use object pushing strategically, and reason about changing win conditions. Make it solvable, use only mechanics supported by the game, and export it as a new native level file.", 1),
 ("Create a level that teaches the player how to manipulate the IS YOU rule.", 7),
 ("Make an easy level about pushing rocks into water.", 7),
 ("A medium level with skulls where the win condition changes, no object pushing.", 7),
 ("Hard level about the IS YOU rule and pushing boxes into lava.", 3),
 ("Easy level, solvable in at most 8 moves, with a unique solution.", 7),
 ("Create a hard level where the only rocks are behind the water and the water can only be crossed by sinking a rock in it.", 1),
 ("Make a level with teleporters and a PULL rule.", 1),
 ("Hard level about changing the win condition but without any rule manipulation.", 1),
]
def slim_frames(frames):
    return [{"state": f["state"], "rules": f["rules"], "cells": [[c["x"], c["y"], c["name"], c["id"]] for c in f["cells"]]} for f in frames]
def slim(r, source):
    out = {k: r.get(k) for k in ("request", "status", "seed", "spec", "width", "height", "dsl", "native", "solution",
                                 "unmet_requirements", "attempts", "search", "contradictions", "elapsed_seconds",
                                 "presentation", "delivered_from", "ai", "design_notes")}
    out["source"] = source
    if r.get("verification"):
        out["verification"] = r["verification"]
    if r.get("frames"):
        out["frames"] = slim_frames(r["frames"])
    for c in out.get("contradictions") or []:
        ev = c.get("evidence") or {}
        if ev.get("dsl"):
            lv = A.Level.from_dsl(ev["dsl"])
            ev["cells"] = [[x, y, n, i] for i, ((x, y), st) in enumerate(lv.cells.items()) for n in st]
    return out
gallery = []
for req, seed in REQUESTS:
    for k in range(6):          # prefer landscape boards for the page layout
        r = PL.generate(req, game, seed=seed + 1000 * k, save=False, use_llm=False)
        if r.get("width", 9) >= r.get("height", 0) and r["status"] in ("FULLY_VALIDATED", "REJECTED_CONTRADICTION"):
            break
    print(r["status"], "|", req[:60]); gallery.append(slim(r, "deterministic parser + constraint planner (no LLM), recorded offline"))
show = ROOT / "out" / "showcase"
llm_runs = []
if show.exists():
    for p in sorted(show.glob("llm_*.json")):
        llm_runs.append(slim(json.loads(p.read_text()), "LLM pipeline (Gemini), recorded on the team's machine"))
# engine traces for the JS model test
traces, rng = [], random.Random(5)
levels = [g["dsl"] for g in gallery + llm_runs if g.get("dsl")]
for dsl in levels:
    path = A.write_temp(A.Level.from_dsl(dsl))
    for _ in range(40):
        moves = "".join(rng.choice("UDLR") for _ in range(60))
        fr = A.replay(path, moves)["frames"]
        traces.append({"dsl": dsl, "moves": moves, "frames": [{"state": f["state"], "cells": sorted([c["x"], c["y"], c["name"]] for c in f["cells"])} for f in fr]})
    os.unlink(path)
for g in gallery + llm_runs:
    if g.get("solution"):
        path = A.write_temp(A.Level.from_dsl(g["dsl"])); fr = A.replay(path, g["solution"])["frames"]; os.unlink(path)
        traces.append({"dsl": g["dsl"], "moves": g["solution"], "frames": [{"state": f["state"], "cells": sorted([c["x"], c["y"], c["name"]] for c in f["cells"])} for f in fr]})
for t in traces:       # the engine's play state is sticky after WON/LOST: compare up to the first terminal frame
    end = next((i for i, f in enumerate(t["frames"]) if f["state"] != "PLAYING"), len(t["frames"]) - 1)
    t["frames"], t["moves"] = t["frames"][:end + 1], t["moves"][:end]
(ROOT / "docs" / "engine_traces.json").write_text(json.dumps(traces))
spec = game.spec
prov = json.loads((ROOT / "blueprints" / game.name / "provenance.json").read_text())
bench = json.loads((ROOT / "bench" / "results.json").read_text())["summary"]
llm_res = json.loads((ROOT / "bench" / "llm_results.json").read_text()) if (ROOT / "bench" / "llm_results.json").exists() else None
tests = {}
tp = ROOT / "blueprints" / game.name / "tests" / "last_run.json"
if tp.exists(): tests = json.loads(tp.read_text())
# ---- second game: the same pipeline on Sokoban ----
sok = None
if (ROOT / "bench" / "results_sokoban.json").exists():
    sg = PL.Game("sokoban_sg")
    runs = []
    for req, seed in [("Make an easy sokoban level.", 11), ("Create a hard level that needs careful planning with several boxes.", 3),
                      ("Make a level with three boxes and two goals.", 4)]:
        r = PL.generate(req, sg, seed=seed, save=False, use_llm=False)
        s_ = slim(r, "second game (Sokoban), deterministic parser + planner, recorded offline"); s_["game"] = "sokoban_sg"
        runs.append(s_); print("sokoban", r["status"], "|", req)
    sprov = json.loads((ROOT / "blueprints" / "sokoban_sg" / "provenance.json").read_text())
    lines = sum(len(p.read_text().splitlines()) for p in (ROOT / "blueprints" / "sokoban_sg").rglob("*.py"))
    sok = {"runs": runs, "bench": json.loads((ROOT / "bench" / "results_sokoban.json").read_text())["summary"],
           "claims": sprov["summary"], "difftest": sprov["difftest"], "adapter_lines": lines}
data = {"gallery": gallery, "llm_runs": llm_runs, "sokoban": sok,
        "nouns": [e["name"] for e in spec["entities"] if e["kind"] == "noun"],
        "known": [e["name"] for e in spec["entities"]],
        "game": spec["game"], "turn_pipeline": spec["turn_pipeline"], "skills": spec["skills"],
        "claims": prov["claims"], "claim_summary": prov["summary"],
        "unsupported": [{"name": e["name"], "evidence": e.get("support_evidence")} for e in spec["entities"] if e.get("support") == "unsupported"],
        "bench": bench, "llm": llm_res, "tests": tests, "trace_frames": sum(len(t["frames"]) - 1 for t in traces)}
(ROOT / "docs" / "data.js").write_text("window.FORGE_DATA = " + json.dumps(data) + ";\n")
print("gallery", len(gallery), "llm runs", len(llm_runs), "engine frames for JS test", data["trace_frames"])
