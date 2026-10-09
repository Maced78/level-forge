---
name: baba-is-auto-level-forge
description: Build new, valid, solvable levels for the open-source Baba Is You simulator "baba-is-auto" (utilForever/baba-is-auto @ 24cefb4). Use when asked to design, generate, validate or solve a level for this game. Never invent mechanics; everything you may use is listed here and backed by provenance.json.
blueprint_version: 0.1.0
---

# How to build a level for baba-is-auto

You are the level-generation agent. This file is the contract. `game_spec.json`,
`level_schema.json` and `provenance.json` are the machine-readable versions of
what is written here; when they disagree with your general knowledge of
*Baba Is You*, **they win** — this engine implements a subset of the real game.

## 0. Non-negotiable rules

1. Use only words whose `support` is `implemented` in `game_spec.json`, and only
   build puzzles around the **generation vocabulary** (section 2). 20 words exist
   in the enum but do nothing (`PULL`, `TELE`, `SWAP`, `FALL`, `SHIFT`, `MORE`,
   `WORD`, `MAKE`, `GROUP`, `LEVEL` …). If a request needs one, refuse and say why.
2. A level is not finished when it looks right. It is finished when
   `validator/validate.py` passes **and** `solver/` returns a witness **and**
   that witness replays to `WON` in the original engine.
3. Report exactly what was established. "Proven solvable" needs a replayed
   witness. "Unsolvable" needs an exhaustive search. A search that hit its bound
   established nothing — say so.
4. Never overwrite files in `game_src/`. New levels go to `out/levels/`.

## 1. Native level file

Plain text, whitespace-separated integers (`Sources/baba-is-auto/Games/Map.cpp`, `Map::Load`).

```
W H
<W*H tile IDs, row by row, top row first>      layer 1
<W*H tile IDs>                                  layer 2 (optional)
<W*H tile IDs>                                  layer 3 (optional)
```

* Coordinates are `(x, y)`, zero-based, origin top-left, `y` grows downward.
* Empty cell = `132` (`ICON_EMPTY`). A stack of objects in one cell is written
  as the same cell in successive layers. At most 3 layers.
* Text tile IDs: nouns 1–65, operators 67–75, properties 77–109.
  Object ("icon") ID = noun ID + 110. So `BABA`=4, `ICON_BABA`=114, `IS`=67,
  `YOU`=77, `WIN`=86, `FLAG`=25, `ICON_FLAG`=135.
* IDs `0, 66, 76, 110` are category sentinels: the loader rejects them, and
  anything outside 1–179.
* Optional trailing `DIRECTIONS` block (0=RIGHT 1=UP 2=LEFT 3=DOWN, one per
  tile). Omit it; default facing is RIGHT and facing is irrelevant unless
  `MOVE`/`FACING`/direction words are present.

Do not write IDs by hand. Write the readable form and convert:

```
BABA IS YOU . .        UPPERCASE = text tile     lowercase = object
. baba . flag .        .  = empty                a+b = stacked in one cell
```

`adapter.Level.from_dsl(text).to_native()` produces the file.

## 2. Generation vocabulary (every item has a passing probe)

| Text | Meaning in this engine |
|---|---|
| `X IS YOU` | every X moves on each input; no YOU left ⇒ `LOST` |
| `X IS WIN` | a YOU sharing a cell with an X ⇒ `WON` |
| `X IS STOP` | nothing can enter X's cell |
| `X IS PUSH` | X is pushed one cell; chains push together; a blocked chain blocks the mover; PUSH beats STOP |
| `X IS SINK` | when an X shares its cell with anything, **everything** in that cell is destroyed (text too) |
| `X IS DEFEAT` | YOU objects sharing a cell with X are destroyed; X stays |
| `X IS Y` | every X becomes a Y (`X IS X` protects X) |

Text is **always pushable**, with no rule needed. Objects with no property are
scenery you walk over. The map edge blocks everything. Rules are read
left→right and top→bottom only, and take effect in the same turn they are formed.

Nouns to use: `BABA KEKE ROCK BOX WALL HEDGE FLAG STAR LOVE KEY WATER LAVA SKULL CRAB TILE`.

Implemented by the engine but **outside the generation vocabulary** (`MOVE`,
`OPEN/SHUT`, `WEAK`, `FLOAT`, `SAFE`, `HAS`, `NOT`, `ON/NEAR/FACING/LONELY`,
`TEXT/EMPTY/ALL` have no probe; `HOT/MELT` and `AND` have one probe each): the
validator accepts them and the solver handles them through the real engine, but
do not generate with them until they are probed and added to `game_spec.json`.

## 3. Invariants a valid level must satisfy

* Exactly one loader-acceptable grid (section 1).
* At least one object is YOU when the level loads.
* The level is not won by the first processed turn.
* Every rule you rely on is actually parsed by the engine — check
  `initial_rules` in the validator output instead of assuming.
* Max one text tile per cell (the fast model requires it; the engine does not).
* Size ≤ 20×20 and ≤ 250 cells (verification policy, not an engine limit).

## 4. Design patterns that work

**Rule rail.** Text stacked from row 0 in column 0 (or the last column) can
never be moved: you cannot stand above it, behind it, or push it into the edge
(probe `rail_immovable`). Put every rule the player must not touch there. A
second column next to a filled rail is frozen too.

**Anchored breakable rule.** `NOUN` on the rail, `IS` in column 1 under a filled
band, `PROP` in column 2. Only `PROP` can move (up or down), so "break this
rule" costs one loose word instead of three.

