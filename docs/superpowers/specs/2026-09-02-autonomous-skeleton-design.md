# Скелет автономного агента (ai-god-mode)

- **Тип:** spec
- **Статус:** реализовано
- **Обновлено:** 2026-09-02

Переиспользуемый скелет для проектов, где Claude Code работает **полностью
автономно — никогда не спрашивает разрешений**, но не может разрушить репозиторий,
машину или утащить секреты. Скелет вынесен из практик проекта
`/Users/stalyzade/oleg/marketing` (спека repo-gates), исправлен по фактам
документации Claude Code ≥2.1.257 и дополнен.

## Принцип

**Гейт принуждает, CLAUDE.md объясняет** (унаследовано от друга). Слои защиты,
от сильного к слабому:

```
dontAsk-режим  →  OS-sandbox (Seatbelt)  →  guard-хук (git-семантика)  →  git-хуки  →  CLAUDE.md
   кто решает        файлы + сеть             история и main               формат        смысл
```

Ключевые факты документации, на которых строится дизайн (проверено на 2.1.257):

- `bypassPermissions` **не подходит**: ask-правила и critical-path `rm` в нём
  всё равно спрашивают, allow игнорируется, а protected paths (`.claude/`,
  `.git/`) становятся беззащитны.
- `dontAsk` **буквально никогда не ждёт ввода**: всё, что спросило бы, —
  деняется. Работает то, что в `allow`, read-only-набор Bash и то, что
  PreToolUse-хук вернул как `allow`. Protected paths и critical-path `rm` —
  деняются, т.е. агент не может расширить себе права (запись в
  `.claude/settings.json`, `.zshrc`, `.mcp.json` заблокирована системой).
- PreToolUse-хук с exit 2 блокирует вызов **раньше** allow-правил; его `allow`
  не перебивает deny/ask-правила. Поэтому ask-правила из глобальных настроек
  подлежат переносу (см. §7).
- Sandbox (Seatbelt) ограничивает **Bash и все дочерние процессы** на уровне ОС:
  запись только в cwd + tmp + additionalDirectories, защита `~/.claude`,
  `.git/hooks`, `.git/config`; сеть — только по allowlist доменов.
- `--worktree <name>` даёт **нативную** изоляцию от main checkout: правки и
  git-команды в основную копию блокируются самим Claude Code, «you can't turn
  this check off».

## Структура репозитория скелета

Скелет — это проект с уже применённым скелетом (dogfooding):

```
04_ai_god_mode/
├── README.md                 как пользоваться: 3 команды
├── SECURITY.md               модель угроз: что гарантируем, что нет
├── CLAUDE.md                 регламент агента (секция «О проекте» — заглушка)
├── ai                        launcher: ./ai <task-name> [prompt]
├── check                     проектные проверки; в скелете — тесты guard
├── bootstrap.sh              core.hooksPath=.githooks + chmod (на новой машине)
├── install-global.sh         global/ → ~/.claude/  (см. §6)
├── uninstall-global.sh       откат install-global (из бэкапа)
├── backup-global.sh          ~/.claude → global/backup/  (перед сменой машины)
├── new-project.sh <dir>      копирует манифест в новый проект + bootstrap
├── .gitignore                .env, .mcp.json, tmp/, .claude/worktrees/, …
├── .worktreeinclude          .env, .env.local — копируются в worktree
├── .claude/
│   ├── settings.json         dontAsk + sandbox + allow + hooks (см. §2)
│   └── hooks/
│       └── preflight.sh      UserPromptSubmit: guard установлен? нет → exit 2
├── .githooks/
│   ├── pre-commit            запускает ./check, если он есть
│   ├── commit-msg            → commit_msg.py
│   ├── commit_msg.py         Conventional Commits + запрет соавторства
│   └── pre-push              отказ пушить в main/master и при --no-verify-обходе
├── docs/
│   ├── README.md
│   └── superpowers/{specs,plans}/
└── global/                   эталон глобального слоя (живёт в ~/.claude/)
    ├── hooks/
    │   ├── guard.py          PreToolUse-страж (см. §3)
    │   └── test_guard.py     табличные тесты: команда → блок/пропуск
    ├── settings.fragment.json  что мерджится в ~/.claude/settings.json
    └── backup/               снимок ~/.claude (в .gitignore — knowledge, *.mcp.json)
```

**Манифест new-project.sh** (что копируется в новый проект):
`CLAUDE.md`, `ai`, `check` (заглушка), `bootstrap.sh`, `.gitignore`,
`.worktreeinclude`, `.claude/`, `.githooks/`, `docs/` (пустой каркас).
`global/`, `SECURITY.md` и install/backup-скрипты **не копируются** — они
принадлежат скелету.

