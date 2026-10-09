# baba-is-auto — mechanics, grounded in source

Game: `utilForever/baba-is-auto` @ `24cefb48`, MIT. Paths are relative to
`game_src/`. Line numbers for every claim are in `provenance.json` (resolved
by regex anchors each time the blueprint is rebuilt, so they stay correct or
the claim is downgraded). Status words: **confirmed** = source line + passing
probe on the built engine; **inferred**; **unresolved**.

## Architecture

| Part | Where |
|---|---|
| Object / word IDs | `Includes/baba-is-auto/Enums/{Noun,Op,Property,Icon}Type.def`, assembled in `GameEnums.hpp` |
| Level loading | `Sources/baba-is-auto/Games/Map.cpp` — `Map::Load` |
| Turn logic, rule parsing | `Sources/baba-is-auto/Games/Game.cpp` (2,191 lines) |
| Rules container | `Sources/baba-is-auto/Rules/RuleManager.cpp` |
| Python binding | `Extensions/BabaPython/` (pybind11 module `pyBaba`) |
| Playable GUI | `Extensions/BabaGUI/main.py <level.txt>` (pygame) |
| Shipped levels | `Resources/Maps/*.txt` (51 files, mostly unit-test fixtures) |

`ObjectType` is one enum: `NOUN_TYPE`(0), nouns, `OP_TYPE`(66), operators,
`PROPERTY_TYPE`(76), properties, `ICON_TYPE`(110), icons, then four synthetic
`LOCKED_*` values. `ConvertTextToIcon` adds 110 to a noun.

## One turn — `Game::MovePlayer(dir)`

Extracted automatically from the function body:

1. `ProcessPlayerMove` — every YOU stack moves; pushes resolve recursively
2. `ParseRules`
3. `ProcessDirectionProperties`, `ProcessMoveProperty` (not in generation vocabulary)
4. `ParseRules`
5. `ProcessTransformations` — `X IS Y`, from one snapshot
6. `ParseRules`
7. `ProcessSink` → `ProcessWeak` → `ProcessHotMelt` → `ProcessDefeat` → `ProcessOpenShut`
8. `CheckPlayState` — WON / LOST
9. `ParseRules`

Consequences:

* A rule completed by a push is live for the transformation and effect phases
  of the same turn (confirmed, probe `rule_same_turn`).
* Steps 7–8 use the rules parsed at step 6, so a word destroyed by SINK in
  step 7 still counts for DEFEAT and for the win check of that turn (read from
  the source order; no dedicated probe, but the model implements it this way
  and agrees with the engine in differential tests).
* The constructor does not call `CheckPlayState`: nothing is won or lost at
  load, only when a turn is processed (confirmed, probe `load_state_not_evaluated`).

## Movement — `CanMove`, `ProcessMove`, `ProcessPush`

* Destination outside the grid ⇒ blocked.
* Destination holds a non-text object that is STOP and not PUSH ⇒ blocked.
* Destination holds anything pushable (any text tile, or a PUSH object) ⇒ the
  pushables must themselves be able to move one cell the same way, recursively;
  otherwise the mover is blocked.
* Objects with neither property do not interact: the mover shares the cell.
* YOU stacks are processed in an order that depends on the direction
  (`PlayerStackComesFirst`), front-most first.

## Rules — `ParseRules`, `ParseRule`

At every cell, once horizontally and once vertically: `NOUN IS (NOUN | PROPERTY)`,
reading right or down (confirmed). `AND` chains expand into independent rules
(confirmed). Rules are not de-duplicated (`RuleManager::AddRule` appends; source
reading): the same sentence formed twice is two rules, which matters only for
transformations (two targets ⇒ an extra object is spawned).

## Effects

| Property | Function | Behaviour (confirmed) |
|---|---|---|
| WIN | `CheckPlayState` | a YOU in a cell that contains a WIN instance ⇒ WON |
| — | `CheckPlayState` | no YOU instance anywhere ⇒ LOST |
| SINK | `ProcessSink` | a cell with ≥ 2 instances, one of them SINK ⇒ all removed |
| DEFEAT | `ProcessDefeat` | YOU instances in a cell containing a DEFEAT instance are removed |
| HOT / MELT | `ProcessHotMelt` | MELT instances in a cell containing a HOT instance are removed |
| noun | `ProcessTransformations` | `X IS Y` retypes X; `X IS X` protects it |

## Words that do nothing

`PULL SWAP TELE FALL SHIFT MORE WORD BEST SLEEP RED BLUE HIDE BONUS END DONE`
have zero references in `Game.cpp`; `MAKE` is parsed but never consumed;
`GROUP LEVEL CURSOR IMAGE` have no special meaning. The repository's own
`Documents/rule-language.md` says the same, and probe `unsupported_inert`
shows `ROCK IS PULL` pulling nothing. The analysis is automatic: the count of
`ObjectType::<WORD>` references in `Game.cpp` is stored per word in
`game_spec.json`.

## The fast model (`solver/model.hpp`)

The engine copies its rule list on almost every property query, so it explores
about 2,000 states per second. `model.hpp` re-states `MovePlayer`, `CanMove`,
`ProcessMove`, `ParseRules`, transformations, sink, defeat and the win check
for the subset *ordinary nouns + IS + YOU/STOP/PUSH/WIN/SINK/DEFEAT* and runs
at about 100,000–150,000 states per second. Each function names the engine
function it mirrors.

It is used for search only. Safeguards:

* a level is called solvable only after the witness is replayed to `WON` in
  the original engine (and again through `pyBaba`);
* `babasolve --difftest N` random-walks both in lock-step and compares the
  whole board and the win/lose flags after each move;
* levels using any other word are searched with the engine itself
  (`--backend engine` forces this for any level).

## What is not established

| Item | Status | Effect |
|---|---|---|
| Model ≡ engine on the subset | differential-tested, **not proven** | "unsolvable" and dead-state counts are model-level claims |
| State key ignores object IDs and stacking order | inferred | same |
| Wait input available to players | unresolved | search uses U/D/L/R; "unsolvable" means with those four inputs |
| `EMPTY IS MOVE` direction | random (`std::mt19937`, `random_device`) | `EMPTY` is excluded from generation |
| MOVE, OPEN/SHUT, WEAK, FLOAT, SAFE, HAS, conditions, NOT, special nouns | implemented, **no probe here** | accepted and solved via the engine, never generated |
| Difficulty | computed score (trap pressure, dead-state ratio, rule changes, sacrificed words; length excluded) | not compared with human ratings |
