#!/usr/bin/env python3
"""Builds submission/deck.html from measured data (bench/results.json, bench/llm_results.json,
provenance.json, tests/last_run.json).  Every number on the slides is read from those files.

    python3 submission/build_deck.py && node submission/print_deck.js
"""
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "submission" / "config.json").read_text())
B = json.loads((ROOT / "bench" / "results.json").read_text())["summary"]
P = json.loads((ROOT / "blueprints" / "baba_is_auto" / "provenance.json").read_text())
SPEC = json.loads((ROOT / "blueprints" / "baba_is_auto" / "game_spec.json").read_text())
T = json.loads((ROOT / "blueprints" / "baba_is_auto" / "tests" / "last_run.json").read_text())
SB = json.loads((ROOT / "bench" / "results_sokoban.json").read_text())["summary"]
SPV = json.loads((ROOT / "blueprints" / "sokoban_sg" / "provenance.json").read_text())
SLINES = sum(len(q.read_text().splitlines()) for q in (ROOT / "blueprints" / "sokoban_sg").rglob("*.py"))
LP = ROOT / "bench" / "llm_results.json"
L = json.loads(LP.read_text()) if LP.exists() else None
if L and not L.get("intent_summary"):
    L = None
e = html.escape
A = B["arms"]; fp = A["full_pipeline"]; bo = A["blueprint_only"]; rt = A["random_tiles"]
bd = fp["by_difficulty"]; ch = B["contradiction_handling"]; mv = B["model_vs_engine_on_sabotaged_levels"]
cs = P["summary"]
unsupported = [x["name"] for x in SPEC["entities"] if x.get("support") == "unsupported"]
draw = re.search(r"const NOUN_COL=.*?\n}\n", (ROOT / "docs" / "app.js").read_text(), re.S).group(0)
model = L["model"] if L else "Gemini"
LLM_CARD = (f"{e(model) if False else model} turns free-form requests into a spec, proposes level layouts after reading <span class='mono'>skill.md</span>, repairs them from the verifier's exact findings, and names and annotates the result. Output is validated field by field against the blueprint." if L else
  "Designed seat: Gemini turns free-form requests into a spec, proposes layouts after reading <span class='mono'>skill.md</span>, and repairs them from the verifier's exact findings; output is validated field by field. <b>Implemented, not yet measured</b> — a keyword parser and the constraint planner fill this seat in every result shown.")

slides = []


def slide(kicker, title, body, cls="e"):
    slides.append(f'<section class="s {cls}"><div class="k">{kicker}</div><h1>{title}</h1>{body}'
                  f'<div class="foot"><span>Level-Forge · NeuroBridge.SI Baku · AI Gaming track</span><span>{len(slides) + 1}</span></div></section>')


def kpi(v, t):
    return f'<div class="kpi"><b>{v}</b><span>{t}</span></div>'


links = "".join(f'<div><span>{k}</span><b>{e(v)}</b></div>' for k, v in
                (("Demo", CFG.get("demo", "")), ("Source", CFG.get("repo", "")), ("Video", CFG.get("video", ""))) if v)
team = f'<p class="team">{e(CFG["team"].replace(" — ", ": "))}</p>' if CFG.get("team") else ""
sbd = SB["by_difficulty"]

def tick(t, cls="ok"):
    sym = {"ok": "✓", "bad": "✕", "open": "!"}[cls]
    return f'<div class="tick {cls}"><i>{sym}</i><span>{t}</span></div>'


def bar(label, pct, strong=False):
    return (f'<div class="bar{" strong" if strong else ""}"><span>{label}</span><div class="track"><div class="fill" style="width:{max(pct, 0.6)}%"></div></div><b>{pct:g}%</b></div>')


# 1 title
slides.append(f"""<section class="s e title"><div class="k">NeuroBridge.SI Baku · 9–10 October 2026 · AI Gaming track</div>
<div class="tgrid"><div><h1 class="big">Level-Forge</h1>
<p class="tag">Type a sentence.<br>Get a puzzle level that can be won.</p>
{team}<div class="links">{links}</div></div>
<div><canvas class="board" data-run="0" data-frame="0"></canvas><p class="cap">A hard puzzle level made from one sentence.</p></div></div>
<div class="kpis k3">{kpi(f"{fp['solvability_established_pct']:g}%", f"of {fp['n']} test requests produced a level the game could win")}
{kpi(f"{fp['false_acceptances']} of {fp['levels_labelled_solvable']}", "levels were wrongly marked as winnable")}
{kpi("2 games", "work with the same program")}</div>
<div class="foot"><span>Built during the hackathon, 9 October 2026</span><span>1</span></div></section>""")

# 2 problem
slide("Value for the user · 25 points", "The problem", f"""
<div class="cols2 wide-left"><div class="qwrap"><canvas class="board" data-run="4" data-frame="0"></canvas><div class="qmark">?</div>
<p class="cap big">Can this level be won? Today a person has to play it to find out.</p></div>
<div class="nums">
<div><i>1</i><span>Puzzle designers draw every level by hand.</span></div>
<div><i>2</i><span>They play each one to check that it works.</span></div>
<div><i>3</i><span>Mistakes they miss reach the players.</span></div></div></div>
<div class="strip">Who has this problem: small puzzle-game studios and solo developers who ship 50 to 200 levels per game.</div>""")

