#!/usr/bin/env python3
"""Keyboard player for generated Sokoban levels, drawn with the Sokoban game's own images.
   python3 forge/play_sokoban.py LEVEL.txt [SOLUTION]
Arrows/WASD move, Z undo, R restart, P plays the verified solution, F fullscreen, Esc quits.
Moves use the blueprint's model of the engine (compared with the original engine move by move in the tests)."""
import os
import sys
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import importlib.util  # noqa: E402
import pygame  # noqa: E402

spec = importlib.util.spec_from_file_location("sok_adapter", ROOT / "blueprints" / "sokoban_sg" / "adapter.py")
A = importlib.util.module_from_spec(spec); sys.modules["sok_adapter"] = A; spec.loader.exec_module(A)
IMG = ROOT / "games" / "sokoban_sg" / "img"
KEYS = {pygame.K_UP: "U", pygame.K_w: "U", pygame.K_DOWN: "D", pygame.K_s: "D",
        pygame.K_LEFT: "L", pygame.K_a: "L", pygame.K_RIGHT: "R", pygame.K_d: "R"}


def main():
    level = Path(sys.argv[1]); solution = sys.argv[2] if len(sys.argv) > 2 else ""
    w, h, walls, goals, boxes, player = A.parse(level.read_text())
    start = (player, boxes)
    pygame.init()
    info = pygame.display.Info()
    cell = max(32, min(96, int(info.current_w * 0.8) // w, int(info.current_h * 0.75) // h))
    HUD = 64
    screen = pygame.display.set_mode((cell * w, cell * h + HUD), pygame.RESIZABLE)
    pygame.display.set_caption(f"Level-Forge - Sokoban - {level.name}")
    raw = {k: pygame.image.load(str(IMG / f)).convert_alpha() for k, f in
           {"floor": "floor.png", "wall": "obs.png", "box": "box.png", "boxg": "boxg.png", "goal": "goal.png",
            "U": "playerU.png", "D": "playerD.png", "L": "playerL.png", "R": "playerR.png"}.items()}
    font = pygame.font.SysFont(None, 26)
    state, hist, facing, auto, full = start, [], "D", [], False
    clock = pygame.time.Clock()
    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                return
            if ev.type == pygame.KEYDOWN:
                if ev.key in KEYS and not auto:
                    facing = KEYS[ev.key]
                    new, _ = A.model_step(w, h, walls, state, facing)
                    if new != state:
                        hist.append(state); state = new
                elif ev.key == pygame.K_z and hist:
                    state = hist.pop()
                elif ev.key == pygame.K_r:
                    state, hist, auto = start, [], []
                elif ev.key == pygame.K_p and solution:
                    state, hist, auto = start, [], list(solution)
                elif ev.key == pygame.K_f:
                    full = not full
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN) if full else \
                        pygame.display.set_mode((cell * w, cell * h + HUD), pygame.RESIZABLE)
        if auto:
            facing = auto.pop(0)
            state, _ = A.model_step(w, h, walls, state, facing)
            pygame.time.wait(140)
        sw, sh = screen.get_size()
        c = max(16, min(sw // w, (sh - HUD) // h))
        ox, oy = (sw - c * w) // 2, (sh - HUD - c * h) // 2
        t = {k: pygame.transform.smoothscale(v, (c, c)) for k, v in raw.items()}
        screen.fill((18, 20, 28))
        pl, bx = state
        for i in range(w * h):
            x, y = ox + (i % w) * c, oy + (i // w) * c
            screen.blit(t["floor"], (x, y))
            if i in walls: screen.blit(t["wall"], (x, y))
            if i in goals: screen.blit(t["goal"], (x, y))
            if i in bx: screen.blit(t["boxg" if i in goals else "box"], (x, y))
            if i == pl: screen.blit(t[facing], (x, y))
        won = bx <= goals
        msg = "SOLVED!   R restart" if won else f"moves {len(hist)}   boxes on goals {len(bx & goals)}/{len(bx)}   arrows move · Z undo · R restart" + (" · P play solution" if solution else "") + " · F fullscreen"
        screen.blit(font.render(msg, True, (87, 199, 133) if won else (220, 224, 235)), (14, sh - HUD + 20))
        pygame.display.flip()
        clock.tick(60)


if __name__ == "__main__":
    main()
