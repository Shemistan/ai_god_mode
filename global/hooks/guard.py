#!/usr/bin/env python3
"""PreToolUse-страж для автономного режима (dontAsk).

Блокирует git-семантику (защита main, истории, обход хуков), эксфильтрацию
и обращения к секретам. Файловую и сетевую изоляцию обеспечивают sandbox и
protected paths Claude Code — здесь не дублируются (см. SECURITY.md скелета).

Контракт: JSON события на stdin; блок → exit 2 + причина в stderr (уходит
модели); инструменты вне HANDLED → stdout-JSON permissionDecision=allow,
чтобы dontAsk не денял их молча. Кривой вход → exit 0 (fail-open).
"""
GUARD_VERSION = "1"

import datetime
import json
import os
import re
import subprocess
import sys

HANDLED = {"Bash", "Read", "Edit", "Write", "MultiEdit", "NotebookEdit"}
PROTECTED = ("main", "master")

_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")

# git + глобальные опции перед подкомандой (-C ., -c k=v, --no-pager, …),
# чтобы `git -C . push --force` и т.п. не обходили категории 1-3 ниже.
_GIT = r"\bgit\b(?:\s+(?:-[cCp]\s*\S+|--[\w-]+(?:=\S+)?))*"

SECRET_PATTERNS = [
    r"\.env\b",
    r"\.pem\b",
    r"\.key\b",
    r"\.netrc\b",
    r"(~|\$HOME|/Users/[^/\s]+|/home/[^/\s]+)/\.(ssh|aws|kube|gnupg)\b",
]


def _unquoted(c):
    """Команда с вычищенным содержимым кавычек — для проверки флагов,
    чтобы `git commit -m "про -n флаг"` не ловился как обход хуков."""
    return _QUOTED.sub("''", c)


def _flag(text, letter):
    """Однобуквенный флаг letter, в т.ч. в склейке (-fd, -nm)."""
    return re.search(r"(?:^|\s)-[a-zA-Z]*" + letter, text) is not None


def secret_violation(text):
    """Причина блокировки обращения к секрету или None."""
    for p in SECRET_PATTERNS:
        if re.search(p, text):
            return "обращение к секретам (.env/.pem/.key/~/.ssh/~/.aws/…) запрещено"
    return None


