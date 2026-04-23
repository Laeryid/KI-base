<!-- last_verified: 2026-04-23 -->
# KI: Knowledge Testing - Core & Infrastructure

## Overview
Инфраструктура тестирования системы управления знаниями Pocket Team. Обеспечивает проверку движка (Engine), аудита и интеграции с MCP в изолированных условиях.

## Key Components
| Class / Function | File | Purpose |
|---|---|---|
| `tmp_project` fixture | `.know/tests/conftest.py` | Создает временную структуру проекта с `.know`, `doc_config.json` и фиктивным исходным кодом. |
| `KnowledgeEngine` tests | `.know/tests/test_knowledge_engine.py`, `test_knowledge_engine_extra.py` | Проверка захвата состояния, расчета хешей, обнаружения изменений и связки с артефактами. |
| `Audit` tests | `.know/tests/test_audit_coverage.py`, `test_analyze_module.py` | Проверка корректности расчета Density (плотности) и выявления Blind Spots. |
| `Security` tests | `.know/tests/test_mcp_security.py` | Валидация защиты от Path Traversal и ограничение доступа только к папке `.know`. |
| `Edge Cases` | `.know/tests/test_edge_cases.py` | Тестирование поведения при пустых файлах, битых JSON и отсутствии конфигурации. |

## Testing Strategy
- **File System Isolation**: Все тесты используют фикстуру `tmp_path` из pytest. Движок знаний инициализируется внутри этой временной папки.
- **Mocking Scripts**: Тесты `scripts/` часто импортируют функционал напрямую через манипуляцию с `sys.path` в `conftest.py`.
- **Validation Markers**: Используются маркеры `@pytest.mark.positive` and `@pytest.mark.negative` для разделения сценариев успеха и обработки ошибок.

## How to Run
Для запуска тестов системы знаний используйте команду:
```powershell
.venv\Scripts\python.exe -m pytest .know/tests/
```






## Related KIs

