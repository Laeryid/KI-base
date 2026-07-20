import os
import sys
import json
from pathlib import Path

def detect_venv(root_dir: str) -> str:
    # Mimic the detect_venv logic
    venv_scripts = Path(root_dir) / ".venv" / "Scripts"
    fake_py = venv_scripts / "python.exe"
    if fake_py.exists():
        return str(fake_py.as_posix())
    return str(Path(sys.executable).as_posix())

def setup_gitignore(project_root: str, is_master: bool = False) -> None:
    gitignore = Path(project_root) / ".gitignore"
    if is_master:
        content = (
            "# KI_base: Master repository mode\n"
            "!scripts/\n"
            "!tests/\n"
            "!knowledge/\n"
        )
    else:
        content = (
            "# KI_base: Project mode\n"
            "scripts/\n"
            "tests/\n"
            "!knowledge/\n"
        )
    gitignore.write_text(content, encoding="utf-8")

def find_knowledge_root():
    # Helper to find .know or other knowledge dir
    cwd = Path.cwd()
    # Check if there is a .know folder in current directory
    if (cwd / ".know").exists():
        return cwd / ".know"
    return cwd

def init_ki_system() -> None:
    # Parse arguments
    project_root = None
    is_master = False
    for arg in sys.argv:
        if arg.startswith("--project-root="):
            project_root = Path(arg.split("=")[1])
        elif arg == "--master":
            is_master = True
            
    if not project_root:
        project_root = Path.cwd()
        
    know_dir = project_root / ".know"
    if not know_dir.exists():
        know_dir = project_root
        
    setup_gitignore(str(know_dir), is_master=is_master)
    
    # Read/write ki_config.json
    ki_config_path = know_dir / "ki_config.json"
    existing_cfg = {}
    if ki_config_path.exists():
        try:
            existing_cfg = json.loads(ki_config_path.read_text(encoding="utf-8"))
        except Exception:
            pass
            
    # Update config but preserve custom settings
    if "paths" not in existing_cfg:
        existing_cfg["paths"] = {}
    existing_cfg["paths"]["knowledge_root"] = ".know"
    existing_cfg["paths"]["project_root"] = ".."
    
    ki_config_path.write_text(json.dumps(existing_cfg, indent=4), encoding="utf-8")
