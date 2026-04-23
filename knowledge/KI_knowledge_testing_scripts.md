<!-- last_verified: 2026-04-23 -->
# KI: Knowledge Testing - Scripts & Helpers

## Overview
Детальное описание тестов для вспомогательных скриптов инициализации и синхронизации системы знаний. Эти тесты проверяют корректность настройки окружения, обновления файлов инструкций (`AGENTS.md`) и конфигурации `.gitignore`.

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `test_init_ki_system.py` | `.know/tests/test_init_ki_system.py` | Проверка обнаружения venv, обновления `.gitignore` (идемпотентность) и добавления секций в `AGENTS.md`. |
| `test_sync_and_add_ki.py` | `.know/tests/test_sync_and_add_ki.py` | Тестирование синхронизации таблицы KI в `AGENTS.md` и регистрации новых KI в `doc_config.json`. |
| `test_ki_utils.py` | `.know/tests/test_ki_utils.py` | Валидация логики поиска корня знаний и загрузки конфигурации из разных источников. |

## Non-obvious Details
- **Hardlink Support**: Тесты проверяют создание жестких ссылок для воркфлоу, что требует нахождения источника и цели на одном физическом диске.
- **Idempotency**: Все скрипты обновления файлов (`.gitignore`, `AGENTS.md`) спроектированы так, чтобы повторный запуск не дублировал данные.

## Common Pitfalls
- **Python Path**: Скрипты в тестах часто добавляют `../scripts` в `sys.path`. При изменении структуры папок тесты могут перестать находить модули.
- **Venv Detection**: `detect_venv` ищет стандартные имена (`.venv`, `venv`). Если используется нестандартное имя, тесты могут упасть или использовать системный интерпретатор.







## Related KIs

