"""Agent 2 - Verified Level Generator.

    request -> spec -> contradiction check -> plan -> level IR -> native file
            -> validate -> solve -> certify in the real engine -> skill proofs
            -> accept, or repair and try again (bounded)

The game-specific parts (adapter, validator, planner, patterns) are imported
from the blueprint package named by `game`; nothing in this file knows about
Baba Is You.
"""
from __future__ import annotations

import importlib
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import intent, llm

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "out" / "levels"

STATUS_ORDER = ["UNVERIFIED", "STRUCTURALLY_VALID", "PROVEN_SOLVABLE", "FULLY_VALIDATED"]


class Game:
    def __init__(self, name="baba_is_auto"):
        base = f"blueprints.{name}"
        self.name = name
        self.A = importlib.import_module(base + ".adapter")
        self.V = importlib.import_module(base + ".validator.validate")
        self.P = importlib.import_module(base + ".generator.patterns")
        self.planner = importlib.import_module(base + ".generator.planner")
        self.spec = self.A.SPEC
        self.skills = {s["id"]: s for s in self.spec["skills"]}


# --------------------------------------------------------------------------
# Spec-level contradiction detection (before anything is generated)
# --------------------------------------------------------------------------
IMPLIES = {"win_condition_change": "rule_manipulation", "you_change": "rule_manipulation"}


def find_contradictions(game: Game, spec: dict):
    out = []
    for tok in spec["unsupported_requested"]:
        ent = next((e for e in game.spec["entities"] if e["name"] == tok), {})
        out.append({"kind": "unsupported_mechanic",
                    "explanation": f"'{tok}' exists as a word in this game's enum but has no behaviour: "
                                   f"{ent.get('support_evidence', '')}. A level relying on it would be invalid.",
                    "suggestions": ["use PUSH / STOP / SINK / DEFEAT, which are implemented and probe-confirmed",
                                    "implement the mechanic in the engine, then regenerate the blueprint"]})
    for phrase in spec["foreign_requested"]:
        out.append({"kind": "mechanic_not_in_game",
                    "explanation": f"'{phrase}' is not a mechanic of this game: nothing in the analysed source "
                                   f"implements it, and the generator may not invent mechanics.",
                    "suggestions": ["describe the challenge in terms of the game's own rules"]})
    for tok in spec["outside_vocabulary"]:
        out.append({"kind": "outside_verified_vocabulary",
                    "explanation": f"'{tok}' is implemented by the engine but has no probe in this blueprint yet, "
                                   f"so the generator will not build a level around it.",
                    "suggestions": [f"add a probe for {tok} to tests/probes.py and rebuild the blueprint",
                                    "request a mechanic from the verified vocabulary"]})
    req, forb = set(spec["skills_required"]), set(spec["skills_forbidden"])
    for s in sorted(req & forb):
        out.append({"kind": "skill_conflict",
                    "explanation": f"'{s}' is both required and forbidden.",
                    "suggestions": ["remove one of the two statements"]})
    for a, b in game.spec.get("skill_implies", IMPLIES if game.name == "baba_is_auto" else {}).items():
        if a in req and b in forb:
            out.append({"kind": "skill_conflict",
                        "explanation": f"'{a}' is required but '{b}' is forbidden; in this game a "
                                       f"{game.skills[a]['label'].lower()} IS a rule change "
                                       f"({game.skills[a]['definition']}).",
                        "suggestions": [f"allow {b}", f"drop the {a} requirement"]})
    c = spec["constraints"]
    if c.get("max_moves") is not None and c.get("min_moves") is not None and c["max_moves"] < c["min_moves"]:
        out.append({"kind": "numeric_conflict",
                    "explanation": f"max_moves={c['max_moves']} is below min_moves={c['min_moves']}.",
                    "suggestions": ["fix the bounds"]})
    pol = game.V.POLICY
    if c.get("width", 0) > pol["max_width"] or c.get("height", 0) > pol["max_height"]:
        out.append({"kind": "size_conflict",
                    "explanation": f"{c.get('width')}x{c.get('height')} exceeds the size this blueprint can "
                                   f"verify exhaustively.",
                    "suggestions": ["request a smaller level"]})
    return out