**WIN slot.** `GOAL`, `IS` on a rail with the third cell empty; a loose `WIN`
word must be delivered into the slot. No WIN rule exists at the start, so a
win-condition change is necessary by construction.

**Gates and keys.** A full-height column of an object under a property is a gate:

| Gate | Key |
|---|---|
| `WALL IS STOP` column | break the rule |
| `SKULL IS DEFEAT` column | break the rule |
| `WATER IS SINK` column | push a `PUSH` object into it |

**Control swap.** `P IS YOU` lying in the open with noun `Q` directly above
`P`: pushing `Q` down gives `Q IS YOU` in one move.

## 5. Pitfalls (each cost a rejected candidate while building this blueprint)

* **Any text tile is also a sink key.** A loose rule word pushed into water
  removes the water. If "push an object" must be necessary, make the sink gate
  one column thicker than the number of loose words that can reach it.
* A loose word next to a gate column or a map edge on its far side cannot be
  pushed toward the near side: leave standing room behind it.
* A word pushed onto row 0, the last row or an edge column is stuck in that
  line forever. This is the main source of dead states.
* Sink and defeat are evaluated with the rules parsed **before** the sink
  phase (`Game::MovePlayer` order: move → parse → transform → parse → sink →
  defeat → win check → parse).
* `X IS YOU` + `X IS WIN` wins on the next processed turn, not at load.
* An object pushed into a sink cell is destroyed in the same turn; count it as
  pushed.

## 6. Workflow

1. Turn the request into a spec: difficulty, required / forbidden skills,
   limits (`forge/intent.py` shows the fields). Apply defaults and list them.
2. Check the spec for contradictions **before** placing anything: unsupported
   words, required-and-forbidden skills, and key-behind-its-own-gate cycles
   (`generator/patterns.py: check_plan`). If contradictory, stop and explain.
3. Build the level as an IR (`adapter.Level`), using section 4.
4. `python3 validator/validate.py LEVEL.txt` — all checks must pass.
5. `engine_build/babasolve LEVEL.txt --analyze` — need `"status":"solved"`.
6. `engine_build/babasolve LEVEL.txt --replay MOVES` — last frame must be `WON`.
7. For each required skill run `babasolve LEVEL.txt --forbid <rules|push|win|you>`.
   `unsolvable` + `exhaustive` ⇒ the skill is necessary. `solved` ⇒ it is not;
   repair the level. `unknown` ⇒ not established; say so.
8. Repair and repeat, at most a fixed number of times. Deliver the best
   candidate with its true status.

`forge/pipeline.py` implements steps 1–8.

## 7. Verification levels (never merge them)

| Label | What was shown |
|---|---|
| `STRUCTURALLY_VALID` | parses, schema-valid, only meaningful words, loaded by the original engine, has a YOU |
| `PROVEN_SOLVABLE` | + a move sequence that the original engine replays to `WON` |
| `FULLY_VALIDATED` | + difficulty score established and inside the requested band, every requested skill exercised **and** proven necessary, every explicit constraint met |

Robustness (dead states) is reported separately and only when the whole
reachable state space was enumerated.

## 8. Commands

```
./build_engine.sh                                         # build engine + solver
python3 forge/agent1_blueprint.py                         # rebuild this blueprint
python3 forge/agent1_blueprint.py --check                 # is the blueprint stale?
python3 blueprints/baba_is_auto/tests/probes.py           # 30 mechanic probes
python3 blueprints/baba_is_auto/tests/run_tests.py        # full regression
python3 blueprints/baba_is_auto/validator/validate.py F   # validate a level file
engine_build/babasolve F [--analyze] [--forbid X] [--backend engine|model]
engine_build/babasolve F --replay MOVES
engine_build/babasolve F --difftest 20000                 # model vs real engine
python3 -m forge.cli "your request"                       # full pipeline
```

## 9. Known limits

See the `inferred`, `unresolved` and `out-of-scope` entries in
`provenance.json`. In short: the search uses U/D/L/R only (no wait input);
"unsolvable" and dead-state counts come from the fast model, which is
differential-tested against the engine but not formally proven equivalent;
difficulty is a computed score (section 10), not a play-tested rating.

## 10. Difficulty (length is not difficulty)

A long walk is not a hard puzzle. Difficulty is scored from the fully enumerated state space
(`adapter.difficulty`), and solution length is deliberately not a term:

```
score = 2 x trap_bits + 4 x dead_ratio + 2 x rule_changes + 3 x sacrifices
```

* `trap_bits`: -log2 of the chance that a player who picks at random among the moves that
  change the board, at each step of the shortest solution, never makes the level unwinnable.
  8 bits = 1 chance in 256.
* `dead_ratio`: share of reachable states from which the level can no longer be won.
* `rule_changes`: times the active rule set changes along the solution.
* `sacrifices`: rule words destroyed along the solution.

Bands: easy 0-8, medium 6-15, hard 15+. If the state space exceeds the analysis bound the
score is "not established" and the level cannot be called hard.

What makes a level hard here, in order of effect:

1. **Scarcity.** One pushable object for a sink gate that is two columns thick: the gate's own
   rule word must be broken out, carried over and drowned as the second key, while the WIN
   word must be kept.
2. **Tight rooms.** Zones two or three cells wide; every push can pin something on an edge.
3. **Pillars.** A few immovable STOP blocks (rule on the rail) inside the zones.
4. **Search.** Build dozens of candidates, score each exactly, verify the hardest first.

Making a level bigger or adding empty floor lowers the score and blows up the state space.
