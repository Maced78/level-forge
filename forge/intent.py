"""Stage A - natural-language request -> structured design spec.

Two interchangeable front ends produce the same JSON spec:

  * parse_request()   deterministic, keyword driven, no network.  Its
                      vocabulary comes from the blueprint (game_spec.json:
                      skills[].keywords, entities, support status), so it is
                      not hard-coded to one game.
  * llm.parse_request_llm()  the same contract, filled in by an LLM when an
                      API key is configured (see forge/llm.py).

Everything downstream (contradiction check, planning, verification) consumes
only the spec, never the raw text.
"""
from __future__ import annotations

import re

NEG = r"(?:no|not|without|never|avoid|avoids|avoiding|don't|do not|dont|exclude|excludes|excluding|forbid|forbids|free of|must not|shouldn't|should not)"

DIFFICULTY = {
    "easy": ["easy", "simple", "beginner", "tutorial", "teach", "teaches", "introduc", "gentle", "first level"],
    "hard": ["hard", "difficult", "challenging", "expert", "tricky", "brutal", "tough", "advanced", "fiendish"],
    "medium": ["medium", "moderate", "intermediate", "normal"],
}

# Ideas people ask for that are not in this game at all.
FOREIGN = {
    "teleport": "TELE", "portal": "TELE", "pull": "PULL", "magnet": "PULL", "gravity": "FALL", "fall": "FALL",
    "conveyor": "SHIFT", "belt": "SHIFT", "swap": "SWAP", "sleep": "SLEEP", "timer": None, "laser": None,
    "enemy ai": None, "jump": None, "ice": None, "slide": None, "sliding": None, "bomb": None,
    "switch": None, "button": None, "pressure plate": None,
}


def _has(text, phrase):
    return re.search(r"(?<![a-z])" + re.escape(phrase) + r"(?:s|es)?(?![a-z])", text) is not None


def _negated(text, phrase):
    """True if `phrase` occurs inside a negated clause ("no X", "without any X or Y")."""
    for m in re.finditer(r"(?<![a-z])" + re.escape(phrase) + r"(?:s|es)?(?![a-z])", text):
        clause = re.split(r"[.;:!?]| but | and (?:it|the level|make|must|should|use|require|test|include|with a)",
                          text[:m.start()])[-1]
        if re.search(r"(?<![a-z])" + NEG + r"(?![a-z])", clause[-70:]):
            return True
    return False


def parse_request(request: str, spec: dict) -> dict:
    text = " " + request.lower().replace("’", "'") + " "
    text_q = re.sub(r"[\"“”']", "", text)
    out = {"raw": request, "difficulty": None, "skills_required": [], "skills_forbidden": [],
           "unsupported_requested": [], "foreign_requested": [], "outside_vocabulary": [],
           "dependencies": [], "defaults_applied": [], "constraints": {}}

    for level in ("hard", "easy", "medium"):
        if any(_has(text, w) or (w.endswith("c") and w in text) for w in DIFFICULTY[level]):
            out["difficulty"] = level
            break
    if out["difficulty"] is None:
        out["difficulty"] = "medium"
        out["defaults_applied"].append("difficulty=medium (not specified)")

    # skills, by blueprint keywords; longest keyword first so 'win condition' beats 'rule'
    for sk in spec["skills"]:
        hits = [k for k in sorted(sk["keywords"], key=len, reverse=True) if _has(text_q, k)]
        if not hits:
            continue
        neg = [_negated(text_q, k) for k in hits]
        if all(neg):
            out["skills_forbidden"].append(sk["id"])
        elif any(neg) and len(hits) > 1:      # asked for and ruled out in the same request
            out["skills_required"].append(sk["id"])
            out["skills_forbidden"].append(sk["id"])
        else:
            out["skills_required"].append(sk["id"])

    # mechanics the engine does not implement / the game does not have
    words = {e["name"]: e for e in spec["entities"] if e["kind"] in ("property", "operator", "noun")}
    for name, e in words.items():
        if e.get("support") == "unsupported" and (_has(text, name.lower() + " rule") or
                                                  re.search(r"\b" + name + r"\b", request)):
            if not _negated(text, name.lower()):
                out["unsupported_requested"].append(name)
    for phrase, token in FOREIGN.items():
        m = re.search(r"(?<![a-z])" + re.escape(phrase) + r"[a-z]*", text)
        if m and not _negated(text, m.group(0)):
            if token and words.get(token, {}).get("support") == "unsupported":
                if token not in out["unsupported_requested"]:
                    out["unsupported_requested"].append(token)
            elif token is None or token not in words:      # not a mechanic of this game at all
                out["foreign_requested"].append(phrase)
    gen = set(spec["generation_vocabulary"]["text"])
    for name, e in words.items():
        if e["kind"] == "property" and e.get("support") in ("implemented", "partial") and name not in gen:
            if re.search(r"\b" + name + r"\b", request) or _has(text, "is " + name.lower()):
                out["outside_vocabulary"].append(name)

    # numeric / structural constraints
    c = out["constraints"]
    m = re.search(r"(?:at most|no more than|within|under|max(?:imum)?(?: of)?|in)\s+(\d+)\s+moves", text)
    if m:
        c["max_moves"] = int(m.group(1))
    m = re.search(r"(?:at least|no fewer than|min(?:imum)?(?: of)?|more than)\s+(\d+)\s+moves", text)
    if m:
        c["min_moves"] = int(m.group(1))
    m = re.search(r"(\d+)\s*(?:x|by|×)\s*(\d+)", text)
    if m:
        c["width"], c["height"] = int(m.group(1)), int(m.group(2))
    if re.search(r"unique (?:solution|path)|single solution|only one solution|exactly one solution", text):
        c["unique_solution"] = True
    if re.search(r"(?:no|without|avoid|free of)[a-z ]{0,25}(?:dead ?locks?|soft ?locks?|unwinnable|dead ends?|irreversible)", text):
        c["no_dead_states"] = True

    # explicit placement dependencies: "<key> ... behind / beyond / on the far side of ... <gate>"
    gate_words = {"sink": ["water", "lava", "river", "moat"], "stop": ["wall", "hedge", "walls"],
                  "defeat": ["skull", "skulls", "crab", "crabs"]}
    key_words = {"sink": ["rock", "rocks", "box", "boxes", "crate", "pushable", "boulder"],
                 "stop": ["stop rule", "is stop", "wall rule", "rule that makes"],
                 "defeat": ["defeat rule", "is defeat", "skull rule"]}
    behind = r"(?:behind|beyond|past|on the (?:far|other) side of|locked behind|across)"
    for kind in gate_words:
        for kw in key_words[kind]:
            for gw in gate_words[kind]:
                if re.search(re.escape(kw) + r"[a-z ,']{0,60}" + behind + r"[a-z ]{0,25}" + re.escape(gw), text_q):
                    dep = {"gate_kind": kind, "key": kw, "gate": gw,
                           "text": f"the {kw} is placed behind the {gw}"}
                    if dep not in out["dependencies"] and not any(d["gate_kind"] == kind for d in out["dependencies"]):
                        out["dependencies"].append(dep)
    for dep in out["dependencies"]:
        need = {"sink": "object_pushing", "stop": "rule_manipulation", "defeat": "hazard_defeat"}[dep["gate_kind"]]
        if need not in out["skills_required"]:
            out["skills_required"].append(need)
        if dep["gate_kind"] == "sink" and "hazard_sink" not in out["skills_required"]:
            out["skills_required"].append("hazard_sink")

    if not out["skills_required"]:
        out["defaults_applied"].append("no mechanic named: the planner picks mechanics that fit the difficulty")
    return out
