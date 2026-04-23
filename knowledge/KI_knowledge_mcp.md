<!-- last_verified: 2026-04-23 -->
# KI: Knowledge MCP Server

## Overview
Адаптер Model Context Protocol (MCP), обеспечивающий интерфейс между ИИ-агентами и системой управления знаниями проекта через стандарт JSON-RPC (stdio).

## Key Components

| Class / Function | File | Purpose |
|---|---|---|
| `validate_path` | `knowledge_mcp.py` | Обеспечивает безопасность (песочницу), проверяя пути и расширения файлов. |
| `run_script` | `knowledge_mcp.py` | Унифицированный запуск вспомогательных Python-скриптов из `.know/scripts/`. |
| `METHODS` | `knowledge_mcp.py` | Реестр соответствия имен инструментов MCP внутренним функциям реализации. |
| `main` | `knowledge_mcp.py` | Цикл обработки JSON-RPC сообщений из stdin/stdout. |

## Security & Sandboxing
- **Path Validation**: Любой доступ к файлу через MCP проходит через `validate_path`. Запрещены абсолютные пути и переходы в родительские директории (`..`).
- **Jail Directory**: Все файловые операции ограничены корневой директорией `.know/`. Попытки выхода (Path Traversal) через `..` или абсолютные пути блокируются.
- **Executable Protection**: Инструменты `write_know_file` и `edit_know_file` запрещают модификацию файлов с расширениями `.py`, `.bat`, `.ps1`, `.exe`, `.sh` и др. Это предотвращает самомодификацию кода сервера или инъекции скриптов.
- **Config Protection**: Файл `doc_config.json` защищен от полной перезаписи через `write_know_file`. Допускается только частичное редактирование через `edit_know_file`.
- **Windows UTF-8 Fix**: Принудительная установка кодировки `utf-8` для stdin/stdout/stderr для корректной передачи кириллицы в Windows.

## Available Tools
Сервер предоставляет инструменты для:
1. **Аудита**: `audit_coverage`, `find_unmapped_files`, `analyze_module`.
2. **Управления состоянием**: `save_state`, `restore_mapping`, `check_changes`.
3. **Редактирования**: `read_know_file`, `write_know_file`, `edit_know_file`, `make_know_dir`.
4. **Синхронизации**: `sync_agents_md`, `generate_dir_index`, `analyze_dependencies`.








## Related KIs

## Non-obvious Details
- **Shadowing Python Path**: Скрипт добавляет свою директорию в `sys.path[0]`, чтобы импортировать `ki_utils` и `knowledge_engine` вне зависимости от рабочего окружения.
- **Tool Schema Generation**: Схема входных данных (`inputSchema`) для инструментов генерируется динамически на основе `DEFAULT_TOOLS` при вызове `tools/list`.

## Common Pitfalls
- **Path Traversal Error**: Если агент передает путь, начинающийся с `/` или содержащий `..`, сервер вернет `PermissionError`. Пути должны быть относительными (напр., `knowledge/KI_name.md`).
- **Config Overwrite**: Полная перезапись `doc_config.json` через `write_know_file` заблокирована. Это критический файл конфигурации; его потеря приведет к разрушению связей в базе знаний. Используйте `edit_know_file` для точечных правок.
- **Binary Files**: Сервер предназначен для работы с текстовыми Markdown-файлами. Попытка чтения/записи бинарных данных может привести к ошибкам кодировки.