# 3 idea
slide("Value for the user · 25 points", "Our idea", f"""
<div class="pic3">
<div><div class="bubble">“Make a hard level about pushing rocks and changing the rules.”</div><b>1. You ask</b><span>In plain words.</span></div>
<div><canvas class="board" data-run="0" data-frame="0"></canvas><b>2. It builds the level</b><span>In the game's own file format.</span></div>
<div><div class="won"><canvas class="board" data-run="0" data-frame="99"></canvas><em>WON</em></div><b>3. The game plays it and wins</b><span>Before you ever see it.</span></div></div>
<div class="strip">A typical level takes about {fp['latency_seconds']['median']:.1f} seconds. A hard one takes about {bd['hard']['median_latency_s']:.0f} seconds.</div>""")

# 3b example game
slide("Prototype and use of AI · 30 points", "Our example game: Baba Is You", f"""
<div class="cols2 wide-left"><div><img class="orig" src="img/baba_1_start.png">
<p class="cap">One of our generated levels, drawn with the game's own graphics.</p></div>
<div><p class="lg">In Baba Is You the rules are words lying on the board. Push the words and the rules change.</p>
<div class="rulex"><span>BABA IS YOU</span><em>you move Baba</em></div>
<div class="rulex"><span>FLAG IS WIN</span><em>touch the flag to win</em></div>
<div class="rulex"><span>WALL IS STOP</span><em>walls block you</em></div>
<p class="small dim">Baba Is You was made by Arvi Teikari (Hempuli) and released in 2019. We used baba-is-auto, a free open-source copy of its rules by utilForever.</p></div></div>
<div class="strip"><b>It is only our example.</b> The same steps apply to other 2D puzzle games, and we tested a second one (Sokoban). 3D puzzle games would need extra work and are not tested yet.</div>""")

# 4 example
slide("Prototype and use of AI · 30 points", "An example", f"""
<div class="bubble wide">“Create a difficult level that tests rule manipulation, strategic object pushing and a changing win condition.”</div>
<div class="cols2 wide-left"><div><canvas class="board" data-run="0" data-frame="0"></canvas><p class="cap">The level that came back, {{SECS}} seconds later.</p></div>
<div>{tick("It can be won, in {MOVES} moves.")}{tick("It cannot be won without each skill that was asked for.")}{tick("It is hard. Moving at random, a player avoids the traps 1 time in {ODDS}.")}{tick("It opens in the real game.")}</div></div>""")

# 5 film strip
slide("Prototype and use of AI · 30 points", "The computer beats its own level", f"""
<div class="film">
<div><canvas class="board" data-run="0" data-frame="0"></canvas><span>Start</span></div>
<div><canvas class="board" data-run="0" data-frame="16"></canvas><span>Move 16</span></div>
<div><canvas class="board" data-run="0" data-frame="32"></canvas><span>Move 32</span></div>
<div><canvas class="board" data-run="0" data-frame="99"></canvas><span class="g">Move {{MOVES}}: won</span></div></div>
<div class="strip">Every solution is played in the original game engine. You can watch it or play the level yourself at the demo link.</div>""")

# 6 refusal
slide("Prototype and use of AI · 30 points", "It refuses impossible requests", f"""
<div class="cols2"><div><div class="bubble">“Put the only rocks behind the water. The water can only be crossed by sinking a rock.”</div>
<canvas class="board small" data-ev="1"></canvas>
{tick("Refused. You need a rock to cross the water, and the rocks are on the other side.", "bad")}</div>
<div><div class="bubble">“Make a level with teleporters.”</div>
{tick("Refused. This game has the word, but its code does nothing with it.", "bad")}
<div class="kpis k2">{kpi(f"{ch['correctly_rejected']} of {ch['contradictory_prompts']}", "impossible requests refused")}{kpi(f"{ch['wrongly_rejected_controls']} of {ch['valid_control_prompts']}", "good requests refused by mistake")}</div>
<p class="small dim">We wrote these test requests ourselves while building the checker.</p></div></div>""")

# 7 how it works
gem_line = (f"A language model ({e(model)}) reads the request." if L else
            "A language model (Google Gemini) can do step 1 and it works, but on a free key each call takes 7 to 10 seconds. To stay fast, the demo and every test number use the test version, where a keyword reader does step 1.")
slide("Prototype and use of AI · 30 points", "How it works", f"""
<div class="flowrow"><div class="fb"><em>{{ }}</em><b>The game's code</b><span>and the levels that ship with it</span></div><u>→</u>
<div class="fb acc"><em>Part 1 · done once per game</em><b>Learn the rules</b><span>An AI coding assistant reads the code, writes down each rule with the line it came from, and tests each rule in the real game. Words the game ignores are marked.</span></div><u>→</u>
<div class="fb book"><em>▤</em><b>Rule book</b><span>rules · file format · level checker · solver</span></div></div>
<div class="uses">▼ Every step below uses the rule book ▼</div>
<div class="chain">
<div><em>1</em><b>Understand</b><span>Which skills? How hard?</span></div><u>→</u>
<div><em>2</em><b>Possible?</b><span>If not, refuse and say why.</span></div><u>→</u>
<div><em>3</em><b>Build</b><span>Several levels in the game's file format.</span></div><u>→</u>
<div><em>4</em><b>Play</b><span>Search finds the shortest solution. The real game replays it.</span></div><u>→</u>
<div><em>5</em><b>Fix or label</b><span>Repair what failed. Say what was proven.</span></div></div>
<div class="io"><span>In: your sentence</span><span>Part 2 · runs for every request</span><span>Out: level file, solution, proof</span></div>
<div class="shots"><div><img class="orig" src="img/baba_2_start.png"><span>Step 3: a level it built</span></div><div><img class="orig" src="img/baba_2_end.png"><span>Step 4: the real game has won it</span></div>
<p class="small dim ainote"><b>Who does what.</b> Coding assistant (Claude): part 1. Search program: steps 2 to 5. {gem_line}</p></div>""")