# --------------------------------------------------------------------------
# Verification of one candidate
# --------------------------------------------------------------------------
def verify(game: Game, native_text: str, spec: dict, budget_ms=6000, quick=False):
    A, V = game.A, game.V
    t0 = time.time()
    path = Path(A.tempfile.mkstemp(suffix=".txt", prefix="cand_")[1])
    path.write_text(native_text)
    rep = {"status": "UNVERIFIED", "levels": {}, "reasons": [], "skills": {}}
    try:
        v = V.validate_file(path)
        rep["levels"]["structural"] = {"passed": v["structurally_valid"], "checks": v["checks"],
                                        "warnings": v.get("warnings", [])}
        rep["initial_rules"] = v.get("initial_rules", [])
        if not v["structurally_valid"]:
            rep["reasons"].append("structural: " + "; ".join(c["check"] for c in v["checks"] if not c["passed"]))
            return rep
        rep["status"] = "STRUCTURALLY_VALID"

        s = A.solve(path, analyze=True, max_ms=budget_ms, max_states=3_000_000)
        an = s.get("analysis", {})
        rep["search"] = {k: s.get(k) for k in ("status", "proof", "backend", "length", "states_explored",
                                               "elapsed_ms", "wait_allowed")}
        if s["status"] != "solved":
            rep["levels"]["solvable"] = {
                "passed": False, "established": s["status"] == "unsolvable",
                "detail": ("proved UNSOLVABLE: all %d reachable states explored, none wins" % s["states_explored"])
                if s["status"] == "unsolvable" else
                ("not established: no solution within %d states / %d ms" % (s["states_explored"], budget_ms))}
            rep["reasons"].append("unsolvable" if s["status"] == "unsolvable" else "no solution found in bound")
            return rep

        # A model-found solution counts only after the ORIGINAL engine replays it to WON.
        moves = s["moves"]
        tr = A.replay(path, moves)
        frames = tr["frames"]
        engine_won = frames[-1]["state"] == "WON" and all(f["state"] != "WON" for f in frames[:-1])
        py = A.replay_python_binding(path, moves)
        rep["levels"]["solvable"] = {
            "passed": engine_won, "established": True,
            "detail": f"{len(moves)}-move witness found by the {s['backend']} search and replayed to WON in "
                      + ("the tested model only: " + tr.get("engine_note", "") if tr.get("engine") == "model_fallback"
                         else "the original engine") + (
                          "; pyBaba binding independently reports " + py["final_state"] if py.get("loaded") else ""),
            "witness": moves, "engine_replay_won": engine_won,
            "python_binding_final_state": py.get("final_state")}
        if not engine_won or (py.get("loaded") and py["final_state"] != "WON"):
            rep["reasons"].append("witness rejected by the real engine (model/engine disagreement)")
            rep["levels"]["solvable"]["passed"] = False
            return rep
        rep["status"] = "PROVEN_SOLVABLE"
        rep["solution"] = moves
        rep["frames"] = frames
        ev = A.analyse_trace(frames)
        rep["trace_events"] = {k: len(val) for k, val in ev.items()}
        rep["rule_timeline"] = ev["rule_changes"]

        # --- solution quality ------------------------------------------------
        c = spec["constraints"]
        lo, hi = game.planner.BANDS[spec["difficulty"]][1]
        diff = A.difficulty(s, ev)
        rep["difficulty"] = diff
        q = {"shortest_length": len(moves), "optimal": True,
             "shortest_solution_count": an.get("shortest_solution_count"),
             "shortest_count_exact": an.get("shortest_count_exact"),
             "difficulty_score": diff["score"], "difficulty_established": diff["established"],
             "difficulty_components": diff["components"],
             "difficulty_band": [lo, hi],
             "in_band": diff["established"] and lo <= diff["score"] <= hi}
        q_ok = q["in_band"]
        if not diff["established"]:
            rep["reasons"].append("difficulty not established: state space exceeded the analysis bound")
        elif not q["in_band"]:
            rep["reasons"].append(f"difficulty score {diff['score']} outside {spec['difficulty']} band {lo}-{hi}")
        if c.get("max_moves") is not None:
            q["max_moves_ok"] = len(moves) <= c["max_moves"]
            q_ok &= q["max_moves_ok"]
            if not q["max_moves_ok"]:
                rep["reasons"].append(f"shortest solution {len(moves)} > max_moves {c['max_moves']}")
        if c.get("min_moves") is not None:
            q["min_moves_ok"] = len(moves) >= c["min_moves"]
            q_ok &= q["min_moves_ok"]
            if not q["min_moves_ok"]:
                rep["reasons"].append(f"shortest solution {len(moves)} < min_moves {c['min_moves']}")
        if c.get("unique_solution"):
            q["unique_shortest_ok"] = bool(an.get("shortest_count_exact")) and an.get("shortest_solution_count") == 1
            q_ok &= q["unique_shortest_ok"]
            if not q["unique_shortest_ok"]:
                rep["reasons"].append(f"{an.get('shortest_solution_count')} distinct shortest solutions (unique requested)")
        rep["levels"]["solution_quality"] = {"passed": q_ok, **q}

        # --- robustness --------------------------------------------------------
        rob = {"analysis_complete": an.get("complete", False), "reachable_states": an.get("reachable_states"),
               "dead_states": an.get("dead_states") if an.get("complete") else None,
               "lost_states": an.get("lost_states")}
        if an.get("complete") and an.get("reachable_states"):
            rob["dead_state_ratio"] = round(an["dead_states"] / an["reachable_states"], 4)
            rob["detail"] = (f"all {an['reachable_states']} reachable states enumerated; "
                             f"{an['dead_states']} are dead (no winning continuation)")
        else:
            rob["detail"] = (f"state space larger than the bound ({an.get('reachable_states')} states seen); "
                             f"dead-state count NOT established")
        rob_ok = True
        if c.get("no_dead_states"):
            rob_ok = bool(an.get("complete")) and an.get("dead_states") == 0
            if not rob_ok:
                rep["reasons"].append("dead states exist or could not be ruled out (none requested)")
        rep["levels"]["robustness"] = {"passed": rob_ok, **rob}

        # --- skills: exercised in the witness, and proven necessary by ablation ---
        req, forb = spec["skills_required"], spec["skills_forbidden"]
        skills_ok = True

        def ablate(flag):
            return A.solve(path, forbid=[flag], max_ms=2000 if quick else 8000, max_states=3_000_000)

        def static_arg(sid):
            try:
                return A.static_necessity(sid, frames[0]["rules"], frames[0])
            except TypeError:
                return A.static_necessity(sid, frames[0]["rules"])
        static = {sid: static_arg(sid) for sid in req}
        to_run = {sid: game.skills[sid]["necessity_ablation"] for sid in list(req) + list(forb)
                  if game.skills[sid].get("necessity_ablation") and not static.get(sid)}
        with ThreadPoolExecutor(max_workers=2) as ex:
            abl = dict(zip(to_run, ex.map(ablate, to_run.values())))
        for sid in req:
            exercised = A.skill_exercised(sid, ev, frames)
            entry = {"required": True, "exercised_in_witness": exercised}
            a = abl.get(sid)
            if static.get(sid):
                entry["necessity"] = "proven"
                entry["proof"] = "static"
                entry["detail"] = static[sid]
            elif a is not None:
                entry["proof"] = "ablation"
                entry["ablation"] = {"forbid": to_run[sid], "result": a["status"], "states": a["states_explored"]}
                if a["status"] == "unsolvable":
                    entry["necessity"] = "proven"
                    entry["detail"] = (f"with '{to_run[sid]}' moves forbidden the level is unsolvable "
                                       f"(exhaustive, {a['states_explored']} states): every solution uses this skill")
                elif a["status"] == "solved":
                    entry["necessity"] = "refuted"
                    entry["detail"] = f"a {a['length']}-move solution exists that never uses it: {a['moves']}"
                else:
                    entry["necessity"] = "not_established"
                    entry["detail"] = "ablation search hit its bound"
            else:
                entry["necessity"] = "n/a"
            ok = exercised and entry["necessity"] in ("proven", "n/a")
            entry["passed"] = ok
            if not ok:
                skills_ok = False
                rep["reasons"].append(f"skill {sid}: " + ("not exercised" if not exercised else
                                                          f"necessity {entry['necessity']}"))
            rep["skills"][sid] = entry
        for sid in forb:
            a = abl.get(sid)
            entry = {"required": False, "forbidden": True}
            if a is not None and a["status"] == "solved":
                entry["passed"] = True
                entry["detail"] = f"solvable without it ({a['length']} moves): {a['moves']}"
                entry["alternative_witness"] = a["moves"]
            else:
                entry["passed"] = a is None
                entry["detail"] = "level cannot be solved without the forbidden skill" if a is not None else "n/a"
            if not entry["passed"]:
                skills_ok = False
                rep["reasons"].append(f"forbidden skill {sid} is needed")
            rep["skills"][sid] = entry
        rep["levels"]["mechanic_coverage"] = {"passed": skills_ok,
                                               "covered": sum(1 for s_ in req if rep["skills"][s_]["passed"]),
                                               "requested": len(req)}
        if q_ok and rob_ok and skills_ok:
            rep["status"] = "FULLY_VALIDATED"
        return rep
    finally:
        rep["verify_seconds"] = round(time.time() - t0, 2)
        try:
            os.unlink(path)
        except OSError:
            pass


