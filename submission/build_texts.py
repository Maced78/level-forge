#!/usr/bin/env python3
"""Writes submission/SUBMISSION.md (texts for the platform form) and README.md from measured data."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "submission" / "config.json").read_text())
B = json.loads((ROOT / "bench" / "results.json").read_text())["summary"]
SB = json.loads((ROOT / "bench" / "results_sokoban.json").read_text())["summary"]
P = json.loads((ROOT / "blueprints" / "baba_is_auto" / "provenance.json").read_text())
SP = json.loads((ROOT / "blueprints" / "sokoban_sg" / "provenance.json").read_text())
T = json.loads((ROOT / "blueprints" / "baba_is_auto" / "tests" / "last_run.json").read_text())
LP = ROOT / "bench" / "llm_results.json"
L = json.loads(LP.read_text()) if LP.exists() else None
L = L if (L and L.get("intent_summary") and L.get("totals", {}).get("cached_answers")) else None
fp, bo, rt = B["arms"]["full_pipeline"], B["arms"]["blueprint_only"], B["arms"]["random_tiles"]
bd, ch, mv = fp["by_difficulty"], B["contradiction_handling"], B["model_vs_engine_on_sabotaged_levels"]
model = L["model"] if L else "Google Gemini"
model_disc = (f"{model} (request parsing, level proposals, repair, naming)" if L else
  "Google Gemini, free key (reads requests, names levels; works but slow, so the demo and all reported numbers use the test version without it)")
f = lambda x: f"{x['correct']}/{x['of']}"
llm_q = "NOT BENCHMARKED: Gemini. It works in the app (it parsed requests and named levels on a free key, 7-10 s per call), but the free tier is too slow and limited for a 200-request benchmark, so every number here comes from the test version (keyword reader + planner)."
llm_r = "\n**Language model: works, not benchmarked.** Gemini parsed requests and named levels through `forge/llm.py` on a free key (7-10 s per call; sample answers in `out/llm_cache.json`). The comparison benchmark `bench/llm_evidence.py` has not been completed, so no number in this repository comes from an LLM.\n"
MODELS = None
if L:
    I, G = L["intent_summary"], L["generation_summary"]
    llm_q = (f"LLM evidence ({model}): on {I['llm']['all']['of']} hand-labelled requests the LLM parsed {f(I['llm']['all'])} correctly vs "
             f"{f(I['keyword']['all'])} for the keyword parser ({f(I['llm']['paraphrased'])} vs {f(I['keyword']['paraphrased'])} on paraphrased requests). "
             f"Asked to write the level file directly, the LLM produced {G['raw_llm']['solvable']}/{G['raw_llm']['n']} solvable levels; "
             f"with our skill.md {G['llm_skill']['solvable']}/{G['llm_skill']['n']}; with verifier feedback {G['llm_loop']['fully_validated']}/{G['llm_loop']['n']} fully validated; "
             f"full pipeline {G['full_pipeline']['fully_validated']}/{G['full_pipeline']['n']} fully validated. ")
    llm_r = (f"\n**Language model, measured ({model}).** Request understanding on {I['llm']['all']['of']} hand-labelled requests: LLM {f(I['llm']['all'])}, keyword parser {f(I['keyword']['all'])} "
             f"(paraphrased only: {f(I['llm']['paraphrased'])} vs {f(I['keyword']['paraphrased'])}). Level building on {G['raw_llm']['n']} requests, fully validated: "
             f"LLM writing the file directly {G['raw_llm']['fully_validated']}, LLM + skill.md {G['llm_skill']['fully_validated']}, LLM + verifier feedback {G['llm_loop']['fully_validated']}, full pipeline {G['full_pipeline']['fully_validated']}.\n")

quality = (
    f"WHAT WE TESTED. (1) Benchmark, {fp['n']} generated requests x 3 ways of making a level, all scored by one verifier: full pipeline {fp['solvability_established_pct']:g}% solvable "
    f"(solution replayed in the original engine) and {fp['fully_validated_pct']:g}% fully validated; the same constructor without verification {bo['solvability_established_pct']:g}% / {bo['fully_validated_pct']:g}%; "
    f"random tiles {rt['solvability_established_pct']:g}% / {rt['fully_validated_pct']:g}%. (2) False acceptance: {fp['false_acceptances']} of {fp['levels_labelled_solvable']} levels labelled solvable failed an independent replay. "
    f"(3) Fast search model vs the real engine: {T['difftest_moves']:,} random moves compared with no disagreement; same verdict on {mv['agree']}/{mv['comparable_verdicts']} deliberately damaged levels. "
    f"(4) {P['summary'].get('confirmed', 0)} game-mechanic claims, each tied to a source line and a probe on the real engine; regression suite {T['passed']}/{T['total']}. "
    f"(5) Impossible requests: {ch['correctly_rejected']}/{ch['contradictory_prompts']} refused with a reason, {ch['wrongly_rejected_controls']}/{ch['valid_control_prompts']} valid controls wrongly refused (this set was tuned against the detector, so it is a regression test). "
    f"(6) Second game (Sokoban) through the unchanged loop: {SB['trials']} requests, {SB['solvable_pct']:g}% solvable, {SB['fully_validated_pct']:g}% fully validated, {SB['false_acceptances']}/{SB['labelled_solvable']} false acceptances, {SP['difftest']['moves_compared']:,} model-vs-engine moves. "
    f"{llm_q}\n\n"
    f"WHAT BROKE. The real engine explores only ~2,000 states/s, so we wrote a fast model and replay every solution in the real engine. The ablation search showed our early claim 'pushing is required' was false (a rule word can be drowned instead of a rock); we changed the construction. "
    f"Early 'hard' levels were long but easy (0-1 trap points), so difficulty is now computed from the full state space, not length. The first Sokoban run was only 68% fully validated (boxes placed in dead corners); fixed. "
    f"Hard requests are still not fully validated {100 - bd['hard']['fully_validated_pct']:.1f}% of the time; those are delivered with the lower label and the unmet requirement listed. Our first Gemini run failed on an invalid key and the script silently saved keyword-parser results as LLM results; we caught it, deleted the numbers, and the script now refuses to record a fallback. Gemini now works, but at 7-10 s per call on a free key it is too slow for the benchmark.\n\n"
    f"COMPARISON WITH TODAY. By hand, a designer learns whether a level is solvable or bypassable only by play-testing. A general LLM asked for a level file does not know the engine's tile IDs or which rules it implements"
    + (f" (measured: {L['generation_summary']['raw_llm']['solvable']}/{L['generation_summary']['raw_llm']['n']} solvable)" if L else "") +
    f". Level-Forge returns a native level in a median of {fp['latency_seconds']['median']} s (hard: ~{bd['hard']['median_latency_s']} s) with a replayable solution and proofs.\n\n"
    f"NOT ESTABLISHED. Model = engine is tested, not proven. 'Unsolvable' means with the four directional inputs. The difficulty score is our definition and is not calibrated on human players. We did not time human designers, so we claim seconds per verified level, not hours saved. Benchmark requests come from templates inside the generator's vocabulary.")

sub = f"""# Submission texts — copy each block into the platform form