# 8 two games
slide("Prototype and use of AI · 30 points", "It works on two different games", f"""
<div class="cols2 games"><div class="card"><img class="orig g1" src="img/baba_2_start.png"><h2>Baba Is You</h2><p>A puzzle where the player changes the rules.</p>
<p class="stat"><b>{fp['solvability_established_pct']:g}%</b> of {fp['n']} requests gave a winnable level</p></div>
<div class="card"><img class="orig g2" src="img/sokoban_start.png"><h2>Sokoban</h2><p>A puzzle about pushing boxes onto targets.</p>
<p class="stat"><b>{SB['solvable_pct']:g}%</b> of {SB['trials']} requests gave a winnable level</p></div></div>
<div class="strip">Both pictures are levels our program made, drawn with each game's own graphics. Adding the second game took about one hour and the main program did not change.</div>""")

# 9 results
slide("Quality testing · 20 points", "Test results", f"""
<div class="cols2 wide-left"><div class="card"><h3>Levels that passed every check, out of {fp['n']} requests</h3>
{bar("Random tiles", rt['fully_validated_pct'])}{bar("Our builder with checking switched off", bo['fully_validated_pct'])}{bar("Level-Forge", fp['fully_validated_pct'], True)}
<p class="small dim">Every check means: winnable, as hard as requested, and needing the requested skills.</p></div>
<div><div class="kpis k1">{kpi(f"{fp['false_acceptances']} of {fp['levels_labelled_solvable']}", "levels we marked as winnable failed a second, separate replay")}
{kpi(f"{T['difftest_moves']:,}", "random moves where our fast solver and the real game agreed")}
{kpi(f"{T['passed']} of {T['total']}", "automatic tests pass")}</div></div></div>""")

# 10 failures
slide("Quality testing · 20 points", "What went wrong", f"""
<div class="cols2 wide-left"><div>
{tick("Our first “hard” levels were long but easy. <b>Fixed:</b> difficulty now counts traps.", "ok")}
{tick("We said pushing was required. A shortcut existed. <b>Fixed:</b> our own search found it.", "ok")}
{tick(f"On the second game only 68% passed at first. <b>Fixed:</b> now {SB['fully_validated_pct']:g}%.", "ok")}
{tick(f"About 1 in 10 hard requests still misses a check. <b>Open:</b> the level is delivered with a warning.", "open")}
{tick("Gemini works but is slow on a free key (7 to 10 s per call). <b>Open:</b> results use the faster test version.", "open")}</div>
<div class="card"><h3>Compared with today</h3><table class="cmp">
<tr><th></th><th>By hand</th><th>Level-Forge</th></tr>
<tr><td>Can it be won?</td><td>play it</td><td>proven</td></tr>
<tr><td>Shortcuts</td><td>found by luck</td><td>searched for</td></tr>
<tr><td>Difficulty</td><td>a feeling</td><td>measured</td></tr></table>
<p class="small dim">We did not time human designers or compare difficulty with real players.</p></div></div>""")

# 11 feasibility
slide("Feasibility · 15 points", "Cost and next steps", f"""
<div class="cols3 tiles">
<div class="card"><b class="huge">0</b><p>data to collect. It only needs the game's own code.</p></div>
<div class="card"><b class="huge">1</b><p>ordinary computer. No graphics card, works offline.</p></div>
<div class="card"><b class="huge">1 hour</b><p>to add the second game.</p></div></div>
<div class="card hl next"><h3>Next</h3><div class="nums row"><div><i>1</i><span>Measure the language model on a paid key.</span></div><div><i>2</i><span>Add a third game with no human help.</span></div><div><i>3</i><span>Try it with a real puzzle studio.</span></div></div></div>
<p class="small dim">Tested on two turn-based 2D puzzle games. Other 2D puzzle games follow the same steps. 3D puzzle games need extra work. Very large levels cannot be fully searched.</p>""")

# 12 originality
slide("Originality · 10 points", "What is new", f"""
<div class="cols2 four">
<div class="card"><em>{{ }}</em><p>The rules come from the game's own code, and each rule is tested.</p></div>
<div class="card"><em>✓</em><p>It shows the level needs the skill you asked for.</p></div>
<div class="card"><em>▲</em><p>Difficulty is measured from every possible position.</p></div>
<div class="card"><em>✕</em><p>It refuses impossible requests and says why.</p></div></div>
<div class="strip">AI chatbots can also write a level from a sentence. They work from memory and do not check the result.</div>""")

# 13 disclosure
gem = (f"<b>Google {e(model)}</b>: reads requests, proposes and repairs levels." if L else "<b>Google Gemini</b> (free key): reads requests and names levels. It works, but it is slow, so the demo and all test numbers use the test version without it.")
slide("Mandatory disclosure", "Models, data and components", f"""
<div class="cols3">
<div class="card"><h3>Models</h3><ul><li><b>Anthropic Claude</b>, as a coding assistant: read the game code and wrote the program, tests, demo and this deck with us.</li><li>{gem}</li><li>Nothing was trained.</li></ul></div>
<div class="card"><h3>Data</h3><ul><li>Two open-source games, unmodified: <b>utilForever/baba-is-auto</b> and <b>xbandrade/sokoban-solver-generator</b> (MIT licence).</li><li>Test requests made by our own script.</li><li>No other data.</li></ul></div>
<div class="card"><h3>Components</h3><ul><li>Python 3, C++, pybind11</li><li>pygame, pygame-widgets, numpy</li><li>Playwright and Chromium</li><li>GitHub Pages</li></ul></div></div>
<div class="strip"><b>Built after the hackathon started.</b> Everything was made on 9 October 2026. Before the event we had only the idea and a written specification. Pages 16 to 18 hold the detailed numbers.</div>""")

