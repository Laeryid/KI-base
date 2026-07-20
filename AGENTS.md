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
| `initialize` / `server/discover` | Handshake. Оба обрабатываются одинаково. `server/discover` — новый метод протокола (с 2026-07). |
| `notifications/initialized` | Сервер запрашивает `roots/list` у клиента для детекции workspace |
| `tools/list` | Возвращает список инструментов (eager + `ki_call`) |
| `tools/call` | Вызов конкретного инструмента |
| `resources/list` / `resources/read` | Виртуальные ресурсы: `ki://instructions.md`, `ki://knowledge-items.md` |
| Все остальные | Возвращает `-32601 Method not found` (не молчит!) |

---

## Инструменты (Tools)

Инструменты делятся на две группы:

**Eager (всегда загружены):**
- `ki_status` — статус воркспейса
- `read_know_file` — чтение KI-файла
- `write_know_file` — запись KI-файла
- `edit_know_file` — редактирование KI-файла (patch-like)

**Lazy (через диспетчер `ki_call`):**
- Все остальные тяжелые инструменты: `audit_coverage`, `generate_dir_index`, `ki_init_project`, `git_checkpoint` и т.д.

Агент вызывает `ki_call(action="help")` чтобы получить полный список lazy-инструментов и их схемы.

---

## Workspace Detection (определение проекта)

Сервер пытается определить активный воркспейс в таком порядке:

1. `--workspace` CLI-аргумент при запуске
2. `rootUri` / `workspaceFolders` в запросе `initialize`/`server/discover`
3. Рекурсивный поиск `file://` URI в любом поле params
4. Ответ клиента на запрос `roots/list` (после `notifications/initialized`)

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

### `uvx` кэш
`uvx` агрессивно кэширует пакеты. После публикации новой версии на PyPI пользователям нужно запустить `uvx --refresh ki-manager` один раз для обновления кэша.

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
| `src/ki_manager/scripts/ki_utils.py` | Нормализация путей, загрузка конфигов, workspace detection |
| `pyproject.toml` | Версия, entrypoint (`ki-manager = "ki_manager.server:main"`) |
| `publishing.md` | Пошаговая инструкция по релизу |
| `README.md` | Документация для пользователей (включая Troubleshooting) |