## 1. Launcher `./ai`

```
./ai <task-name> ["стартовый промпт"]
```

1. Запускает `doctor` (встроен в `ai`, отдельный файл не нужен): guard
   установлен в `~/.claude/hooks/` и его версия совпадает с `global/hooks/`;
   PreToolUse подключён в `~/.claude/settings.json`; `core.hooksPath=.githooks`;
   в репо есть хотя бы один коммит. Любой провал → понятное сообщение и exit 1.
2. `exec claude --worktree "$task" --permission-mode dontAsk [prompt]`.

Worktree создаётся в `.claude/worktrees/<task>/` на ветке `worktree-<task>` от
интеграционной ветки `staging` (с 2026-09-07, см.
`2026-09-07-staging-flow-design.md`; до этого — от default-ветки). Main
checkout недоступен агенту нативно. Повторный запуск с тем же именем открывает
существующий worktree (продолжение задачи).

Запуск голым `claude` в проекте тоже безопасен (settings проекта дают dontAsk +
sandbox), но не изолирован worktree'ом — preflight-хук (§4) предупреждает об
этом в контекст агента, не блокируя.

## 2. `.claude/settings.json` проекта

```json
{
  "permissions": {
    "defaultMode": "dontAsk",
    "allow": [
      "Bash", "Edit", "Write", "Read", "Glob", "Grep",
      "WebFetch", "WebSearch", "Agent", "Skill", "TodoWrite",
      "NotebookEdit", "EnterWorktree", "ExitWorktree"
    ],
    "additionalDirectories": []
  },
  "sandbox": {
    "enabled": true,
    "autoAllowBashIfSandboxed": true,
    "failIfUnavailable": true,
    "allowUnsandboxedCommands": false,
    "excludedCommands": ["docker *", "gh *"],
    "network": {
      "allowedDomains": [
        "github.com", "*.github.com", "*.githubusercontent.com",
        "stash.msk.avito.ru",
        "pypi.org", "files.pythonhosted.org",
        "registry.npmjs.org",
        "proxy.golang.org", "sum.golang.org", "storage.googleapis.com",
        "api.anthropic.com", "statsig.anthropic.com", "sentry.io"
      ],
      "allowLocalBinding": true
    }
  },
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [{ "type": "command",
        "command": "\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/preflight.sh" }] }
    ]
  }
}
```

Решения:

- **`allow` перечисляет инструменты целиком** — в dontAsk это единственный
  способ «никогда не деняй молча». Безопасность даёт не permission system, а
  sandbox + guard + protected paths (которые allow-правила перебить не могут).
- **MCP-инструменты** покрываются guard'ом: на не-заблокированные вызовы он
  возвращает JSON `permissionDecision: "allow"` — иначе каждый MCP-вызов в
  dontAsk был бы denied. Перечислять сотни `mcp__*` в allow не нужно.
- `excludedCommands`: `docker` несовместим с sandbox, Go-CLI `gh` падает по TLS
  под Seatbelt (из документации). Список расширяется по мере надобности —
  команды вне sandbox всё равно проходят guard.
- `allowedDomains` — стартовый список; новый домен = правка settings человеком
  (агенту этот файл недоступен — protected path). Это осознанная единственная
  точка, где автономный агент может упереться: он получает deny, пишет об этом
  и продолжает остальную работу.
- `additionalDirectories` — пуст по умолчанию; в конкретном проекте сюда
  добавляются внешние читаемые каталоги (например, `~/avito/dwh/1_issues`).
- `failIfUnavailable: true` — без песочницы не работаем вообще.

В **глобальный фрагмент** (не в проект, т.к. проектные файлы для этих ключей
игнорируются) уходят: `sandbox.network.strictAllowlist: true` (deny вместо
prompt для незнакомых доменов), `sandbox.filesystem.denyRead:
["~/.ssh", "~/.aws", "~/.kube", "~/.gnupg", "~/.netrc"]`.

## 3. Guard `~/.claude/hooks/guard.py`

PreToolUse на `Bash|Write|Edit|MultiEdit|NotebookEdit|Read` и на `*` для
MCP-allow (см. ниже). Один файл, stdlib-only, Python 3. Читает JSON со stdin;
корень репо — от `cwd` события (не от расположения файла — guard глобальный;
в worktree `cwd` указывает на worktree, это корректно). Контракт:

- **блок** → exit 2 + причина в stderr (уходит модели);
- **пропуск Bash/Write/…** → exit 0;
- **пропуск прочих инструментов** (MCP и др.) → stdout-JSON
  `{"hookSpecificOutput": {"hookEventName": "PreToolUse",
  "permissionDecision": "allow", "permissionDecisionReason": "guard: ok"}}` —
  чтобы dontAsk не денял их молча. Хук-`allow` не перебивает deny/ask-правила
  и protected paths — эскалации нет.
- Каждый блок пишется в `~/.claude/guard.log` (время, cwd, инструмент, причина).
- Кривой JSON на входе → exit 0 (fail-open, не ломаем агента).
- В начале файла — `GUARD_VERSION = "N"`; doctor сравнивает с эталоном.

Категории блокировок (только то, что **не** покрывают sandbox и protected
paths):

| # | Категория | Ловим |
|---|---|---|
| 1 | Обход гейтов | `git commit`/`git push` с `--no-verify`/`-n`; `core.hooksPath` в любом виде (`git config`, `git -c`, `-c` после подкоманды) |
| 2 | История | `push --force/--force-with-lease/-f/+refspec`; `reset --hard`; `rebase`; `filter-branch`; `clean -f`; `stash drop/clear`; `branch -D`; `push --delete`/`:branch`; `update-ref -d`; `reflog expire` |
| 3 | Main защищён | state-changing git на main/master: `commit`, `merge`, `cherry-pick`, `am`, `revert`, `pull` — если HEAD на main/master (проверка через `git -C <cwd> symbolic-ref`); `push` в main/master по refspec (`HEAD:main`, `main`) или текущей ветке; `branch -f main`, `switch -C main`, `checkout -B main` |
| 4 | Секреты (2-й пояс к denyRead) | Bash-обращение к `.env*`, `*.pem`, `*.key`, `~/.ssh`, `~/.aws`, `~/.netrc`, `~/.kube`, `security find-*-password`; Read-инструмент по тем же маскам |
| 5 | Эксфильтрация | `curl` с `-d @`, `--data-binary @`, `-T`, `--upload-file`, `-F x=@`; `wget --post-file`; `scp`/`rsync` с `host:`-назначением; `nc` с перенаправлением файла |
| 6 | Система | `sudo`; `launchctl`; `crontab`; `defaults write`; `rm -rf` в любой склейке флагов (дублирует critical-path-механизм для не-критических путей) |

Что guard **не делает** (закрыто другими слоями, см. SECURITY.md): запись вне
репо (sandbox + dontAsk), запись в `.claude/`/`.git/hooks`/`.zshrc` (protected
paths + sandbox), `find -delete`/`shutil.rmtree` вне cwd (sandbox), сетевой
доступ к чужим хостам (strictAllowlist).

Известный предел: guard — регексный слой, `python -c`/`node -e`-обёртки он
не парсит. Для файловых эффектов это закрывает sandbox; для git-семантики
(категории 1–3) остаётся щель «git из скрипта» — принято осознанно,
плюс её страхуют pre-push и pre-commit (git-хуки видят результат, не команду).

## 4. Preflight `.claude/hooks/preflight.sh` (UserPromptSubmit)

Быстрая проверка на каждый промпт (метка-файл в `$TMPDIR` — полная проверка
раз в сессию):

- `~/.claude/hooks/guard.py` существует и PreToolUse-хук присутствует в
  `~/.claude/settings.json` → иначе **exit 2** со stderr «⛔ guard не
  установлен — запусти install-global.sh из скелета». Промпт блокируется,
  работа не начинается. (Сверка версии guard с эталоном — забота doctor
  в `./ai`, не preflight.)
- `git config core.hooksPath` = `.githooks` → иначе exit 2 «запусти
  ./bootstrap.sh».
- Сессия не в worktree (cwd == main checkout) → **не** блокировать, но выдать
  в stdout (попадает в контекст) напоминание «работаешь в main checkout;
  для задач используй ./ai <task>».

## 5. Git-хуки `.githooks/`

- **commit-msg** (`commit_msg.py`): `тип(область)?: описание`; типы
  `feat fix docs refactor test chore build ci perf style`; сабж ≤72; блок строк
  `Co-Authored-By`, `Generated with`, `Claude-Session`.
- **pre-commit**: `[ -x ./check ] && ./check` — иначе пропуск. В скелете
  `./check` = `python3 -m unittest discover -s global/hooks`; в новом проекте —
  заглушка с комментариями (линтер, тесты).