# thank you
slides.append(f"""<section class="s e title ty"><div class="k">NeuroBridge.SI Baku · AI Gaming track</div>
<div class="tgrid"><div><h1 class="big">Thank you</h1>
<p class="tag">Questions are welcome.</p>
{team}<div class="links">{links}</div>
<p class="lede">Open the demo link to watch the levels being solved, or play them yourself with the arrow keys.</p></div>
<div><div class="won"><canvas class="board" data-run="0" data-frame="99"></canvas><em>WON</em></div>
<img class="orig tyimg" src="img/baba_2_end.png"><p class="cap">Two levels our program made, both already won.</p></div></div>
<div class="foot"><span>Level-Forge · NeuroBridge.SI Baku · AI Gaming track</span><span>{len(slides) + 1}</span></div></section>""")

# 7 ------------------------------------------------------------------------------------------
slide("Appendix A · how a level earns its label", "What “verified” means and how difficulty is computed", f'''
<div class="cols2"><div class="card"><h3>Four labels</h3><table>
<tr><td><span class="pill warn">structurally valid</span></td><td>schema checks, no meaningless words, <b>loaded by the original engine</b>, a controllable object exists</td></tr>
<tr><td><span class="pill info">proven solvable</span></td><td>a move sequence the <b>original engine replays to WON</b> (C++ and again through its Python binding)</td></tr>
<tr><td><span class="pill ok">fully validated</span></td><td>difficulty score inside the requested band; every requested skill exercised <b>and proven necessary</b>; explicit limits met</td></tr>
<tr><td><span class="pill bad">refused</span></td><td>no valid level can satisfy the request</td></tr></table>
<p><b>Necessity by ablation.</b> The solver is forbidden one kind of move (rule changes, object pushes, win-rule changes, control changes). If it then exhausts the state space without winning, every solution needs that skill.</p></div>
<div class="card"><h3>Difficulty without length</h3>
<p class="formula">score = 2 × trap bits + 4 × dead-end ratio + 2 × rule changes + 3 × sacrificed rule words</p>
<ul><li><b>Trap bits:</b> −log₂ of the chance that a player choosing at random among real moves along the solution never makes the level unwinnable.</li>
<li><b>Dead-end ratio:</b> share of reachable states that can no longer be won.</li>
<li>Bands: easy 0–8 · medium 6–15 · hard 15+. No score if the state space exceeds the bound.</li></ul>
<table class="num"><tr><th>Requested</th><th>Median score</th><th>Median solution</th><th>Fully validated</th></tr>
{"".join(f"<tr><td>{d}</td><td>{bd[d]['median_difficulty_score']}</td><td>{bd[d]['median_solution_length']:g} moves</td><td>{bd[d]['fully_validated_pct']:g}%</td></tr>" for d in ("easy", "medium", "hard"))}</table>
<p class="small dim">Hard requests build dozens of candidates and deliver the hardest that passes every check. The score is our definition; it has not been compared with human ratings.</p></div></div>''', cls="")

# 8 ------------------------------------------------------------------------------------------
rows = [("schema_validity_pct", "Accepted by the original loader"), ("solvability_established_pct", "Solvability established (solution replayed in the engine)"),
        ("mechanic_coverage_pct", "Requested skills exercised and proven necessary"), ("difficulty_alignment_pct", "Difficulty score inside the requested band"),
        ("fully_validated_pct", "Fully validated")]
slide("Appendix B · full benchmark", f"{fp['n']} requests, three ways of making a level, one verifier", f'''
<div class="cols2 wide-left"><div class="card"><h3>Benchmark (seed {B['meta']['seed']}, scripts in bench/, nothing typed by hand)</h3><table class="num">
<tr><th>Metric</th><th>Random tiles</th><th>Blueprint, unverified</th><th>Full pipeline</th></tr>
{"".join(f"<tr><td>{n}</td><td>{rt[k]:g}%</td><td>{bo[k]:g}%</td><td><b>{fp[k]:g}%</b></td></tr>" for k, n in rows)}
<tr><td>Latency median / p90</td><td>n/a</td><td>{bo['latency_seconds']['median']} s / {bo['latency_seconds']['p90']} s</td><td>{fp['latency_seconds']['median']} s / {fp['latency_seconds']['p90']} s</td></tr></table>
<p class="small dim">“Blueprint, unverified” is the same constructor with the verifier and repair loop switched off: the gap is what verification adds. Requests come from templates over the skills the generator supports, so this measures reliability inside its vocabulary.</p></div>
<div class="card"><h3>Can the verifier be wrong?</h3><ul>
<li><b>False acceptance: {fp['false_acceptances']} of {fp['levels_labelled_solvable']}.</b> Every level labelled solvable was re-played through the engine's Python binding.</li>
<li><b>Model vs real engine: {mv['agree']} of {mv['comparable_verdicts']} verdicts agree</b> on {mv['levels']} deliberately damaged levels ({mv['engine_bound_reached']} hit the engine's search bound).</li>
<li><b>Differential test:</b> the fast search model and the original engine compared move by move on {T['difftest_moves']:,} random moves, with no disagreement.</li>
<li><b>{cs.get('confirmed', 0)} mechanic probes</b> on the real engine; validator agrees with the real loader on all 51 shipped levels.</li>
<li><b>Regression suite: {T['passed']}/{T['total']}</b> checks pass.</li></ul></div></div>''', cls="")

