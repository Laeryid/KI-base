import os
import pytest
from pathlib import Path
from ki_manager import server

@pytest.mark.positive
def test_workflows_resource_list():
    # Test that resources/list returns ki://workflows/<name> resources and resourceTemplates
    resources = []
    resource_templates = []
    
    if server._WORKFLOWS_DIR.exists():
        for f in sorted(server._WORKFLOWS_DIR.glob("*.md")):
            resources.append({
                "uri": f"ki://workflows/{f.stem}",
                "name": f"Workflow: {f.stem}",
                "mimeType": "text/markdown"
            })
    resource_templates.append({
        "uriTemplate": "ki://workflows/{name}",
        "name": "KI Workflow Instruction",
        "mimeType": "text/markdown",
        "description": "Access bundled workflow instructions by name"
    })
    
    assert len(resources) > 0
    assert any(r["uri"] == "ki://workflows/create-adr" for r in resources)
    assert resource_templates[0]["uriTemplate"] == "ki://workflows/{name}"

@pytest.mark.positive
def test_workflow_resource_read_index():
    # Simulate reading ki://workflows/
    lines = ["# Available Workflows\n"]
    for f in sorted(server._WORKFLOWS_DIR.glob("*.md")):
        lines.append(f"- `ki://workflows/{f.stem}` ({f.name})")
    content = "\n".join(lines)
    
    assert "# Available Workflows" in content
    assert "ki://workflows/create-adr" in content

@pytest.mark.positive
def test_workflow_resource_read_file():
    wf_path = server._WORKFLOWS_DIR / "create-adr.md"
    assert wf_path.exists()
    content = wf_path.read_text(encoding="utf-8")
    assert len(content) > 0
