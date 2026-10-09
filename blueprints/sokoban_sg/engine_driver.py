"""Runs INSIDE the original game's directory and drives its real engine headlessly.
    python3 engine_driver.py LEVEL.dat MOVES   ->  JSON frames on stdout
Uses only the game's own classes: src.game.Game, Player.update, Game.get_curr_state."""
import json, os, sys
os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
sys.path.insert(0, os.getcwd())
import contextlib, io
buf = io.StringIO()
try:
    import pygame, numpy  # noqa: F401,E401  the rules need these two
except Exception as e:
    print(json.dumps({"status": "engine_unavailable", "error": f"{type(e).__name__}: {e}"}))
    sys.exit(0)
try:
    import pygame_widgets  # noqa: F401  GUI buttons only; the rules never call it
except Exception:
    from unittest import mock
    for name in ("pygame_widgets", "pygame_widgets.button", "pygame_widgets.textbox", "pygame_widgets.toggle"):
        sys.modules[name] = mock.MagicMock()
try:
    with contextlib.redirect_stdout(buf):
        from src.game import Game
except Exception as e:      # the engine itself cannot start on this machine (not a problem with the level)
    print(json.dumps({"status": "engine_unavailable", "error": f"{type(e).__name__}: {e}"}))
    sys.exit(0)
try:
    with contextlib.redirect_stdout(buf):
        game = Game(path=sys.argv[1])
    if game.player is None or game.puzzle_size is None:
        raise ValueError("engine did not load the level: " + buf.getvalue().strip()[:200])
    h, w = game.puzzle_size
    frames = [{"cells": game.get_curr_state(), "solved": bool(game.is_level_complete())}]
    for m in (sys.argv[2] if len(sys.argv) > 2 else ""):
        moved = game.player.update(key=m)
        frames.append({"cells": game.get_curr_state(), "solved": bool(game.is_level_complete()), "moved": moved})
    print(json.dumps({"status": "ok", "width": w, "height": h, "frames": frames}))
except Exception as e:
    print(json.dumps({"status": "load_error", "error": f"{type(e).__name__}: {e}"}))
