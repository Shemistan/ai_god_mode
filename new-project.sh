#!/bin/sh
# Развернуть скелет в новый проект: ./new-project.sh <dir>
set -e
SRC=$(cd "$(dirname "$0")" && pwd)
DEST="$1"
if [ -z "$DEST" ]; then
  echo "usage: ./new-project.sh <dir>" >&2
  exit 1
fi
mkdir -p "$DEST"
DEST=$(cd "$DEST" && pwd)
if [ "$DEST" = "$SRC" ]; then
  echo "⛔ целевая папка совпадает со скелетом" >&2
  exit 1
fi
case "$DEST" in
  "$SRC"/*)
    echo "⛔ целевая папка внутри скелета — разверни проект вне $SRC" >&2
    exit 1
    ;;
esac

copy() { # copy <относительный путь>; не перезаписывает существующее
  if [ -e "$DEST/$1" ]; then
    echo "· пропуск (уже есть): $1"
  else
    mkdir -p "$DEST/$(dirname "$1")"
    cp "$SRC/$1" "$DEST/$1"
    echo "✓ $1"
  fi
}

copy CLAUDE.md
copy ai
copy finish
copy check
copy bootstrap.sh
copy .gitignore
copy .worktreeinclude
copy .claude/settings.json
copy .claude/hooks/preflight.sh
copy .githooks/pre-commit
copy .githooks/commit-msg
copy .githooks/commit_msg.py
copy .githooks/pre-push
copy docs/README.md
mkdir -p "$DEST/docs/superpowers/specs" "$DEST/docs/superpowers/plans"

cd "$DEST"
if [ ! -d .git ]; then
  git init -q
  echo "✓ git init"
fi
sh bootstrap.sh
if ! git rev-parse HEAD >/dev/null 2>&1; then
  git add -A
  git commit -q -m "chore: скелет ai-god-mode"
  echo "✓ первый коммит"
fi
echo "✓ проект готов: $DEST"
echo "  1) заполни секцию «О проекте» в CLAUDE.md"
echo "  2) запускай задачи: ./ai <task-name>"