def bash_violation(c, branch=None):
    """Причина блокировки bash-команды или None. branch — текущая ветка."""
    u = _unquoted(c)

    # --- 1. Целостность гейтов ---
    if "hooksPath" in u:
        return "подмена core.hooksPath запрещена"
    if re.search(r"\bgit\b[^|;&]*--no-verify", u):
        return "обход git-хуков (--no-verify) запрещён"
    m = re.search(_GIT + r"\s+commit\b([^|;&]*)", u)
    if m and _flag(m.group(1), "n"):
        return "обход хуков (git commit -n) запрещён"

    # --- 2. История ---
    m = re.search(_GIT + r"\s+push\b([^|;&]*)", u)
    if m:
        rest = m.group(1)
        if "--force" in rest or _flag(rest, "f") or re.search(r"\s\+\S", rest):
            return "force-push запрещён"
        if "--delete" in rest or _flag(rest, "d") or re.search(r"\s:\S", rest):
            return "удаление удалённой ветки запрещено"
        if re.search(r"(\s|:)(refs/heads/)?(main|master)(\s|$)", rest):
            return "push в main/master запрещён — работай в ветке (./ai <task>)"
        if branch in PROTECTED:
            return "push с ветки %s запрещён — работай в ветке (./ai <task>)" % branch
    if re.search(_GIT + r"\s+reset\b[^|;&]*--hard", u):
        return "git reset --hard запрещён"
    if re.search(_GIT + r"\s+(rebase|filter-branch)\b", u):
        return "переписывание истории (rebase/filter-branch) запрещено"
    if re.search(_GIT + r"\s+pull\b[^|;&]*--rebase\b", u):
        return "переписывание истории (pull --rebase) запрещено"
    m = re.search(_GIT + r"\s+clean\b([^|;&]*)", u)
    if m and ("--force" in m.group(1) or _flag(m.group(1), "f")):
        return "git clean -f запрещён"
    if re.search(_GIT + r"\s+stash\s+(drop|clear)\b", u):
        return "git stash drop/clear запрещён"
    m = re.search(_GIT + r"\s+branch\b([^|;&]*)", u)
    if m and re.search(r"(?:^|\s)-[a-zA-Z]*D", m.group(1)):
        return "git branch -D запрещён"
    if re.search(_GIT + r"\s+update-ref\b[^|;&]*(\s-d\b|--delete)", u):
        return "git update-ref -d запрещён"
    if re.search(_GIT + r"\s+reflog\s+expire\b", u):
        return "git reflog expire запрещён"

    # --- 3. Main защищён ---
    if branch in PROTECTED and re.search(
            _GIT + r"\s+(commit|merge|cherry-pick|am|revert|pull)\b", u):
        return ("изменение ветки %s запрещено — создай ветку (./ai <task>)"
                % branch)
    if re.search(_GIT + r"\s+branch\s+-[a-zA-Z]*[fM][a-zA-Z]*\s+(main|master)\b", u):
        return "перемещение main/master запрещено"
    if re.search(_GIT + r"\s+(switch\s+-[a-zA-Z]*C|checkout\s+-[a-zA-Z]*B)[a-zA-Z]*\s+(main|master)\b", u):
        return "пересоздание main/master запрещено"

    # --- 4. Секреты (второй пояс к sandbox.denyRead) ---
    v = secret_violation(c)
    if v:
        return v
    if re.search(r"\bsecurity\b[^|;&]*find-(generic|internet)-password", u):
        return "доступ к Keychain запрещён"

    # --- 5. Эксфильтрация ---
    if re.search(r"\bcurl\b", u):
        if (re.search(r"(?:^|\s)(-d|--data|--data-binary|--data-urlencode)(?:=|\s+)?@", u)
                or re.search(r"(?:^|\s)(-T\b|--upload-file\b)", u)
                or re.search(r"(?:^|\s)-F\s+\S*@", u)):
            return "выгрузка локальных файлов наружу (curl) запрещена"
    if re.search(r"\bwget\b[^|;&]*--post-file", u):
        return "wget --post-file запрещён"
    if re.search(r"\b(scp|rsync)\b[^|;&]*\s(\S+@)?[A-Za-z0-9][\w.-]*:\S*", u):
        return "scp/rsync на удалённый хост запрещён"
    if re.search(r"\bnc\b[^|;&]*<", c):
        return "выгрузка файла через nc запрещена"

    # --- 6. Система (ловим и по абсолютному пути, и по \-экранированию) ---
    if re.search(r"(?:^|[\s;|&(])(?:\S*/)?\\?sudo\b", u):
        return "sudo запрещён"
    if re.search(r"(?:^|[\s;|&(])(?:\S*/)?\\?(launchctl|crontab)\b", u):
        return "изменение системных планировщиков запрещено"
    if re.search(r"\bdefaults\s+write\b", u):
        return "defaults write запрещён"
    if re.search(r"(?:^|[\s;|&(])(?:\S*/)?\\?rm\b", u):
        rec = "--recursive" in u or _flag(u, "r") or _flag(u, "R")
        force = "--force" in u or _flag(u, "f")
        if rec and force:
            return "rm -rf запрещён"

    return None


def current_branch(cwd):
    """Текущая ветка git в cwd или None (в worktree cwd — сам worktree)."""
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3)
        return r.stdout.strip() or None
    except Exception:
        return None


def evaluate(data, cwd):
    """Причина блокировки события или None."""
    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    if tool == "Bash":
        c = ti.get("command", "")
        branch = current_branch(cwd) if re.search(r"\bgit\b", c) else None
        return bash_violation(c, branch)
    if tool == "Read":
        p = ti.get("file_path") or ""
        return secret_violation(p) if p else None
    return None


def _log(tool, detail, reason, cwd):
    try:
        line = "%s\t%s\t%s\t%s\t%s\n" % (
            datetime.datetime.now().isoformat(timespec="seconds"),
            cwd, tool, reason, detail[:300])
        with open(os.path.expanduser("~/.claude/guard.log"), "a",
                  encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)
    tool = data.get("tool_name", "")
    cwd = data.get("cwd") or os.getcwd()
    reason = evaluate(data, cwd)
    if reason:
        ti = data.get("tool_input") or {}
        detail = ti.get("command") or ti.get("file_path") or ""
        _log(tool, detail, reason, cwd)
        print("⛔ guard: %s" % reason, file=sys.stderr)
        sys.exit(2)
    if tool not in HANDLED:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": "guard: ok",
        }}))
    sys.exit(0)


if __name__ == "__main__":
    main()
