#!/bin/sh
# Откат install-global: восстановить settings из последнего бэкапа, убрать guard.
set -e
cd "$(dirname "$0")" || exit 1
BAK=$(ls -t global/backup/settings.json.bak-* 2>/dev/null | head -1)
if [ -z "$BAK" ]; then
  echo "⛔ бэкапов в global/backup/ нет — откатывать нечего" >&2
  exit 1
fi
cp "$BAK" "$HOME/.claude/settings.json"
rm -f "$HOME/.claude/hooks/guard.py" "$HOME/.claude/hooks/preflight.sh"
echo "✓ восстановлен $BAK, guard.py и preflight.sh удалены"
echo "⚠ ask-правила, перенесённые в ручной проект, остаются там (безопасно)."