**Track:** AI Gaming

**Title**

```
Level-Forge: verified puzzle levels from a sentence
```

**The user and the problem**

```
For level designers at small puzzle-game studios and solo developers who must ship 50-200 hand-made levels for Sokoban-like or rule-rewriting puzzle games. Today every level is drawn by hand and then play-tested by hand to find out whether it can be won, whether it can be bypassed, and how hard it is; asking a general LLM for a level does not help, because it does not know the engine's real rules or file format and nothing tells you whether the result is solvable. Level-Forge reads the game's source code, writes a machine-checked blueprint of the rules the engine really implements, and turns a plain-language request into a level in the game's own file format that has been validated, solved and replayed in the original engine, with proof of which skills it requires and a computed difficulty. Impossible requests are refused with the reason. Shown working on two open-source games (a Baba Is You engine and a Sokoban) through one unchanged generation loop.
```

**Demo link**

```
{CFG['demo']}
```

**Source code**

```
{CFG['repo']}
```

**Video (up to 2 minutes)**

```
{CFG.get('video') or 'PASTE THE LINK AFTER UPLOADING submission/Level-Forge_demo.webm'}
```

**Setup instructions**

```
The demo link opens in any browser with no login or setup: pick a recorded request, press Play solution, press "Play it yourself" (arrow keys), or type your own level into "Verify your own level" - the solver runs live in the tab. The gallery replays runs recorded from the real pipeline. To run live generation locally (Linux/macOS, ~2 min): git clone {CFG['repo']}.git && cd level-forge && bash build_engine.sh && bash run_demo.sh, then open http://localhost:8765. Needs g++, python3 and python3-dev. On Windows, run the same commands inside WSL (Ubuntu). Without an API key the app runs its test version (a keyword reader instead of the language model) and says so at the top of the page; this is the version the demo uses, because Gemini takes 7-10 s per call on a free key. Optional: put GEMINI_API_KEY=... in .env to switch Gemini on. Second game: choose "Sokoban" in the game selector. Known limitation: hard requests take 7-20 s because the system searches for the hardest level that passes every check.
```

