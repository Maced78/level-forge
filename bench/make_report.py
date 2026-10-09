#!/usr/bin/env python3
"""Turns bench/results.json into bench/REPORT.md (numbers only; nothing is typed by hand)."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
s = json.loads((HERE / "results.json").read_text())["summary"]
A, m = s["arms"], s["meta"]
names = [("random_tiles", "Random tiles (no blueprint)"), ("blueprint_only", "Blueprint-guided, unverified"),
         ("full_pipeline", "Full pipeline")]
rows = [("schema_validity_pct", "Schema validity (accepted by the original loader)", "%"),
        ("rule_validity_pct", "Rule validity (all structural checks)", "%"),
        ("solvability_established_pct", "Solvability established (witness replayed in the engine)", "%"),
        ("mechanic_coverage_pct", "Mechanic coverage (requested skills exercised and proven necessary)", "%"),
        ("difficulty_alignment_pct", "Difficulty score established and inside the requested band", "%"),
        ("fully_validated_pct", "Fully validated", "%"), ("mean_attempts", "Mean generation attempts", "")]
L = ["# Benchmark report", "",
     f"{m['trials']} prompts x 3 arms, seed {m['seed']}, {m['workers']} workers. "
     f"{m['platform']}, {m['cpu_count']} CPUs, Python {m['python']}. Wall clock {m['wall_clock_seconds']} s.",
     f"Limits per candidate: analysis {m['limits']['analysis_ms']} ms / {m['limits']['analysis_max_states']:,} states, "
     f"ablation {m['limits']['ablation_ms']} ms, at most {m['limits']['max_attempts']} attempts; "
     f"hard requests first search for {m['limits'].get('hard_search_seconds')} s and keep the hardest candidate.",
     "Difficulty score = 2 x trap bits + 4 x dead-state ratio + 2 x rule changes + 3 x sacrificed rule words "
     "(see `adapter.difficulty`); solution length is not part of it. Bands: easy 0-8, medium 6-15, hard 15+.",
     f"Verifier: {m['verifier']}.", "",
     "Prompts are built from templates over difficulty x skill combinations (`make_prompts`). "
     "All three arms are scored afterwards by the same verifier.", "",
     "| Metric | " + " | ".join(n for _, n in names) + " |", "|---|" + "---:|" * 3]
for k, label, u in rows:
    L.append(f"| {label} | " + " | ".join(f"{A[a][k]}{u}" for a, _ in names) + " |")
L.append("| Latency median / p90 / max (s) | " + " | ".join(
    f"{A[a]['latency_seconds']['median']} / {A[a]['latency_seconds']['p90']} / {A[a]['latency_seconds']['max']}"
    for a, _ in names) + " |")
L.append("| Proved unsolvable / unresolved within bound | " + " | ".join(
    f"{A[a]['proved_unsolvable']} / {A[a]['unresolved_within_bound']}" for a, _ in names) + " |")
trials = json.loads((HERE / "results.json").read_text())["trials"]
none = {a: sum(1 for t in trials if t["arms"][a].get("status") in ("FAILED", "REJECTED_CONTRADICTION")
               or t["arms"][a].get("claimed") in ("FAILED", "REJECTED_CONTRADICTION")) for a, _ in names}
L.append("| No level produced (counted as invalid in every row above) | " + " | ".join(str(none[a]) for a, _ in names) + " |")
fp = A["full_pipeline"]
L += ["", "## Full pipeline by difficulty", "", "| Difficulty | n | Fully validated | Solvable | Median difficulty score | Median solution | Median latency |",
      "|---|---:|---:|---:|---:|---:|---:|"]
for d, x in fp["by_difficulty"].items():
    L.append(f"| {d} | {x['n']} | {x['fully_validated_pct']}% | {x['solvable_pct']}% | "
             f"{x.get('median_difficulty_score')} | {x['median_solution_length']} moves | {x['median_latency_s']} s |")
c, v = s["contradiction_handling"], s["model_vs_engine_on_sabotaged_levels"]
L += ["", "## False acceptance", "",
      f"- Levels the pipeline labelled solvable: **{fp['levels_labelled_solvable']}**. Witness re-played "
      f"independently through the game's `pyBaba` binding: **{fp['false_acceptances']}** did not reach WON "
      f"(false-acceptance rate {fp['false_acceptance_rate_pct']}%).",
      f"- Sabotage test: {v['levels']} accepted levels were damaged (a tile deleted or two cells swapped) and "
      f"re-solved by both the fast model and the original engine. Verdicts were comparable on "
      f"{v['comparable_verdicts']} (the engine search hit its bound on {v['engine_bound_reached']}); they "
      f"agreed on **{v['agree']}** and disagreed on **{v['disagree']}**. "
      f"{v['of_which_witness_wins_in_real_engine']}/{v['model_says_solved']} model witnesses won in the real engine.",
      "", "## Contradiction handling", "",
      f"- Contradictory prompts rejected with an explanation and a suggestion: **{c['rejected_with_suggestion']}/"
      f"{c['contradictory_prompts']}**.",
      f"- Valid control prompts wrongly rejected: **{c['wrongly_rejected_controls']}/{c['valid_control_prompts']}**.",
      "- This prompt set was written by the same author as the detector and tuned against it "
      "(misses found in early runs were fixed). Treat it as a regression test, not as an estimate of "
      "accuracy on unseen phrasing."]
if c["missed"]:
    L.append("- Missed: " + "; ".join(c["missed"]))
sp = HERE / "results_sokoban.json"
if sp.exists():
    S = json.loads(sp.read_text())["summary"]
    L += ["", "## Second game: Sokoban, through the unchanged pipeline", "",
          f"`bench/run_benchmark_sokoban.py`, {S['trials']} requests on `{S['game']['name']}` ({S['game']['license']}). "
          f"Solvable (replayed in the original pygame engine): **{S['solvable_pct']}%**; fully validated: **{S['fully_validated_pct']}%**; "
          f"false acceptances: **{S['false_acceptances']}/{S['labelled_solvable']}**; impossible requests refused: {S['contradictory_rejected']}; "
          f"valid controls wrongly refused: {S['valid_controls_wrongly_rejected']}; median {S['median_seconds']} s per request.", "",
          "| Difficulty | n | Fully validated | Solvable | Median score | Median solution |", "|---|---:|---:|---:|---:|---:|"]
    for d, x in S["by_difficulty"].items():
        L.append(f"| {d} | {x['n']} | {x['fully_validated_pct']}% | {x['solvable_pct']}% | {round(x['median_score'], 1)} | {x['median_solution_length']} moves |")
    L += ["", "The first run of this benchmark scored 68.3% fully validated (boxes were placed in dead corners and the "
          "difficulty bands were uncalibrated); the constructor was fixed and the bands set before the run reported here."]
lp = HERE / "llm_results.json"
if lp.exists():
    R = json.loads(lp.read_text())
    if R.get("intent_summary") and R.get("totals", {}).get("cached_answers"):
        I, G = R["intent_summary"], R["generation_summary"]
        g = lambda x: f"{x['correct']}/{x['of']}"
        L += ["", f"## Language model measurements ({R['model']})", "",
              "| Request understanding (hand-labelled) | Keyword parser | LLM |", "|---|---:|---:|",
              f"| Literal wording | {g(I['keyword']['literal'])} | {g(I['llm']['literal'])} |",
              f"| Paraphrased | {g(I['keyword']['paraphrased'])} | {g(I['llm']['paraphrased'])} |",
              f"| All | {g(I['keyword']['all'])} | {g(I['llm']['all'])} |", "",
              "| Who builds the level | Loads | Solvable | Fully validated |", "|---|---:|---:|---:|"]
        for k, n in (("raw_llm", "LLM writes the level file directly"), ("llm_skill", "LLM + skill.md"),
                     ("llm_loop", "LLM + skill.md + verifier feedback"), ("full_pipeline", "Full pipeline")):
            if k in G:
                L.append(f"| {n} | {G[k]['loader_accepts']}/{G[k]['n']} | {G[k]['solvable']}/{G[k]['n']} | {G[k]['fully_validated']}/{G[k]['n']} |")
        L += ["", f"{R['totals']['cached_answers']} model calls, {R['totals']['tokens']:,} tokens. Small samples; labels written by the team."]
L += ["", "## Not measured", ""] + [f"- **{k}**: {val}" for k, val in s["not_measured"].items()]
L += ["", "## Reading these numbers", "",
      "- 'Blueprint-guided, unverified' is the same constructor as the full pipeline with the verifier and "
      "repair loop switched off. The gap between the two columns is what verification and repair add.",
      "- 'Random tiles' is a floor, not a stand-in for a language model's ability.",
      "- 'Fully validated' below 100% is the pipeline declining to over-claim: those levels are delivered "
      "with the lower label and the unmet requirement listed.",
      "- Reproduce with `python3 bench/run_benchmark.py && python3 bench/make_report.py`."]
(HERE / "REPORT.md").write_text("\n".join(L) + "\n")
print("\n".join(L))
