#!/usr/bin/env bash
# One command for the demo: build (first run only), check the blueprint, start the UI.
set -euo pipefail
cd "$(dirname "$0")"
[ -x engine_build/babasolve ] || ./build_engine.sh
python3 forge/agent1_blueprint.py --check || true
# The second game (Sokoban) needs pygame and numpy. Try to install them; the demo still starts without them.
python3 -c "import pygame, numpy" 2>/dev/null || python3 -m pip install --user -q pygame numpy 2>/dev/null \
  || python3 -m pip install --user -q --break-system-packages pygame numpy 2>/dev/null \
  || echo "Note: pygame/numpy not installed. Sokoban will use its tested model instead of the original engine."
echo
echo "Open http://localhost:${PORT:-8765}   (Ctrl+C to stop)"
exec python3 forge/server.py --port "${PORT:-8765}"
