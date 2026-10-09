#!/usr/bin/env bash
# Puts this folder on GitHub and switches on the demo website (GitHub Pages, served from /docs).
#   bash publish.sh [github-user] [repo-name]        defaults: Maced78 level-forge
set -euo pipefail
cd "$(dirname "$0")"
GH_USER="${1:-Maced78}"; REPO="${2:-level-forge}"
URL="https://github.com/$GH_USER/$REPO.git"

command -v git >/dev/null || { echo "git is not installed. Run: sudo apt install git"; exit 1; }
grep -qx ".env" .gitignore 2>/dev/null || echo ".env" >> .gitignore      # the key file never leaves this computer
[ -d .git ] || git init -q
git checkout -q -B main
git config user.name  >/dev/null || git config user.name  "$GH_USER"
git config user.email >/dev/null || git config user.email "$GH_USER@users.noreply.github.com"
git rm -q --cached .env 2>/dev/null || true
chmod +x build_engine.sh run_demo.sh publish.sh set_key.sh 2>/dev/null || true
git add -A
# record the scripts as executable in the repository, so "./run_demo.sh" works after a fresh clone
for f in build_engine.sh run_demo.sh publish.sh set_key.sh; do [ -f "$f" ] && git update-index --chmod=+x "$f"; done
if git ls-files | grep -qx ".env"; then echo "Stopping: .env would be published."; exit 1; fi
git diff --cached --quiet || git commit -q -m "Level-Forge: NeuroBridge.SI Baku submission"
git remote remove origin 2>/dev/null || true
git remote add origin "$URL"

if command -v gh >/dev/null; then
  gh auth status >/dev/null 2>&1 || gh auth login --hostname github.com --git-protocol https --web
  gh repo view "$GH_USER/$REPO" >/dev/null 2>&1 || gh repo create "$GH_USER/$REPO" --public
  git push -u origin main --force
  gh api -X POST "repos/$GH_USER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 \
    || gh api -X PUT "repos/$GH_USER/$REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 \
    || echo "Could not switch Pages on automatically: Settings > Pages > Deploy from a branch > main > /docs > Save"
else
  echo "The GitHub command-line tool (gh) is not installed, so two steps are manual:"
  echo "  1. Create an EMPTY public repository named '$REPO' at https://github.com/new (no README)."
  read -rp "     Press Enter when it exists... " _
  git push -u origin main --force      # asks for your GitHub user name and a personal access token
  echo "  2. On GitHub: Settings > Pages > Deploy from a branch > main > /docs > Save"
fi
echo
echo "Source: https://github.com/$GH_USER/$REPO"
echo "Demo:   https://${GH_USER,,}.github.io/$REPO/   (ready about one minute after Pages is switched on)"
