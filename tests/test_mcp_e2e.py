"""
test_mcp_e2e.py

End-to-End integration test for the ki-manager MCP server running as an actual subprocess.
Tests JSON-RPC stdio protocol, handshake, tools listing, and tool execution.
"""

import os
import sys
import json
import subprocess
import pytest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


class MCPClientSession:
    """Helper client to simulate an IDE communicating with ki-manager over stdio."""

    def __init__(self, workspace_path: str = None):
        self.workspace_path = workspace_path or str(ROOT_DIR)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT_DIR / "src")
        env["PYTHONIOENCODING"] = "utf-8"

        self.proc = subprocess.Popen(
            [sys.executable, "-m", "ki_manager.server", "--workspace", self.workspace_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            bufsize=1,
        )
        self.req_id = 0

    def send_request(self, method: str, params: dict = None, timeout: float = 5.0) -> dict:
        self.req_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
            "params": params or {},
        }
        raw_req = json.dumps(req, ensure_ascii=False)
        self.proc.stdin.write(raw_req + "\n")
        self.proc.stdin.flush()

        line = self.proc.stdout.readline()
        if not line:
            stderr_out = self.proc.stderr.read()
            raise RuntimeError(f"Server closed connection unexpectedly. Stderr: {stderr_out}")

        return json.loads(line)

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.stdout.close()
            self.proc.stderr.close()
            self.proc.terminate()
            self.proc.wait(timeout=2.0)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


@pytest.fixture
def e2e_project(tmp_path):
    """Creates a temporary project with initialized .ki-base."""
    ki_base = tmp_path / ".ki-base"
    ki_base.mkdir(parents=True, exist_ok=True)
    
    ki_config = {
        "project_name": "E2ETestProject",
        "knowledge_root": ".ki-base",
        "language": "python"
    }
    (ki_base / "ki_config.json").write_text(json.dumps(ki_config), encoding="utf-8")

    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "app.py").write_text("print('hello')\n", encoding="utf-8")

    doc_config = {
        "knowledge_items": {
            "KI_app.md": {
                "summary": "Main application",
                "depends_on": ["src/app.py"]
            }
        }
    }
    (ki_base / "doc_config.json").write_text(json.dumps(doc_config), encoding="utf-8")
    return tmp_path


@pytest.fixture
def mcp_session(e2e_project):
    session = MCPClientSession(workspace_path=str(e2e_project))
    yield session
    session.close()


@pytest.mark.positive
def test_e2e_server_discover_handshake(mcp_session, e2e_project):
    """Verifies modern MCP handshake 'server/discover'."""
    resp = mcp_session.send_request("server/discover", {
        "_meta": {
            "io.modelcontextprotocol/clientInfo": {
                "workspaceUri": f"file:///{str(e2e_project).replace(os.sep, '/')}"
            }
        }
    })
    assert resp.get("jsonrpc") == "2.0"
    assert "result" in resp
    res = resp["result"]
    assert res.get("serverInfo", {}).get("name") == "ki-manager"
    assert "protocolVersion" in res


@pytest.mark.positive
def test_e2e_initialize_legacy_handshake(mcp_session, e2e_project):
    """Verifies standard/legacy MCP handshake 'initialize'."""
    resp = mcp_session.send_request("initialize", {
        "rootUri": f"file:///{str(e2e_project).replace(os.sep, '/')}"
    })
    assert resp.get("jsonrpc") == "2.0"
    assert "result" in resp
    assert resp["result"].get("serverInfo", {}).get("name") == "ki-manager"


@pytest.mark.positive
def test_e2e_tools_list(mcp_session):
    """Verifies tools/list enumerates expected core tools including ki_graph_visualize."""
    mcp_session.send_request("server/discover")

    resp = mcp_session.send_request("tools/list")
    assert "result" in resp
    tools = resp["result"].get("tools", [])
    tool_names = {t["name"] for t in tools}

    assert "ki_instructions" in tool_names
    assert "audit_coverage" in tool_names
    assert "ki_status" in tool_names
    assert "ki_graph_visualize" in tool_names


@pytest.mark.positive
def test_e2e_tool_call_instructions(mcp_session):
    """Verifies executing a tool call returns proper content structure."""
    mcp_session.send_request("server/discover")

    resp = mcp_session.send_request("tools/call", {
        "name": "ki_instructions",
        "arguments": {"document": "overview"}
    })
    assert "result" in resp
    content = resp["result"].get("content", [])
    assert len(content) > 0
    assert "Global AI Instructions" in content[0]["text"]


@pytest.mark.positive
def test_e2e_tool_call_graph_visualize(mcp_session):
    """Verifies calling ki_graph_visualize via MCP stdio protocol."""
    mcp_session.send_request("server/discover")

    resp = mcp_session.send_request("tools/call", {
        "name": "ki_graph_visualize",
        "arguments": {"mode": "ki-only"}
    })
    assert "result" in resp
    content = resp["result"].get("content", [])
    assert len(content) > 0
    assert "```mermaid" in content[0]["text"]


@pytest.mark.negative
def test_e2e_unknown_method(mcp_session):
    """Verifies unknown methods return JSON-RPC error -32601."""
    resp = mcp_session.send_request("non_existent_method")
    # server returns {"result": {"isError": True, "error": {"code": -32601}}}
    error_obj = resp.get("error") or resp.get("result", {}).get("error", {})
    assert error_obj.get("code") == -32601
