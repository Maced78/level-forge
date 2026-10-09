"""LLM seat of the pipeline (Google Gemini, plain HTTPS, no SDK).

What the language model does here, and what it is never trusted with:

    request text ──► parse_request()   spec JSON      (validated against the blueprint)
    spec + skill.md ► propose_levels()  candidate layouts (each one goes through the
                                        validator, the solver and the engine replay)
    verifier report ► repair_level()    a corrected layout, given the exact failure reasons
    verified facts ─► describe_level()  title, designer note, player hint

The model proposes; the symbolic side disposes.  Nothing the model returns is
accepted without a machine check, and a level is never labelled solvable
because a model said so.

Key:   GEMINI_API_KEY (or FORGE_GEMINI_KEY) in the environment or in ./.env
Model: FORGE_MODEL, else the newest "flash" model the key can call (discovered
       through ListModels, so no model name is hard-coded).

Every call is cached in out/llm_cache.json (key = hash of model-independent
prompt).  With no key, cached answers are replayed and marked as such; with no
key and no cache entry the caller falls back to the deterministic parser and
planner, and the result says so.

    python3 -m forge.llm --selftest
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = Path(__file__).resolve().parent / "prompts"
CACHE_PATH = ROOT / "out" / "llm_cache.json"
API = os.environ.get("FORGE_GEMINI_BASE", "https://generativelanguage.googleapis.com/v1beta")
MIN_INTERVAL = float(os.environ.get("FORGE_LLM_MIN_INTERVAL", "0"))   # seconds between calls (rate limits)

_state = {"model": None, "last_call": 0.0, "cache": None, "log": [], "provider": None}


# --------------------------------------------------------------------------
# plumbing
# --------------------------------------------------------------------------
def api_key():
    for name in ("FORGE_GEMINI_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        if os.environ.get(name):
            return os.environ[name].strip()
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r"\s*(?:export\s+)?(FORGE_GEMINI_KEY|GEMINI_API_KEY|GOOGLE_API_KEY)\s*=\s*['\"]?([^'\"\s]+)", line)
            if m:
                return m.group(2)
    return None


def _cache():
    if _state["cache"] is None:
        try:
            _state["cache"] = json.loads(CACHE_PATH.read_text())
        except Exception:
            _state["cache"] = {}
    return _state["cache"]


def _save_cache():
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(_state["cache"], indent=0))


def mode():
    """'live' (key present), 'replay' (no key, cached answers exist) or 'off'."""
    if os.environ.get("FORGE_LLM", "").lower() in ("0", "off", "no") or _state.get("dead"):
        return "off"
    if api_key():
        return "live"
    # Without a key the system runs its built-in test version. Cached answers are replayed only on request.
    return "replay" if os.environ.get("FORGE_LLM", "").lower() == "replay" and _cache() else "off"


# Two Google endpoints accept API keys: AI Studio ("AIza..." keys) and Vertex AI express mode
# ("AQ...." keys).  The first one that accepts the key is remembered.
PROVIDERS = [
    {"name": "Google AI Studio", "list": API + "/models?pageSize=200", "gen": API + "/models/{model}:generateContent"},
    {"name": "Vertex AI (express mode)",
     "list": "https://aiplatform.googleapis.com/v1beta1/publishers/google/models?pageSize=200",
     "gen": "https://aiplatform.googleapis.com/v1/publishers/google/models/{model}:generateContent"},
]


def _providers():
    if _state.get("provider") is not None:
        return [PROVIDERS[_state["provider"]]]
    order = list(PROVIDERS)
    if (api_key() or "").startswith("AQ."):
        order.reverse()
    return order


def _http(url, body=None, timeout=90):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "x-goog-api-key": api_key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _generate(model, body):
    """POST to the first provider that accepts the key."""
    last = None
    for prov in _providers():
        try:
            data = _http(prov["gen"].format(model=model), body)
            _state["provider"] = PROVIDERS.index(prov)
            return data
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            key_problem = e.code in (400, 401, 403) and any(x in detail for x in (
                "API_KEY_INVALID", "API key not valid", "PERMISSION_DENIED", "UNAUTHENTICATED", "API_KEY_SERVICE_BLOCKED"))
            if key_problem and _state.get("provider") is None:
                last = urllib.error.HTTPError(e.url, e.code, f"{prov['name']}: {detail}", e.headers, None)
                last.detail = f"{prov['name']}: {detail}"
                continue
            e.detail = detail
            raise
    raise last


def pick_model():
    if _state["model"]:
        return _state["model"]
    if os.environ.get("FORGE_MODEL"):
        _state["model"] = os.environ["FORGE_MODEL"]
        return _state["model"]
    names = []
    for prov in _providers():
        try:
            data = _http(prov["list"], timeout=30)
            for m in data.get("models", data.get("publisherModels", [])):
                if "supportedGenerationMethods" not in m or "generateContent" in m["supportedGenerationMethods"]:
                    names.append(m["name"].split("/")[-1])
            if names:
                break
        except Exception:
            continue
    names = [n for n in names if n.startswith("gemini")]

    def rank(n):
        bad = any(x in n for x in ("image", "tts", "live", "audio", "embedding", "vision", "thinking", "exp",
                                   "preview", "lite", "8b", "learnlm", "gemma", "robotics", "computer"))
        ver = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return ("flash" in n and not bad, "flash" in n, float(ver.group(1)) if ver else 0.0, -len(n))

    names.sort(key=rank, reverse=True)
    _state["model"] = names[0] if names else "gemini-2.5-flash"
    return _state["model"]


def call(system: str, user: str, tag: str = "", max_tokens: int = 8192, temperature: float = 0.4):
    """One JSON-mode completion.  Returns (parsed_json, meta)."""
    key = hashlib.sha256((system + "\n\x00\n" + user).encode()).hexdigest()[:24]
    cache = _cache()
    live = (api_key() is not None and os.environ.get("FORGE_LLM", "").lower() not in ("0", "off", "no")
            and not _state.get("dead"))
    if key in cache and (not live or os.environ.get("FORGE_LLM_CACHE", "1") != "0"):
        ent = cache[key]
        meta = dict(ent["meta"], cached=True, replayed=not live, tag=tag)
        _state["log"].append(meta)
        return ent["json"], meta
    if not live:
        raise RuntimeError("no LLM key configured and no cached answer for this prompt")
    model = pick_model()
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens,
                                 "responseMimeType": "application/json"}}
    last = None
    for attempt in range(6):
        wait = MIN_INTERVAL - (time.time() - _state["last_call"])
        if wait > 0:
            time.sleep(wait)
        t0 = time.time()
        _state["last_call"] = t0
        try:
            data = _generate(model, body)
            text = "".join(p.get("text", "") for p in data["candidates"][0]["content"].get("parts", []))
            parsed = _loads(text)
            usage = data.get("usageMetadata", {})
            meta = {"model": model, "seconds": round(time.time() - t0, 2), "tag": tag,
                    "prompt_tokens": usage.get("promptTokenCount"),
                    "output_tokens": usage.get("candidatesTokenCount"),
                    "total_tokens": usage.get("totalTokenCount"), "cached": False, "replayed": False}
            cache[key] = {"json": parsed, "meta": {k: meta[k] for k in ("model", "seconds", "prompt_tokens",
                                                                        "output_tokens", "total_tokens")}}
            _save_cache()
            _state["log"].append(meta)
            return parsed, meta
        except urllib.error.HTTPError as e:
            detail = getattr(e, "detail", None) or e.read().decode(errors="replace")[:600]
            last = f"HTTP {e.code}: {detail}"
            if e.code in (429, 500, 502, 503, 504):
                m = re.search(r'"retryDelay":\s*"(\d+)', detail)
                time.sleep(min(70, int(m.group(1)) + 2) if m else 8 * (attempt + 1))
                continue
            if e.code == 404 and attempt == 0:      # model name not available to this key
                _state["model"] = None
                os.environ.pop("FORGE_MODEL", None)
                model = pick_model()
                continue
            if e.code in (400, 401, 403):   # key rejected: stop calling for the rest of this run
                _state["dead"] = "the API key was rejected by Google"
            break
        except (KeyError, IndexError, ValueError) as e:   # empty or malformed answer: one retry
            last = f"malformed answer: {type(e).__name__}: {e}"
            continue
        except Exception as e:                            # network: do not keep the user waiting
            last = f"{type(e).__name__}: {e}"
            _state["dead"] = "Google could not be reached"
            break
    raise RuntimeError(f"LLM call failed ({tag}): {last}")


def status():
    """What the UI shows: is the language model in use, and if not, why."""
    if os.environ.get("FORGE_LLM", "").lower() in ("0", "off", "no"):
        return {"mode": "off", "reason": "switched off"}
    if _state.get("dead"):
        return {"mode": "off", "reason": _state["dead"]}
    if not api_key():
        return {"mode": "off", "reason": "no API key is set up"}
    return {"mode": "live", "reason": ""}


def _loads(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?|```$", "", text.strip()).strip()
    try:
        return json.loads(text)
    except ValueError:
        a, b = text.find("{"), text.rfind("}")
        return json.loads(text[a:b + 1])


def take_log():
    log, _state["log"] = _state["log"], []
    return log


def usage_summary(log):
    return {"calls": len(log), "live_calls": sum(1 for m in log if not m.get("cached")),
            "models": sorted({m["model"] for m in log if m.get("model")}),
            "seconds": round(sum(m.get("seconds") or 0 for m in log if not m.get("cached")), 2),
            "prompt_tokens": sum(m.get("prompt_tokens") or 0 for m in log),
            "output_tokens": sum(m.get("output_tokens") or 0 for m in log),
            "total_tokens": sum(m.get("total_tokens") or 0 for m in log),
            "replayed_from_cache": any(m.get("replayed") for m in log),
            "by_step": [{k: m.get(k) for k in ("tag", "model", "seconds", "total_tokens", "cached")} for m in log]}


# --------------------------------------------------------------------------
# the four seats
# --------------------------------------------------------------------------
def parse_request(request: str, spec: dict) -> dict:
    """Stage A with a language model.  Output is validated field by field
    against the blueprint; anything the blueprint does not know is dropped."""
    skills = [{k: s[k] for k in ("id", "label", "definition")} for s in spec["skills"]]
    unsupported = sorted(e["name"] for e in spec["entities"] if e.get("support") == "unsupported")
    outside = sorted(e["name"] for e in spec["entities"] if e["kind"] == "property"
                     and e.get("support") in ("implemented", "partial")
                     and e["name"] not in spec["generation_vocabulary"]["text"])
    system = (PROMPTS / "agent2_intent.md").read_text()
    user = (f"GAME: {spec['game']['name']} - {spec['game']['description']}\n"
            f"SKILLS (the only ids you may use): {json.dumps(skills)}\n"
            f"WORDS THAT EXIST BUT DO NOTHING IN THIS ENGINE: {unsupported}\n"
            f"WORDS IMPLEMENTED BUT NOT YET VERIFIED BY THE BLUEPRINT: {outside}\n"
            f"GATE KINDS: sink (water/lava column, key = push a rock/box in), stop (wall/hedge column, "
            f"key = break its IS STOP rule), defeat (skull/crab column, key = break its IS DEFEAT rule)\n"
            f"REQUEST: {request}")
    out, meta = call(system, user, tag="intent")
    ids = {s["id"] for s in spec["skills"]}
    words = {e["name"]: e for e in spec["entities"]}
    clean = {"raw": request, "difficulty": out.get("difficulty") if out.get("difficulty") in ("easy", "medium", "hard")
             else "medium",
             "skills_required": [s for s in out.get("skills_required", []) if s in ids],
             "skills_forbidden": [s for s in out.get("skills_forbidden", []) if s in ids],
             "unsupported_requested": [w for w in out.get("unsupported_requested", [])
                                       if words.get(w, {}).get("support") == "unsupported"],
             "foreign_requested": [str(x)[:60] for x in out.get("foreign_requested", [])][:6],
             "outside_vocabulary": [w for w in out.get("outside_vocabulary", []) if w in outside],
             "dependencies": [], "defaults_applied": [str(x)[:120] for x in out.get("defaults_applied", [])][:6],
             "constraints": {}, "summary": str(out.get("summary", ""))[:300]}
    for d in out.get("dependencies", []) or []:
        if isinstance(d, dict) and d.get("gate_kind") in ("sink", "stop", "defeat"):
            clean["dependencies"].append({"gate_kind": d["gate_kind"], "key": str(d.get("key", ""))[:40],
                                          "gate": str(d.get("gate", ""))[:40], "text": str(d.get("text", ""))[:160]})
    c = out.get("constraints") or {}
    for k in ("max_moves", "min_moves", "width", "height"):
        if isinstance(c.get(k), (int, float)) and c[k] > 0:
            clean["constraints"][k] = int(c[k])
    for k in ("unique_solution", "no_dead_states"):
        if c.get(k) is True:
            clean["constraints"][k] = True
    return clean, meta


def propose_levels(request: str, spec_json: dict, skill_md: str, n: int = 2):
    system = (PROMPTS / "agent2_propose.md").read_text() + "\n\n=== SKILL FILE ===\n" + skill_md
    user = (f"REQUEST: {request}\nPARSED SPEC: {json.dumps({k: spec_json[k] for k in ('difficulty', 'skills_required', 'skills_forbidden', 'constraints')})}\n"
            f"Return exactly {n} candidates.")
    out, meta = call(system, user, tag="propose", temperature=0.7)
    cands = []
    for c in (out.get("candidates") or [])[:n]:
        if isinstance(c, dict) and isinstance(c.get("dsl"), str):
            cands.append({"dsl": c["dsl"].replace("\\n", "\n"), "idea": str(c.get("idea", ""))[:300]})
    return cands, meta


def repair_level(request: str, dsl: str, reasons: list, initial_rules: list, skill_md: str):
    system = (PROMPTS / "agent2_repair.md").read_text() + "\n\n=== SKILL FILE ===\n" + skill_md
    user = (f"REQUEST: {request}\nYOUR LEVEL:\n{dsl}\n\nRULES THE ENGINE ACTUALLY PARSED AT LOAD: {initial_rules}\n"
            f"VERIFIER FINDINGS (machine-checked, not opinions):\n- " + "\n- ".join(reasons))
    out, meta = call(system, user, tag="repair", temperature=0.5)
    return {"dsl": str(out.get("dsl", "")).replace("\\n", "\n"), "idea": str(out.get("change", ""))[:300]}, meta


def describe_level(request: str, facts: dict):
    system = (PROMPTS / "agent2_describe.md").read_text()
    out, meta = call(system, "REQUEST: " + request + "\nVERIFIED FACTS (use only these):\n" + json.dumps(facts),
                     tag="describe", max_tokens=2048, temperature=0.8)
    return {"title": str(out.get("title", ""))[:60], "designer_note": str(out.get("designer_note", ""))[:500],
            "player_hint": str(out.get("player_hint", ""))[:240]}, meta


def selftest():
    print("mode:", mode())
    key = api_key() or ""
    if mode() != "live":
        print("No key found. Put GEMINI_API_KEY=... in", ROOT / ".env")
        return 1
    if "PASTE" in key or len(key) < 20:
        print("The key in .env is still the placeholder. Edit .env and put your real key after GEMINI_API_KEY=")
        return 1
    print(f"key: {key[:4]}... ({len(key)} characters)")
    try:
        out, meta = call("Answer in JSON.", 'Return {"ok": true, "word": "forge"} exactly. nonce ' + str(time.time()),
                         tag="selftest", max_tokens=512)
    except Exception as e:
        print("FAILED:", str(e)[:900])
        print("\nNeither Google AI Studio nor Vertex AI accepted this key. Create a key at "
              "https://aistudio.google.com/apikey (it starts with AIza), put it in .env and run this again.")
        return 1
    print("provider:", PROVIDERS[_state["provider"]]["name"], "| model:", meta["model"])
    print("answer:", out, "| seconds:", meta["seconds"], "| tokens:", meta["total_tokens"])
    print("SELFTEST OK" if out.get("ok") else "unexpected answer")
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(selftest() if "--selftest" in sys.argv else 0)
