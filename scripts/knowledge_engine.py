"""
knowledge_engine.py

Core logic of the knowledge management system:
- Hashing files
- Tracking state (doc_state.json)
- Identifying modified/new/deleted files
- Mapping changes to artifacts and knowledge items
"""

import os
import hashlib
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


class KnowledgeEngine:
    def __init__(self, project_root: str, knowledge_root: str = ".know"):
        self.project_root = Path(project_root).resolve()
        self.knowledge_root = self.project_root / knowledge_root
        self.state_file = self.knowledge_root / "doc_state.json"
        self.config_file = self.knowledge_root / "doc_config.json"
        self._doc_config = None

    @property
    def doc_config(self) -> Dict[str, Any]:
        """Loads doc_config.json (knowledge system manifest)."""
        if self._doc_config is None:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self._doc_config = json.load(f)
            else:
                self._doc_config = {}
        return self._doc_config

    def _calculate_file_hash(self, filepath: str) -> str:
        """Computes the SHA-256 hash of a file."""
        sha256_hash = hashlib.sha256()
        try:
            with open(filepath, "rb") as f:
                for byte_block in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(byte_block)
            return sha256_hash.hexdigest()
        except Exception:
            return ""

    def load_state(self) -> Dict:
        """Loads state from doc_state.json."""
        if not os.path.exists(self.state_file):
            return {}
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
        return {}

    def save_state(self, state: Dict[str, Any]) -> None:
        """Saves the state to doc_state.json."""
        os.makedirs(self.knowledge_root, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=4, ensure_ascii=False)

    def _collect_deps(self, depends_on: List[str], tracked_files: Dict[str, str]) -> None:
        """Recursively collects dependencies from the config."""
        knowledge_foldername = self.knowledge_root.name
        EXCLUDE = {".git", "__pycache__", "node_modules", "venv", ".venv",
                   "dist", "build", knowledge_foldername}
        for dep in depends_on:
            full_path = self.project_root / dep
            if full_path.is_file():
                rel_path = os.path.relpath(full_path, self.project_root)
                tracked_files[rel_path] = str(full_path)
            elif full_path.is_dir():
                for root, dirs, files in os.walk(full_path):
                    dirs[:] = [d for d in dirs if d not in EXCLUDE]
                    for f in files:
                        abspath = os.path.join(root, f)
                        rel_path = os.path.relpath(abspath, self.project_root)
                        tracked_files[rel_path] = abspath

    def scan_tracked_files(self) -> Dict[str, Dict[str, Any]]:
        """Scans all tracked files and returns their metadata (mtime, abspath)."""
        config = self.doc_config
        tracked_files = {}
        for artifact in config.get("artifacts", {}).values():
            self._collect_deps(artifact.get("depends_on", []), tracked_files)
        for ki_info in config.get("knowledge_items", {}).values():
            self._collect_deps(ki_info.get("depends_on", []), tracked_files)

        current_state_meta = {}
        for rel_path, abspath in tracked_files.items():
            try:
                current_state_meta[rel_path] = {
                    "mtime": os.path.getmtime(abspath),
                    "abspath": abspath
                }
            except OSError:
                continue
        return current_state_meta

    def capture_full_state(self) -> Dict[str, Any]:
        """Captures the full state (hashes and mtimes) for all tracked files."""
        current_meta = self.scan_tracked_files()
        state = {}
        for rel_path, info in current_meta.items():
            state[rel_path] = {
                "hash": self._calculate_file_hash(info["abspath"]),
                "mtime": info["mtime"]
            }
        return state

    def check_for_changes(self) -> Tuple[List[str], List[str], List[str]]:
        """
        Compares the current state with the saved state.
        Returns (modified, new, deleted).
        """
        saved_state = self.load_state()
        current_meta = self.scan_tracked_files()
        modified, new, deleted = [], [], []

        for rel_path, info in current_meta.items():
            if rel_path not in saved_state:
                new.append(rel_path)
            else:
                saved = saved_state[rel_path]
                if info["mtime"] > saved.get("mtime", 0):
                    if self._calculate_file_hash(info["abspath"]) != saved.get("hash"):
                        modified.append(rel_path)

        for rel_path in saved_state:
            if rel_path not in current_meta:
                deleted.append(rel_path)

        return modified, new, deleted

    def get_affected_artifacts_map(self, changed_files: List[str]) -> Dict[str, List[str]]:
        """Maps changed files to artifacts that depend on them."""
        return self._build_affected_map(changed_files, self.doc_config.get("artifacts", {}))

    def get_affected_ki_map(self, changed_files: List[str]) -> Dict[str, List[str]]:
        """Maps changed files to Knowledge Items that depend on them."""
        return self._build_affected_map(changed_files, self.doc_config.get("knowledge_items", {}))

    def _build_affected_map(self, changed_files: List[str],
                             entries: Dict[str, Any]) -> Dict[str, List[str]]:
        """Internal helper to build the affected items map."""
        affected_map = {}
        for entry_path, entry_info in entries.items():
            dependencies = entry_info.get("depends_on", [])
            relevant_changes = []
            for dep in dependencies:
                norm_dep = os.path.normpath(dep).replace("\\", "/")
                for changed_file in changed_files:
                    norm_changed = os.path.normpath(changed_file).replace("\\", "/")
                    if norm_changed == norm_dep or norm_changed.startswith(norm_dep + "/"):
                        if changed_file not in relevant_changes:
                            relevant_changes.append(changed_file)
            if relevant_changes:
                affected_map[entry_path] = relevant_changes
        return affected_map

    def get_staleness_report(self) -> Dict[str, Any]:
        """Generates a complete report of changes and stale documentation."""
        modified, new, deleted = self.check_for_changes()
        changed = modified + new
        return {
            "changed_files": {"modified": modified, "new": new, "deleted": deleted},
            "stale_artifacts": self.get_affected_artifacts_map(changed),
            "stale_knowledge_items": self.get_affected_ki_map(changed),
            "summary": {
                "changed_files_count": len(changed),
                "generated_at": datetime.utcnow().isoformat(),
            }
        }
