#!/usr/bin/env python3
"""Regression suite for the baba-is-auto blueprint.  Exit code 0 = all green.

  1 probes            every mechanic claim, on the built engine
  2 difftest          fast model vs original engine, move by move
  3 verified levels   stored levels still have the same optimal solution and
                      still replay to WON (C++ engine and pyBaba binding)
  4 backend parity    model search and engine search return the same verdict
  5 validator         malformed / unplayable files are rejected
  6 contradictions    a key behind its own gate is caught before generation
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from blueprints.baba_is_auto import adapter as A  # noqa: E402
from blueprints.baba_is_auto.generator import patterns as P  # noqa: E402
from blueprints.baba_is_auto.tests import probes  # noqa: E402
from blueprints.baba_is_auto.validator import validate as V  # noqa: E402

FIX = json.loads((HERE / "levels" / "verified_levels.json").read_text())
SOUP = """
BABA IS   YOU  .    .    .    .    .
.    .    .    .    .    .    .    .
.    baba ROCK .    IS   .    FLAG .
.    .    .    KEKE .    WIN  .    .
.    rock .    IS   .    .    flag .
.    .    .    .    PUSH .    keke .
.    .    WATER .   SINK .    water .
.    .    .    .    .    .    .    .
"""
results = []


def record(group, name, ok, detail=""):
    results.append((group, name, ok, detail))
    print(("PASS " if ok else "FAIL ") + f"[{group}] {name}" + (f" - {detail}" if detail else ""))


def tmp(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    f.write(text)
    f.close()
    return f.name


def run(args):
    return json.loads(subprocess.run([str(A.SOLVER)] + [str(a) for a in args], capture_output=True,
                                     text=True).stdout)


# 1 probes
for pid, r in probes.run_all().items():
    record("probe", pid, r["passed"], r.get("error", ""))

# 2 differential test
steps_total = 0
for name, dsl in [("soup (forms random rules, incl. transformations)", SOUP)] + [(f["name"], f["dsl"]) for f in FIX]:
    path = tmp(A.Level.from_dsl(dsl).to_native())
    n = 60000 if name.startswith("soup") else 8000
    d = run([path, "--difftest", n, "--seed", 11])
    steps_total += d.get("steps", 0)
    record("difftest", name, d.get("status") == "agree", f"{d.get('steps')} moves" if d.get("status") == "agree" else str(d))
    os.unlink(path)

# 3 verified levels, 4 backend parity
for f in FIX:
    path = tmp(A.Level.from_dsl(f["dsl"]).to_native())
    s = A.solve(path, max_ms=20000, max_states=3_000_000)
    ok = s["status"] == "solved" and s["length"] == f["length"]
    record("verified-level", f["name"], ok, f"optimal {s.get('length')} (stored {f['length']})")
    fr = A.replay(path, f["solution"])["frames"]
    py = A.replay_python_binding(path, f["solution"])
    record("replay", f["name"], fr[-1]["state"] == "WON" and py.get("final_state", "WON") == "WON",
           f"engine {fr[-1]['state']}, pyBaba {py.get('final_state', 'not built')}")
    if f.get("engine_parity"):
        e = run([path, "--backend", "engine", "--max-ms", 60000, "--max-states", 60000])
        record("backend-parity", f["name"], e["status"] == "solved" and e["length"] == s["length"],
               f"engine search {e['status']} {e.get('length')} vs model {s.get('length')}")
    os.unlink(path)

# 5 validator
bad = {"empty": "", "zero dims": "0 3\n4 67 77\n", "non-int": "3 1\n4 IS 77\n", "sentinel id": "3 1\n4 66 77\n",
       "short": "3 2\n4 67 77\n", "four layers": "3 1\n" + "4 67 77\n" * 4,
       "no YOU": "3 2\n4 67 86\n114 132 132\n", "unsupported word": "4 2\n4 67 77 132\n51 67 80 114\n",
       "won immediately": "3 3\n4 67 77\n4 67 86\n114 132 132\n"}
for name, text in bad.items():
    path = tmp(text)
    v = V.validate_file(path)
    record("validator-rejects", name, not v["structurally_valid"],
           "; ".join(c["check"] for c in v["checks"] if not c["passed"]))
    os.unlink(path)
path = tmp(A.Level.from_dsl(FIX[0]["dsl"]).to_native())
record("validator-accepts", FIX[0]["name"], V.validate_file(path)["structurally_valid"])
os.unlink(path)

# 6 contradictions
try:
    P.check_plan(P.Plan(zone_widths=[3, 3], gates=[{"kind": "sink", "noun": "WATER", "key_zone": 1}]))
    record("contradiction", "key behind its own gate", False, "not detected")
except P.PlanError as e:
    record("contradiction", "key behind its own gate", e.kind == "cycle", " -> ".join(e.cycle))

failed = [r for r in results if not r[2]]
print(f"\n{len(results) - len(failed)}/{len(results)} passed; model and engine compared on {steps_total} moves")
(HERE / "last_run.json").write_text(json.dumps(
    {"passed": len(results) - len(failed), "total": len(results), "difftest_moves": steps_total,
     "failures": [list(r) for r in failed]}, indent=1))
sys.exit(1 if failed else 0)
