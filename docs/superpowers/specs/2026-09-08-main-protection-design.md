# Полномочия агента и неприкосновенность `main`

- **Тип:** spec
- **Статус:** реализовано
- **Обновлено:** 2026-09-08

## Задача

Явно зафиксировать контракт: агент сам ведёт весь поток веток, а `main`/`master`
не трогает вообще.

**Разрешено агенту:** создавать ветки, вливать их в `staging`, пушить свою ветку
и `staging` в origin, открывать и обновлять PR `staging → main`.

**Запрещено:** любая манипуляция с `main`/`master`, включая слияние PR.

## Что было дырявым

Поток `worktree → staging → PR` (спека `2026-09-07-staging-flow-design.md`) уже
работал, но «любая манипуляция с main» не выполнялась — guard пропускал:

| Дыра | Почему проходило |
|---|---|
| `git switch main && git commit -m x` | ветка вычислялась один раз до выполнения, guard видел ветку задачи |
| `git reset --soft HEAD~1` на `main` | в списке защищённых подкоманд был только `--hard` глобально |
| `git update-ref refs/heads/main <sha>` | блокировался лишь `update-ref -d` |
| `git branch -m/-d main` | регекс ловил только `-f`/`-M` |
| `git push --all` / `--mirror` | пушит и `main` тоже |
| `git symbolic-ref HEAD refs/heads/main` | правила не было |
| `gh pr merge`, `gh api -X PATCH …/git/refs/heads/main`, `…/merges` | `gh` не проверялся вообще, хотя вынесен из sandbox в `excludedCommands` |

## Решение

1. **Посегментный разбор команды** (`guard.py`). Составная команда режется по
   `;`, `&&`, `||`, `|`, переводу строки — уже после вычистки кавычек, чтобы
   разделитель в сообщении коммита не порождал ложный сегмент. Ветка
   пересчитывается по ходу: `switch_target()` определяет, на что переключается
   сегмент (`git switch -c feat staging` → `feat`; `git checkout main -- file`
   → None, это восстановление файлов). Побочный плюс: `git switch -c feat
   staging && git commit …` из main checkout теперь корректно разрешён.
2. **Расширенная категория 3** (main защищён): `reset` на защищённой ветке,
   `branch -<флаг> main` с любым флагом, `update-ref`/`symbolic-ref` на
   `refs/heads/main`, `push --all/--mirror`.
3. **Новая категория 3b** (`gh`): запрещены `gh pr merge`, `gh repo
   delete/archive` и write-вызовы `gh api` по путям `git/refs/heads/main`,
   `branches/main`, `/merges`, `pulls/N/merge`. Открытие, просмотр и
   редактирование PR (`gh pr create/list/view/edit`, `gh api` на чтение)
   намеренно разрешены — на них держится `./finish`.
4. **`pre-commit` как git-уровень**: под агентом (`CLAUDECODE` в окружении)
   коммит в `main`/`master` отклоняется хуком, а не регексом. Это страхует
   любой обход guard'а изнутри скрипта. Человеку в своём терминале коммит в
   `main` оставлен — README, шаг 5, на это опирается.
5. **`./check` предупреждает о протухшем guard**: установленный
   `~/.claude/hooks/guard.py` сверяется с репозиторным; расхождение — warning
   с напоминанием про `./install-global.sh`.

`staging` по-прежнему не защищена: агент пишет в неё сам, в `main` она
попадает только через PR, который сливает человек.

## Файлы

| Файл | Изменение |
|---|---|
| `global/hooks/guard.py` | `GUARD_VERSION=2`; `bash_violation` → сегменты + `switch_target`; `git_violation`/`other_violation`; категории 3 и 3b |
| `global/hooks/test_guard.py` | 20 BLOCKED-кейсов (дыры выше) и 17 ALLOWED-кейсов на полномочия агента |
| `.githooks/pre-commit` | запрет коммита в main/master под `CLAUDECODE` |
| `check` | warning о расхождении установленного guard'а с репозиторным |
| `CLAUDE.md`, `README.md`, `SECURITY.md` | контракт «что можно / что нельзя», строки модели угроз |

## Оговорки

- Guard — регексный best-effort: гарантию дают worktree-изоляция, `pre-commit`
  и `pre-push`. Серверный branch protection на GitHub — отдельно и обязателен
  для командных репозиториев.
- Новые правила действуют только после `./install-global.sh` (guard
  копируется в `~/.claude/hooks/`; каталог агенту недоступен на запись).
- Проверку версии guard'а логичнее держать в `.claude/hooks/preflight.sh`
  (блокировать промпт при протухшем guard), но этот каталог защищён от записи
  агента — правку делает человек.
