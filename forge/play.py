#!/usr/bin/env python3
"""Play a level in the ORIGINAL engine, in a resizable window.

    python3 forge/play.py LEVEL.txt [SOLUTION]

Every move goes through pyBaba.Game.MovePlayer - the game's own engine. The
game's bundled GUI (game_src/Extensions/BabaGUI/main.py) opens a fixed
24-pixel-per-cell window, only replays a scripted action file and has no
sprite for several objects, so this player replaces it; it uses the game's
sprites where they exist and a labelled tile where they do not.

    arrows / WASD  move        Z  undo        R  restart
    P  play the verified solution (if one was passed)
    F  fullscreen              Esc  quit
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "engine_build"))
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402
import pyBaba  # noqa: E402

SPRITES = ROOT / "game_src" / "Extensions" / "BabaGUI" / "sprites"
T = pyBaba.ObjectType
DIRS = {"U": pyBaba.Direction.UP, "D": pyBaba.Direction.DOWN, "L": pyBaba.Direction.LEFT,
        "R": pyBaba.Direction.RIGHT}
KEYS = {pygame.K_UP: "U", pygame.K_w: "U", pygame.K_DOWN: "D", pygame.K_s: "D",
        pygame.K_LEFT: "L", pygame.K_a: "L", pygame.K_RIGHT: "R", pygame.K_d: "R"}
COLORS = {"BABA": (244, 244, 248), "KEKE": (240, 138, 93), "ROCK": (200, 164, 106), "BOX": (201, 139, 78),
          "WALL": (124, 132, 156), "HEDGE": (79, 157, 105), "FLAG": (242, 193, 78), "STAR": (247, 226, 107),
          "LOVE": (239, 111, 156), "KEY": (242, 166, 90), "WATER": (74, 144, 226), "LAVA": (255, 107, 53),
          "SKULL": (192, 57, 43), "CRAB": (226, 92, 92), "TILE": (57, 64, 90), "IS": (231, 233, 239),
          "YOU": (229, 96, 156), "WIN": (242, 193, 78), "STOP": (79, 157, 105), "PUSH": (200, 164, 106),
          "SINK": (74, 144, 226), "DEFEAT": (192, 57, 43)}
HUD = 34


class Player:
    def __init__(self, level, solution=""):
        self.level, self.solution = level, solution
        self.game = pyBaba.Game(level)
        self.moves = ""
        m = self.game.GetMap()
        self.w, self.h = m.GetWidth(), m.GetHeight()
        info = pygame.display.Info()
        cell = max(24, min(72, (info.current_w - 80) // self.w, (info.current_h - 160 - HUD) // self.h))
        self.screen = pygame.display.set_mode((cell * self.w, cell * self.h + HUD), pygame.RESIZABLE)
        pygame.display.set_caption(f"Level-Forge - {Path(level).name} (original baba-is-auto engine)")
        self.cache, self.fullscreen, self.auto = {}, False, None

    # -- drawing ----------------------------------------------------------
    def cell(self):
        sw, sh = self.screen.get_size()
        return max(8, min(sw // self.w, (sh - HUD) // self.h))

    def sprite(self, obj_type, cell):
        key = (obj_type, cell)
        if key in self.cache:
            return self.cache[key]
        name = obj_type.name
        is_icon = name.startswith("ICON_")
        base = name[5:] if is_icon else name
        path = SPRITES / ("icon" if is_icon else "text") / f"{base}.gif"
        surf = pygame.Surface((cell, cell), pygame.SRCALPHA)
        if path.exists():
            surf = pygame.transform.scale(pygame.image.load(str(path)).convert_alpha(), (cell, cell))
        else:
            col = COLORS.get(base, (154, 163, 184))
            pad = max(2, cell // 10)
            rect = pygame.Rect(pad, pad, cell - 2 * pad, cell - 2 * pad)
            if is_icon:
                pygame.draw.rect(surf, col, rect, border_radius=cell // 6)
                ink = (10, 11, 16)
            else:
                pygame.draw.rect(surf, (18, 20, 28), rect, border_radius=cell // 8)
                pygame.draw.rect(surf, col, rect, width=max(1, cell // 24), border_radius=cell // 8)
                ink = col
            label = base.lower() if is_icon else base
            font = pygame.font.SysFont("dejavusansmono,menlo,consolas,monospace",
                                       max(8, int(cell * (0.30 if len(label) <= 4 else 0.22))), bold=True)
            txt = font.render(label, True, ink)
            surf.blit(txt, txt.get_rect(center=(cell // 2, cell // 2)))
        self.cache[key] = surf
        return surf

    def draw(self):
        cell = self.cell()
        sw, sh = self.screen.get_size()
        ox, oy = (sw - cell * self.w) // 2, (sh - HUD - cell * self.h) // 2
        self.screen.fill((10, 11, 16))
        m = self.game.GetMap()
        for y in range(self.h):
            for x in range(self.w):
                pygame.draw.rect(self.screen, (24, 27, 38), (ox + x * cell, oy + y * cell, cell, cell), 1)
                inst = [i for i in m.At(x, y).GetInstances() if i.type != T.ICON_EMPTY]
                # objects first, then text, so words stay readable on top of scenery
                for i in sorted(inst, key=lambda i: pyBaba.IsTextType(i.type)):
                    self.screen.blit(self.sprite(i.type, cell), (ox + x * cell, oy + y * cell))
        state = self.game.GetPlayState()
        font = pygame.font.SysFont("dejavusansmono,menlo,consolas,monospace", 15)
        if state == pyBaba.PlayState.WON:
            msg, col = f"WON in {len(self.moves)} moves   R restart   Esc quit", (143, 240, 184)
        elif state == pyBaba.PlayState.LOST:
            msg, col = "LOST - nothing is YOU   Z undo   R restart", (255, 177, 174)
        else:
            msg = f"moves {len(self.moves)}   arrows move   Z undo   R restart   F fullscreen"
            if self.solution:
                msg += f"   P play verified solution ({len(self.solution)})"
            col = (143, 150, 168)
        self.screen.blit(font.render(msg, True, col), (10, sh - HUD + 9))
        pygame.display.flip()

    # -- game -------------------------------------------------------------
    def over(self):
        return self.game.GetPlayState() in (pyBaba.PlayState.WON, pyBaba.PlayState.LOST)

    def move(self, m):
        if not self.over():
            self.game.MovePlayer(DIRS[m])
            self.moves += m

    def restart(self, moves=""):
        self.game = pyBaba.Game(self.level)     # fresh engine object, then replay
        self.moves = ""
        for m in moves:
            self.move(m)

    def run(self, max_frames=None):
        clock, frames = pygame.time.Clock(), 0
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type == pygame.KEYDOWN:
                    if e.key == pygame.K_ESCAPE:
                        return
                    if e.key in KEYS:
                        self.auto = None
                        self.move(KEYS[e.key])
                    elif e.key == pygame.K_z:
                        self.auto = None
                        self.restart(self.moves[:-1])
                    elif e.key == pygame.K_r:
                        self.auto = None
                        self.restart()
                    elif e.key == pygame.K_p and self.solution:
                        self.restart()
                        self.auto = 0
                    elif e.key == pygame.K_f:
                        self.fullscreen = not self.fullscreen
                        if self.fullscreen:
                            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                        else:
                            self.screen = pygame.display.set_mode((64 * self.w, 64 * self.h + HUD),
                                                                  pygame.RESIZABLE)
            if self.auto is not None and frames % 9 == 0:
                if self.auto < len(self.solution):
                    self.move(self.solution[self.auto])
                    self.auto += 1
                else:
                    self.auto = None
            self.draw()
            clock.tick(60)
            frames += 1
            if max_frames and frames >= max_frames:
                return


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    pygame.init()
    Player(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "").run()
    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
