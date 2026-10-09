"""Turns a structured design spec into candidate plans (game-specific)."""
from __future__ import annotations

import random

from . import patterns as P

# difficulty -> (number of puzzle elements, band of the difficulty SCORE from adapter.difficulty).
# The score ignores solution length on purpose: a long walk is not a hard puzzle.
BANDS = {"easy": (1, (0, 8)), "medium": (2, (6, 15)), "hard": (3, (15, 1000))}

# which construction element makes which skill necessary
ELEMENT_FOR = {
    "rule_manipulation": ["stop_gate", "defeat_gate", "form_win"],
    "object_pushing": ["sink_gate"],
    "win_condition_change": ["form_win"],
    "you_change": ["swap"],
    "hazard_sink": ["sink_gate"],
    "hazard_defeat": ["defeat_gate"],
}
SKILLS_OF = {
    "stop_gate": {"rule_manipulation"},
    "defeat_gate": {"rule_manipulation", "hazard_defeat"},
    "form_win": {"rule_manipulation", "win_condition_change"},
    "sink_gate": {"object_pushing", "hazard_sink"},
    "swap": {"rule_manipulation", "you_change"},
}


def choose_elements(spec, rng):
    required = list(spec["skills_required"])
    forbidden = set(spec["skills_forbidden"])
    allowed = [e for e, sk in SKILLS_OF.items() if not (sk & forbidden)]
    chosen = []
    # most constrained skill first, so one element can cover several requirements
    required.sort(key=lambda sk: len([e for e in ELEMENT_FOR[sk] if e in allowed]))
    for skill in required:
        if any(skill in SKILLS_OF[e] for e in chosen):
            continue
        opts = [e for e in ELEMENT_FOR[skill] if e in allowed]
        if not opts:
            raise P.PlanError(
                f"'{skill}' is required, but every construction that exercises it also needs a "
                f"forbidden skill ({', '.join(sorted(forbidden))})",
                kind="skill_conflict",
                suggestions=["drop one of the two requirements"])
        chosen.append(rng.choice(opts))
    target = spec.get("elements") or BANDS[spec["difficulty"]][0]
    if spec.get("dependencies"):
        target = len(chosen)          # an explicit "only key" request: add nothing that could act as a key
    pool = [e for e in allowed if e not in chosen]
    rng.shuffle(pool)
    while len(chosen) < target and pool:
        e = pool.pop()
        if e == "swap" and "you_change" not in required and spec["difficulty"] != "hard":
            continue
        chosen.append(e)
    return chosen


def make_plan(spec, rng: random.Random, attempt=0) -> P.Plan:
    els = choose_elements(spec, rng)
    hard = spec["difficulty"] == "hard"
    plan = P.Plan(height=spec.get("height") or 6)
    said = spec.get("raw", "").lower()

    def choose(options):
        """Prefer a noun the request names ("rocks", "water", "skulls")."""
        named = [n for n in options if n.lower() in said]
        return rng.choice(named or options)

    plan.player, plan.other = rng.sample(P.PLAYERS, 2) if rng.random() < 0.3 else ("BABA", "KEKE")
    plan.goal_noun = choose(P.GOALS)
    plan.push_noun = choose(P.PUSH_NOUNS)
    gates = []
    for e in els:
        if e == "stop_gate":
            gates.append({"kind": "stop", "noun": choose(P.STOP_NOUNS), "key_zone": 0})
        elif e == "defeat_gate":
            gates.append({"kind": "defeat", "noun": choose(P.DEFEAT_NOUNS), "key_zone": 0})
        elif e == "sink_gate":
            gates.append({"kind": "sink", "noun": choose(P.SINK_NOUNS), "key_zone": None})
    rng.shuffle(gates)
    used = set()
    for g in gates:                       # one gate per noun
        while g["noun"] in used:
            g["noun"] = rng.choice({"stop": P.STOP_NOUNS, "defeat": P.DEFEAT_NOUNS, "sink": P.SINK_NOUNS}[g["kind"]])
        used.add(g["noun"])
    if "swap" in els:
        # zone 0 holds the first character and the YOU rule, sealed by a protected STOP gate;
        # the second character starts just behind it, so every other gate lies on ITS way to
        # the goal and breakable rules (anchored in zone 0) must be dealt with before the swap.
        plan.swap = True
        noun = next(n for n in P.STOP_NOUNS if n not in used)
        gates.insert(0, {"kind": "stop", "noun": noun, "key_zone": 0, "static": True})
        plan.other_zone = 1
    for i, g in enumerate(gates):
        if g["key_zone"] is None:
            g["key_zone"] = i if rng.random() < 0.75 else rng.randrange(1 if plan.swap else 0, i + 1)
    # an explicit dependency in the request ("the rock is behind the water") overrides placement
    for dep in spec.get("dependencies", []):
        for i, g in enumerate(gates):
            if g["kind"] == dep["gate_kind"]:
                g["key_zone"] = i + 1
    plan.gates = gates
    if "form_win" in els:
        plan.goal = "form_win"
    base = 4 if len(gates) == 0 else 3
    plan.zone_widths = [base + (1 if (i == 0 and plan.swap) else 0) + (attempt // 6) % 2
                        for i in range(len(gates) + 1)]
    if spec.get("width"):
        fixed = 2 + len(gates) + 1
        per = max(2, (spec["width"] - fixed) // (len(gates) + 1))
        plan.zone_widths = [per] * (len(gates) + 1)
    # stay inside the verification size policy (20 wide)
    k = sum(1 for g in gates if g["kind"] in ("stop", "defeat") and not g.get("static"))
    width = lambda: 2 + sum(plan.zone_widths) + sum(1 + (k if g["kind"] == "sink" else 0) for g in gates) + 2
    if plan.swap:                         # the 'P IS YOU' sentence needs three free columns in zone 0
        plan.zone_widths[0] = 4 + (1 if k else 0)
    first = 1 if plan.swap else 0
    while width() > 20 and max(plan.zone_widths[first:] or [2]) > 2:
        rest = plan.zone_widths[first:]
        plan.zone_widths[first + rest.index(max(rest))] -= 1
    plan.rocks = 1
    if hard or spec["difficulty"] == "medium":
        # Hard = tight and scarce, not big: one pushable only (rule words have to be drowned as
        # well), small rooms, and immovable blocks that punish careless pushes.
        plan.scarce = hard
        free_stop = [n for n in P.STOP_NOUNS if n not in used and not any(g["noun"] == n for g in gates)]
        if free_stop and rng.random() < (0.75 if hard else 0.4):
            plan.pillar_noun = free_stop[0]
            plan.pillars = rng.randint(1, 4 if hard else 2)
        if hard and not spec.get("width"):
            plan.zone_widths = [max(3, plan.zone_widths[0])] + [rng.choice([2, 3]) for _ in plan.zone_widths[1:]]
            if plan.swap:
                plan.zone_widths[0] = 4 + (1 if k else 0)
    return plan
