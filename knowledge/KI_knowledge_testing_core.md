<!-- last_verified: 2026-04-21 -->
# KI: Knowledge System Core Testing

## Overview
Тестирование низкоуровневых механизмов системы знаний: движка (Engine), безопасности MCP-прокси и базовых утилит.

## Key Components
| File | Purpose |
|---|---|
| `.know/tests/conftest.py` | Инфраструктура тестов: фикстура `tmp_project` для создания изолированной среды `.know`. |
| `.know/tests/test_knowledge_engine.py` | Валидация базового цикла: сканирование -> расчет хешей -> обнаружение изменений. |
| `.know/tests/test_knowledge_engine_extra.py` | Расширенные тесты движка: обработка скрытых файлов, прав доступа и больших объемов данных. |
| `.know/tests/test_mcp_security.py` | Тестирование защиты от выхода за пределы `.know` (Path Traversal) и прав на запись. |
| `.know/tests/test_mcp_arguments.py` | Проверка валидации аргументов MCP-инструментов и обработки некорректных типов данных. |
| `.know/tests/test_edge_cases.py` | Тестирование стабильности при отсутствии `doc_config.json`, пустых директориях и поврежденных индексах. |
| `.know/tests/test_ki_utils.py` | Тесты вспомогательных функций для парсинга markdown и работы с путями. |

## Non-obvious Details
- **Path Isolation**: Тесты принудительно переопределяют путь к `.know`, чтобы не затронуть реальную базу знаний проекта.
- **Fixture Lifecycle**: Фикстура `tmp_project` автоматически очищается после каждого теста, предотвращая накопление "грязного" состояния.






## Related KIs

