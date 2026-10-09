"""Design spec -> plan, for Sokoban."""
from __future__ import annotations

import random
import re

from . import patterns as P

# difficulty -> (elements, band of adapter.difficulty score); length is not part of the score
BANDS = {"easy": (1, (0, 7)), "medium": (2, (5, 12)), "hard": (3, (11, 1000))}
WORDS = {"one": 1, "a": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _count(raw, noun):
    m = re.search(r"(\d+|one|two|three|four|five|single|a)\s+(?:\w+\s+)?" + noun, raw)
    if not m:
        return None
    return int(m.group(1)) if m.group(1).isdigit() else WORDS[m.group(1)]


def make_plan(spec, rng: random.Random, attempt=0) -> P.Plan:
    d = spec["difficulty"]
    raw = spec.get("raw", "").lower()
    boxes = {"easy": 1, "medium": 2, "hard": 3}[d]
    if "multi_box" in spec["skills_required"]:
        boxes = max(boxes, 2)
    asked_boxes, asked_goals = _count(raw, r"(?:box|boxes|crate|crates)"), _count(raw, r"(?:goal|goals|target|targets)")
    boxes = asked_boxes or boxes
    goals = asked_goals or boxes
    w, h = {"easy": (7, 6), "medium": (8, 7), "hard": (8, 7)}[d]
    plan = P.Plan(width=spec.get("width") or w, height=spec.get("height") or h, boxes=boxes, goals=goals,
                  walls=rng.randint(1, 3) if d == "easy" else rng.randint(3, 7))
    return plan
