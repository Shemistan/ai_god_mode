#!/bin/sh
# UserPromptSubmit: блокирует работу, если защита не установлена.
# exit 2 = промпт блокируется, stderr уходит пользователю и модели.

if [ ! -f "$HOME/.claude/hooks/guard.py" ]; then
  echo "⛔ guard не установлен — запусти install-global.sh из скелета ai-god-mode" >&2
  exit 2
fi
if ! grep -q 'guard\.py' "$HOME/.claude/settings.json" 2>/dev/null; then
  echo "⛔ guard.py не подключён PreToolUse-хуком в ~/.claude/settings.json — запусти install-global.sh" >&2
  exit 2
fi
if [ "$(git config core.hooksPath 2>/dev/null)" != ".githooks" ]; then
  echo "⛔ git-хуки не включены — запусти ./bootstrap.sh" >&2
  exit 2
fi
# Напоминание (в контекст агента, не блокирует): сессия вне worktree.
case "$PWD" in
  */.claude/worktrees/*) : ;;
*) echo "ℹ️ Сессия в main checkout: коммиты здесь запрещены. Для задачи с изменениями сначала EnterWorktree <slug>, затем git merge staging (см. CLAUDE.md «Старт задачи»)." ;;
esac
exit 0