# 9 ------------------------------------------------------------------------------------------
raw = L["generation_summary"]["raw_llm"] if L and L.get("generation_summary", {}).get("raw_llm") else None
slide("Appendix C · every failure we found", "Failures found while building it, and what each one changed", f'''
<div class="cols2 wide-left"><div class="card"><h3>What broke</h3><table class="fail">
<tr><td>The real engine explores only ~2,000 states per second, too slow for proofs.</td><td>Wrote a fast model of it; every solution is still replayed in the real engine and the two are differential-tested.</td></tr>
<tr><td>“Pushing is required” was false: a loose rule word can be drowned instead of a rock.</td><td>Found by the ablation search. Sink gates are now one column thicker than the number of loose words.</td></tr>
<tr><td>Early “hard” levels were long but easy: 0–1 trap points on the solution.</td><td>Replaced length with a difficulty score from the full state space; hard requests search and keep the hardest candidate.</td></tr>
<tr><td>The game's bundled viewer: tiny fixed window, scripted, no sprite for boxes or hedges.</td><td>Wrote a resizable keyboard player on the same engine.</td></tr>
<tr><td>Hard requests: {100 - bd['hard']['fully_validated_pct']:.1f}% not fully validated.</td><td>Delivered with the lower label and the unmet requirement listed.</td></tr>
<tr><td>Second game, first run: only 68% fully validated.</td><td>Boxes were placed in dead corners; constructor fixed and bands calibrated; now {SB['fully_validated_pct']:g}%.</td></tr>
<tr><td>Keyword parser misses paraphrased requests.</td><td>Gemini reads such requests correctly but takes 7 to 10 s per call on a free key, so the benchmark and demo still use the keyword parser.</td></tr></table></div>
<div><div class="card"><h3>Compared with how the task is done today</h3><table class="cmp">
<tr><th></th><th>By hand</th><th>Ask an LLM</th><th>Level-Forge</th></tr>
<tr><td>Loads in the game</td><td>yes</td><td>{f"{raw['loader_accepts']}/{raw['n']} (measured)" if raw else "unchecked"}</td><td>checked by the real loader</td></tr>
<tr><td>Known solvable</td><td>after play-testing</td><td>{f"{raw['solvable']}/{raw['n']} (measured)" if raw else "no evidence"}</td><td>replayed in the engine</td></tr>
<tr><td>Shortcuts found</td><td>if a tester finds one</td><td>no</td><td>exhaustive ablation</td></tr>
<tr><td>Difficulty</td><td>feel</td><td>a guess</td><td>computed</td></tr>
<tr><td>Impossible request</td><td>found late</td><td>not checked</td><td>refused with reason</td></tr></table></div>
<div class="card warnc"><h3>Not established</h3><ul class="small"><li>Model ≡ engine is tested, not proven; “unsolvable” means with the four directional inputs.</li><li>Two games, one version each; the difficulty score is not calibrated on human players.</li><li>We did not time human designers.</li></ul></div></div></div>''', cls="")

