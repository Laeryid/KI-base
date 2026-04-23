<!-- last_verified: 2026-04-22 -->
# KI: Knowledge Management Infrastructure (Core)

## Overview
Ядро системы управления знаниями Pocket Team. Обеспечивает техническую инициализацию, расчет хешей, аудит покрытия, генерацию индексов и интеграцию через MCP.

## Key Components
| Component | File | Purpose |
|---|---|---|
| **System Init** | `.know/scripts/init_ki_system.py` | Первичная настройка: хард-линки воркфлоу, обновление `.gitignore` и генерация MCP-конфига. |
| **Knowledge Engine** | `.know/scripts/knowledge_engine.py` | Техническое ядро: расчет SHA-256 хешей, фильтрация по `mtime` и маппинг зависимостей. |
| **KI Utils** | `.know/scripts/ki_utils.py` | Общие утилиты: разрешение путей проекта и базы знаний, загрузка конфигураций. |
| **Audit Provider** | `.know/scripts/audit_coverage.py` | Сбор метрик Density (плотность) и Complexity (сложность). |
| **Dependency Analyzer** | `.know/scripts/ki_dependency_analyzer.py` | Анализ связей между KI на основе импортов в коде. |
| **Module Analyzer** | `.know/scripts/analyze_module.py` | Глубокий анализ покрытия конкретной директории или модуля. |
| **Unmapped Finder** | `.know/scripts/find_unmapped_files.py` | Поиск файлов проекта, не привязанных к KI в `doc_config.json`. |
| **Index Generator** | `.know/scripts/generate_dir_index.py` | Автоматическая сборка `DIR_INDEX.md` на основе структуры проекта. |
| **Agent Sync** | `.know/scripts/sync_agents_md.py` | Синхронизация правил и контекста в `AGENTS.md`. |
| **Knowledge MCP** | `.know/scripts/knowledge_mcp.py` | Интерфейс взаимодействия через протокол MCP с поддержкой "песочницы". |

## Knowledge MCP Tools
Система предоставляет следующие инструменты через MCP (KnowledgeManager):
- **audit_coverage**: Запуск полного аудита.
- **sync_agents_md**: Обновление инструкций для агентов.
- **generate_dir_index**: Пересборка индекса файлов.
- **check_changes**: Проверка изменений в отслеживаемых файлах.
- **save_state**: Фиксация текущего состояния хешей (commit).
- **read_know_file / write_know_file**: Безопасные операции с файлами внутри `.know`.
- **edit_know_file**: Атомарное редактирование (текстовая замена) внутри `.know`.
- **analyze_dependencies**: Автоматическое связывание KI по коду.

## Technical Details
- **Path Resolution Logic**: Утилита `ki_utils.py` ищет корень базы знаний (`knowledge_root`) в следующем порядке:
    1. Аргумент командной строки `--config`.
    2. Поле `knowledge_root` в `ki_config.json`.
    3. Родительская директория скрипта (стандарт для `.know/scripts/`).
    4. Поиск папки `.know` в текущей и родительской директориях.
- **Security Sandboxing**: MCP-сервер ограничивает доступ только директорией `.know`. Попытки выйти за пределы (`..` или абсолютные пути) блокируются в `validate_path`.
- **Execution Protection**: Запрещено изменять исполняемые файлы (`.py`, `.exe`, `.bat`, `.sh` и др.) через MCP-инструменты записи.
- **Config Integrity**: Прямая перезапись `doc_config.json` через `write_know_file` запрещена. Разрешено только частичное редактирование (`edit_know_file`) для предотвращения потери структуры базы знаний.
- **mtime Optimization**: Для ускорения аудита система сначала проверяет время изменения файла (`mtime`). SHA-256 хеш пересчитывается только если файл физически изменился на диске.
- **Forced Efficiency Injection**: Скрипт `init_ki_system.py` автоматически вставляет в `AGENTS.md` критические правила: блоки планирования (Affected layers), линтинг перед сохранением и запрет на каскадную асинхронность.

## Common Pitfalls
- **Stale State**: Если `doc_state.json` поврежден, возможны ложные срабатывания аудита. Решение: `save_state` для принудительной синхронизации хешей.
- **Critical Config Loss**: Недопустима полная перезапись `doc_config.json` инструментами, не имеющими логики валидации структуры (как `write_know_file`). Это приведет к потере всех метаданных и связей. Используйте только `edit_know_file` или специализированные скрипты.
- **Python Path**: Скрипты инициализации пытаются автоматически определить `.venv`. Если в системе несколько окружений, убедитесь, что в `ki_config.json` прописан верный `venv_python`.
- **Encoding Issues**: На Windows скрипты используют принудительную кодировку UTF-8 в `sys.stdin/stdout`, но внешние вызовы (например, `find_unmapped_files`) могут столкнуться с ограничениями системной кодовой страницы при наличии кириллицы в именах файлов.






## Related KIs

