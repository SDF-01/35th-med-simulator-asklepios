#!/usr/bin/env python3
"""Content-addressed primitives for the Project Asklepios release graph.

The graph is intentionally implemented with the Python standard library so the
package can authenticate and inspect its own release orchestration before npm,
Lean, or application dependencies are installed.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

GRAPH_PATH = Path("config/release/RELEASE_GRAPH.json")
CLASSIFICATIONS = ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ReleaseGraphError(RuntimeError):
    """Raised when a graph, lock, path, receipt, or plan is structurally unsafe."""


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_repository_bytes(path: Path) -> bytes:
    """Return cross-platform source identity bytes.

    UTF-8 text is normalized to LF so a Windows CRLF checkout cannot change the
    release identity. A UTF-8 BOM is rejected rather than silently stripped.
    Binary or non-UTF-8 files retain byte identity.
    """
    value = path.read_bytes()
    if value.startswith(b"\xef\xbb\xbf"):
        raise ReleaseGraphError(f"UTF-8 BOM forbidden in locked input:{path}")
    if b"\x00" in value:
        return value
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return value
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def sha256_repository_file(path: Path) -> str:
    return sha256_bytes(canonical_repository_bytes(path))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReleaseGraphError(f"required JSON missing:{path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReleaseGraphError(f"invalid JSON:{path}:{type(exc).__name__}:{exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseGraphError(f"JSON root is not an object:{path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _safe_relative(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ReleaseGraphError(f"unsafe repository path:{value!r}")
    normalized = value.replace("\\", "/")
    pure = PurePosixPath(normalized)
    if pure.is_absolute() or normalized.startswith("/") or any(part in {"", ".", ".."} for part in pure.parts):
        raise ReleaseGraphError(f"unsafe repository path:{value}")
    return pure.as_posix()


def _matches(path: str, pattern: str) -> bool:
    pattern = pattern.replace("\\", "/")
    pure = PurePosixPath(path)
    return fnmatch.fnmatchcase(path, pattern) or pure.match(pattern)


def _expand_pattern(root: Path, pattern: str) -> list[Path]:
    pattern = _safe_relative(pattern)
    # pathlib handles ** deterministically and does not follow directory symlinks.
    candidates = list(root.glob(pattern))
    exact = root / pattern
    if exact.exists() and exact not in candidates:
        candidates.append(exact)
    result: list[Path] = []
    for candidate in candidates:
        if candidate.is_symlink():
            raise ReleaseGraphError(f"symlink forbidden in locked input:{candidate.relative_to(root).as_posix()}")
        if candidate.is_dir():
            for child in sorted(candidate.rglob("*")):
                if child.is_symlink():
                    raise ReleaseGraphError(f"symlink forbidden in locked input:{child.relative_to(root).as_posix()}")
                if child.is_file():
                    result.append(child)
        elif candidate.is_file():
            result.append(candidate)
    return result


def collect_input_files(root: Path, specification: Mapping[str, Any]) -> dict[str, str]:
    include = specification.get("include", [])
    exclude = specification.get("exclude", [])
    if not isinstance(include, list) or not all(isinstance(item, str) for item in include):
        raise ReleaseGraphError("input-set include must be a string list")
    if not isinstance(exclude, list) or not all(isinstance(item, str) for item in exclude):
        raise ReleaseGraphError("input-set exclude must be a string list")
    paths: dict[str, Path] = {}
    for pattern in include:
        for candidate in _expand_pattern(root, pattern):
            relative = candidate.relative_to(root).as_posix()
            if any(_matches(relative, blocked) for blocked in exclude):
                continue
            paths[relative] = candidate
    return {relative: sha256_repository_file(paths[relative]) for relative in sorted(paths)}


def lock_input_sets(root: Path, graph: dict[str, Any], selected: Iterable[str] | None = None) -> dict[str, Any]:
    root = root.resolve()
    graph = json.loads(json.dumps(graph))
    input_sets = graph.get("input_sets")
    if not isinstance(input_sets, dict):
        raise ReleaseGraphError("input_sets must be an object")
    names = list(selected) if selected is not None else sorted(input_sets)
    for set_id in names:
        if set_id not in input_sets:
            raise ReleaseGraphError(f"unknown input set:{set_id}")
        input_sets[set_id]["files"] = collect_input_files(root, input_sets[set_id])
    return graph


def verify_input_set(root: Path, set_id: str, specification: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = specification.get("files")
    if not isinstance(expected, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in expected.items()):
        return [f"input set lock malformed:{set_id}"]
    try:
        observed = collect_input_files(root.resolve(), specification)
    except Exception as exc:  # noqa: BLE001 - surfaced as a fail-closed lock error
        return [f"input set inventory failed:{set_id}:{type(exc).__name__}:{exc}"]
    missing = sorted(set(expected) - set(observed))
    extra = sorted(set(observed) - set(expected))
    if missing:
        errors.append(f"input set files missing:{set_id}:{missing}")
    if extra:
        errors.append(f"input set files added:{set_id}:{extra}")
    for path in sorted(set(expected) & set(observed)):
        if expected[path] != observed[path]:
            errors.append(f"input set hash differs:{set_id}:{path}")
    return errors


def _validate_output_descriptor(value: Any) -> None:
    if isinstance(value, str):
        _safe_relative(value)
        return
    if isinstance(value, dict) and isinstance(value.get("path"), str):
        _safe_relative(value["path"])
        if "required" in value and not isinstance(value["required"], bool):
            raise ReleaseGraphError(f"output required flag is not Boolean:{value['path']}")
        return
    raise ReleaseGraphError(f"invalid output descriptor:{value!r}")


def load_graph(root: Path, graph_path: Path = GRAPH_PATH) -> dict[str, Any]:
    root = root.resolve()
    path = graph_path if graph_path.is_absolute() else root / graph_path
    graph = read_json(path)
    if graph.get("schema_version") != "1.0.0":
        raise ReleaseGraphError("release graph schema differs")
    graph_id = graph.get("graph_id")
    if not isinstance(graph_id, str) or not _SAFE_ID.fullmatch(graph_id):
        raise ReleaseGraphError("release graph ID is unsafe")
    if graph.get("classifications") != CLASSIFICATIONS:
        raise ReleaseGraphError("classification vocabulary differs")
    input_sets = graph.get("input_sets")
    if not isinstance(input_sets, dict) or not input_sets:
        raise ReleaseGraphError("input_sets must be a nonempty object")
    for set_id, specification in input_sets.items():
        if not isinstance(set_id, str) or not _SAFE_ID.fullmatch(set_id):
            raise ReleaseGraphError(f"unsafe input set ID:{set_id}")
        if not isinstance(specification, dict):
            raise ReleaseGraphError(f"input set is not an object:{set_id}")
        for key in ("include", "exclude"):
            if not isinstance(specification.get(key), list):
                raise ReleaseGraphError(f"input set {key} is not a list:{set_id}")
        if not isinstance(specification.get("files"), dict):
            raise ReleaseGraphError(f"input set files lock missing:{set_id}")
    managed = graph.get("managed_package_scripts")
    if not isinstance(managed, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in managed.items()):
        raise ReleaseGraphError("managed_package_scripts must be a string map")
    stages = graph.get("stages")
    if not isinstance(stages, list) or not stages:
        raise ReleaseGraphError("stages must be a nonempty list")
    seen: set[str] = set()
    order: dict[str, int] = {}
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise ReleaseGraphError(f"stage is not an object:{index}")
        stage_id = stage.get("id")
        if not isinstance(stage_id, str) or not _SAFE_ID.fullmatch(stage_id):
            raise ReleaseGraphError(f"unsafe stage ID:{stage_id}")
        if stage_id in seen:
            raise ReleaseGraphError(f"duplicate stage ID:{stage_id}")
        seen.add(stage_id)
        order[stage_id] = index
        command = stage.get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise ReleaseGraphError(f"stage command differs:{stage_id}")
        needs = stage.get("needs")
        if not isinstance(needs, list) or not all(isinstance(item, str) for item in needs):
            raise ReleaseGraphError(f"stage needs differs:{stage_id}")
        set_ids = stage.get("input_sets")
        if not isinstance(set_ids, list) or not all(isinstance(item, str) for item in set_ids):
            raise ReleaseGraphError(f"stage input sets differ:{stage_id}")
        for set_id in set_ids:
            if set_id not in input_sets:
                raise ReleaseGraphError(f"stage references unknown input set:{stage_id}:{set_id}")
        outputs = stage.get("outputs")
        if not isinstance(outputs, list):
            raise ReleaseGraphError(f"stage outputs differ:{stage_id}")
        for output in outputs:
            _validate_output_descriptor(output)
        if stage.get("failure_classification") not in CLASSIFICATIONS:
            raise ReleaseGraphError(f"stage failure classification differs:{stage_id}")
        if not isinstance(stage.get("read_only"), bool):
            raise ReleaseGraphError(f"stage read_only differs:{stage_id}")
    for stage in stages:
        for dependency in stage["needs"]:
            if dependency not in seen:
                raise ReleaseGraphError(f"stage dependency missing:{stage['id']}:{dependency}")
            if order[dependency] >= order[stage["id"]]:
                raise ReleaseGraphError(f"stage order is not topological:{stage['id']}:{dependency}")
    targets = graph.get("targets")
    if not isinstance(targets, dict) or not targets:
        raise ReleaseGraphError("targets must be a nonempty object")
    for target, specification in targets.items():
        if not isinstance(target, str) or not _SAFE_ID.fullmatch(target):
            raise ReleaseGraphError(f"unsafe target ID:{target}")
        if not isinstance(specification, dict):
            raise ReleaseGraphError(f"target is not an object:{target}")
        terminal = specification.get("terminal_stages")
        if not isinstance(terminal, list) or not terminal or not all(item in seen for item in terminal):
            raise ReleaseGraphError(f"target terminal stages differ:{target}")
    # Exercise every target now so cycles or unreachable dependency defects fail at load.
    for target in targets:
        target_stage_ids(graph, target)
    return graph


def stage_map(graph: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(stage["id"]): stage for stage in graph["stages"]}


def target_stage_ids(graph: Mapping[str, Any], target: str) -> list[str]:
    targets = graph.get("targets", {})
    if target not in targets:
        raise ReleaseGraphError(f"unknown release target:{target}")
    stages = stage_map(graph)
    state: dict[str, int] = {}
    ordered: list[str] = []

    def visit(stage_id: str) -> None:
        mark = state.get(stage_id, 0)
        if mark == 1:
            raise ReleaseGraphError(f"release graph cycle at:{stage_id}")
        if mark == 2:
            return
        if stage_id not in stages:
            raise ReleaseGraphError(f"release target references missing stage:{stage_id}")
        state[stage_id] = 1
        for dependency in stages[stage_id].get("needs", []):
            visit(dependency)
        state[stage_id] = 2
        ordered.append(stage_id)

    for terminal in targets[target]["terminal_stages"]:
        visit(terminal)
    return ordered


def _referenced_npm_scripts(body: str) -> list[str]:
    return re.findall(r"(?:^|[;&|]\s*)npm\s+run\s+([A-Za-z0-9:._-]+)", body)


def _resolve_npm_script(name: str, scripts: Mapping[str, str], stack: tuple[str, ...] = ()) -> dict[str, Any]:
    if name not in scripts:
        raise ReleaseGraphError(f"npm script missing:{name}")
    if name in stack:
        raise ReleaseGraphError(f"npm script recursion:{'->'.join((*stack, name))}")
    body = scripts[name]
    dependencies = []
    for dependency in _referenced_npm_scripts(body):
        dependencies.append(_resolve_npm_script(dependency, scripts, (*stack, name)))
    return {"script": name, "body": body, "dependencies": dependencies}


def resolve_command(command: list[str], scripts: Mapping[str, str]) -> dict[str, Any]:
    payload: dict[str, Any] = {"argv": list(command)}
    if len(command) >= 3 and command[0] in {"npm", "npm.cmd"} and command[1] == "run":
        payload["npm"] = _resolve_npm_script(command[2], scripts)
        payload["extra_argv"] = command[3:]
    return payload


def native_executable(executable: str, os_name: str | None = None) -> str:
    """Resolve command shims consistently for direct execution."""
    platform_name = os.name if os_name is None else os_name
    if platform_name == "nt" and executable in {"npm", "npx"}:
        return f"{executable}.cmd"
    return executable


def native_command(
    command: list[str],
    os_name: str | None = None,
    *,
    comspec: str | None = None,
) -> list[str]:
    """Return a directly executable, platform-correct argv.

    Windows command shims (``.cmd``/``.bat``) are scripts rather than native
    executables.  Calling them as though they were binaries is interpreter and
    Python-version dependent.  Route them through an explicit, non-interactive
    ``cmd.exe`` boundary and preserve the original argv with Windows quoting.
    POSIX commands remain unchanged.
    """
    if not command:
        raise ReleaseGraphError("empty stage command")
    platform_name = os.name if os_name is None else os_name
    resolved = list(command)
    resolved[0] = native_executable(resolved[0], platform_name)
    if platform_name == "nt" and Path(resolved[0]).suffix.lower() in {".cmd", ".bat"}:
        command_processor = comspec or os.environ.get("COMSPEC") or "cmd.exe"
        return [command_processor, "/d", "/s", "/c", subprocess.list2cmdline(resolved)]
    return resolved


@lru_cache(maxsize=1)
def _base_tool_versions() -> dict[str, str]:
    versions: dict[str, str] = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    probes = {
        "node": ["node", "--version"],
        "npm": native_command(["npm", "--version"]),
        "git": ["git", "--version"],
        "lake": ["lake", "--version"],
    }
    for name, command in probes.items():
        if shutil.which(command[0]) is None:
            versions[name] = "MISSING"
            continue
        try:
            completed = subprocess.run(command, text=True, capture_output=True, check=False, timeout=8)
            text = (completed.stdout or completed.stderr).strip().splitlines()
            versions[name] = text[0] if completed.returncode == 0 and text else f"ERROR:{completed.returncode}"
        except Exception as exc:  # noqa: BLE001
            versions[name] = f"ERROR:{type(exc).__name__}"
    return versions


def collect_tool_versions(command: list[str], os_name: str | None = None) -> dict[str, str]:
    versions = dict(_base_tool_versions())
    executable = native_executable(command[0], os_name)
    versions["stage_executable"] = executable
    versions["stage_executable_path"] = shutil.which(executable) or "MISSING"
    return versions


def stage_input_snapshot(root: Path, graph: Mapping[str, Any], stage: Mapping[str, Any]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for set_id in stage.get("input_sets", []):
        specification = graph["input_sets"][set_id]
        observed = collect_input_files(root, specification)
        snapshot[f"@input-set/{set_id}"] = sha256_text(canonical_json(observed))
        for path, digest in observed.items():
            prior = snapshot.get(path)
            if prior is not None and prior != digest:
                raise ReleaseGraphError(f"input snapshot collision:{path}")
            snapshot[path] = digest
    return dict(sorted(snapshot.items()))


def compute_stage_input_root(
    graph: Mapping[str, Any],
    stage: Mapping[str, Any],
    inputs: Mapping[str, str],
    dependency_receipts: Mapping[str, Mapping[str, Any]],
    tool_versions: Mapping[str, str],
) -> str:
    payload = {
        "graph_id": graph["graph_id"],
        "stage_id": stage["id"],
        "stage_config_sha256": sha256_text(canonical_json(stage)),
        "inputs": dict(sorted(inputs.items())),
        "dependency_receipts": {
            key: value.get("receipt_sha256") for key, value in sorted(dependency_receipts.items())
        },
        "tool_versions": dict(sorted(tool_versions.items())),
    }
    return sha256_text(canonical_json(payload))


def _output_descriptor(value: Any) -> tuple[str, bool]:
    _validate_output_descriptor(value)
    if isinstance(value, str):
        return _safe_relative(value), True
    return _safe_relative(value["path"]), bool(value.get("required", True))


def output_inventory(root: Path, outputs: Iterable[Any]) -> tuple[dict[str, Any], list[str]]:
    inventory: dict[str, Any] = {}
    errors: list[str] = []
    for descriptor in outputs:
        relative, required = _output_descriptor(descriptor)
        path = root / relative
        if path.is_symlink():
            errors.append(f"stage output symlink forbidden:{relative}")
            continue
        if not path.exists():
            if required:
                errors.append(f"required stage output missing:{relative}")
            continue
        if path.is_file():
            inventory[relative] = {
                "type": "file",
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            continue
        if path.is_dir():
            members: dict[str, Any] = {}
            for child in sorted(path.rglob("*")):
                member = child.relative_to(root).as_posix()
                if child.is_symlink():
                    errors.append(f"stage output tree symlink forbidden:{member}")
                elif child.is_file():
                    members[member] = {
                        "bytes": child.stat().st_size,
                        "sha256": sha256_file(child),
                    }
            inventory[relative] = {
                "type": "directory",
                "files": members,
                "tree_sha256": sha256_text(canonical_json(members)),
            }
            continue
        errors.append(f"unsupported stage output type:{relative}")
    return dict(sorted(inventory.items())), sorted(set(errors))


def output_root_sha256(inventory: Mapping[str, Any]) -> str:
    return sha256_text(canonical_json(dict(sorted(inventory.items()))))


def graph_file_sha256(root: Path, graph_path: Path = GRAPH_PATH) -> str:
    """Return the semantic graph identity used by checkpoint receipts.

    Per-input-set file locks are intentionally excluded from this root. Their
    exact contents are already committed into each stage input root, so keeping
    them here would invalidate unrelated branches whenever one input set is
    relocked. Commands, edges, targets, policies, include/exclude rules, and all
    other graph semantics remain covered.
    """
    path = graph_path if graph_path.is_absolute() else root / graph_path
    graph = read_json(path)
    semantic = json.loads(json.dumps(graph))
    for specification in semantic.get("input_sets", {}).values():
        if isinstance(specification, dict):
            specification["files"] = "@BOUND_IN_STAGE_INPUT_ROOT"
    return sha256_text(canonical_json(semantic))


def make_receipt(
    *,
    graph: Mapping[str, Any],
    graph_file_hash: str,
    stage: Mapping[str, Any],
    command: list[str],
    resolved_command: Mapping[str, Any],
    input_root: str,
    output_root: str,
    output_inventory_value: Mapping[str, Any],
    tool_versions: Mapping[str, str],
    dependency_receipts: Mapping[str, Mapping[str, Any]],
    exit_status: int,
    classification: str,
    started_at: str,
    completed_at: str,
    errors: Iterable[str],
) -> dict[str, Any]:
    if classification not in CLASSIFICATIONS:
        raise ReleaseGraphError(f"receipt classification differs:{classification}")
    receipt: dict[str, Any] = {
        "schema_version": "1.0.0",
        "graph_id": graph["graph_id"],
        "graph_sha256": graph_file_hash,
        "stage": stage["id"],
        "stage_config_sha256": sha256_text(canonical_json(stage)),
        "command": list(command),
        "resolved_command": resolved_command,
        "input_root_sha256": input_root,
        "output_root_sha256": output_root,
        "output_inventory": output_inventory_value,
        "dependency_receipts": {
            key: value.get("receipt_sha256") for key, value in sorted(dependency_receipts.items())
        },
        "tool_versions": dict(sorted(tool_versions.items())),
        "exit_status": int(exit_status),
        "classification": classification,
        "started_at": started_at,
        "completed_at": completed_at,
        "errors": sorted({str(item) for item in errors if str(item)}),
    }
    receipt["receipt_sha256"] = sha256_text(canonical_json(receipt))
    return receipt


def receipt_valid(receipt: Any) -> bool:
    if not isinstance(receipt, dict):
        return False
    digest = receipt.get("receipt_sha256")
    if not isinstance(digest, str) or len(digest) != 64:
        return False
    payload = dict(receipt)
    payload.pop("receipt_sha256", None)
    return digest == sha256_text(canonical_json(payload))


def receipt_path(receipt_dir: Path, stage_id: str) -> Path:
    if not _SAFE_ID.fullmatch(stage_id):
        raise ReleaseGraphError(f"unsafe receipt stage ID:{stage_id}")
    return receipt_dir / f"{stage_id}.json"


def load_receipt(receipt_dir: Path, stage_id: str) -> dict[str, Any] | None:
    path = receipt_path(receipt_dir, stage_id)
    if not path.is_file() or path.is_symlink():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - malformed receipts are simply non-reusable
        return None
    return value if isinstance(value, dict) else None


def reusable_receipt(
    receipt: dict[str, Any] | None,
    *,
    graph: Mapping[str, Any],
    graph_file_hash: str,
    stage: Mapping[str, Any],
    input_root: str,
    current_output_root: str,
    tool_versions: Mapping[str, str],
    dependency_receipts: Mapping[str, Mapping[str, Any]],
) -> bool:
    if not receipt_valid(receipt):
        return False
    assert receipt is not None
    expected_dependencies = {
        key: value.get("receipt_sha256") for key, value in sorted(dependency_receipts.items())
    }
    return all([
        receipt.get("schema_version") == "1.0.0",
        receipt.get("graph_id") == graph.get("graph_id"),
        receipt.get("graph_sha256") == graph_file_hash,
        receipt.get("stage") == stage.get("id"),
        receipt.get("stage_config_sha256") == sha256_text(canonical_json(stage)),
        receipt.get("input_root_sha256") == input_root,
        receipt.get("output_root_sha256") == current_output_root,
        receipt.get("tool_versions") == dict(sorted(tool_versions.items())),
        receipt.get("dependency_receipts") == expected_dependencies,
        receipt.get("classification") == "PASS",
        receipt.get("exit_status") == 0,
    ])


def target_plan(root: Path, graph: Mapping[str, Any], target: str) -> list[dict[str, Any]]:
    package = read_json(root / "package.json")
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        raise ReleaseGraphError("package scripts missing")
    stages = stage_map(graph)
    plan: list[dict[str, Any]] = []
    for stage_id in target_stage_ids(graph, target):
        stage = stages[stage_id]
        plan.append({
            "stage": stage_id,
            "needs": list(stage.get("needs", [])),
            "command": list(stage["command"]),
            "resolved_command": resolve_command(list(stage["command"]), scripts),
            "input_sets": list(stage.get("input_sets", [])),
            "outputs": stage.get("outputs", []),
            "read_only": bool(stage.get("read_only")),
            "failure_classification": stage.get("failure_classification"),
        })
    return plan


def plan_payload(plan: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [json.loads(json.dumps(item, sort_keys=True)) for item in plan]