**Disclosure — Models**

```
{model_disc}; Anthropic Claude (coding agent: wrote the blueprints and prototype with us)
```

**Disclosure — Data**

```
No datasets. Source + shipped levels of two MIT games: utilForever/baba-is-auto, xbandrade/sokoban-solver-generator. Synthetic benchmark prompts.
```

**Disclosure — Components**

```
Python stdlib, C++17/g++, pybind11, pygame, pygame-widgets, numpy, Playwright/Chromium (tests, PDF), GitHub Pages. No templates.
```

**Checkbox:** tick "This project was built after the hackathon started." Research done beforehand: the idea and its written specification only.

**Quality testing — what did you test, and what broke?**

```
{quality}
```
"""
(ROOT / "submission" / "SUBMISSION.md").write_text(sub)

readme = f"""# Level-Forge: verified puzzle levels from a sentence

**Live demo:** {CFG['demo']}  ·  **Deck:** `submission/Level-Forge_pitch_deck.pdf`  ·  NeuroBridge.SI Baku, AI Gaming track  ·  {CFG['team']}

Level-Forge reads a puzzle game's **source code**, writes a machine-checked blueprint of the rules the engine
really implements, and turns a level designer's request into a **native level file** that has been validated,
solved and replayed in the original engine — with proof of which skills it requires, a computed difficulty,
and an honest label for what was and was not established. Impossible requests are refused with the reason.

