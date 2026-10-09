#!/usr/bin/env bash
# Stores your Gemini key in .env (git-ignored), tests it, and optionally starts the evidence run.
cd "$(dirname "$0")"
read -r -s -p "Paste your Gemini API key and press Enter (nothing is shown while you paste): " KEY; echo
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
if [ ${#KEY} -lt 20 ]; then echo "That does not look like a key (too short). Nothing was changed."; exit 1; fi
( umask 077; printf 'GEMINI_API_KEY=%s\n' "$KEY" > .env )
echo "Saved to .env. Testing..."
if python3 -m forge.llm --selftest; then
  if [ "${1:-}" = "--run" ]; then echo; echo "Key works. Starting the evidence run (about 10 minutes)..."; python3 bench/llm_evidence.py; fi
else
  echo; echo "The key was saved but Google rejected it. Copy the whole message above and send it to Claude."; exit 1
fi
