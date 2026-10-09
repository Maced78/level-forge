#!/usr/bin/env python3
"""Command-line front end.

    python3 -m forge.cli "Create a hard level about rule manipulation" [--seed 7] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys

from . import pipeline as PL


def main():
    ap = argparse.ArgumentParser(description="Generate and verify a level from a natural-language request")
    ap.add_argument("request")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--game", default="baba_is_auto", help="blueprint package name (baba_is_auto, sokoban_sg)")
    ap.add_argument("--attempts", type=int, default=10)
    ap.add_argument("--json", action="store_true", help="print the full machine-readable report")
    a = ap.parse_args()
    res = PL.generate(a.request, PL.Game(a.game), seed=a.seed, max_attempts=a.attempts)
    if a.json:
        print(json.dumps({k: v for k, v in res.items() if k != "frames"}, indent=1))
        return 0
    print(f"status: {res['status']}   (seed {res['seed']}, {res.get('elapsed_seconds')}s)")
    if res["status"] == "REJECTED_CONTRADICTION":
        for c in res["contradictions"]:
            print(f"\n[{c['kind']}] {c['explanation']}")
            if c.get("cycle"):
                print("  cycle: " + "  ->  ".join(c["cycle"]))
            if (c.get("evidence") or {}).get("detail"):
                print("  evidence: " + c["evidence"]["detail"])
            for s in c.get("suggestions", []):
                print("  try: " + s)
        return 2
    print(res.get("dsl", ""))
    v = res.get("verification", {})
    for name, lv in v.get("levels", {}).items():
        tag = "INFO" if name == "robustness" and lv.get("passed") else ("PASS" if lv.get("passed") else "FAIL")
        print(f"  {tag}  {name}: {lv.get('detail', '')}")
    d = v.get("difficulty")
    if d:
        print(f"  difficulty score {d['score']} (established: {d['established']}) {d['components']}")
    for sid, s in v.get("skills", {}).items():
        print(f"  skill {sid}: necessity {s.get('necessity')} - {s.get('detail', '')}")
    if res.get("solution"):
        print(f"solution ({len(res['solution'])} moves): {res['solution']}")
    if res.get("unmet_requirements"):
        print("not met / not established: " + "; ".join(res["unmet_requirements"]))
    if res.get("files"):
        print("exported:", res["files"]["level"], "+", res["files"]["report"])
    return 0 if res["status"] in ("PROVEN_SOLVABLE", "FULLY_VALIDATED") else 1


if __name__ == "__main__":
    sys.exit(main())
