# Модель угроз скелета

Автономность достигается режимом `dontAsk` (никогда не ждёт ввода: разрешённое
выполняется, остальное блокируется). Безопасность — слоями, от сильного к
слабому. Проверено на Claude Code 2.1.257.

| Угроза | Слой | Гарантия |
|---|---|---|
| Запись вне проекта | OS-sandbox (Seatbelt) + dontAsk | ОС-уровень: только cwd, tmp, additionalDirectories |
| Сеть на чужие хосты | sandbox `allowedDomains` + `strictAllowlist` | ОС-уровень: deny вне списка |
| Выход из песочницы | `allowUnsandboxedCommands: false` | системная: retry вне sandbox отключён |
| Самоэскалация прав (запись .claude/, .zshrc, .mcp.json, .git/hooks) | protected paths + sandbox | системная: в dontAsk — deny, allow-правила это не перебивают |
| `rm -rf /`, снос home | critical paths | системная: в dontAsk — deny |
| Порча main / истории git | guard (PreToolUse) + pre-commit + pre-push + worktree-изоляция `./ai` | worktree — системная («нельзя выключить»); pre-commit/pre-push — git-уровень; guard — best-effort |
| Слияние в main мимо человека (`gh pr merge`, `gh api` на `refs/heads/main`, `/merges`) | guard | best-effort; открытие и обновление PR намеренно разрешены |
| Порча `staging` (интеграционная ветка агента) | guard: force-push, `branch -D`, `push --delete` запрещены для всех веток; `./finish` двигает `staging` только fast-forward | best-effort; `staging` намеренно доступна агенту на запись, в main попадает только через PR |
| Обход git-хуков (`--no-verify`, hooksPath) | guard | best-effort (регексы) |
| Эксфильтрация файлов (curl -d @, scp, rsync) | guard + strictAllowlist | best-effort + ОС-сеть |
| Чтение секретов (~/.ssh, ~/.aws, .env) | sandbox `denyRead` + guard + deny-правила Read | ОС для Bash; guard для инструмента Read |
| Кривой формат коммитов, соавторство | commit-msg-хук | git-уровень |

## Явно вне гарантий

- **Prompt injection**: dontAsk не защищает от вредоносных инструкций в
  прочитанном контенте — слои лишь ограничивают ущерб. Для работы с
  недоверенным вебом использовать auto mode вместо скелета.
- **Server-side branch protection**: локальные гейты снимаемы человеком;
  на GitHub/Stash настраивается отдельно (obligatory для командных репо).
- **Обход guard изнутри скриптов** (`python -c` с git-командами): guard —
  регексный best-effort; результат страхуют pre-commit, pre-push и
  worktree-изоляция.
- **Человек в своём терминале**: `pre-commit` запрещает коммит в
  `main`/`master` только под агентом (`CLAUDECODE`), чтобы не ломать
  документированный шаг «закоммитить скелет в main» вручную.
- **Человек за клавиатурой**: скелет защищает от ошибок агента, не от
  намеренных действий пользователя.

## Секреты для скриптов проекта

Агенту нужны API-ключи, но guard блокирует любое упоминание `.env` в командах
и чтение файла инструментом Read — так и задумано. Рецепт (из `marketing`,
`tools/research/env_file.py`): **скрипт читает файл секретов сам**, агент
только запускает скрипт.

```python
import os

# путь якорим на корень репозитория, а не на cwd — иначе запуск
# из подкаталога не найдёт файл
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_secrets(path=os.path.join(ROOT, ".env")):
    """КЛЮЧ=значение → os.environ; реальное окружение приоритетнее файла."""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except FileNotFoundError:
        return
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
            v = v[1:-1]
        os.environ.setdefault(k.strip(), v)
```

- Значения не печатать и не логировать — вывод скрипта уходит в контекст модели.
- Шаблон ключей без значений — `.env.example` (скелетный `.gitignore` режет
  `.env.*`, поэтому добавь исключение `!.env.example`). Сам файл уже в
  `.gitignore` и в `.worktreeinclude`, чтобы `./ai` донёс его в worktree.
- `set -a && . ./.env` агент выполнить не сможет (guard) — это ожидаемо.

## Известные точки остановки агента

Единственное, обо что автономный агент может «упереться» (получит deny и
продолжит без этого): новый сетевой домен вне `allowedDomains`. Это осознанно:
расширение списка — правка `.claude/settings.json` человеком.
