# ai-god-mode — скелет автономного Claude Code

Полная автономность (агент никогда не спрашивает) без права сломать репозиторий,
машину или утащить секреты. Дизайн: `docs/superpowers/specs/`, модель угроз:
`SECURITY.md`.

## Установка (один раз на машину)

```sh
./install-global.sh   # guard + sandbox-политика + снятие глобальных ask
```

## Новый проект: пошагово

1. **Развернуть скелет** (из каталога `ai-god-mode`; папка проекта может быть
   пустой или уже с кодом и git-историей — существующие файлы не трогаются):

   ```sh
   ./new-project.sh ~/path/to/project
   ```

   Скрипт копирует `CLAUDE.md`, `ai`, `finish`, `check`, `bootstrap.sh`,
   `.claude/` (dontAsk + sandbox), `.githooks/`, `docs/` (индексы, грабли),
   `tools/docs_gate.py`, `templates/go-service/`, делает `git init` и первый
   коммит, если их не было, и включает git-хуки.

2. **Заполнить секцию «О проекте»** в `~/path/to/project/CLAUDE.md`: что за
   проект, стек, как запускать, как тестировать. Это единственный контекст,
   который агент получает о проекте.

3. **Добавить проектные проверки** в `./check` (линтер, тесты) — их гоняет
   pre-commit и `./finish`. Уже встроено: гейт документации (шапки и статусы
   спек/планов/ADR, автоиндексы — `docs/README.md`) и `make check` для каждого
   сервиса `app/<svc>/` с Makefile. Go-сервис заводится из шаблона:
   `mkdir -p app && cp -R templates/go-service app/<svc>` (см. `templates/go-service/README.md`).

4. **Подключить origin и `gh`**, если ещё нет: `git remote add origin …`,
   `gh auth login -h github.com`. Без origin `./finish` только двигает
   локальную `staging`, без `gh` не открывает PR.

5. **Закоммитить скелет в main** (если репозиторий уже существовал):

   ```sh
   cd ~/path/to/project
   git add -A && git commit -m "chore: скелет ai-god-mode"
   ```

6. **Запустить `claude` и написать задачу**:

   ```sh
   cd ~/path/to/project
   claude
   ```

   Дальше агент всё делает сам по регламенту `CLAUDE.md`: создаёт worktree
   под задачу, встаёт на `staging` (заводит её, если нет), при большой задаче
   декомпозирует и ведёт каждую подзадачу в своей ветке, после каждой
   запускает `./finish`, в конце отдаёт ссылку на PR `staging → main` и
   просит проверить. Скриптов от тебя не требуется.

   `./ai <slug> ["промпт"]` — необязательный ярлык: то же самое, но worktree
   от `staging` создаётся до старта сессии скриптом, а не агентом.

**Обновить скелет в существующем проекте**: `new-project.sh` не перезаписывает
файлы, поэтому скопируй руками `ai`, `finish`, `check`, `.githooks/`,
`.claude/hooks/preflight.sh` (обёртка над общим хуком), `tools/docs_gate.py`,
индексы `docs/**/README.md` (шапки спек/планов переведи на YAML — формат в
`docs/README.md`) и сверь разделы регламента в `CLAUDE.md` (секцию «О проекте»
не трогай). На новой машине хуки включаются один раз командой `sh bootstrap.sh`.

Логика preflight-хука общая: `global/hooks/preflight.sh` ставится в
`~/.claude/hooks/` через `install-global.sh`, а `.claude/hooks/preflight.sh`
в проекте — только обёртка, которая его вызывает. Правишь проверки в
`global/hooks/preflight.sh`, запускаешь `install-global.sh`, и изменение
действует во всех проектах сразу.

## Поток веток

```
main  ◀── PR (сливаешь сам) ──  staging  ◀── ./finish ──  worktree-<task>
```

Агент ведёт задачу подзадачами, каждая в своей ветке от `staging`, и после
каждой запускает `./finish`: проверки, push ветки, `staging` fast-forward,
push, PR `staging → main` (создать или обновить). Останавливается агент,
когда задача выполнена целиком, и отдаёт ссылку на PR. Ты проверяешь PR и
сливаешь в main. Для PR нужен авторизованный `gh` (`gh auth login`).

Агенту **разрешено**: заводить ветки, вливать их в `staging`, пушить свою
ветку и `staging` в origin, открывать и обновлять PR `staging → main`.
Агенту **запрещено** всё, что трогает `main`/`master`: коммит, push,
`branch -f/-m/-d main`, `update-ref`, `push --all/--mirror`, `gh pr merge`
и запись в main через `gh api`. Слияние PR — только человек.

Точка входа — обычный `claude` в корне проекта. Preflight-хук напоминает
агенту в контекст, что он в main checkout и должен уйти в worktree; guard,
pre-commit и pre-push не дают ему коммитить или пушить в main, если он это
проигнорирует.

## Перед сменой машины

```sh
./backup-global.sh && git add global/backup && git commit -m "chore: снимок ~/.claude"
```

## Прочее

- `./check` — проектные проверки (их же гоняет pre-commit).
- `./finish ["заголовок PR"]` — завершить подзадачу из её ветки (зовёт агент).
- `./bootstrap.sh` — включить git-хуки на новой машине.
- `./uninstall-global.sh` — откат глобальной установки.
