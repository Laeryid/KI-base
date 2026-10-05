---
name: ki-manager-workflows
description: >-
  Skill for writing, modifying, and maintaining ki-manager workflow instructions.
  Triggered by requests to edit or create workflows in src/ki_manager/workflows/ or
  GLOBAL_INSTRUCTIONS. Enforces dual-mode directives (full vs compact) so instructions
  render valid tool calls for both standard and facade MCP clients.
---

# ki-manager: Разработка и поддержка инструкций (Workflows)

## Overview

В `ki-manager` инструкции для AI-агентов поставляются через:
- MCP-инструмент `ki_instructions(document="...")`
- MCP Prompts (`knowledge-instructions`, `scaffold-knowledge`, etc.)
- Виртуальные ресурсы `ki://instructions.md` и `ki://workflows/*`
- Файлы `instructions.md` в каталогах IDE
- Agent Skills (`ki-manager install-skills`)

Сервер поддерживает два режима экспозиции инструментов:
1. **`--tool-mode full`** — доступны 33 инструмента напрямую.
2. **`--tool-mode compact`** — доступны только 6 инструментов (`ki_instructions`, `ki_search`, `ki_read`, `ki_tools`, `ki_call`, `ki_mutate`).

> [!IMPORTANT]
> Все workflow-инструкции в `src/ki_manager/workflows/*.md` и `GLOBAL_INSTRUCTIONS` в `server.py` **ОБЯЗАНЫ поддерживать оба режима** через директивы шаблонного рендеринга.

---

## Trigger phrases

Скилл активируется при:
- «добавь новый воркфло» / «создай workflow»
- «обнови инструкцию» / «отредактируй воркфло»
- редактировании файлов в `src/ki_manager/workflows/*.md`
- изменении `GLOBAL_INSTRUCTIONS` в `src/ki_manager/server.py`

---

## Директивы шаблонного рендеринга

В файлах Markdown используются HTML-комментарии, которые обрабатываются функцией `render_instruction()`:

### 1. Блок с альтернативой (if-compact / else-compact)
```markdown
<!-- if-compact -->
`ki_call(tool="audit_coverage")`
<!-- else-compact -->
`audit_coverage()`
<!-- /if-compact -->
```

### 2. Блок только для full режима
```markdown
<!-- if-full -->
Текст, видимый только при полном списке инструментов.
<!-- /if-full -->
```

### 3. Динамическая подстановка папки знаний
`{{KI_DIR}}` автоматически заменяется на имя активной папки базы знаний (`.ki-base` или `knowledge`).

---

## Правила сопоставления инструментов (Tool Mapping)

| Инструмент / Действие | В режиме `full` | В режиме `compact` |
|---|---|---|
| **Чтение документации** | `ki_read(rel_path="...")` или `read_know_file` | `ki_read(rel_path="...", section="...", max_chars=...)` |
| **Поиск по знаниям / ADR** | `ki_search(query="...")` | `ki_search(query="...", scope="all\|ki\|adr")` |
| **Read-Only анализ** (`audit_coverage`, `generate_dir_index`, `analyze_dependencies`, `ki_scaffold_status`, `git_diff_secured`, etc.) | Прямой вызов: `audit_coverage()` | Через `ki_call`: `ki_call(tool="audit_coverage", args={...})` |
| **Мутирующие операции** (`ki_scaffold`, `ki_finalize_scaffolds`, `update_last_verified`, `create_adr`, `write_know_file`, `edit_know_file`, `git_checkpoint`, `save_state`) | Прямой вызов: `create_adr(...)`, `write_know_file(...)` | Через `ki_mutate`: `ki_mutate(tool="create_adr", args={...})` |
| **Просмотр схем инструментов** | Встроенная схема IDE | `ki_tools()` (каталог) или `ki_tools(name="<tool_name>")` |

---

## Стандарт оформления Frontmatter

Каждый workflow-файл в `src/ki_manager/workflows/` обязан содержать frontmatter с директивой `allowed-tools`:

```markdown
---
name: ki-manager-<workflow-name>
description: <Краткое описание на английском>
metadata:
  author: ki-manager
  version: "1.X"
<!-- if-compact -->
allowed-tools: ki_instructions ki_read ki_search ki_tools ki_call ki_mutate
<!-- else-compact -->
allowed-tools: <полный список инструментов, используемых в воркфло>
<!-- /if-compact -->
---
```

---

## Чеклист перед коммитом изменений в воркфло

1. [ ] В файле нет прямых вызовов скрытых инструментов вне блоков `<!-- else-compact -->` или `<!-- if-full -->`.
2. [ ] В `<!-- if-compact -->` вызовы используют `ki_call` (для read-only) и `ki_mutate` (для мутирующих).
3. [ ] В `Safety & Tooling Rules` отражены оба режима.
4. [ ] Добавлены/обновлены тесты в `tests/test_instruction_rendering.py`.
5. [ ] Запущен pytest: `.venv\Scripts\pytest.exe tests/test_instruction_rendering.py`.
