# solver/

`babasolve.cpp` — breadth-first search over game states, with two transition functions:

* `--backend engine`: the original `baba_is_auto::Game` (unmodified sources, linked in). ~2,000 states/s.
* `--backend model`: `model.hpp`, a model of the subset documented in `mechanics.md`. ~100,000+ states/s.
* default `auto`: model when the level is inside the subset, engine otherwise.

```
babasolve LEVEL.txt                      shortest solution (optimal: BFS)
babasolve LEVEL.txt --analyze            + reachable / dead states, number of shortest solutions
babasolve LEVEL.txt --forbid rules       search with rule-changing moves removed (also: push, win, you)
babasolve LEVEL.txt --replay UDLR...     frame-by-frame trace from the ORIGINAL engine
babasolve LEVEL.txt --difftest 20000     model and engine side by side on a random walk
```

Output is one JSON object. `status` is `solved` (proof: witness), `unsolvable` (proof: exhaustive) or
`unknown` (proof: bounded — nothing established). Bounds: `--max-states`, `--max-ms`.

Built by `./build_engine.sh` into `engine_build/babasolve`.
