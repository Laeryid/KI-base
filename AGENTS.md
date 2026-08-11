# AGENTS.md — Руководство для AI-агентов

Этот файл описывает проект `ki-manager` для AI-агентов, работающих с данным репозиторием.

---

## Что это за проект?

**`ki-manager`** — это MCP-сервер (Model Context Protocol), написанный на Python. Он реализует JSON-RPC 2.0 поверх `stdin/stdout` и предоставляет AI-агентам (Antigravity, Claude, Cursor и т.д.) инструменты для управления базой знаний проекта (Knowledge Items, KI).

**Репозиторий сам использует себя**: в папке `knowledge/` лежат KI-файлы, документирующие этот же репозиторий.

---

## Архитектура

```
src/ki_manager/
├── server.py              ← Единственный entry point. MCP-петля stdin/stdout.
├── __init__.py            ← Версия пакета (__version__)
├── scripts/               ← Бизнес-логика. НЕ зависит от MCP.
│   ├── ki_utils.py        ← Утилиты: пути, нормализация, workspace detection
│   ├── audit_coverage.py  ← Анализ покрытия документацией
│   ├── generate_dir_index.py
│   ├── ki_dependency_analyzer.py
│   └── knowledge_engine.py
├── tools/
│   └── scaffold.py        ← ki_init_project (создание структуры .ki-base/)
├── templates/             ← Jinja/md-шаблоны для генерации файлов
└── workflows/             ← Bundled workflow-инструкции (копируются в IDE)
```

**Важно:** `scripts/` — это самостоятельные Python-скрипты. `server.py` запускает их через `subprocess` или напрямую импортирует. Логика MCP и бизнес-логика строго разделены.

---

## Как работает MCP-цикл

`server.py` запускает бесконечный цикл `while True: line = sys.stdin.readline()`.

Каждая строка — это один JSON-RPC запрос. Ответ записывается в `sys.stdout` + немедленный `.flush()`.

**Поддерживаемые методы:**
| Метод | Действие |
|-------|----------|
| `initialize` | Handshake (deprecated в новой спецификации) |
| `server/discover` | Handshake (новый метод протокола с 2026-07-28) |
| `notifications/initialized` | Сервер запрашивает `roots/list` у клиента для детекции workspace |
| `tools/list` | Возвращает список инструментов |
| `tools/call` | Вызов конкретного инструмента |
| `resources/list` / `resources/read` | Виртуальные ресурсы: `ki://instructions.md`, `ki://knowledge-items.md` |
| Все остальные | Возвращает `-32601 Method not found` (не молчит!) |

---

## Инструменты (Tools)

Все инструменты выставляются напрямую через `tools/list`. Деления на eager/lazy нет.

**Инструменты по группам:**

| Группа | Инструменты |
|--------|-------------|
| Инструкции | `ki_instructions` |
| Инициализация | `ki_init_project`, `ki_migrate_project` |
| Реестр | `ki_register_project`, `ki_list_projects`, `ki_status`, `ki_prune_registry` |
| Покрытие | `audit_coverage`, `generate_dir_index`, `analyze_dependencies`, `analyze_all_dependencies`, `find_unmapped_files`, `analyze_module` |
| Scaffold | `ki_scaffold`, `ki_scaffold_status`, `update_last_verified` |
| Файлы | `read_know_file`, `write_know_file`, `edit_know_file`, `make_know_dir` |
| Git | `git_checkpoint`, `git_restore`, `git_diff_secured` |
| Состояние | `save_state`, `restore_mapping` |

Полный список с описаниями возвращает `tools/list`. Для получения инструкций по воркфло используй `ki_instructions`.

---

## Workspace Detection (определение проекта)

Сервер пытается определить активный воркспейс в таком порядке:

0. `_meta.io.modelcontextprotocol/clientInfo.workspaceUri` в каждом запросе (новый протокол 2026-07-28)
1. `--workspace` CLI-аргумент при запуске
2. `rootUri` / `workspaceFolders` в запросе `initialize`/`server/discover`
3. Рекурсивный поиск `file://` URI в любом поле params
4. Ответ клиента на запрос `roots/list` (после `notifications/initialized`)
5. `path` / `project_path` аргументы вызова инструмента

Текущий воркспейс хранится в `ki_utils.ACTIVE_WORKSPACE_PATH`.

---

## Отладка

### Логи
Все `REQ:` и `RESP:` сообщения логируются в:
```
~/.ki_base/logs/<дата>.log
```
Смотри туда **первым делом** при любых проблемах.

