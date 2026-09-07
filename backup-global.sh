#!/bin/sh
# Снимок личной части ~/.claude в git скелета (перед сменой машины).
set -e
cd "$(dirname "$0")" || exit 1
DEST=global/backup/claude-home
mkdir -p "$DEST"
for f in settings.json CLAUDE.md; do
  [ -f "$HOME/.claude/$f" ] && cp "$HOME/.claude/$f" "$DEST/$f"
done
for d in skills commands; do
  if [ -d "$HOME/.claude/$d" ]; then
    rm -rf "$DEST/$d"
    cp -R "$HOME/.claude/$d" "$DEST/$d"
  fi
done
echo "✓ снимок ~/.claude → $DEST"
echo "  дальше: git add global/backup && git commit -m 'chore: снимок ~/.claude'"