def quick_score(game: Game, level):
    """Cheap pre-score for the hard-level search: solve + trace only, no skill proofs."""
    A = game.A
    path = A.write_temp(level)
    try:
        s = A.solve(path, analyze=True, max_ms=1200, max_states=400_000)
        if s.get("status") != "solved" or not (s.get("path") or {}).get("established"):
            return None
        frames = A.replay(path, s["moves"])["frames"]
        if frames[-1]["state"] != "WON":
            return None
        return A.difficulty(s, A.analyse_trace(frames))["score"]
    finally:
        os.unlink(path)


def score(rep):
    """Order candidates: higher is better."""
    return (STATUS_ORDER.index(rep["status"]), -len(rep["reasons"]), (rep.get("difficulty") or {}).get("score") or 0)


# --------------------------------------------------------------------------
# The generate -> verify -> repair loop
# --------------------------------------------------------------------------
def generate(request: str, game: Game | None = None, seed: int | None = None, max_attempts=12,
             verify_repair=True, budget_ms=6000, save=True, quick=False, spec_override=None, proposer=None,
             search_seconds=15, use_llm=None, llm_proposals=2):
    game = game or Game()
    t0 = time.time()
    seed = random.randrange(10 ** 6) if seed is None else seed
    rng = random.Random(seed)
    use_llm = (llm.mode() != "off") if use_llm is None else (use_llm and llm.mode() != "off")
    llm.take_log()
    ai = {"mode": llm.mode() if use_llm else "off", "intent_source": "keyword parser", "errors": [], "proposals": []}
    kw_spec = intent.parse_request(request, game.spec)
    spec = spec_override or kw_spec
    if use_llm and not spec_override:
        try:
            spec, meta = llm.parse_request(request, game.spec)
            ai["intent_source"] = f"LLM ({meta['model']})"
            ai["keyword_parser_would_have_said"] = {k: kw_spec[k] for k in ("difficulty", "skills_required",
                                                                           "skills_forbidden")}
            # safety net: the deterministic detector may only ADD reasons to refuse, never remove them
            for k in ("unsupported_requested", "foreign_requested"):
                spec[k] = spec[k] + [w for w in kw_spec[k] if w not in spec[k]]
            if not spec["dependencies"]:
                spec["dependencies"] = kw_spec["dependencies"]
        except Exception as e:
            ai["errors"].append(f"intent: {e}")
            spec = kw_spec
    spec.update({k: v for k, v in spec["constraints"].items() if k in ("width", "height")})
    result = {"request": request, "game": game.name, "seed": seed, "spec": spec, "attempts": [], "ai": ai,
              "blueprint_version": game.spec["blueprint_version"], "game_commit": game.spec["game"]["commit"]}

    contradictions = find_contradictions(game, spec)
    # dependency cycles are detected on the plan graph, before any tile is placed
    plan = None
    if not contradictions:
        try:
            plan = game.planner.make_plan(spec, random.Random(seed))
            game.P.check_plan(plan)
        except game.P.PlanError as e:
            c = {"kind": "dependency_cycle" if e.kind == "cycle" else e.kind, "explanation": e.explanation,
                 "cycle": e.cycle, "suggestions": e.suggestions}
            if e.kind == "cycle":
                c["evidence"] = cycle_evidence(game, plan, seed)
                if c["evidence"].get("solver_status") == "solved":
                    c["explanation"] += (" NOTE: the solver nevertheless found a way through the literal "
                                         "layout, so the dependency is not the only key; see evidence.")
            contradictions.append(c)
    if contradictions:
        ai["usage"] = llm.usage_summary(llm.take_log())
        result.update({"status": "REJECTED_CONTRADICTION", "contradictions": contradictions,
                       "elapsed_seconds": round(time.time() - t0, 2)})
        return result

    # ---- LLM as designer: it proposes layouts, the verifier judges them, it gets one repair ----
    best = None
    if use_llm and verify_repair and not proposer and llm_proposals > 0:
        skill_md = (ROOT / "blueprints" / game.name / "skill.md").read_text()

        def try_candidate(cand, label):
            nonlocal best
            entry = {"attempt": len(result["attempts"]) + 1, "proposer": label, "plan": cand.get("idea", "")}
            rec = {"by": label, "idea": cand.get("idea", ""), "dsl": cand["dsl"]}
            try:
                level = game.A.Level.from_dsl(cand["dsl"])
                level.meta = {"plan": cand.get("idea", ""), "notes": []}
                native = level.to_native()
            except Exception as e:
                entry.update({"status": "UNVERIFIED", "reasons": [f"malformed level text: {e}"]})
                rec.update({"status": "REJECTED", "reasons": entry["reasons"]})
                result["attempts"].append(entry)
                ai["proposals"].append(rec)
                return None
            rep = verify(game, native, spec, budget_ms=min(budget_ms, 4000), quick=True)
            if not rep["reasons"] and rep["status"] != "FULLY_VALIDATED":
                rep["reasons"].append("did not pass verification")
            entry.update({"status": rep["status"], "reasons": rep["reasons"], "size": f"{level.width}x{level.height}",
                          "difficulty_score": (rep.get("difficulty") or {}).get("score"),
                          "verify_seconds": rep.get("verify_seconds")})
            rec.update({"status": rep["status"], "reasons": rep["reasons"],
                        "initial_rules": rep.get("initial_rules", []),
                        "difficulty_score": (rep.get("difficulty") or {}).get("score")})
            result["attempts"].append(entry)
            ai["proposals"].append(rec)
            cand_ = {"level": level, "native": native, "report": rep}
            if best is None or score(rep) > score(best["report"]):
                best = cand_
            return rec

        try:
            cands, meta = llm.propose_levels(request, spec, skill_md, n=llm_proposals)
            recs = [r for r in (try_candidate(c, f"LLM proposal ({meta['model']})") for c in cands) if r]
            if recs and not any(r["status"] == "FULLY_VALIDATED" for r in recs):
                worst_first = sorted(recs, key=lambda r: STATUS_ORDER.index(r["status"]) if r["status"] in STATUS_ORDER else -1)
                target = worst_first[-1]
                fixed, meta = llm.repair_level(request, target["dsl"], target["reasons"],
                                               target.get("initial_rules", []), skill_md)
                try_candidate(fixed, f"LLM repair after verifier feedback ({meta['model']})")
        except Exception as e:
            ai["errors"].append(f"proposals: {e}")
        ai["proposals_fully_validated"] = sum(1 for r in ai["proposals"] if r["status"] == "FULLY_VALIDATED")

    # Hard requests: sample many candidates cheaply, score them, and fully verify the hardest first.
    pool = []
    if verify_repair and not proposer and spec["difficulty"] == "hard" and search_seconds > 0:
        t_search, tried = time.time(), 0
        while time.time() - t_search < search_seconds and tried < 400:
            tried += 1
            try:
                plan = game.planner.make_plan(spec, rng, tried)
                level = game.P.build(plan, rng)
                if rng.random() < 0.35:
                    level = game.P.transpose(level)
            except (game.P.PlanError, ValueError):
                continue
            pre = quick_score(game, level)
            if pre is not None:
                pool.append((pre, tried, level))
        pool.sort(key=lambda x: -x[0])
        result["search"] = {"candidates_built": tried, "candidates_scored": len(pool),
                            "seconds": round(time.time() - t_search, 1),
                            "best_scores": [p[0] for p in pool[:5]],
                            "median_score": pool[len(pool) // 2][0] if pool else None}
    llm_done = best is not None and best["report"]["status"] == "FULLY_VALIDATED" and spec["difficulty"] != "hard"
    for attempt in range(0 if llm_done else max_attempts):
        entry = {"attempt": len(result["attempts"]) + 1}
        try:
            if proposer and attempt < len(proposer):
                level = game.A.Level.from_dsl(proposer[attempt]["dsl"])
                entry["proposer"] = proposer[attempt].get("by", "recorded LLM proposal")
                level.meta = {"plan": proposer[attempt].get("idea", ""), "notes": []}
            elif pool:
                pre, _, level = pool.pop(0)
                entry["proposer"] = f"hardest remaining of {result['search']['candidates_scored']} scored candidates (pre-score {pre})"
            else:
                plan = game.planner.make_plan(spec, rng, attempt)
                level = game.P.build(plan, rng)
                if rng.random() < 0.35:
                    level = game.P.transpose(level)
                entry["proposer"] = "constraint-based planner"
            entry["plan"] = level.meta.get("plan")
            native = level.to_native()
        except (game.P.PlanError, ValueError) as e:
            entry.update({"status": "PLAN_FAILED", "reasons": [str(e)]})
            result["attempts"].append(entry)
            continue
        if not verify_repair:
            rep = {"status": "UNVERIFIED", "levels": {}, "reasons": [], "skills": {}}
        else:
            rep = verify(game, native, spec, budget_ms=budget_ms, quick=quick)
        entry.update({"status": rep["status"], "reasons": rep["reasons"], "size": f"{level.width}x{level.height}",
                      "difficulty_score": (rep.get("difficulty") or {}).get("score"),
                      "verify_seconds": rep.get("verify_seconds")})
        result["attempts"].append(entry)
        cand = {"level": level, "native": native, "report": rep}
        if best is None or score(rep) > score(best["report"]):
            best = cand
        if rep["status"] == "FULLY_VALIDATED" or not verify_repair:
            break

    if best is None:
        ai["usage"] = llm.usage_summary(llm.take_log())
        result.update({"status": "FAILED", "elapsed_seconds": round(time.time() - t0, 2)})
        return result
    rep = best["report"]
    level = best["level"]
    result.update({
        "status": rep["status"], "width": level.width, "height": level.height,
        "dsl": level.to_dsl(), "native": best["native"], "design_notes": level.meta,
        "verification": {k: v for k, v in rep.items() if k != "frames"},
        "frames": rep.get("frames"), "solution": rep.get("solution"),
        "unmet_requirements": rep["reasons"],
        "elapsed_seconds": round(time.time() - t0, 2),
    })
    result["delivered_from"] = next((a.get("proposer") for a in result["attempts"]
                                     if a.get("status") == rep["status"]
                                     and a.get("difficulty_score") == (rep.get("difficulty") or {}).get("score")), None)
    if use_llm and rep["status"] in ("PROVEN_SOLVABLE", "FULLY_VALIDATED"):
        try:
            d = rep.get("difficulty") or {}
            facts = {"requested_difficulty": spec["difficulty"], "status": rep["status"],
                     "size": f"{level.width}x{level.height}", "shortest_solution_moves": len(rep.get("solution") or ""),
                     "difficulty_score": d.get("score"), "difficulty_components": d.get("components"),
                     "rules_at_start": rep.get("initial_rules"),
                     "rule_changes_along_solution": [{"added": r["added"], "removed": r["removed"]}
                                                     for r in rep.get("rule_timeline", [])],
                     "skills_proven_necessary": [k for k, v in rep.get("skills", {}).items()
                                                 if v.get("necessity") == "proven"]}
            result["presentation"], _ = llm.describe_level(request, facts)
        except Exception as e:
            ai["errors"].append(f"describe: {e}")
    ai["usage"] = llm.usage_summary(llm.take_log())
    if save:
        result["files"] = export(result)
    return result


def cycle_evidence(game: Game, plan, seed):
    """Build the contradictory layout anyway and let the solver confirm it."""
    try:
        orig = game.P.check_plan
        game.P.check_plan = lambda p: True
        try:
            level = game.P.build(plan, random.Random(seed))
        finally:
            game.P.check_plan = orig
        path = game.A.write_temp(level)
        s = game.A.solve(path, max_ms=6000, max_states=3_000_000)
        os.unlink(path)
        return {"dsl": level.to_dsl(), "width": level.width, "height": level.height,
                "solver_status": s["status"], "proof": s["proof"], "states_explored": s["states_explored"],
                "detail": ("the layout exactly as requested was built and searched exhaustively: "
                           f"{s['states_explored']} reachable states, none of them a win")
                if s["status"] == "unsolvable" else f"solver result: {s['status']}"}
    except Exception as e:  # evidence is optional
        return {"error": str(e)}


def export(result):
    OUT.mkdir(parents=True, exist_ok=True)
    n = 1 + len(list(OUT.glob("forge_*.txt")))
    while (OUT / f"forge_{n:04d}.txt").exists():
        n += 1
    base = OUT / f"forge_{n:04d}"
    base.with_suffix(".txt").write_text(result["native"])
    report = {k: v for k, v in result.items() if k not in ("frames", "files")}
    base.with_suffix(".report.json").write_text(json.dumps(report, indent=1))
    return {"level": str(base.with_suffix(".txt").relative_to(ROOT)),
            "report": str(base.with_suffix(".report.json").relative_to(ROOT))}
