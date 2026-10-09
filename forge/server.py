#!/usr/bin/env python3
"""Local web UI for Level-Forge (standard library only).

    python3 forge/server.py [--port 8765]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from forge import agent1_blueprint as A1, intent, pipeline as PL  # noqa: E402

GAME = PL.Game()
GAMES = {"baba_is_auto": GAME}


def game_for(name):
    """Blueprint packages are loaded on demand: the same pipeline serves every game."""
    name = name if (ROOT / "blueprints" / str(name) / "adapter.py").exists() else "baba_is_auto"
    if name not in GAMES:
        GAMES[name] = PL.Game(name)
    return GAMES[name]
BP = ROOT / "blueprints" / GAME.name
LOCK = threading.Lock()


def blueprint_payload():
    spec = GAME.spec
    prov = json.loads((BP / "provenance.json").read_text())
    ex_path = BP / "tests" / "example_levels.json"
    ex = json.loads(ex_path.read_text())["levels"] if ex_path.exists() else []
    old, new = spec["source_fingerprint"], A1.fingerprint()
    changed = [f for f in new if old.get(f) != new[f]]
    by_kind = {}
    for e in spec["entities"]:
        by_kind.setdefault(e["kind"], []).append(e)
    return {
        "game": spec["game"], "blueprint_version": spec["blueprint_version"], "generated_at": spec["generated_at"],
        "stale": bool(changed), "changed_files": changed,
        "stale_sections": sorted({s for f in changed for s in A1.ANALYSED[f]}),
        "analysed_files": list(A1.ANALYSED),
        "counts": {k: len(v) for k, v in by_kind.items()},
        "turn_pipeline": spec["turn_pipeline"], "skills": spec["skills"],
        "generation_vocabulary": spec["generation_vocabulary"],
        "words": [{"name": e["name"], "kind": e["kind"], "id": e["id"], "support": e.get("support"),
                   "evidence": e.get("support_evidence")} for e in spec["entities"] if e["kind"] != "icon"],
        "claims": prov["claims"], "claim_summary": prov["summary"],
        "level_schema": json.loads((BP / "level_schema.json").read_text()),
        "example_levels": {"total": len(ex), "loader_agreement": sum(e["loader_accepts"] == e["schema_valid"] for e in ex),
                           "solved": sum(e["solver"] == "solved" for e in ex)},
        "skill_md": (BP / "skill.md").read_text() if (BP / "skill.md").exists() else "",
        "mechanics_md": (BP / "mechanics.md").read_text() if (BP / "mechanics.md").exists() else "",
        "engine_available": GAME.A.engine_available(),
    }


def static_frame(level):
    return {"state": "PLAYING", "rules": [], "cells": [{"x": x, "y": y, "name": n, "dir": 4, "id": i}
                                                        for i, ((x, y), st) in enumerate(level.cells.items())
                                                        for n in st]}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            body = (ROOT / "forge" / "static" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/api/blueprint":
            self.send_json(blueprint_payload())
        elif path == "/api/status":
            from forge import llm
            self.send_json(llm.status())
        elif path == "/api/benchmark":
            p = ROOT / "bench" / "results.json"
            self.send_json(json.loads(p.read_text())["summary"] if p.exists() else {"missing": True})
        else:
            self.send_json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        try:
            if self.path == "/api/generate":
                with LOCK:
                    seed = data.get("seed")
                    game = game_for(data.get("game"))
                    res = PL.generate(data["request"], game, seed=int(seed) if str(seed or "").strip() else None,
                                      max_attempts=int(data.get("max_attempts", 40 if game.name == "sokoban_sg" else 10)))
                    res["game_title"] = game.spec["game"]["name"]
                for c in res.get("contradictions", []):
                    ev = c.get("evidence") or {}
                    if ev.get("dsl") and data.get("game", "baba_is_auto") == "baba_is_auto":
                        ev["frame"] = static_frame(GAME.A.Level.from_dsl(ev["dsl"]))
                self.send_json(res)
            elif self.path == "/api/verify":
                with LOCK:
                    level = GAME.A.Level.from_dsl(data["dsl"])
                    spec = intent.parse_request(data.get("request", ""), GAME.spec)
                    rep = PL.verify(GAME, level.to_native(), spec)
                res = {"request": data.get("request", ""), "spec": spec, "status": rep["status"],
                       "width": level.width, "height": level.height, "dsl": level.to_dsl(),
                       "native": level.to_native(), "frames": rep.pop("frames", None) or [static_frame(level)],
                       "solution": rep.get("solution"), "verification": rep, "unmet_requirements": rep["reasons"],
                       "attempts": [{"attempt": 1, "status": rep["status"], "reasons": rep["reasons"],
                                     "proposer": "hand-written / LLM proposal", "size": f"{level.width}x{level.height}"}],
                       "design_notes": {}, "seed": None}
                self.send_json(res)
            elif self.path == "/api/launch":
                self.send_json(launch(data["native"], data.get("solution") or "", data.get("game") or ""))
            else:
                self.send_json({"error": "not found"}, 404)
        except Exception as e:  # surface errors to the UI instead of hanging the request
            self.send_json({"error": f"{type(e).__name__}: {e}"}, 500)


def launch(native_text, solution="", game=""):
    """Open the level in forge/play.py: a resizable, keyboard-playable window that drives
    the ORIGINAL engine through its pyBaba binding (see that file for why the game's own
    scripted, fixed-size GUI is not used)."""
    try:
        import pygame  # noqa: F401
    except ImportError:
        return {"ok": False, "error": "pygame is not installed: run  pip install pygame  and click again"}
    path = ROOT / "out" / "levels" / "_launch.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(native_text)
    sok = game == "sokoban_sg" or set(native_text.split()) <= set("+-@X*$%")
    player = "play_sokoban.py" if sok else "play.py"
    subprocess.Popen([sys.executable, str(ROOT / "forge" / player), str(path), solution or ""], cwd=ROOT)
    return {"ok": True}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    a = ap.parse_args()
    print(f"Level-Forge UI: http://localhost:{a.port}")
    ThreadingHTTPServer(("127.0.0.1", a.port), Handler).serve_forever()
