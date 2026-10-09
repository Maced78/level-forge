# Submission texts — copy each block into the platform form

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
https://maced78.github.io/level-forge/
```

**Source code**

```
https://github.com/Maced78/level-forge
```

**Video (up to 2 minutes)**

```
PASTE THE LINK AFTER UPLOADING submission/Level-Forge_demo.webm
```

**Setup instructions**

```
The demo link opens in any browser with no login or setup: pick a recorded request, press Play solution, press "Play it yourself" (arrow keys), or type your own level into "Verify your own level" - the solver runs live in the tab. The gallery replays runs recorded from the real pipeline. To run live generation locally (Linux/macOS, ~2 min): git clone https://github.com/Maced78/level-forge.git && cd level-forge && bash build_engine.sh && bash run_demo.sh, then open http://localhost:8765. Needs g++, python3 and python3-dev. On Windows, run the same commands inside WSL (Ubuntu). Without an API key the app runs its test version (a keyword reader instead of the language model) and says so at the top of the page; this is the version the demo uses, because Gemini takes 7-10 s per call on a free key. Optional: put GEMINI_API_KEY=... in .env to switch Gemini on. Second game: choose "Sokoban" in the game selector. Known limitation: hard requests take 7-20 s because the system searches for the hardest level that passes every check.
```

**Disclosure — Models**

```
Google Gemini, free key (reads requests, names levels; works but slow, so the demo and all reported numbers use the test version without it); Anthropic Claude (coding agent: wrote the blueprints and prototype with us)
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
WHAT WE TESTED. (1) Benchmark, 200 generated requests x 3 ways of making a level, all scored by one verifier: full pipeline 100% solvable (solution replayed in the original engine) and 95.5% fully validated; the same constructor without verification 92% / 59%; random tiles 0% / 0%. (2) False acceptance: 0 of 200 levels labelled solvable failed an independent replay. (3) Fast search model vs the real engine: 100,000 random moves compared with no disagreement; same verdict on 117/117 deliberately damaged levels. (4) 30 game-mechanic claims, each tied to a source line and a probe on the real engine; regression suite 60/60. (5) Impossible requests: 19/19 refused with a reason, 0/10 valid controls wrongly refused (this set was tuned against the detector, so it is a regression test). (6) Second game (Sokoban) through the unchanged loop: 60 requests, 96.7% solvable, 96.7% fully validated, 0/58 false acceptances, 3,000 model-vs-engine moves. NOT BENCHMARKED: Gemini. It works in the app (it parsed requests and named levels on a free key, 7-10 s per call), but the free tier is too slow and limited for a 200-request benchmark, so every number here comes from the test version (keyword reader + planner).

WHAT BROKE. The real engine explores only ~2,000 states/s, so we wrote a fast model and replay every solution in the real engine. The ablation search showed our early claim 'pushing is required' was false (a rule word can be drowned instead of a rock); we changed the construction. Early 'hard' levels were long but easy (0-1 trap points), so difficulty is now computed from the full state space, not length. The first Sokoban run was only 68% fully validated (boxes placed in dead corners); fixed. Hard requests are still not fully validated 10.6% of the time; those are delivered with the lower label and the unmet requirement listed. Our first Gemini run failed on an invalid key and the script silently saved keyword-parser results as LLM results; we caught it, deleted the numbers, and the script now refuses to record a fallback. Gemini now works, but at 7-10 s per call on a free key it is too slow for the benchmark.

COMPARISON WITH TODAY. By hand, a designer learns whether a level is solvable or bypassable only by play-testing. A general LLM asked for a level file does not know the engine's tile IDs or which rules it implements. Level-Forge returns a native level in a median of 0.778 s (hard: ~6.82 s) with a replayable solution and proofs.

NOT ESTABLISHED. Model = engine is tested, not proven. 'Unsolvable' means with the four directional inputs. The difficulty score is our definition and is not calibrated on human players. We did not time human designers, so we claim seconds per verified level, not hours saved. Benchmark requests come from templates inside the generator's vocabulary.
```
