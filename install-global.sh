#!/bin/sh
# Установка глобального слоя скелета в ~/.claude/ (идемпотентно).
set -e
cd "$(dirname "$0")" || exit 1
mkdir -p "$HOME/.claude/hooks" global/backup
cp global/hooks/guard.py "$HOME/.claude/hooks/guard.py"
cp global/hooks/preflight.sh "$HOME/.claude/hooks/preflight.sh"
chmod +x "$HOME/.claude/hooks/preflight.sh"
echo "✓ guard.py, preflight.sh → ~/.claude/hooks/"

python3 - "$HOME/.claude/settings.json" global/settings.fragment.json <<'PYEOF'
import copy
import datetime
import json
import os
import sys

# Куда переносим глобальные ask-правила (решение B из спеки, §7).
ASK_TARGET = os.path.expanduser(
    "~/avito/dwh/ai/my_tasks/.claude/settings.local.json")

settings_path, fragment_path = sys.argv[1], sys.argv[2]
settings = {}
if os.path.exists(settings_path):
    with open(settings_path, encoding="utf-8") as f:
        settings = json.load(f)
orig = copy.deepcopy(settings)
with open(fragment_path, encoding="utf-8") as f:
    fragment = json.load(f)

def save(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")

# 1. PreToolUse-хук guard.
pre = settings.setdefault("hooks", {}).setdefault("PreToolUse", [])
has_guard = any("guard.py" in h.get("command", "")
                for e in pre for h in e.get("hooks", []))
if not has_guard:
    pre.append(fragment["hooks"]["PreToolUse"][0])
    print("✓ PreToolUse-хук guard добавлен")
else:
    print("· PreToolUse-хук guard уже подключён")

# 2. Sandbox-ключи (только user/managed scope).
sb = settings.setdefault("sandbox", {})
sb.setdefault("network", {})["strictAllowlist"] = True
deny = sb.setdefault("filesystem", {}).setdefault("denyRead", [])
for p in fragment["sandbox"]["filesystem"]["denyRead"]:
    if p not in deny:
        deny.append(p)
print("✓ sandbox: strictAllowlist=true, denyRead=%s" % deny)

# 3. Снять permissions.ask и перенести в ручной проект.
perms = settings.setdefault("permissions", {})
ask = perms.pop("ask", None)
if ask:
    os.makedirs(os.path.dirname(ASK_TARGET), exist_ok=True)
    target = {}
    if os.path.exists(ASK_TARGET):
        with open(ASK_TARGET, encoding="utf-8") as f:
            target = json.load(f)
    tgt_ask = target.setdefault("permissions", {}).setdefault("ask", [])
    for r in ask:
        if r not in tgt_ask:
            tgt_ask.append(r)
    save(ASK_TARGET, target)
    print("✓ ask-правила (%d) перенесены в %s" % (len(ask), ASK_TARGET))
else:
    print("· ask-правил в глобальных настройках нет")

# 4. Фикс нерабочих Write(path)-правил → Edit(path).
for key in ("deny", "allow"):
    rules = perms.get(key, [])
    fixed = []
    for r in rules:
        if r.startswith("Write(") and r.endswith(")"):
            new = "Edit(" + r[len("Write("):]
            if new not in rules and new not in fixed:
                print("✓ %s: %s → %s" % (key, r, new))
                fixed.append(new)
                continue
            print("✓ %s: %s удалён (дубликат %s)" % (key, r, new))
            continue
        fixed.append(r)
    if rules:
        perms[key] = fixed

# 5. Бэкап и запись — только если реально что-то изменилось.
if settings == orig:
    print("· настройки уже актуальны, бэкап не создаётся")
else:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = "global/backup/settings.json.bak-%s" % stamp
    save(bak, orig)
    print("✓ бэкап: %s" % bak)
    save(settings_path, settings)
    print("✓ ~/.claude/settings.json обновлён")
PYEOF
echo "✓ install-global завершён"
