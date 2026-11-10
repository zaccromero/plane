#!/bin/sh
# Owner-run, once. Installs two user LaunchAgents: start Plane at login, dump it nightly.
# Run from a normal terminal (it calls launchctl). Re-running replaces both jobs.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
BIN="$HOME/.local/bin"; AGENTS="$HOME/Library/LaunchAgents"; LOGS="$HOME/Library/Logs"
mkdir -p "$BIN" "$AGENTS" "$LOGS"
install -m 0755 "$HERE/plane-up.sh" "$BIN/drako-plane-up"
install -m 0755 "$HERE/plane-backup.sh" "$BIN/drako-plane-backup"
for name in ai.drako.plane ai.drako.plane-backup; do
  sed -e "s|__HOME__|$HOME|g" "$HERE/$name.plist" > "$AGENTS/$name.plist"
  launchctl bootout "gui/$(id -u)/$name" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$AGENTS/$name.plist"
done
echo "installed: ai.drako.plane (login), ai.drako.plane-backup (03:30 daily)"
