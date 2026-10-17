#!/bin/bash
# Checks Fireship on YouTube and publishes new episodes to the GitHub repo.
# YouTube blocks GitHub's servers, so this runs on a Mac; launchd starts it every
# 10 minutes (see install.sh). Fireship posts Mon-Fri between 16:00 and 21:00 UTC,
# so inside that window every start does a check, and outside it at most one
# check every 2 hours (a Mac that was asleep catches up when it wakes).
set -euo pipefail

REPO_DIR="${REPO_DIR:-$HOME/.local/share/video-2-podcast}"
CHANNEL="https://www.youtube.com/@Fireship/videos"
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | tail -1)"

cd "$REPO_DIR"
trap 'osascript -e "display notification \"Fireship sync failed, see ~/Library/Logs/video-2-podcast-fireship.log\" with title \"video-2-podcast\"" || true' ERR

dow=$(date -u +%u)   # 1 = Monday
hm=$(date -u +%H%M)
if [ "$dow" -le 5 ] && [ "$hm" -ge 1545 ] && [ "$hm" -le 2115 ]; then
  in_window=1
else
  in_window=0
fi
age() { echo $(( $(date +%s) - $(stat -f %m "$1" 2>/dev/null || echo 0) )); }
if [ "$in_window" -eq 0 ] && [ "$(age .last-check)" -lt 7200 ]; then
  exit 0
fi

echo "$(date -u +%FT%TZ) checking Fireship (in_window=$in_window)"

# YouTube changes often; keep yt-dlp current (at most once a day, failure is not fatal).
if [ "$(age .last-update)" -gt 86400 ]; then
  .venv/bin/pip install -q -U yt-dlp && touch .last-update || echo "yt-dlp update failed"
fi

git pull --rebase --autostash -q

result=$(mktemp)
GITHUB_OUTPUT="$result" .venv/bin/python podcast.py --show fireship --playlist "$CHANNEL"
ids=$(sed -n 's/^ids=//p' "$result")
removed=$(sed -n 's/^removed=//p' "$result")
rm -f "$result"

for id in $ids; do
  gh release create "ep-$id" "out/$id.m4a" --title "$id" --notes "" || gh release upload "ep-$id" "out/$id.m4a" --clobber
done
for id in $removed; do
  gh release delete "ep-$id" --cleanup-tag --yes || true
done
rm -f out/*

git add fireship.json fireship.xml
if ! git diff --cached --quiet; then
  git commit -q -m "Fireship: update episodes ${ids:-(removals only)}"
  git push -q || { git pull --rebase -q && git push -q; }
  echo "published: ${ids:-none added}"
fi
touch .last-check