- **pre-push**: читает stdin (refs); push в `refs/heads/main|master` → exit 1.
  Работает даже если guard обойдён (git-хук — независимый слой). Плюс в
  сообщении — что делать (влить через PR/merge руками).

`bootstrap.sh`: `git config core.hooksPath .githooks` + `chmod +x` всему.

## 6. Глобальный слой и его скрипты

`install-global.sh` (идемпотентный, python3 для JSON-мерджа):

1. `cp global/hooks/guard.py ~/.claude/hooks/guard.py`.
2. Бэкап `~/.claude/settings.json` → `global/backup/settings.json.bak-<дата>`.
3. Мердж `global/settings.fragment.json` в `~/.claude/settings.json`:
   - добавить PreToolUse-hook guard'а (если нет);
   - добавить `sandbox.filesystem.denyRead` и `sandbox.network.strictAllowlist`;
   - **удалить `permissions.ask`** (см. §7) — с печатью того, что удалено;
   - починить битые правила `Write(**/.env*)`, `Write(**/secrets/**)` →
     `Edit(...)` (Claude Code сам предупреждает, что Write-правила не работают);
   - остальное (плагины, звуковые хуки, тема…) — не трогать.
4. Печать диффа «было → стало».

`uninstall-global.sh`: восстановить последний бэкап settings, удалить guard.py.

`backup-global.sh`: `rsync ~/.claude/{settings.json,CLAUDE.md,skills,commands}
global/backup/claude-home/` (без `knowledge/`, `*.mcp.json`, кэшей — они в
`.gitignore` скелета). Запускать перед сменой машины; хранится в git скелета.

## 7. Миграция глобальных ask-правил (решение B)

`ask`-массив (`sudo`, `rm`, `mv`, `curl`, `git add/commit/push/merge`) из
`~/.claude/settings.json` **удаляется** — иначе в dontAsk эти команды деняются
и автономность не работает. Чтобы поведение ручного проекта не изменилось,
`install-global.sh` переносит этот массив в
`/Users/stalyzade/avito/dwh/ai/my_tasks/.claude/settings.local.json`
(создать/домерджить). Путь захардкожен в скрипте константой рядом с шапкой —
поменять легко.

## 8. CLAUDE.md (шаблон)

Секции: **О проекте** (заглушка) · **Автономность** (не задавать вопросов; при
блоке guard/sandbox — не обходить, зафиксировать в итоговом отчёте что и почему;
plan mode и AskUserQuestion не использовать — в dontAsk они денятся) ·
**Задачи и ветки** (задача = `./ai <task>`, работа в worktree, финал — push
ветки `worktree-<task>` и краткий отчёт; main не трогать) · **Коммиты** (формат;
строку соавторства не добавлять; `./check` перед коммитом) · **Временные файлы**
(scratchpad/tmp, не мусорить в репо) · **Документация** (спеки и планы — в
`docs/superpowers/`, статус в шапке файла).

## 9. SECURITY.md

Таблица «угроза → слой → гарантия/best-effort»: что закрыто ОС (sandbox), что
системой (dontAsk, protected paths, worktree isolation), что регексами (guard —
best-effort), что регламентом (CLAUDE.md — не защита). Явно вне гарантий:
prompt injection (dontAsk не защищает от него — только ограничивает ущерб),
server-side branch protection (настраивается на GitHub/Stash отдельно),
злонамеренный человек за клавиатурой.

## 10. Тесты

- `global/hooks/test_guard.py` — табличный unittest, ~60 кейсов:
  блокируемые (все категории §3, включая обходные формы: склеенные флаги,
  `git -c core.hooksPath=`, `push origin HEAD:main`, `curl --data-binary @f`)
  и **обязанные проходить** (`rm file.txt`, `git push origin worktree-x`,
  `git commit -m` на feature-ветке, `curl -d '{"json":1}'`, `git fetch`).
  Прогон: `./check` и pre-commit.
- `commit_msg.py` — свой тест-набор там же.
- Скрипты (`install/new-project/backup`) проверяются вручную на
  тестовой папке при реализации (в плане — отдельные шаги с чек-листом).

## Явно вне scope (YAGNI)

- CI (GitHub Actions) — нет remote; добавить при появлении.
- Автосинк guard'а по проектам — guard глобальный, синк не нужен.
- Лимиты трат/бюджетов (ADR 0003 друга) — не актуально для кодовых проектов.
- Windows/Linux — скелет заточен под macOS (Seatbelt).
- Двусторонний sync `global/backup` ↔ `~/.claude` — только ручной snapshot.