It runs on two open-source games through one unchanged generation loop:
[`baba-is-auto`](https://github.com/utilForever/baba-is-auto) (C++ Baba Is You engine, in `game_src/`) and
[`sokoban-solver-generator`](https://github.com/xbandrade/sokoban-solver-generator) (pygame Sokoban, in `games/sokoban_sg/`).

## Run it

```bash
bash build_engine.sh          # once, ~2 min: needs g++ (C++17), python3 + python3-dev, pip
bash run_demo.sh              # http://localhost:8765
```

- **Language model (optional):** put `GEMINI_API_KEY=...` in `.env` (or run `bash set_key.sh`). Without a key the system
  runs its test version (keyword reader + constraint planner) and says so at the top of the page. Gemini works but takes
  7-10 s per call on a free key, which is why the demo uses the test version.
- **Windows:** run the same commands inside WSL (Ubuntu): `wsl --install`, then `sudo apt install -y git g++ python3 python3-dev python3-pip` (not tested by us).
- **Second game:** pick "Sokoban" in the UI (`run_demo.sh` installs pygame and numpy if missing) or
  `python3 -m forge.cli "A medium level with two boxes" --game sokoban_sg`.
- **Play a level in the original engine:** the "Play in the original engine" button (`forge/play.py`, needs pygame).

```bash
python3 -m forge.cli "Create a hard level about rule manipulation and pushing" --seed 1
python3 forge/agent1_blueprint.py [--check]            # rebuild / staleness-check the Baba blueprint
python3 blueprints/sokoban_sg/build_blueprint.py       # probes + model-vs-engine test for Sokoban
python3 blueprints/baba_is_auto/tests/run_tests.py     # regression suite ({T['passed']}/{T['total']} passing)
python3 bench/run_benchmark.py && python3 bench/make_report.py     # 200-request benchmark
python3 bench/run_benchmark_sokoban.py                 # second-game benchmark
python3 bench/llm_evidence.py                          # LLM measurements (needs a key)
node docs/test_model.js                                # JS model vs frames recorded from the engine
```

## Architecture

```
 game source ──► AGENT 1 (blueprint engineer) ──► blueprint package ◄── probes on the ORIGINAL engine
                 reads source, writes claims        skill.md · game_spec.json · provenance.json
                 with source lines + probes         validator/ · solver/ · generator/ · tests/ · adapter.py

 request ──► AGENT 2 (game-independent loop, forge/pipeline.py)
             A  LLM → spec, validated against the blueprint          (forge/llm.py, fallback forge/intent.py)
             B  contradiction check: unsupported words, skill conflicts, key-behind-its-gate cycles
             C  LLM proposals + constraint planner build candidates
             D  native level file
             E  validate → solve → replay in the original engine → prove skills → score → repair
         ──► level + report: STRUCTURALLY_VALID / PROVEN_SOLVABLE / FULLY_VALIDATED / REFUSED
```

A new game is a new package under `blueprints/<game>/` implementing the adapter contract (level ⇄ native file,
validate, solve with ablation, replay in the real engine, skills, plan, difficulty). The Sokoban package took about
one hour and the loop in `forge/` was not changed for it.

**Why search runs on a model.** The Baba engine explores ~2,000 states/s; proofs need far more. `solver/model.hpp`
models the subset the generator uses, and is never trusted: every solution is replayed in the original engine, and
model and engine are compared move by move ({T['difftest_moves']:,} moves, no disagreement).

**Difficulty is not length.** `score = 2 × trap bits + 4 × dead-end ratio + 2 × rule changes + 3 × sacrificed rule words`,
computed from the fully enumerated state space. Hard requests build dozens of candidates and keep the hardest.

## Measured results (generated by `submission/build_texts.py`; details in `bench/REPORT.md`)

| | Random tiles | Blueprint, unverified | Full pipeline |
|---|---:|---:|---:|
| Accepted by the original loader | {rt['schema_validity_pct']:g}% | {bo['schema_validity_pct']:g}% | {fp['schema_validity_pct']:g}% |
| Solvability established | {rt['solvability_established_pct']:g}% | {bo['solvability_established_pct']:g}% | {fp['solvability_established_pct']:g}% |
| Requested skills proven necessary | {rt['mechanic_coverage_pct']:g}% | {bo['mechanic_coverage_pct']:g}% | {fp['mechanic_coverage_pct']:g}% |
| Fully validated | {rt['fully_validated_pct']:g}% | {bo['fully_validated_pct']:g}% | {fp['fully_validated_pct']:g}% |

- {fp['n']} requests, median latency {fp['latency_seconds']['median']} s (hard ≈ {bd['hard']['median_latency_s']} s). False acceptances: {fp['false_acceptances']}/{fp['levels_labelled_solvable']}.
- Model vs real engine on {mv['levels']} damaged levels: {mv['agree']}/{mv['comparable_verdicts']} verdicts agree.
- Impossible requests refused: {ch['correctly_rejected']}/{ch['contradictory_prompts']}; valid controls wrongly refused: {ch['wrongly_rejected_controls']}/{ch['valid_control_prompts']}.
- **Second game (Sokoban), same loop:** {SB['trials']} requests, {SB['solvable_pct']:g}% solvable, {SB['fully_validated_pct']:g}% fully validated, {SB['false_acceptances']}/{SB['labelled_solvable']} false acceptances.
{llm_r}
How to read this: the benchmark requests come from templates inside the generator's vocabulary; the two left columns
are not language models; the contradiction set was tuned against the detector; the difficulty score is our
definition and has not been compared with human ratings.

## Limits

- Two games, one version each. Both blueprints were written by a coding agent working with the team; a fully
  unattended Agent 1 has not been demonstrated.
- The Baba generator composes one family of patterns (rails, gates, keys, a WIN slot, a control swap) and emits
  7 of the 26 operator and property words the engine gives behaviour to. The Sokoban generator is random rooms
  filtered by the solver.
- Search uses the four directional inputs; "unsolvable" means with those inputs. Model ≡ engine is tested, not proven.
- A level whose state space exceeds the analysis bound gets no difficulty score and cannot be labelled hard.
- The hosted demo replays recorded runs; live generation needs the local build.

## Disclosure

Models: {model_disc}; Anthropic Claude (coding agent that wrote the blueprints
and prototype with the team during the hackathon). Data: none collected; two MIT-licensed games vendored unmodified.
Components: Python standard library, g++, pybind11, pygame, pygame-widgets, numpy, Playwright. Built on 9 October 2026.

## Layout

```
forge/                     game-independent: pipeline, intent, llm, server + UI, cli, play, agent1_blueprint
blueprints/baba_is_auto/   skill.md, mechanics.md, game_spec.json, level_schema.json, provenance.json,
                           adapter.py, validator/, solver/ (C++), generator/, tests/
blueprints/sokoban_sg/     skill.md, game_spec.json, provenance.json, adapter.py, engine_driver.py,
                           validator/, generator/, tests/, build_blueprint.py
game_src/  games/sokoban_sg/   the two games, unmodified (MIT)
bench/                     benchmarks, results, REPORT.md
docs/                      the hosted demo (GitHub Pages) + JS model and its test
submission/                pitch deck (PDF), form texts, builders
```
"""
(ROOT / "README.md").write_text(readme)
print("SUBMISSION.md + README.md written", "(with LLM results)" if L else "(LLM results pending)")
