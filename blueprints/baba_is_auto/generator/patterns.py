"""Constraint-based level construction for baba-is-auto.

A level is planned as a chain of ZONES separated by GATES, like a lock-and-key
graph:

    zone0 --gate0--> zone1 --gate1--> ... --> goal

Each gate kind has exactly one kind of KEY, taken from mechanics the blueprint
has confirmed by probe:

    gate "stop"    column of <noun> under '<noun> IS STOP'    key: break that rule
    gate "defeat"  column of <noun> under '<noun> IS DEFEAT'  key: break that rule
    gate "sink"    column of <noun> under '<noun> IS SINK'    key: push a PUSH object in

Design pattern "rule rail" (probe `rail_immovable`): text stacked in column 0
(or the last column) contiguously from row 0 can never be moved.  The rail
holds
  * protected rules  - vertical, three cells, constants of the level;
  * anchors          - the subject of a breakable rule: 'NOUN' on the rail,
                       'IS PROP' continuing into the zone, so exactly two
                       words are loose;
  * a WIN slot       - 'GOAL', 'IS' and an empty third cell that the loose
                       WIN word must be delivered to.
Keeping most words frozen is what keeps the state space small enough for an
exhaustive proof.

The plan is a dependency graph; `check_plan` rejects cyclic plans (a key that
is only reachable through its own gate) before anything is placed.  Placement
inside zones is randomised; the solver is the judge.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .. import adapter as A

PLAYERS = ["BABA", "KEKE"]
GOALS = ["FLAG", "STAR", "LOVE", "KEY"]
STOP_NOUNS = ["WALL", "HEDGE"]
SINK_NOUNS = ["WATER", "LAVA"]
DEFEAT_NOUNS = ["SKULL", "CRAB"]
PUSH_NOUNS = ["ROCK", "BOX"]

GATE_KEY = {
    "stop": "break the '{noun} IS STOP' rule",
    "defeat": "break the '{noun} IS DEFEAT' rule",
    "sink": "push a {push} into the {noun}",
}


@dataclass
class Plan:
    height: int = 6
    zone_widths: list = field(default_factory=lambda: [3])
    gates: list = field(default_factory=list)      # [{kind, noun, key_zone, static}]
    goal: str = "reach"                            # reach | form_win
    swap: bool = False                             # control must be handed to `other`
    other_zone: int = -1                           # where `other` starts (swap only)
    player: str = "BABA"
    other: str = "KEKE"
    goal_noun: str = "FLAG"
    push_noun: str = "ROCK"
    rocks: int = 1
    scarce: bool = False                           # exactly one pushable: rule words must be drowned too
    pillars: int = 0                               # immovable STOP blocks inside the zones
    pillar_noun: str = "HEDGE"
    decoys: int = 0
    notes: list = field(default_factory=list)

    def describe(self):
        parts = [f"gate{i}:{g['kind']}({g['noun']}, key in zone {g['key_zone']})"
                 for i, g in enumerate(self.gates)]
        return (f"{len(self.zone_widths)} zone(s), " + (", ".join(parts) or "no gates")
                + f", goal={self.goal}" + (", control swap" if self.swap else ""))

    def elements(self):
        return len(self.gates) + (self.goal != "reach") + self.swap


class PlanError(Exception):
    """The plan is contradictory; .explanation and .suggestions say why."""

    def __init__(self, explanation, cycle=None, suggestions=(), kind="layout"):
        super().__init__(explanation)
        self.explanation = explanation
        self.cycle = cycle or []
        self.suggestions = list(suggestions)
        self.kind = kind


def dependency_graph(plan: Plan):
    """Nodes and 'requires' edges of the lock-and-key graph."""
    edges = []
    for i, g in enumerate(plan.gates):
        key = f"key{i}: " + GATE_KEY[g["kind"]].format(noun=g["noun"].lower(), push=plan.push_noun.lower())
        edges.append((f"zone{i + 1}", f"gate{i} open ({g['noun'].lower()} column)"))
        edges.append((f"gate{i} open ({g['noun'].lower()} column)", key))
        edges.append((key, f"zone{g['key_zone']}"))
        if i > 0:
            edges.append((f"zone{i}", f"gate{i - 1} open ({plan.gates[i - 1]['noun'].lower()} column)"))
    edges.append(("win", f"zone{len(plan.gates)}"))
    return edges


def find_cycle(edges):
    graph = {}
    for a, b in edges:
        graph.setdefault(a, []).append(b)
    state, stack = {}, []

    def dfs(n):
        state[n] = 1
        stack.append(n)
        for m in graph.get(n, []):
            if state.get(m) == 1:
                return stack[stack.index(m):] + [m]
            if m not in state:
                c = dfs(m)
                if c:
                    return c
        stack.pop()
        state[n] = 2
        return None

    for n in list(graph):
        if n not in state:
            c = dfs(n)
            if c:
                return c
    return None


def rail_rows(plan: Plan):
    """How many rail cells the plan needs on the left / in total."""
    statics = static_rules(plan)
    anchors = [g for g in plan.gates if g["kind"] in ("stop", "defeat") and not g.get("static")]
    return statics, anchors


def check_plan(plan: Plan):
    """Symbolic check before any placement: the key of every gate must be
    obtainable without first passing that gate, and the rails must fit."""
    cyc = find_cycle(dependency_graph(plan))
    if cyc:
        i = next(i for i, g in enumerate(plan.gates) if g["key_zone"] > i)
        g = plan.gates[i]
        what = GATE_KEY[g["kind"]].format(noun=g["noun"].lower(), push=plan.push_noun.lower())
        raise PlanError(
            f"Circular dependency: the {g['noun'].lower()} gate can only be opened if the player can "
            f"{what}, but that key is placed in zone {g['key_zone']}, which is only reachable through "
            f"the same gate.",
            cycle=cyc, kind="cycle",
            suggestions=[f"place the key in zone {i} or earlier, in front of the {g['noun'].lower()} gate",
                         "add a second key in front of the gate",
                         "make the gate's rule breakable from the player's side so there is another way through"])
    for i, g in enumerate(plan.gates):
        if g["kind"] in ("stop", "defeat") and not g.get("static") and g["key_zone"] != 0:
            raise PlanError("breakable gate rules are anchored on the left rail, i.e. in zone 0",
                            suggestions=["set key_zone to 0"])
    statics, anchors = rail_rows(plan)
    bands = plan.height // 3
    if len(anchors) > plan.height - 3:
        raise PlanError(f"{len(anchors)} breakable rules do not fit under the rail of a height-{plan.height} map",
                        suggestions=["increase the height", "request fewer mechanics"])
    if len(statics) + (plan.goal == "form_win") > 4 * bands:
        raise PlanError(f"{len(statics)} protected rules do not fit on the rails of a height-{plan.height} map",
                        suggestions=["increase the height", "request fewer mechanics"])
    return True


def static_rules(plan: Plan):
    rules = []
    if not plan.swap:
        rules.append((plan.player, "IS", "YOU"))
    if any(g["kind"] == "sink" for g in plan.gates):
        rules.append((plan.push_noun, "IS", "PUSH"))
    for g in plan.gates:
        if g["kind"] == "sink" or g.get("static"):
            rules.append((g["noun"], "IS", g["kind"].upper()))
    if plan.goal == "reach":
        rules.append((plan.goal_noun, "IS", "WIN"))
    if plan.pillars:
        rules.append((plan.pillar_noun, "IS", "STOP"))
    return rules


def build(plan: Plan, rng: random.Random) -> A.Level:
    check_plan(plan)
    H = plan.height
    statics, anchors = rail_rows(plan)

    # ---- rail allocation --------------------------------------------------
    # Left block = columns 0 and 1, right block = the last two columns.  A
    # vertical rule in the second column of a block is frozen as long as the
    # outer column is filled next to it.  Anchored rules go under the first
    # band of the left block: NOUN in column 0, IS in column 1 (frozen when
    # both columns are filled above it), PROP in column 2 - the only loose word.
    bands = H // 3
    k = len(anchors)
    left_bands = (H - k) // 3 if k else bands

    def allocate(slot_opt):
        """Greedy fill given a slot position; returns (placed, slot) or None."""
        todo = list(statics)
        placed = {("L", 0, 0): todo.pop(0) if todo else None}
        slot = slot_opt
        if k and slot != ("L", 1, 0):
            # column 1 must be filled above the anchors or their IS words come loose;
            # with nothing else to protect, the classic identity rule is used as filler
            placed[("L", 1, 0)] = todo.pop(0) if todo else (plan.goal_noun, "IS", plan.goal_noun)
        cols = [("R", 0), ("R", 1)] + ([] if k else [("L", 0), ("L", 1)])
        if not k and rng.random() < 0.5:
            cols = [("L", 0), ("R", 0), ("L", 1), ("R", 1)]
        height = {c: 0 for c in cols}
        height[("L", 0)] = 1
        if ("L", 1, 0) in placed:
            height[("L", 1)] = 1
        limit = {("L", 0): left_bands, ("L", 1): left_bands, ("R", 0): bands, ("R", 1): bands}
        blocked = set()
        if slot:
            side, ci, band = slot
            blocked.add((side, 1, band))          # the slot's inner neighbour must stay free
            if ci != 0 and not (k and slot == ("L", 1, 0)):
                return None
        while todo:
            r = todo.pop(0)
            for c in cols:
                b = height.get(c, 0)
                pos = (c[0], c[1], b)
                if b >= limit[c] or pos in blocked or pos == slot:
                    continue
                if c[1] == 1 and height.get((c[0], 0), 0) <= b:
                    continue                      # inner column only next to a filled outer band
                if slot and slot[0] == c[0] and slot[1] == c[1] and b == slot[2]:
                    continue
                placed[pos] = r
                height[c] = b + 1
                break
            else:
                return None
        if slot and not (k and slot == ("L", 1, 0)):
            if height.get((slot[0], 0), 0) != slot[2] or slot[2] >= limit[(slot[0], 0)]:
                return None                       # the slot must sit directly under filled bands
        return placed, slot

    if plan.goal == "form_win":
        opts = [("R", 0, b) for b in range(bands)] + (
            [] if (k or plan.swap) else [("L", 0, b) for b in range(1, left_bands)])
        rng.shuffle(opts)
    else:
        opts = [None]
    result = None
    for o in opts:
        result = allocate(o)
        if result:
            break
    if not result:
        raise PlanError("the protected rules and the WIN slot do not fit on the rails",
                        suggestions=["increase the height", "request fewer mechanics"])
    placed, slot = result
    keys = list(placed) + ([slot] if slot else [])
    lw = 2 if (k or any(o[0] == "L" and o[1] == 1 for o in keys)) else 1
    rw = max([o[1] + 1 for o in keys if o[0] == "R"] + [0])
    if k and plan.zone_widths[0] < 2:
        plan.zone_widths[0] = 2

    # A sink gate is as thick as the number of things that could be drowned in it besides
    # a pushable object, plus one: every loose rule word is also a sink key (probe sink_text),
    # so this is what keeps "push an object" necessary.
    for g in plan.gates:
        g["thick"] = 1 + (k if g["kind"] == "sink" else 0)
    W = lw + sum(plan.zone_widths) + sum(g["thick"] for g in plan.gates) + rw
    lv = A.Level(W, H)
    reserved = set()

    def col_of(o):
        return o[1] if o[0] == "L" else W - 1 - o[1]

    for o, r in placed.items():
        if r:
            for j, word in enumerate(r):
                lv.put(col_of(o), 3 * o[2] + j, word)

    # ---- zones and gate columns -------------------------------------------
    zones, x = [], lw
    for i, zw in enumerate(plan.zone_widths):
        zones.append(list(range(x, x + zw)))
        x += zw
        if i < len(plan.gates):
            plan.gates[i]["x"] = x
            for _ in range(plan.gates[i]["thick"]):
                for y in range(H):
                    lv.put(x, y, "ICON_" + plan.gates[i]["noun"])
                x += 1
    last = len(zones) - 1

    for i, g in enumerate(anchors):
        row = 3 + i
        lv.put(0, row, g["noun"])
        lv.put(1, row, "IS")
        lv.put(2, row, g["kind"].upper())
        reserved.update({(2, row - 1), (2, row + 1), (3, row)})

    def cells(zone, interior=False):
        return [(cx, cy) for cx in zones[zone] for cy in range(H)
                if not (interior and cy in (0, H - 1))
                and lv.free(cx, cy) and (cx, cy) not in reserved]

    def pick(zone, interior=False, avoid_cols=()):
        c = [p for p in cells(zone, interior) if p[0] not in avoid_cols]
        if not c:
            raise PlanError(f"zone {zone} is too small for everything that must be placed in it",
                            suggestions=["increase the level size", "request fewer elements"])
        return rng.choice(c)

    # ---- goal --------------------------------------------------------------
    if plan.swap:
        # 'P IS YOU' lies in zone 0 with the other noun parked right above P.
        zx = zones[0]
        opts = [(cx, cy) for cx in zx[:len(zx) - 2] for cy in range(2, H - 1)
                if all(lv.free(cx + j, cy) for j in range(3)) and lv.free(cx, cy - 1) and lv.free(cx, cy - 2)
                and lv.free(cx, cy + 1)]
        if not opts:
            raise PlanError("zone 0 is too small for the 'IS YOU' rule", suggestions=["increase the level size"])
        cx, cy = rng.choice(opts)
        for j, word in enumerate((plan.player, "IS", "YOU")):
            lv.put(cx + j, cy, word)
        lv.put(cx, cy - 1, plan.other)
        reserved.update({(cx, cy + 1), (cx + 1, cy - 1), (cx + 2, cy - 1)})
        px, py = (cx, cy - 2) if rng.random() < 0.4 else pick(0)
        lv.put(px, py, "ICON_" + plan.player)
        reserved.add((cx, cy - 2))
        ox, oy = pick(last if plan.other_zone < 0 else min(plan.other_zone, last))
        lv.put(ox, oy, "ICON_" + plan.other)
    else:
        px, py = pick(0)
        lv.put(px, py, "ICON_" + plan.player)
    reserved.add((px, py))

    gx, gy = pick(last)
    lv.put(gx, gy, "ICON_" + plan.goal_noun)
    reserved.add((gx, gy))

    if plan.goal == "form_win":
        rx, ry = col_of(slot), 3 * slot[2]
        lv.put(rx, ry, plan.goal_noun)
        lv.put(rx, ry + 1, "IS")
        inward = 1 if slot[0] == "L" else -1
        reserved.update({(rx, ry + 2), (rx + inward, ry + 2), (rx + 2 * inward, ry + 2)})
        wz = 0 if slot[0] == "L" else last
        far = zones[wz][-1] if slot[0] == "L" else zones[wz][0]   # needs standing room behind it
        cand = [p for p in cells(wz, interior=True) if abs(p[0] - rx) >= 2
                and (p[0] != far or len(zones[wz]) < 3)] or cells(wz, interior=True)
        if not cand:
            raise PlanError("no interior cell left for the loose WIN word",
                            suggestions=["increase the level size"])
        wx, wy = rng.choice(cand)
        lv.put(wx, wy, "WIN")
        reserved.update({(wx - 1, wy), (wx + 1, wy), (wx, wy - 1), (wx, wy + 1)})

    # ---- sink keys ---------------------------------------------------------
    for g in plan.gates:
        if g["kind"] == "sink":
            kz = g["key_zone"]
            # scarce: one pushable only, so every loose rule word must be sacrificed as well
            for _ in range(1 if plan.scarce else max(plan.rocks, g["thick"])):
                rx_, ry_ = pick(kz, interior=True, avoid_cols=(zones[kz][0],) if len(zones[kz]) > 2 else ())
                lv.put(rx_, ry_, "ICON_" + plan.push_noun)

    # ---- pillars: immovable blocks that turn open floor into a pushing puzzle ----
    for _ in range(plan.pillars):
        try:
            bx, by = pick(rng.randrange(len(zones)))
        except PlanError:
            continue
        lv.put(bx, by, "ICON_" + plan.pillar_noun)

    # ---- decoys ------------------------------------------------------------
    for _ in range(plan.decoys):
        try:
            dx, dy = pick(rng.randrange(len(zones)), interior=True)
        except PlanError:
            continue
        lv.put(dx, dy, "ICON_TILE")

    lv.meta = {"plan": plan.describe(),
               "protected_rules": [" ".join(r) for r in placed.values() if r],
               "breakable_rules": [f"{g['noun']} IS {g['kind'].upper()}" for g in anchors],
               "notes": plan.notes}
    return lv


def transpose(level: A.Level) -> A.Level:
    """Swap x and y: horizontal rules become vertical (still read in the
    engine's reading order) and vice versa."""
    out = A.Level(level.height, level.width, meta=dict(level.meta))
    for (x, y), st in level.cells.items():
        for n in st:
            out.put(y, x, n)
    return out
