# Benchmark report

200 prompts x 3 arms, seed 2026, 2 workers. Linux-6.18.44-fc-v80-x86_64-with-glibc2.39, 2 CPUs, Python 3.13.16. Wall clock 437.9 s.
Limits per candidate: analysis 3000 ms / 3,000,000 states, ablation 2000 ms, at most 8 attempts; hard requests first search for 6 s and keep the hardest candidate.
Difficulty score = 2 x trap bits + 4 x dead-state ratio + 2 x rule changes + 3 x sacrificed rule words (see `adapter.difficulty`); solution length is not part of it. Bands: easy 0-8, medium 6-15, hard 15+.
Verifier: model search + replay of every witness in the original engine; independent re-check through the pyBaba binding.

Prompts are built from templates over difficulty x skill combinations (`make_prompts`). All three arms are scored afterwards by the same verifier.

| Metric | Random tiles (no blueprint) | Blueprint-guided, unverified | Full pipeline |
|---|---:|---:|---:|
| Schema validity (accepted by the original loader) | 100.0% | 100.0% | 100.0% |
| Rule validity (all structural checks) | 0.5% | 98.5% | 100.0% |
| Solvability established (witness replayed in the engine) | 0.0% | 92.0% | 100.0% |
| Mechanic coverage (requested skills exercised and proven necessary) | 0.0% | 87.5% | 99.7% |
| Difficulty score established and inside the requested band | 0.0% | 59.0% | 95.5% |
| Fully validated | 0.0% | 59.0% | 95.5% |
| Mean generation attempts | 1 | 1 | 1.75 |
| Latency median / p90 / max (s) | 0.0 / 0.0 / 0.0 | 0.001 / 0.002 / 0.005 | 0.778 / 7.406 / 27.165 |
| Proved unsolvable / unresolved within bound | 0 / 1 | 12 / 1 | 0 / 0 |
| No level produced (counted as invalid in every row above) | 0 | 0 | 0 |

## Full pipeline by difficulty

| Difficulty | n | Fully validated | Solvable | Median difficulty score | Median solution | Median latency |
|---|---:|---:|---:|---:|---:|---:|
| easy | 67 | 97.0% | 100.0% | 3.5 | 10 moves | 0.02 s |
| medium | 67 | 100.0% | 100.0% | 8.3 | 18 moves | 0.61 s |
| hard | 66 | 89.4% | 100.0% | 20.85 | 44.0 moves | 6.82 s |

## False acceptance

- Levels the pipeline labelled solvable: **200**. Witness re-played independently through the game's `pyBaba` binding: **0** did not reach WON (false-acceptance rate 0.0%).
- Sabotage test: 120 accepted levels were damaged (a tile deleted or two cells swapped) and re-solved by both the fast model and the original engine. Verdicts were comparable on 117 (the engine search hit its bound on 3); they agreed on **117** and disagreed on **0**. 65/65 model witnesses won in the real engine.

## Contradiction handling

- Contradictory prompts rejected with an explanation and a suggestion: **19/19**.
- Valid control prompts wrongly rejected: **0/10**.
- This prompt set was written by the same author as the detector and tuned against it (misses found in early runs were fixed). Treat it as a regression test, not as an estimate of accuracy on unseen phrasing.

## Second game: Sokoban, through the unchanged pipeline

`bench/run_benchmark_sokoban.py`, 60 requests on `sokoban-solver-generator` (MIT). Solvable (replayed in the original pygame engine): **96.7%**; fully validated: **96.7%**; false acceptances: **0/58**; impossible requests refused: 5/5; valid controls wrongly refused: 0/4; median 1.29 s per request.

| Difficulty | n | Fully validated | Solvable | Median score | Median solution |
|---|---:|---:|---:|---:|---:|
| easy | 20 | 100.0% | 100.0% | 4.3 | 6.5 moves |
| medium | 20 | 90.0% | 90.0% | 7.1 | 13.5 moves |
| hard | 20 | 100.0% | 100.0% | 13.6 | 29.0 moves |

The first run of this benchmark scored 68.3% fully validated (boxes were placed in dead corners and the difficulty bands were uncalibrated); the constructor was fixed and the bands set before the run reported here.

## Not measured

- **raw_llm_arm**: requires an API key (forge/llm.py); random_tiles is the no-LLM stand-in
- **llm_plus_skill_md_arm**: requires an API key; blueprint_only is the no-LLM stand-in
- **cross_version_reliability**: only one game version analysed; `agent1_blueprint.py --check` detects source drift but no second version was benchmarked
- **difficulty_vs_human_playtest**: no playtesting; difficulty is the blueprint's own score (trap pressure, dead-state ratio, rule changes, sacrificed words), which has not been compared with human ratings

## Reading these numbers

- 'Blueprint-guided, unverified' is the same constructor as the full pipeline with the verifier and repair loop switched off. The gap between the two columns is what verification and repair add.
- 'Random tiles' is a floor, not a stand-in for a language model's ability.
- 'Fully validated' below 100% is the pipeline declining to over-claim: those levels are delivered with the lower label and the unmet requirement listed.
- Reproduce with `python3 bench/run_benchmark.py && python3 bench/make_report.py`.
