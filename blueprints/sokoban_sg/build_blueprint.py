#!/usr/bin/env python3
"""Agent 1's deterministic half for the Sokoban blueprint: resolves every claim's source line in the
game's code, runs its probe on the original engine, differential-tests the search model against
the engine, and writes provenance.json.

    python3 blueprints/sokoban_sg/build_blueprint.py
"""
import hashlib, json, os, random, re, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
from blueprints.sokoban_sg import adapter as A
from blueprints.sokoban_sg.tests import probes
from blueprints.sokoban_sg.generator import patterns as P

SRC = A.GAME_DIR
FILES = ["src/game.py", "src/player.py", "src/box.py", "src/utils.py"]


def line_of(rel, pattern):
    for i, line in enumerate((SRC / rel).read_text().splitlines(), 1):
        if re.search(pattern, line):
            return i, line.strip()
    return None, None


res = probes.run_all()
claims = []
for pid, r in res.items():
    rel, pat = r["source"]
    ln, text = line_of(rel, pat)
    claims.append({"id": pid, "statement": r["claim"], "status": "confirmed" if (ln and r["passed"]) else "refuted",
                   "source": {"file": rel, "line": ln, "text": text}, "evidence": {"probe": f"tests/probes.py::{pid}", "passed": r["passed"]}})
claims.append({"id": "open_border_crash", "status": "confirmed-by-source",
               "statement": "A level without a closed wall border lets the player index outside the puzzle (target_elem is None).",
               "source": dict(zip(("line", "text"), line_of("src/player.py", r"target_elem = self\.game\.puzzle\[target\]")), file="src/player.py"),
               "consequence": "The validator requires a closed border; the generator always builds one."})
claims.append({"id": "window_limit", "status": "confirmed-by-source",
               "statement": "The engine's fixed 1216x640 window holds at most a 17x10 puzzle.",
               "source": dict(zip(("line", "text"), line_of("src/game.py", r"def __init__\(self, window=None, width=1216, height=640")), file="src/game.py"),
               "consequence": "Size policy 12x9."})
claims.append({"id": "model_equivalence", "status": "inferred",
               "statement": "The search model (adapter.model_step) is equivalent to Player.update + Box.can_move.",
               "basis": "differential-tested below; not proven", "consequence": "'Unsolvable' and dead-state counts are model-level results; every solution is replayed in the engine."})

# differential test: model vs original engine on random walks
rng, moves_total, mismatch = random.Random(3), 0, 0
for k in range(12):
    lv = P.build(P.Plan(width=8, height=7, boxes=2 + k % 2, goals=3, walls=rng.randint(1, 5)), rng)
    path = A.write_temp(lv)
    moves = "".join(rng.choice("UDLR") for _ in range(250))
    frames = A.replay(path, moves)["frames"]
    w, h, walls, goals, boxes, player = A.parse(lv.to_native())
    st = (player, boxes)
    for i, m in enumerate(moves):
        st, _ = A.model_step(w, h, walls, st, m)
        raw = frames[i + 1]["raw"]
        eng = (next(p for p, c in enumerate(raw) if c in "*%"), frozenset(p for p, c in enumerate(raw) if c in "@$"))
        moves_total += 1
        if eng != st or frames[i + 1]["solved"] != (st[1] <= goals):
            mismatch += 1
            break
    os.unlink(path)
prov = {"blueprint_version": A.SPEC["blueprint_version"], "game_commit": A.SPEC["game"]["commit"],
        "source_fingerprint": {f: hashlib.sha256((SRC / f).read_bytes()).hexdigest() for f in FILES},
        "summary": {s: sum(1 for c in claims if c["status"] == s) for s in sorted({c["status"] for c in claims})},
        "difftest": {"moves_compared": moves_total, "mismatching_walks": mismatch, "walks": 12},
        "claims": claims}
(HERE / "provenance.json").write_text(json.dumps(prov, indent=1))
print("claims:", prov["summary"], "| model vs engine:", prov["difftest"])
sys.exit(1 if mismatch or any(c["status"] == "refuted" for c in claims) else 0)
