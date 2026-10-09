---
name: sokoban-sg-level-forge
description: Build valid, solvable levels for the open-source pygame Sokoban "sokoban-solver-generator" (xbandrade, commit 69c7b5c). Second blueprint of Level-Forge; same contract as blueprints/baba_is_auto.
blueprint_version: 0.1.0
---

# How to build a level for sokoban-solver-generator

Everything here comes from the game's source (`games/sokoban_sg/src/`); `provenance.json` holds the
source line and the probe result for each rule.

## Level file (`levels/*.dat`)

One row per line, tokens separated by single spaces, all rows the same length.

| Token | Meaning |
|---|---|
| `+` | wall | 
| `-` | floor |
| `@` | box |
| `X` | goal |
| `*` | player |
| `$` | box on a goal |
| `%` | player on a goal |

## Rules the engine implements (all probed)

* The player moves one cell; walls block (`Player.update`).
* Walking into a box pushes it one cell if the cell behind holds neither a box nor a wall
  (`Box.can_move`; walls are a subclass of Box). Two boxes in a line cannot be pushed.
* A box on a goal becomes `$`; it can be pushed off again.
* The level is complete exactly when no `@` remains (`Game.is_level_complete`).

## Invariants a valid level must satisfy

* Exactly one player. Only the seven tokens above (anything else makes the loader abandon the level).
* **Closed wall border.** The engine indexes `game.puzzle` at the target cell without a bounds
  check; outside the puzzle that cell is `None` and the move fails.
* Boxes ≤ goals, and at least one box off a goal at the start.
* At most 17×10 (the engine's fixed window); this blueprint verifies up to 12×9.

## Pitfalls

* A box with walls on two perpendicular sides is dead unless it is on a goal: never place one there.
* More goals than boxes is fine; more boxes than goals can never be won — refuse the request.

## Verify

```
python3 blueprints/sokoban_sg/validator/validate.py LEVEL.dat
python3 blueprints/sokoban_sg/tests/probes.py
python3 blueprints/sokoban_sg/build_blueprint.py      # probes + model-vs-engine differential test
python3 -m forge.cli "A medium level with two boxes" --game sokoban_sg
```

Difficulty: `2 × trap bits + 4 × dead-end ratio + 1.5 × boxes`; bands easy 0–7, medium 5–12, hard 11+.
Known limits: the generator is random rooms filtered by the solver; the search model is
differential-tested against the engine, not proven equivalent.