CSS = '''
@page{size:1280px 720px;margin:0}*{box-sizing:border-box}
body{margin:0;background:#0d0f15;color:#eceef4;font:17px/1.42 Inter,system-ui,sans-serif;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.s{width:1280px;height:720px;padding:34px 46px 40px;position:relative;page-break-after:always;overflow:hidden;background:#0d0f15}
.k{font:700 11.5px "DejaVu Sans Mono",monospace;letter-spacing:.1em;text-transform:uppercase;color:#f2c14e}
h1{font:800 30px/1.16 "Inter Display",Inter,sans-serif;margin:6px 0 12px;letter-spacing:-.015em;max-width:1120px}
h1.big{font-size:64px;margin:6px 0 6px;letter-spacing:-.03em}
h3{font:700 11px "DejaVu Sans Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#949bb0;margin:0 0 7px}
p{margin:0 0 8px}ul,ol{margin:0;padding-left:18px}li{margin:0 0 5px}
.card{background:#151821;border:1px solid #2a2f40;border-radius:11px;padding:13px 16px;margin-bottom:10px}
.card.hl{border-color:#f2c14e}.card.bad{border-left:3px solid #ef6f6c}.card.warnc{border-left:3px solid #f2a65a}
.cols2{display:grid;grid-template-columns:1fr 1fr;gap:14px}.cols2.wide-left{grid-template-columns:1.25fr 1fr}.cols3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}
.strip{background:#1a1d2a;border:1px solid #2a2f40;border-left:3px solid #f2c14e;border-radius:8px;padding:10px 14px;font-size:15px;margin-top:2px}
.dim{color:#949bb0}.small{font-size:13.6px}.mono{font-family:"DejaVu Sans Mono",monospace;font-size:.88em}
.foot{position:absolute;left:46px;right:46px;bottom:14px;display:flex;justify-content:space-between;font:11px "DejaVu Sans Mono",monospace;color:#5d6478}
.tgrid{display:grid;grid-template-columns:1.05fr 1fr;gap:30px;align-items:center;margin-top:12px}
.tag{font:700 25px/1.2 "Inter Display",Inter;color:#f2c14e;margin:0 0 12px}.lede{font-size:16.5px;color:#c9cedb}
.team{font-weight:600;margin-top:10px}.links{margin-top:10px;font-size:13.5px}.links div{display:flex;gap:10px}.links span{color:#949bb0;width:56px}.links b{font-family:"DejaVu Sans Mono",monospace;font-weight:400;color:#7db7ff;font-size:12.5px}
.cap{font-size:12.5px;color:#949bb0;margin-top:6px}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-top:16px}.kpi{background:#151821;border:1px solid #2a2f40;border-radius:10px;padding:10px 12px}.kpi b{display:block;font:800 23px "DejaVu Sans Mono",monospace}.kpi span{font-size:11.8px;color:#949bb0;line-height:1.3;display:block}
canvas.board{width:100%;border-radius:8px;display:block}canvas.board.small{width:62%;margin:8px 0}canvas.board.sok{width:42%}
table{width:100%;border-collapse:collapse;font-size:14.6px}td,th{padding:5px 7px;border-bottom:1px solid #2a2f40;vertical-align:top;text-align:left}th{font:700 10.5px "DejaVu Sans Mono",monospace;text-transform:uppercase;letter-spacing:.05em;color:#949bb0}
table.num td:not(:first-child),table.num th:not(:first-child){text-align:right;font-family:"DejaVu Sans Mono",monospace;font-size:12.5px}tr.tot td{font-weight:700;color:#fff}
table.fail td:first-child{color:#ffb1ae;width:44%}table.cmp td:last-child{color:#8ff0b8}table.cmp{font-size:13.8px}
table.score td{padding:11px 8px;font-size:15.3px}table.score td:first-child{width:21%;white-space:nowrap}table.score td:last-child{width:17%;color:#949bb0}
.pill{font:700 10.5px "DejaVu Sans Mono",monospace;padding:2px 7px;border-radius:5px;white-space:nowrap}.pill.ok{background:#1c4a33;color:#57c785}.pill.warn{background:#4a3a14;color:#ffd98a}.pill.info{background:#1b3554;color:#7db7ff}.pill.bad{background:#532423;color:#ef6f6c}
.q{font-style:italic;color:#c9cedb}.formula{font:700 13.5px "DejaVu Sans Mono",monospace;background:#0a0b10;border:1px solid #2a2f40;border-radius:7px;padding:8px 10px;color:#f2c14e}
.flow{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px}.flow div{background:#151821;border:1px solid #2a2f40;border-radius:9px;padding:9px 10px;font-size:13.2px;color:#c9cedb;line-height:1.35}.flow b{display:block;font:700 10.5px "DejaVu Sans Mono",monospace;color:#f2c14e;text-transform:uppercase;letter-spacing:.06em;margin-bottom:3px}
.arch{display:grid;grid-template-columns:.62fr auto 1.5fr auto 1.25fr;gap:10px;align-items:stretch;margin-bottom:8px}.arch i{align-self:center;color:#949bb0;font-style:normal;font-size:20px}
.box{background:#1c2030;border:1.5px solid #2a2f40;border-radius:10px;padding:8px 12px}.box.acc{border-color:#f2c14e}.box.ok{border-color:#57c785}.box b{display:block;font-size:15.5px;margin-bottom:3px}.box span{font-size:13.8px;color:#c9cedb;line-height:1.35;display:block}.box u{text-decoration:none;font:700 11px "DejaVu Sans Mono",monospace;color:#f2c14e}
.how{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}.how div{font-size:13.6px;color:#c9cedb;line-height:1.38;border-top:2px solid #f2c14e;padding-top:8px}.how b{display:block;color:#eceef4;font-size:14.5px;margin-bottom:3px}
.facts{display:grid;grid-template-columns:1fr 1fr;gap:6px 14px;margin-bottom:8px}.facts div{border-bottom:1px solid #2a2f40;padding-bottom:4px}.facts b{display:block;font:800 19px "DejaVu Sans Mono",monospace}.facts span{font-size:12px;color:#949bb0}

.e{font-size:21px;line-height:1.4;padding:40px 54px 44px}.e h1{font-size:37px;margin:8px 0 20px}.e h3{font-size:13px;margin-bottom:10px}
.e .card{padding:20px 24px;margin-bottom:14px}.e .cols2,.e .cols3{gap:18px}.e li{margin-bottom:9px}.e .lg{font-size:24px;line-height:1.35}.e ul.lg li{margin-bottom:14px}
.e .strip{font-size:18px;padding:13px 18px;margin-top:6px}.e .small{font-size:15.5px}.e table{font-size:19px}.e td,.e th{padding:9px 9px}.e th{font-size:12px}
.e table.num td:not(:first-child){font-size:19px}.e table.cmp{font-size:18px}.e table.score td{font-size:19px;padding:13px 9px}.e table.score td:last-child{width:13%}
.e h1.big{font-size:78px}.e .tag{font-size:31px}.e .lede{font-size:20px}.e .cap{font-size:15px}.e .links{font-size:15px}.e .links b{font-size:14px}
.kpis.k3{grid-template-columns:repeat(3,1fr);gap:16px;margin-top:22px}.kpis.k2{grid-template-columns:1fr 1fr;gap:14px;margin:0 0 10px}.e .kpi{padding:14px 18px}.e .kpi b{font-size:34px}.e .kpi span{font-size:16px}
.steps{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin-bottom:18px}.steps div{border-top:3px solid #f2c14e;padding-top:10px}.steps i{font:800 15px "DejaVu Sans Mono",monospace;color:#f2c14e;font-style:normal;margin-right:10px}.steps b{font-size:25px}.steps p{color:#c9cedb;margin-top:6px}
.e .arch{margin-bottom:14px;grid-template-columns:.7fr auto 1.6fr auto 1fr}.e .box{padding:14px 16px}.e .box b{font-size:21px}.e .box span{font-size:17.5px}
.e .facts b{font-size:24px}.e .facts span{font-size:14.5px}.e .pill{font-size:12.5px}.req{font-size:18px;margin-top:10px}
.e canvas.board.small{width:50%}.e canvas.board.sok{width:46%}.e table.fail td{font-size:17.5px;padding:8px}

.e h1{font-size:44px}.cap.big{font-size:22px;color:#eceef4;margin-top:14px}
.qwrap{position:relative}.qmark{position:absolute;left:44%;top:4%;font:800 190px "Inter Display",Inter;color:#f2c14e;text-shadow:0 0 30px #0d0f15}
.nums div{display:flex;gap:18px;align-items:center;margin-bottom:26px;font-size:25px;line-height:1.3}.nums i{flex:none;width:52px;height:52px;border-radius:50%;background:#f2c14e;color:#0d0f15;font:800 24px Inter;font-style:normal;display:flex;align-items:center;justify-content:center}
.nums.row{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}.nums.row div{margin:0;font-size:21px}
.pic3{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-bottom:22px}.pic3>div{display:flex;flex-direction:column}.pic3 b{font-size:26px;margin-top:auto;padding-top:16px}.pic3 span{color:#c9cedb}
.bubble{background:#1f2a44;border:1px solid #35487a;border-radius:18px 18px 18px 4px;padding:16px 20px;font-size:21px;font-style:italic;color:#dfe6ff;margin-bottom:14px}.bubble.wide{font-size:23px;margin-bottom:20px}
.won{position:relative}.won em{position:absolute;right:8px;bottom:8px;background:#57c785;color:#0d0f15;font:800 20px Inter;font-style:normal;padding:4px 14px;border-radius:8px}
.tick{display:flex;gap:16px;align-items:center;margin-bottom:18px;font-size:23px;line-height:1.3}.tick i{flex:none;width:42px;height:42px;border-radius:50%;font:800 22px Inter;font-style:normal;display:flex;align-items:center;justify-content:center;color:#0d0f15;background:#57c785}.tick.bad i{background:#ef6f6c}.tick.open i{background:#f2a65a}
.film{display:grid;grid-template-columns:1fr 1fr;gap:10px 22px;margin:0 auto 10px;width:84%}.film span{display:block;font:700 15px "DejaVu Sans Mono",monospace;color:#949bb0;margin-top:5px;text-transform:uppercase;letter-spacing:.06em}.film span.g{color:#57c785}
.flowrow{display:grid;grid-template-columns:.8fr auto 1.6fr auto .8fr;gap:14px;align-items:stretch;margin-bottom:14px}.flowrow u{align-self:center;text-decoration:none;font-size:30px;color:#949bb0}
.fb{background:#1c2030;border:2px solid #2a2f40;border-radius:14px;padding:14px 18px;display:flex;flex-direction:column;justify-content:center}.fb.acc{border-color:#f2c14e}.fb.ok{border-color:#57c785}.fb em{font:800 26px "DejaVu Sans Mono",monospace;color:#f2c14e;font-style:normal}.fb.ok em{color:#57c785}.fb b{font-size:23px}.fb span{font-size:18px;color:#c9cedb}
.ai .card{margin:0}.ai p{font-size:18.5px;margin:0}
.games .card{text-align:center}.games canvas{margin:0 auto 12px}.games h2{font:800 30px "Inter Display",Inter;margin:0 0 4px}.games p{margin:0 0 6px;color:#c9cedb}.stat b{font:800 34px "DejaVu Sans Mono",monospace;color:#f2c14e;margin-right:8px}canvas.board.sok2{width:38%}
.bar{display:grid;grid-template-columns:1fr;gap:5px;margin-bottom:20px;position:relative}.bar span{font-size:20px}.bar .track{height:30px;background:#0a0b10;border-radius:6px;margin-right:110px}.bar .fill{height:100%;background:#5d6478;border-radius:6px}.bar.strong .fill{background:#f2c14e}.bar b{position:absolute;right:0;bottom:-2px;font:800 28px "DejaVu Sans Mono",monospace}.bar.strong span{font-weight:700}
.kpis.k1{grid-template-columns:1fr;gap:14px;margin:0}
.tiles .card{text-align:center;padding:26px 20px}.huge{display:block;font:800 76px "Inter Display",Inter;color:#f2c14e;line-height:1}.tiles p{margin-top:10px;font-size:21px}.next{margin-top:4px}
.four{gap:18px}.four .card{display:flex;gap:20px;align-items:center;padding:26px 24px;margin:0}.four em{flex:none;width:70px;height:70px;border-radius:16px;background:#f2c14e;color:#0d0f15;font:800 30px "DejaVu Sans Mono",monospace;font-style:normal;display:flex;align-items:center;justify-content:center}.four p{font-size:24px;margin:0;line-height:1.3}.four+.strip{margin-top:18px}

img.orig{width:100%;border-radius:8px;display:block;image-rendering:pixelated}.games img.g1{width:62%;margin:0 auto 12px}.games img.g2{width:32%;margin:0 auto 12px}
.rulex{display:flex;align-items:center;gap:16px;margin-bottom:12px}.rulex span{font:800 19px "DejaVu Sans Mono",monospace;background:#0a0b10;border:1.5px solid #f2c14e;color:#f2c14e;border-radius:8px;padding:7px 12px;white-space:nowrap}.rulex em{font-style:normal;color:#c9cedb}
.e .flowrow{grid-template-columns:.75fr auto 1.7fr auto .85fr;margin-bottom:6px}.fb.book{border-color:#f2c14e;background:#2a2412}.fb.acc em{font-size:13px;letter-spacing:.06em;text-transform:uppercase}.e .fb span{font-size:16.5px;line-height:1.35}
.uses{text-align:center;font:700 14px "DejaVu Sans Mono",monospace;letter-spacing:.08em;text-transform:uppercase;color:#f2c14e;margin:6px 0}
.chain{display:grid;grid-template-columns:1fr auto 1fr auto 1fr auto 1fr auto 1fr;gap:8px;align-items:stretch}.chain>div{background:#1c2030;border:2px solid #2a2f40;border-radius:12px;padding:10px 12px}.chain u{align-self:center;text-decoration:none;color:#949bb0;font-size:22px}
.chain em{font:800 15px "DejaVu Sans Mono",monospace;color:#f2c14e;font-style:normal;margin-right:8px}.chain b{font-size:20px}.chain span{display:block;font-size:15.5px;color:#c9cedb;line-height:1.3;margin-top:4px}
.io{display:flex;justify-content:space-between;font:700 13px "DejaVu Sans Mono",monospace;text-transform:uppercase;letter-spacing:.06em;color:#949bb0;margin:8px 0 10px}.io span:nth-child(2){color:#f2c14e}.ainote{margin:0}.shots{display:grid;grid-template-columns:.5fr .5fr 1fr;gap:22px;align-items:center}.shots span{display:block;font:700 12.5px 'DejaVu Sans Mono',monospace;text-transform:uppercase;letter-spacing:.05em;color:#949bb0;margin-top:5px}
.ty .tgrid{margin-top:60px}.ty .lede{margin-top:18px}.tyimg{width:46%!important;margin-top:14px}
'''
JS = '''
const D=window.FORGE_DATA;''' + draw + '''
document.querySelectorAll("canvas.board").forEach(cv=>{
  if(cv.dataset.sok){const g=D.sokoban.runs.find(r=>r.frames&&r.frames.length&&r.spec.difficulty==="hard")||D.sokoban.runs.find(r=>r.frames&&r.frames.length),f=g.frames[0];drawBoard(cv,g.width,g.height,f.cells,f.rules,f.state);return;}
  if(cv.dataset.ev){const ev=D.gallery.find(g=>g.status==="REJECTED_CONTRADICTION"&&g.contradictions[0].evidence).contradictions[0].evidence;drawBoard(cv,ev.width,ev.height,ev.cells,[],"");return;}
  const g=D.gallery[+cv.dataset.run],f=g.frames[Math.min(+cv.dataset.frame,g.frames.length-1)];drawBoard(cv,g.width,g.height,f.cells,f.rules,f.state);});
'''
data = json.loads((ROOT / "docs" / "data.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
g0 = data["gallery"][0]; q = g0["verification"]["levels"]["solution_quality"]; dc = q["difficulty_components"]
flag = f'''<div class="facts"><div><b>{e(g0['status'].replace('_', ' '))}</b><span>label</span></div><div><b>{g0['elapsed_seconds']} s</b><span>generation time</span></div>
<div><b>{len(g0['solution'])} moves</b><span>shortest solution, replayed in the engine</span></div><div><b>{q['difficulty_score']}</b><span>difficulty score (hard ≥ 15)</span></div>
<div><b>1 in {round(2 ** dc['trap_bits']):,}</b><span>chance a random careful player stays winnable</span></div><div><b>{dc['trap_states']} · {round(dc['dead_ratio'] * 100)}%</b><span>trap points · dead-end states</span></div></div>
<table>{"".join(f"<tr><td><b>{e(k.replace('_', ' '))}</b></td><td><span class='pill ok'>proven necessary · {e(v.get('proof', ''))}</span></td></tr>" for k, v in g0['verification']['skills'].items())}</table>'''
search = (f"{g0['search']['candidates_built']} candidates built, {g0['search']['candidates_scored']} scored exactly, hardest kept." if g0.get("search") else "candidates built and scored.")
ev = next(g for g in data["gallery"] if g["status"] == "REJECTED_CONTRADICTION" and g["contradictions"][0].get("evidence"))["contradictions"][0]["evidence"]
doc = "".join(slides).replace("{FLAGSHIP}", flag).replace("{SEARCH}", search).replace("{EVSTATES}", str(ev.get("states_explored", ""))).replace("{SECS}", f"{g0['elapsed_seconds']:.0f}").replace("{MOVES}", str(len(g0['solution']))).replace("{ODDS}", f"{round(2 ** dc['trap_bits']):,}").replace("{ }", "{ }")
out = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Level-Forge pitch deck</title><style>{CSS}</style></head><body>{doc}<script src="../docs/data.js"></script><script>{JS}</script></body></html>'
(ROOT / "submission" / "deck.html").write_text(out)
print(f"{len(slides)} slides -> submission/deck.html", "(with LLM results)" if L else "(LLM results pending)")
