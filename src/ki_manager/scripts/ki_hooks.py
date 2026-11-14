"""
ki_hooks.py

Declarative harness installer and hook runtime for ki-manager.
Contains zero hardcoded logic for specific AI coding harnesses: all install targets,
payload extraction paths, and response templates live in JSON harness manifests
under `templates/harnesses/*.json` or project-local `.ki-base/harnesses/*.json`.
"""

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import ki_utils
    import ki_context
    import ki_lint
except ImportError:
    _SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
    if _SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, _SCRIPTS_DIR)
    import ki_utils
    import ki_context
    import ki_lint


_BUNDLED_HARNESSES_DIR = Path(__file__).resolve().parent.parent / "templates" / "harnesses"

_DEFAULT_RUNTIME: Dict[str, Any] = {
    "workspace_paths": ["workspacePaths.0", "cwd", "workspace"],
    "file_arg_paths": [
        "toolCall.args.Path",
        "toolCall.args.TargetFile",
        "toolCall.args.path",
        "tool_input.file_path",
        "tool_input.path",
        "tool_input.target_file",
        "args.path",
        "path",
    ],
    "ignore_paths": [".ki-base/", ".know/", "knowledge/", "decisions/", "AGENTS.md"],
    "ignore_dir_fields": ["artifactDirectoryPath"],
    "stop_skip_if": {"continuationActive": True, "stop_hook_active": True},
    "stop_require_field_equals": {},
    "pre_edit": {
        "allow": {"stdout": {"decision": "allow"}, "exit_code": 0},
        "deny": {"stdout": {"decision": "deny", "reason": "{context}"}, "exit_code": 0},
    },
    "stop_lint": {
        "allow": {"stdout": {}, "exit_code": 0},
        "block": {"stdout": {"decision": "continue", "reason": "{errors}"}, "exit_code": 0},
    },
}


def _harness_search_dirs(project_root: Optional[str] = None) -> List[Path]:
    """Returns harness manifest directories in priority order (project -> user -> bundled)."""
    dirs: List[Path] = []
    roots_to_check: List[Path] = []
    if project_root:
        roots_to_check.append(Path(project_root))
    cwd_path = Path.cwd()
    if all(cwd_path != r for r in roots_to_check):
        roots_to_check.append(cwd_path)

    for root in roots_to_check:
        for kb_name in (".ki-base", ".know"):
            cand = root / kb_name / "harnesses"
            if cand.is_dir() and cand not in dirs:
                dirs.append(cand)

    user_dir = Path.home() / ".ki_base" / "harnesses"
    if user_dir.is_dir() and user_dir not in dirs:
        dirs.append(user_dir)

    if _BUNDLED_HARNESSES_DIR.is_dir():
        dirs.append(_BUNDLED_HARNESSES_DIR)

    return dirs