### Ключевые строки в логах
| Строка | Значение |
|--------|----------|
| `ki-manager MCP server started (PID: ..., mode: ...)` | Сервер запустился |
| `REQ: {...}` | IDE прислала запрос (stdin работает) |
| `RESP: {...}` | Сервер ответил (stdout работает) |
| `ERROR: [Errno 22] Invalid argument` | Проблема с `stdout.flush()` (см. Known Issues) |
| `SET workspace via ...` | Воркспейс успешно определён |

### Симуляция MCP-клиента вручную
```powershell
# В Windows (PowerShell):
$env:PYTHONPATH="src"; echo '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{}}}' | .venv\Scripts\python.exe -m ki_manager.server

# В Linux/macOS:
PYTHONPATH=src echo '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{}}}' | .venv/bin/python -m ki_manager.server
```
Ответ должен появиться мгновенно. Если процесс завис — проблема в stdin/stdout.

### Проверка инсталлированной vs локальной версии
```powershell
.venv\Scripts\python.exe -c "import ki_manager.server; print(ki_manager.server.__file__)"
```
Должен показывать `src/ki_manager/server.py` (editable install).

---

## Known Issues & Историческое

### `[Errno 22] Invalid argument` на Windows (fixed in 2.0.11)
При оборачивании `sys.stdout` через `codecs.getwriter` вызов `.flush()` крашился на Windows-пайпах, запущенных из Node.js (IDE). Проблема устранена удалением обёртки. Нативный Python stdout достаточен для JSON-RPC.

### `server/discover` vs `initialize` (fixed in 2.0.11)
Antigravity IDE начиная с протокола `2026-07-28` отправляет `"method": "server/discover"` вместо `"method": "initialize"`. Код теперь обрабатывает оба метода одинаково. Не удалять `server/discover` из условия!

### `uvx` vs `uv tool install`
Использование `uvx` в конфигурациях IDE MCP вызывало сбои Handshake и дропы stdio-пайпов из-за задержек создания временных окружений. Рекомендуемый способ установки — глобальная утилита `uv tool install ki-manager`. Для обновления кэша/версии пакета используется `uv tool install --reinstall ki-manager`.

---

## Agent Skills

ki-manager распространяет воркфло-инструкции в формате [Agent Skills](https://agentskills.io).

### Установка скиллов

```bash
# В папку со скиллами IDE:
ki-manager-skills install-skills

# С явным путём:
ki-manager-skills install-skills --path ~/.gemini/config/skills/
```

Скиллы устанавливаются из `src/ki_manager/workflows/*.md`. Существующие файлы не перезаписываются.

### Через MCP-инструмент

Если скиллы не установлены, ИИ может получить любую инструкцию напрямую:
```
ki_instructions({"document": "create-adr"})
```

Доступные документы: `overview`, `knowledge-items`, `create-adr`, `expand-knowledge`, `sync-knowledge`, `update-knowledge`.

---

## Публикация новой версии на PyPI

Смотри `publishing.md` в корне репозитория. Краткий чеклист:

1. Обновить версию в `pyproject.toml` и `src/ki_manager/__init__.py` (оба файла, синхронно!)
2. `git add`, `git commit`, `git push`
3. `git tag v<версия>` + `git push origin v<версия>`
4. GitHub Actions `.github/workflows/publish.yml` автоматически соберёт и опубликует пакет

> [!CAUTION]
> Никогда не создавай тег на старом коммите — `publish.yml` должен быть в истории коммита, на который указывает тег.

---

## Разработка

```powershell
# Установить в editable-режиме
.venv\Scripts\pip.exe install -e .

# Запустить тесты
.venv\Scripts\pytest.exe tests/

# Локальная конфигурация в IDE для разработки
{
  "ki-manager": {
    "command": "C:\\Experiments\\KI-base\\.venv\\Scripts\\python.exe",
    "args": ["-m", "ki_manager.server"]
  }
}
```

---

## Ключевые файлы для изучения

| Файл | Зачем читать |
|------|-------------|
| `src/ki_manager/server.py` | Весь MCP-цикл, все методы, вся диспетчеризация инструментов |
| `src/ki_manager/cli.py` | CLI-команды (install-skills) |
| `src/ki_manager/workflows/*.md` | Воркфло-инструкции в формате Agent Skills |
| `src/ki_manager/scripts/ki_utils.py` | Нормализация путей, загрузка конфигов, workspace detection |
| `pyproject.toml` | Версия, entrypoint (`ki-manager = "ki_manager.server:main"`) |
| `publishing.md` | Пошаговая инструкция по релизу |
| `README.md` | Документация для пользователей (включая Troubleshooting) |
