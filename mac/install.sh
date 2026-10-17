#!/bin/bash
# One-time setup of the Fireship sync on this Mac. Safe to run again.
#   - clones the repo to ~/.local/share/video-2-podcast (separate from any working copy)
#   - creates a Python environment there with yt-dlp
#   - installs and starts a launchd job that runs mac/sync-fireship.sh every 10 minutes
# Needs: git, python3, node (YouTube needs a JavaScript runtime) and a logged-in `gh`.
set -euo pipefail

REPO_DIR="$HOME/.local/share/video-2-podcast"
LABEL="com.vahagn.video2podcast.fireship"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/video-2-podcast-fireship.log"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$(ls -d "$HOME"/.nvm/versions/node/*/bin 2>/dev/null | tail -1)"
for tool in git python3 node gh; do
  command -v "$tool" >/dev/null || { echo "missing: $tool"; exit 1; }
done
gh auth status >/dev/null 2>&1 || { echo "run: gh auth login"; exit 1; }

if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" pull --rebase -q
else
  mkdir -p "$(dirname "$REPO_DIR")"
  gh repo clone vahagn-grigoryan/video-2-podcast "$REPO_DIR"
fi
[ -x "$REPO_DIR/.venv/bin/python" ] || python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/pip" install -q -U yt-dlp

mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>/bin/bash</string><string>$REPO_DIR/mac/sync-fireship.sh</string></array>
  <key>StartInterval</key><integer>600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "installed. Log: $LOG"
echo "stop it with: launchctl bootout gui/$(id -u)/$LABEL && rm $PLIST"