def list_harnesses(project_root: Optional[str] = None) -> List[Dict[str, Any]]:
    """Discovers available declarative harness manifests in priority order."""
    discovered: Dict[str, Dict[str, Any]] = {}
    for d in _harness_search_dirs(project_root):
        for json_file in sorted(d.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                canonical = str(data.get("name") or json_file.stem).strip()
                key = canonical.lower()
                if key not in discovered:
                    entry = dict(data)
                    entry["_source_path"] = str(json_file)
                    entry.setdefault("name", canonical)
                    entry.setdefault("aliases", [canonical])
                    discovered[key] = entry
            except Exception:
                continue
    return list(discovered.values())


def resolve_harness_config(
    harness_ref: Optional[str],
    project_root: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Loads a harness JSON manifest by path, canonical name, alias, or filename stem."""
    if not harness_ref:
        return None

    ref = str(harness_ref).strip()
    # 1. Direct file path check (cwd or project_root)
    direct_candidates = [Path(ref)]
    if project_root and not os.path.isabs(ref):
        direct_candidates.append(Path(project_root) / ref)

    for cand in direct_candidates:
        if cand.is_file():
            data = json.loads(cand.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"Harness manifest '{cand}' must be a JSON object.")
            data = dict(data)
            data.setdefault("name", cand.stem)
            data["_source_path"] = str(cand.resolve())
            return data

    # 2. Name / alias / stem lookup across discovery directories
    ref_lower = ref.lower()
    available = list_harnesses(project_root)
    for manifest in available:
        name = str(manifest.get("name", "")).strip().lower()
        stem = Path(manifest.get("_source_path", "")).stem.lower()
        aliases = [str(a).strip().lower() for a in (manifest.get("aliases") or [])]
        if ref_lower == name or ref_lower == stem or ref_lower in aliases:
            return manifest

    summary = ", ".join(
        f"{m['name']} (aliases: {', '.join(m.get('aliases', []))})" for m in available
    ) or "none"
    raise FileNotFoundError(
        f"Harness '{harness_ref}' not found. Available manifests: {summary}. "
        "You can also pass a direct path to a custom JSON manifest."
    )


def _substitute_tokens(obj: Any, tokens: Dict[str, str]) -> Any:
    """Recursively replaces `{key}` placeholders in strings inside dicts/lists."""
    if isinstance(obj, str):
        out = obj
        for k, v in tokens.items():
            out = out.replace("{" + k + "}", str(v))
        return out
    if isinstance(obj, list):
        return [_substitute_tokens(item, tokens) for item in obj]
    if isinstance(obj, dict):
        return {k: _substitute_tokens(v, tokens) for k, v in obj.items()}
    return obj


def _contains_ki_command(item: Any) -> bool:
    """Detects ki-manager command entries inside hook handler objects for idempotent merge."""
    if isinstance(item, str):
        low = item.lower()
        return (
            "ki-manager" in low
            or "ki_manager.server" in low
            or "hook pre-edit" in low
            or "hook stop-lint" in low
        )
    if isinstance(item, dict):
        return any(_contains_ki_command(v) for v in item.values())
    if isinstance(item, list):
        return any(_contains_ki_command(v) for v in item)
    return False


def _deep_merge_json(existing: Any, overlay: Any) -> Any:
    """Non-destructive recursive merge supporting both dict maps and hook handler arrays."""
    if isinstance(existing, dict) and isinstance(overlay, dict):
        merged = copy.deepcopy(existing)
        for k, v in overlay.items():
            if k in merged:
                merged[k] = _deep_merge_json(merged[k], v)
            else:
                merged[k] = copy.deepcopy(v)
        return merged

    if isinstance(existing, list) and isinstance(overlay, list):
        # Drop older ki-manager items matching the same matcher (or non-matcher ki entries)
        # so re-running install-hooks is idempotent without deleting unrelated user hooks.
        overlay_has_ki = any(_contains_ki_command(x) for x in overlay)
        result: List[Any] = []
        if overlay_has_ki:
            overlay_matchers = {
                item.get("matcher")
                for item in overlay
                if isinstance(item, dict) and _contains_ki_command(item)
            }
            for item in existing:
                if _contains_ki_command(item):
                    matcher = item.get("matcher") if isinstance(item, dict) else None
                    if matcher in overlay_matchers or item in overlay:
                        continue
                result.append(copy.deepcopy(item))
        else:
            result = copy.deepcopy(existing)

        for item in overlay:
            if item not in result:
                result.append(copy.deepcopy(item))
        return result

    return copy.deepcopy(overlay)


def resolve_ki_command(explicit_cmd: Optional[str] = None) -> str:
    """Determines the shell command prefix to invoke ki-manager from hook configs."""
    if explicit_cmd and explicit_cmd.strip():
        return explicit_cmd.strip()
    if shutil.which("ki-manager"):
        return "ki-manager"
    py = sys.executable.replace("\\", "/")
    return f'"{py}" -m ki_manager.server'


def install_harness_hooks(
    harness_ref: str,
    project_root: Optional[str] = None,
    force: bool = False,
    ki_cmd: Optional[str] = None,
) -> Dict[str, Any]:
    """Installs hooks declaratively according to a harness JSON manifest."""
    proj = str(Path(project_root).resolve() if project_root else Path.cwd().resolve())
    manifest = resolve_harness_config(harness_ref, project_root=proj)
    assert manifest is not None

    install_spec = manifest.get("install")
    if not isinstance(install_spec, dict) or not install_spec.get("target_file") or "merge" not in install_spec:
        raise ValueError(
            f"Harness manifest '{manifest.get('name')}' is missing required 'install.target_file' or 'install.merge'."
        )

    tokens = {
        "ki_cmd": resolve_ki_command(ki_cmd),
        "harness": str(manifest.get("name") or harness_ref),
    }
    overlay = _substitute_tokens(install_spec["merge"], tokens)

    raw_target = str(install_spec["target_file"]).strip()
    if raw_target.startswith("~"):
        target_path = Path(os.path.expanduser(raw_target)).resolve()
    elif os.path.isabs(raw_target):
        target_path = Path(raw_target)
    else:
        target_path = (Path(proj) / raw_target).resolve()

    existing_data: Any = {}
    if target_path.exists():
        raw_text = target_path.read_text(encoding="utf-8", errors="replace").strip()
        if raw_text:
            try:
                existing_data = json.loads(raw_text)
            except json.JSONDecodeError as e:
                if not force:
                    raise ValueError(
                        f"Existing hook config '{target_path}' is not valid JSON ({e}). "
                        "Use --force to overwrite."
                    ) from e
                existing_data = {}

    if not isinstance(existing_data, dict):
        if not force:
            raise ValueError(
                f"Existing hook config '{target_path}' is not a JSON object. Use --force to overwrite."
            )
        existing_data = {}

    merged = _deep_merge_json(existing_data, overlay)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(target_path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, str(target_path))
    except Exception:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise

    return {
        "harness": manifest.get("name"),
        "source_manifest": manifest.get("_source_path"),
        "target_file": str(target_path),
    }


def _extract_dot_path(obj: Any, dot_path: str) -> Any:
    """Resolves a dot-separated path (with optional list indices) against dicts/lists."""
    cur = obj
    for part in dot_path.split("."):
        if isinstance(cur, dict):
            if part not in cur:
                return None
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            return None
    return cur


def _extract_first_str(payload: Dict[str, Any], paths: List[str]) -> Optional[str]:
    for p in paths:
        val = _extract_dot_path(payload, p)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _get_runtime_config(
    payload: Dict[str, Any],
    harness_ref: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Merges default runtime schema, ki_config.json['hooks'], and harness manifest runtime."""
    merged = copy.deepcopy(_DEFAULT_RUNTIME)

    # Project ki_config.json overrides (optional user customization without harness file)
    if project_root:
        for kb_dir in (".ki-base", ".know"):
            cfg_path = Path(project_root) / kb_dir / "ki_config.json"
            if cfg_path.is_file():
                try:
                    ki_cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
                    if isinstance(ki_cfg.get("hooks"), dict):
                        merged.update(ki_cfg["hooks"])
                except Exception:
                    pass
                break

    if harness_ref:
        manifest = resolve_harness_config(harness_ref, project_root=project_root)
        if manifest and isinstance(manifest.get("runtime"), dict):
            for k, v in manifest["runtime"].items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict) and k not in ("stop_skip_if", "stop_require_field_equals"):
                    merged[k].update(v)
                else:
                    merged[k] = v

    return merged


def _resolve_workspace_root(
    payload: Dict[str, Any],
    explicit_workspace: Optional[str],
    runtime: Dict[str, Any],
) -> str:
    if explicit_workspace:
        return ki_utils.normalize_path(explicit_workspace)

    ws = _extract_first_str(payload, runtime.get("workspace_paths", []))
    if ws:
        return ki_utils.normalize_path(ws)

    target = _extract_first_str(payload, runtime.get("file_arg_paths", []))
    if target and os.path.isabs(target):
        cand_dir = os.path.dirname(target)
        match = ki_utils.find_project_by_cwd(cand_dir)
        if match and match.get("workspace"):
            return ki_utils.normalize_path(match["workspace"])
        for parent in [Path(cand_dir), *Path(cand_dir).parents]:
            if (parent / ".ki-base").is_dir() or (parent / ".know").is_dir() or (parent / ".git").exists():
                return str(parent.resolve())

    cwd = os.getcwd()
    match = ki_utils.find_project_by_cwd(cwd)
    if match and match.get("workspace"):
        return ki_utils.normalize_path(match["workspace"])
    return cwd


def _has_initialized_kb(ws_root: str) -> bool:
    for d in (".ki-base", ".know"):
        kb_dir = Path(ws_root) / d
        if (kb_dir / "doc_config.json").is_file() or (kb_dir / "ki_config.json").is_file():
            return True
    if (Path(ws_root) / "doc_config.json").is_file() or (Path(ws_root) / "ki_config.json").is_file():
        return True
    return False


def _is_ignored_target(
    target_file: str,
    ws_root: str,
    payload: Dict[str, Any],
    runtime: Dict[str, Any],
) -> bool:
    # 1. Check artifact / scratch directories from payload fields
    for field in runtime.get("ignore_dir_fields", []) or []:
        dir_val = payload.get(field)
        if isinstance(dir_val, str) and dir_val.strip():
            try:
                if ki_utils.is_subpath(os.path.abspath(target_file), os.path.abspath(dir_val)):
                    return True
            except Exception:
                pass

    # 2. Normalize target relative to workspace root
    rel_norm, _ = ki_context._normalize_rel_path(target_file, ws_root)
    if not rel_norm:
        return False
    rel_key = rel_norm.lower() if os.name == "nt" else rel_norm
    base_key = os.path.basename(rel_key)

    for raw_pat in runtime.get("ignore_paths", []) or []:
        pat = str(raw_pat).strip().replace("\\", "/")
        while pat.startswith("./"):
            pat = pat[2:]
        pat = pat.lstrip("/")
        if not pat:
            continue
        pat_key = pat.lower() if os.name == "nt" else pat
        if pat_key.endswith("/"):
            prefix = pat_key.rstrip("/")
            if rel_key == prefix or rel_key.startswith(prefix + "/"):
                return True
        else:
            if rel_key == pat_key or base_key == pat_key:
                return True
    return False


def _render_outcome(
    outcome_spec: Optional[Dict[str, Any]],
    variables: Dict[str, str],
) -> Tuple[int, Optional[str], Optional[str]]:
    if not isinstance(outcome_spec, dict):
        return 0, None, None

    exit_code = int(outcome_spec.get("exit_code", 0))
    stdout_text: Optional[str] = None
    stderr_text: Optional[str] = None

    if "stdout" in outcome_spec and outcome_spec["stdout"] is not None:
        raw_out = _substitute_tokens(outcome_spec["stdout"], variables)
        stdout_text = json.dumps(raw_out, ensure_ascii=False) if isinstance(raw_out, (dict, list)) else str(raw_out)

    if "stderr" in outcome_spec and outcome_spec["stderr"] is not None:
        raw_err = _substitute_tokens(outcome_spec["stderr"], variables)
        stderr_text = json.dumps(raw_err, ensure_ascii=False) if isinstance(raw_err, (dict, list)) else str(raw_err)

    return exit_code, stdout_text, stderr_text


def handle_pre_edit(
    payload: Dict[str, Any],
    harness: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Tuple[int, Optional[str], Optional[str]]:
    """Checks whether active KI/ADR rules for target file were already delivered."""
    # Pre-resolve rough workspace for harness/config lookup
    rough_ws = project_root or _extract_first_str(payload, _DEFAULT_RUNTIME["workspace_paths"]) or os.getcwd()
    runtime = _get_runtime_config(payload, harness_ref=harness, project_root=rough_ws)
    ws_root = _resolve_workspace_root(payload, project_root, runtime)

    pre_spec = runtime.get("pre_edit", {})
    allow_spec = pre_spec.get("allow", {"exit_code": 0})
    deny_spec = pre_spec.get("deny", {"exit_code": 0})

    target_file = _extract_first_str(payload, runtime.get("file_arg_paths", []))
    if not target_file:
        return _render_outcome(allow_spec, {})

    if not _has_initialized_kb(ws_root):
        return _render_outcome(allow_spec, {})

    if _is_ignored_target(target_file, ws_root, payload, runtime):
        return _render_outcome(allow_spec, {})

    # Check cache state without writing yet
    probe = ki_context.get_context_for(
        files=[target_file],
        project_root=ws_root,
        deduplicate=True,
        record_cache=False,
    )
    has_rules = bool(probe.get("adrs") or probe.get("kis"))
    if not has_rules or probe.get("all_deduplicated"):
        return _render_outcome(allow_spec, {})

    # First encounter (or modified/expired rules): deliver context & cache it so retry passes
    delivered = ki_context.get_context_for(
        files=[target_file],
        project_root=ws_root,
        deduplicate=True,
        record_cache=True,
    )
    return _render_outcome(deny_spec, {"context": delivered.get("text", "")})


def _has_kb_git_changes(ws_root: str) -> Optional[bool]:
    """Returns True if KB files have uncommitted git changes, False if clean, None if non-git."""
    if not os.path.exists(os.path.join(ws_root, ".git")):
        return None
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ws_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        if res.returncode != 0:
            return None
        kb_markers = (".ki-base/", ".know/", "knowledge/", "decisions/", "doc_config.json", "agents.md")
        for line in res.stdout.splitlines():
            if len(line) < 4:
                continue
            raw_path = line[3:].strip()
            if " -> " in raw_path:
                raw_path = raw_path.split(" -> ", 1)[1].strip()
            norm = raw_path.strip('"').replace("\\", "/")
            while norm.startswith("./"):
                norm = norm[2:]
            norm = norm.lstrip("/").lower()
            if any(norm == m or norm.startswith(m) for m in kb_markers):
                return True
        return False
    except Exception:
        return None


def handle_stop_lint(
    payload: Dict[str, Any],
    harness: Optional[str] = None,
    project_root: Optional[str] = None,
) -> Tuple[int, Optional[str], Optional[str]]:
    """Runs ki_lint on Stop event only if KB files changed and no loop guard triggered."""
    rough_ws = project_root or _extract_first_str(payload, _DEFAULT_RUNTIME["workspace_paths"]) or os.getcwd()
    runtime = _get_runtime_config(payload, harness_ref=harness, project_root=rough_ws)
    ws_root = _resolve_workspace_root(payload, project_root, runtime)

    stop_spec = runtime.get("stop_lint", {})
    allow_spec = stop_spec.get("allow", {"exit_code": 0})
    block_spec = stop_spec.get("block", {"exit_code": 0})

    # Loop & cancellation guards
    for k, skip_val in (runtime.get("stop_skip_if") or {}).items():
        if payload.get(k) == skip_val:
            return _render_outcome(allow_spec, {})

    for k, req_val in (runtime.get("stop_require_field_equals") or {}).items():
        if k in payload and payload.get(k) is not None and payload.get(k) != req_val:
            return _render_outcome(allow_spec, {})

    if not _has_initialized_kb(ws_root):
        return _render_outcome(allow_spec, {})

    kb_dirty = _has_kb_git_changes(ws_root)
    if kb_dirty is False:
        return _render_outcome(allow_spec, {})

    lint_res = ki_lint.lint_knowledge_base(project_root=ws_root)
    if lint_res.get("ok", True):
        return _render_outcome(allow_spec, {})

    report = ki_lint.format_lint_report(lint_res)
    return _render_outcome(block_spec, {"errors": report})


def run_hook_cli(
    hook_event: str,
    harness: Optional[str] = None,
    project_root: Optional[str] = None,
    stdin_text: Optional[str] = None,
) -> int:
    """CLI handler for `ki-manager hook <pre-edit|stop-lint>`."""
    raw = stdin_text if stdin_text is not None else sys.stdin.read()
    payload: Dict[str, Any] = {}
    if raw and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}

    if hook_event == "pre-edit":
        code, out, err = handle_pre_edit(payload, harness=harness, project_root=project_root)
    elif hook_event == "stop-lint":
        code, out, err = handle_stop_lint(payload, harness=harness, project_root=project_root)
    else:
        print(f"Unknown hook event: {hook_event}", file=sys.stderr)
        return 1

    if out is not None:
        print(out)
    if err is not None:
        print(err, file=sys.stderr)
    return code
