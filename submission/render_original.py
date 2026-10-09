#!/usr/bin/env python3
"""Draws generated levels with the two games' own artwork (sprites shipped in their repositories)."""
import json
from pathlib import Path
from PIL import Image
R = Path(__file__).resolve().parent.parent
D = json.loads((R / "docs" / "data.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
SP = R / "game_src" / "Extensions" / "BabaGUI" / "sprites"
SK = R / "games" / "sokoban_sg" / "img"

def baba(run, frame, out, scale=3):
    g = D["gallery"][run]; f = g["frames"][min(frame, len(g["frames"]) - 1)]
    im = Image.new("RGBA", (g["width"] * 24, g["height"] * 24), (8, 8, 8, 255))
    missing = set()
    for x, y, name in sorted((c[:3] for c in f["cells"]), key=lambda c: c[2] == "ICON_BABA"):
        p = SP / "icon" / (name[5:] + ".gif") if name.startswith("ICON_") else SP / "text" / (name + ".gif")
        if not p.exists():
            missing.add(name); continue
        s = Image.open(p).convert("RGBA"); im.alpha_composite(s, (x * 24, y * 24))
    im.resize((im.width * scale, im.height * scale), Image.NEAREST).convert("RGB").save(out)
    return missing

def soko(out, last=False):
    g = next(r for r in D["sokoban"]["runs"] if r.get("frames") and r["spec"]["difficulty"] == "hard")
    f = g["frames"][-1 if last else 0]
    t = {k: Image.open(SK / v).convert("RGBA").resize((64, 64)) for k, v in
         {"floor": "floor.png", "ICON_WALL": "obs.png", "ICON_BOX": "box.png", "ICON_GOAL": "goal.png", "ICON_PLAYER": "playerD.png", "boxg": "boxg.png"}.items()}
    im = Image.new("RGBA", (g["width"] * 64, g["height"] * 64))
    for y in range(g["height"]):
        for x in range(g["width"]): im.alpha_composite(t["floor"], (x * 64, y * 64))
    goals = {(c[0], c[1]) for c in f["cells"] if c[2] == "ICON_GOAL"}
    order = {"ICON_GOAL": 0, "ICON_WALL": 1, "ICON_BOX": 2, "ICON_PLAYER": 3}
    for x, y, name in sorted((c[:3] for c in f["cells"]), key=lambda c: order[c[2]]):
        s = t["boxg"] if name == "ICON_BOX" and (x, y) in goals else t[name]
        im.alpha_composite(s, (x * 64, y * 64))
    im.convert("RGB").save(out)

O = R / "submission" / "img"
for i, g in enumerate(D["gallery"]):
    if g.get("frames"):
        print(i, baba(i, 0, O / f"baba_{i}_start.png"), g["width"], g["height"])
        baba(i, 999, O / f"baba_{i}_end.png")
soko(O / "sokoban_start.png"); soko(O / "sokoban_end.png", True)
