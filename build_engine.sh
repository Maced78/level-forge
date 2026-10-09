#!/usr/bin/env bash
# Builds the ORIGINAL game engine (baba-is-auto, MIT, unmodified sources in game_src/)
#   engine_build/pyBaba*.so  - the engine's own Python binding (used for replay/validation)
#   engine_build/babasolve   - exhaustive solver whose transition function IS the engine
# Needs only: g++ (C++17), python3 + headers (python3-dev), pip. No CMake required.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
$PY -c "import pybind11" 2>/dev/null || $PY -m pip install -q pybind11 2>/dev/null || $PY -m pip install -q --break-system-packages pybind11
INC=$($PY -c "import sysconfig,pybind11;print('-I'+sysconfig.get_paths()['include'],'-I'+pybind11.get_include())")
SUF=$($PY -c "import sysconfig;print(sysconfig.get_config_var('EXT_SUFFIX'))")
mkdir -p engine_build/obj
FLAGS="-O3 -std=c++17 -fPIC -Igame_src/Includes"
echo "[1/3] compiling engine core (unmodified game_src/Sources)"
pids=()
for f in game_src/Sources/baba-is-auto/*/*.cpp; do
  o=engine_build/obj/core_$(basename "$f" .cpp).o
  [ "$o" -nt "$f" ] || { g++ $FLAGS -c "$f" -o "$o" & pids+=($!); }
done
for p in "${pids[@]:-}"; do [ -z "$p" ] || wait "$p"; done
echo "[2/3] compiling solver -> engine_build/babasolve"
g++ $FLAGS blueprints/baba_is_auto/solver/babasolve.cpp engine_build/obj/core_*.o -o engine_build/babasolve
echo "[3/3] compiling python binding -> engine_build/pyBaba$SUF  (slowest step, ~1-2 min)"
if [ ! -f "engine_build/pyBaba$SUF" ]; then
  g++ $FLAGS -shared -fvisibility=hidden $INC -Igame_src/Extensions/BabaPython/Includes \
    game_src/Extensions/BabaPython/main.cpp game_src/Extensions/BabaPython/Sources/*/*.cpp \
    engine_build/obj/core_*.o -o "engine_build/pyBaba$SUF"
fi
PYTHONPATH=engine_build $PY -c "import pyBaba;g=pyBaba.Game('game_src/Resources/Maps/baba_is_you.txt');print('engine OK, state =',g.GetPlayState())"
engine_build/babasolve game_src/Resources/Maps/baba_is_you.txt
