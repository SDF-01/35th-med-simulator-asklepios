#!/usr/bin/env python3
"""Adversarial tests for graph equivalence, locks, and checkpoint invalidation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import signal
import shutil
import stat
import subprocess
import sys
sys.dont_write_bytecode = True
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PureWindowsPath
from typing import Callable

from check_release_graph import validate
from release_graph_core import GRAPH_PATH, collect_tool_versions, lock_input_sets, receipt_valid, write_json
from release_result import EXPECTED_REJECTION, FAIL, INTERNAL_ERROR, PASS, case_result, suite_classification
from run_scenario_contract_gate import (
    CANONICAL_SCRIPTS as SCENARIO_GATE_CANONICAL_SCRIPTS,
    EXPECTED_OUTPUTS as SCENARIO_GATE_EXPECTED_OUTPUTS,
)

OUTPUT = Path("reports/release-graph-mutations.json")
FIXTURE_COPY_POLICY = "HERMETIC_METADATA_PRESERVING_COPY_V1"
HEAVY_CASE_ISOLATION = "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V2"
MUTATION_CASE_ISOLATION = "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V1"
MUTATION_WORKER_EXECUTION = "SEALED_PER_CASE_MUTATION_SNAPSHOT_EXECUTABLE_V1"
MUTATION_WORKER_RESULT_BINDING = "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1"
MUTATION_CHECKPOINT_PROFILE = "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1"
HEAVY_CHECKPOINT_PROFILE = "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1"
PARTITION_ISOLATION = "CHECKPOINTED_INDEPENDENT_MUTATION_AND_HEAVY_PARTITIONS_V2"
SUITE_SOURCE_ISOLATION = "STABLE_HERMETIC_SUITE_SOURCE_SNAPSHOT_WITH_PER_CASE_COPIES_V2"
SOURCE_SNAPSHOT_ISOLATION = "STABLE_HERMETIC_SUITE_SOURCE_SNAPSHOT_WITH_PER_CASE_COPIES_V2"
HEAVY_RESOURCE_SCHEDULER = "RESOURCE_CLASS_AWARE_EXCLUSIVE_FANOUT_V1"
HEAVY_CASE_SOURCE_GUARD = "PER_CASE_LOCKED_SOURCE_INVENTORY_GUARD_V1"
HEAVY_WORKER_EXECUTION = "SEALED_PER_CASE_SOURCE_SNAPSHOT_EXECUTABLE_V1"
HEAVY_WORKER_RESULT_BINDING = "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1"
BASELINE_FAIL_FAST = "CANONICAL_BASELINE_FAILS_BEFORE_ADVERSARIAL_SCHEDULING_V1"
SOURCE_INTEGRITY_CASE_ID = "release-graph-adversarial-suite-preserves-source-tree"
DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS = 60
DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS = 90
DEFAULT_MUTATION_CHECKPOINT_ROOT = Path(".asklepios/release-graph-mutation-checkpoints")
DEFAULT_HEAVY_CHECKPOINT_ROOT = Path(".asklepios/release-graph-heavy-checkpoints")
DEFAULT_HEAVY_CASE_TIMEOUT_SECONDS = 240
DEFAULT_HEAVY_CASE_WORKERS = 1
WORKSPACE_PATH_PROFILE = "CONTENT_ADDRESSED_COMPACT_WORKSPACE_PATHS_V1"
WORKSPACE_COMPONENT_HASH_HEX = 20
PORTABLE_WINDOWS_PATH_BUDGET = 240
PORTABLE_TEMP_PREFIX = "arg-"

# These cases each launch their own nested process fan-out. Running them at the
# same time can exhaust CPU, file descriptors, and pipe buffers, causing the
# harness to manufacture timeouts that do not reproduce in isolation. Keep the
# general heavyweight pool parallel, but serialize the explicitly high-fanout
# cases so assurance remains bounded and diagnostic rather than load-sensitive.
EXCLUSIVE_HEAVY_CASES = frozenset({
    "scenario-contract-gate-is-hermetic-and-attributed",
    "decision-artifact-mutation-harness-is-cwd-independent-and-attributed",
    "double-build-is-hermetic-deterministic-and-diagnostic",
    "heavy-checkpoint-reuse-and-invalidation",
})


def locked_source_inventory(source: Path) -> dict[str, dict[str, object]]:
    """Hash every graph-locked source plus the graph itself.

    Mutation fixtures must never alter the repository under test. This inventory
    turns that hermeticity assumption into an explicit release ratchet.
    """
    graph = json.loads((source / GRAPH_PATH).read_text(encoding="utf-8"))
    paths = {GRAPH_PATH.as_posix()}
    for specification in graph.get("input_sets", {}).values():
        paths.update((specification.get("files") or {}).keys())
    inventory: dict[str, dict[str, object]] = {}
    for relative in sorted(paths):
        path = source / relative
        if path.is_symlink():
            inventory[relative] = {"kind": "symlink", "target": os.readlink(path)}
        elif path.is_file():
            info = path.stat()
            inventory[relative] = {
                "kind": "file",
                "bytes": info.st_size,
                "mode": stat.S_IMODE(info.st_mode),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        else:
            inventory[relative] = {"kind": "missing"}
    return inventory


def inventory_root_sha256(inventory: dict[str, dict[str, object]]) -> str:
    """Return a deterministic identity for one locked-source inventory."""
    canonical = json.dumps(
        inventory,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _compact_workspace_component(kind: str, case_id: str) -> str:
    """Return a deterministic short directory name for one registry case.

    Full case IDs are preserved in receipts, but never repeated in nested
    workspace paths.  This keeps recursive checkpoint tests safely below the
    legacy Windows MAX_PATH boundary while retaining collision resistance.
    """
    if not kind or any(char not in "abcdefghijklmnopqrstuvwxyz" for char in kind):
        raise ValueError(f"unsafe workspace kind:{kind}")
    digest = hashlib.sha256(case_id.encode("utf-8")).hexdigest()[:WORKSPACE_COMPONENT_HASH_HEX]
    return f"{kind}-{digest}"


def _bounded_worker_log_tail(path: Path, limit: int = 4000) -> str:
    """Retain a bounded UTF-8 diagnostic tail before temporary cleanup."""
    try:
        return path.read_bytes().decode("utf-8", errors="replace")[-limit:]
    except OSError as exc:
        return f"<worker log unavailable:{type(exc).__name__}:{exc}>"


def _portable_temp_parent() -> Path | None:
    """Prefer GitHub's compact runner temp root when it is available."""
    candidate = os.environ.get("RUNNER_TEMP")
    if not candidate:
        return None
    path = Path(candidate)
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return path


def _portable_workspace_path_probe() -> dict[str, object]:
    """Model the deepest recursive workspace using Windows path semantics."""
    base = PureWindowsPath(r"C:\Users\RUNNER~1\AppData\Local\Temp") / f"{PORTABLE_TEMP_PREFIX}12345678"
    longest_locked_source = PureWindowsPath(".github/workflows/facility-decision-integrity-ci.yml")
    heavy_case = "heavy-checkpoint-reuse-and-invalidation"
    nested_case = "heavyweight-result-case-id-mismatch-is-rejected"
    deepest = (
        base
        / "h"
        / _compact_workspace_component("h", heavy_case)
        / "hc"
        / "a"
        / _compact_workspace_component("h", nested_case)
        / "src"
        / longest_locked_source
    )
    mutation = (
        base
        / "m"
        / _compact_workspace_component("m", "offline-release-raw-graph-artifact-cycle-reintroduced")
        / "src"
        / longest_locked_source
    )
    return {
        "profile": WORKSPACE_PATH_PROFILE,
        "budget": PORTABLE_WINDOWS_PATH_BUDGET,
        "deepest_heavy_path": str(deepest),
        "deepest_heavy_length": len(str(deepest)),
        "deepest_mutation_path": str(mutation),
        "deepest_mutation_length": len(str(mutation)),
    }


def inventory_delta(
    before: dict[str, dict[str, object]],
    after: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    """Describe exact locked-source changes instead of returning path names only."""
    changes: list[dict[str, object]] = []
    for relative in sorted(set(before) | set(after)):
        old = before.get(relative)
        new = after.get(relative)
        if old == new:
            continue
        if old is None:
            kind = "ADDED"
            legacy_kind = "ADDED"
        elif new is None:
            kind = "REMOVED"
            legacy_kind = "REMOVED"
        elif old.get("kind") != new.get("kind"):
            kind = "TYPE_CHANGED"
            legacy_kind = "CHANGED"
        else:
            kind = "CONTENT_OR_MODE_CHANGED"
            legacy_kind = "CHANGED"
        changes.append({
            "path": relative,
            "change": legacy_kind,
            "change_kind": kind,
            "before": old,
            "after": new,
        })
    return changes


def copy_repo(source: Path, target: Path) -> None:
    """Create an isolated mutation fixture without shared writable inodes.

    Hard links are deliberately forbidden here. Candidate validators write
    reports and generated evidence that are not all under this harness's
    direct control; a hard-linked fixture can therefore mutate the source
    repository and invalidate later gates. Metadata-preserving copies are
    slower but provide the required hermetic boundary on every platform.
    """
    shutil.copytree(
        source,
        target,
        copy_function=shutil.copy2,
        ignore=shutil.ignore_patterns(
            ".git", ".lake", ".asklepios", "node_modules", "dist",
            "reports", "__pycache__", "*.pyc", "*.pyo",
        ),
    )


def acquire_stable_source_snapshot(
    source: Path,
    target: Path,
    before: dict[str, dict[str, object]],
) -> tuple[dict[str, dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Copy a stable source seed and detect edits that race snapshot acquisition.

    Every mutation and heavyweight case is derived from this seed, never from the
    live working tree.  A concurrent edit therefore cannot be misreported as a
    child-test write, and it cannot produce a mixed-version fixture silently.
    """
    copy_repo(source, target)
    live_after_copy = locked_source_inventory(source)
    snapshot_inventory = locked_source_inventory(target)
    live_drift = inventory_delta(before, live_after_copy)
    snapshot_mismatch = inventory_delta(before, snapshot_inventory)
    return snapshot_inventory, live_drift, snapshot_mismatch


def atomic_write_text(path: Path, text: str) -> None:
    """Atomically replace a fixture file while preserving its executable mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
    handle, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        temporary.write_text(text, encoding="utf-8", newline="\n")
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mutate_graph(repo: Path, mutate: Callable[[dict], None]) -> None:
    path = repo / GRAPH_PATH
    graph = json.loads(path.read_text(encoding="utf-8"))
    mutate(graph)
    atomic_write_text(path, json.dumps(graph, indent=2, sort_keys=True) + "\n")


def relock_graph_input_sets(repo: Path, set_ids: list[str]) -> None:
    path = repo / GRAPH_PATH
    graph = json.loads(path.read_text(encoding="utf-8"))
    graph = lock_input_sets(repo, graph, set_ids)
    write_json(path, graph)


def relock_input_sets_containing_path(repo: Path, relative: str) -> None:
    """Relock every set that authenticates a mutated source path."""
    path = repo / GRAPH_PATH
    graph = json.loads(path.read_text(encoding="utf-8"))
    set_ids = [
        set_id
        for set_id, specification in graph.get("input_sets", {}).items()
        if relative in (specification.get("files") or {})
        or relative in (specification.get("include") or [])
    ]
    if not set_ids:
        raise ValueError(f"no input set authenticates:{relative}")
    graph = lock_input_sets(repo, graph, sorted(set_ids))
    write_json(path, graph)


def graph_stage(graph: dict, stage_id: str) -> dict:
    return next(stage for stage in graph["stages"] if stage["id"] == stage_id)


def _execute_mutation_candidate(
    candidate: Path,
    case_id: str,
    mutate: Callable[[Path], None],
) -> dict:
    """Mutate one already isolated candidate and evaluate its graph fail-closed."""
    print(f"release-graph adversarial case: {case_id}", flush=True)
    try:
        mutate(candidate)
        report_path = candidate / ".asklepios/mutation-release-graph.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/check_release_graph.py",
                "--repo",
                ".",
                "--json-output",
                str(report_path.relative_to(candidate)),
            ],
            cwd=candidate,
            text=True,
            capture_output=True,
            check=False,
            timeout=DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS,
        )
        if not report_path.is_file():
            return case_result(
                case_id,
                INTERNAL_ERROR,
                errors=["mutation validator did not emit a report"],
                validator_returncode=completed.returncode,
                validator_stdout_tail=completed.stdout[-1000:],
                validator_stderr_tail=completed.stderr[-1000:],
            )
        report = json.loads(report_path.read_text(encoding="utf-8"))
        rejected = report.get("classification") != "PASS"
        return case_result(
            case_id,
            EXPECTED_REJECTION if rejected else FAIL,
            errors=[] if rejected else ["mutated orchestration was accepted"],
            observed_classification=report.get("classification"),
            observed_errors=report.get("errors", [])[:10],
            validator_returncode=completed.returncode,
        )
    except subprocess.TimeoutExpired as exc:
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"mutation validator timeout after {DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS}s"],
            validator_stdout_tail=(exc.stdout or "")[-1000:] if isinstance(exc.stdout, str) else "",
            validator_stderr_tail=(exc.stderr or "")[-1000:] if isinstance(exc.stderr, str) else "",
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )


def run_mutation(source: Path, root: Path, case_id: str, mutate: Callable[[Path], None]) -> dict:
    """Compatibility wrapper for one local isolated mutation fixture."""
    candidate = root / case_id
    try:
        copy_repo(source, candidate)
        return _execute_mutation_candidate(candidate, case_id, mutate)
    finally:
        shutil.rmtree(candidate, ignore_errors=True)


def _validated_mutation_case_result(case_id: str, result: object) -> dict:
    """Reject a durable mutation result that claims a different registry key."""
    if not isinstance(result, dict):
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"mutation worker result is not an object:{type(result).__name__}"],
        )
    observed = result.get("case_id")
    if observed != case_id:
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"mutation worker case ID differs:{observed}"],
            observed_case_id=observed,
        )
    return result


def _canonical_json_sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _mutation_checkpoint_path(root: Path, case_id: str) -> Path:
    filename = f"{hashlib.sha256(case_id.encode('utf-8')).hexdigest()}.json"
    return root / filename


def _mutation_checkpoint_envelope(
    context: dict[str, object],
    case_id: str,
    result: dict,
) -> dict:
    base = {
        "schema_version": "1.0.0",
        "profile": MUTATION_CHECKPOINT_PROFILE,
        "case_id": case_id,
        "context": context,
        "result": result,
    }
    return {**base, "checkpoint_sha256": _canonical_json_sha256(base)}


def _load_mutation_checkpoint(
    path: Path,
    context: dict[str, object],
    case_id: str,
) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if not path.exists():
        return None, errors
    if path.is_symlink() or not path.is_file():
        return None, ["mutation checkpoint is not a regular file"]
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"mutation checkpoint unreadable:{type(exc).__name__}:{exc}"]
    if not isinstance(envelope, dict):
        return None, ["mutation checkpoint is not an object"]
    checkpoint_sha256 = envelope.get("checkpoint_sha256")
    unsigned = {key: value for key, value in envelope.items() if key != "checkpoint_sha256"}
    if checkpoint_sha256 != _canonical_json_sha256(unsigned):
        errors.append("mutation checkpoint self-digest differs")
    if envelope.get("profile") != MUTATION_CHECKPOINT_PROFILE:
        errors.append("mutation checkpoint profile differs")
    if envelope.get("case_id") != case_id:
        errors.append("mutation checkpoint case ID differs")
    if envelope.get("context") != context:
        errors.append("mutation checkpoint context differs")
    result = envelope.get("result")
    if not isinstance(result, dict):
        errors.append("mutation checkpoint result is not an object")
        return None, errors
    validated = _validated_mutation_case_result(case_id, result)
    if validated.get("classification") not in {PASS, EXPECTED_REJECTION} or validated.get("pass") is not True:
        errors.append("mutation checkpoint result is not reusable")
    if validated.get("worker_execution") != MUTATION_WORKER_EXECUTION:
        errors.append("mutation checkpoint worker execution differs")
    if validated.get("worker_result_binding") != MUTATION_WORKER_RESULT_BINDING:
        errors.append("mutation checkpoint result binding differs")
    if validated.get("worker_script_sha256") != context.get("worker_script_sha256"):
        errors.append("mutation checkpoint worker script hash differs")
    if validated.get("worker_executable") != "scripts/test_release_graph.py":
        errors.append("mutation checkpoint worker executable differs")
    if validated.get("workspace_path_profile") != WORKSPACE_PATH_PROFILE:
        errors.append("mutation checkpoint workspace path profile differs")
    if errors:
        return None, errors
    reused = copy.deepcopy(validated)
    reused["checkpoint_profile"] = MUTATION_CHECKPOINT_PROFILE
    reused["checkpoint_sha256"] = checkpoint_sha256
    reused["checkpoint_reused"] = True
    reused["checkpoint_path"] = path.name
    return reused, []


def _write_mutation_checkpoint(
    path: Path,
    context: dict[str, object],
    case_id: str,
    result: dict,
) -> dict:
    stored = copy.deepcopy(result)
    stored["checkpoint_profile"] = MUTATION_CHECKPOINT_PROFILE
    stored["checkpoint_reused"] = False
    stored.pop("checkpoint_sha256", None)
    stored.pop("checkpoint_path", None)
    envelope = _mutation_checkpoint_envelope(context, case_id, stored)
    write_json(path, envelope)
    stored["checkpoint_sha256"] = envelope["checkpoint_sha256"]
    stored["checkpoint_path"] = path.name
    return stored


def _mutation_checkpoint_context(
    source: Path,
    source_inventory_root_sha256: str,
    case_timeout_seconds: int,
) -> dict[str, object]:
    graph_value = json.loads((source / GRAPH_PATH).read_text(encoding="utf-8"))
    return {
        "profile": MUTATION_CHECKPOINT_PROFILE,
        "graph_id": graph_value.get("graph_id"),
        "graph_file_sha256": hashlib.sha256((source / GRAPH_PATH).read_bytes()).hexdigest(),
        "source_inventory_root_sha256": source_inventory_root_sha256,
        "worker_script_sha256": hashlib.sha256(
            (source / "scripts/test_release_graph.py").read_bytes()
        ).hexdigest(),
        "worker_execution": MUTATION_WORKER_EXECUTION,
        "worker_result_binding": MUTATION_WORKER_RESULT_BINDING,
        "case_isolation": MUTATION_CASE_ISOLATION,
        "validator_timeout_seconds": DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS,
        "case_timeout_seconds": case_timeout_seconds,
        "workspace_path_profile": WORKSPACE_PATH_PROFILE,
        "tool_versions": collect_tool_versions(["python"]),
    }


def _safe_mutation_checkpoint_root(repo: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"unsafe mutation checkpoint root:{relative}")
    if any("\\" in part or ":" in part or "\x00" in part for part in relative.parts):
        raise ValueError(f"unsafe mutation checkpoint root:{relative}")
    current = repo
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"symlinked mutation checkpoint root:{relative}")
    resolved = (repo / relative).resolve(strict=False)
    try:
        resolved.relative_to(repo.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"mutation checkpoint root escapes repository:{relative}") from exc
    return resolved



def _heavy_checkpoint_path(root: Path, case_id: str) -> Path:
    filename = f"{hashlib.sha256(case_id.encode('utf-8')).hexdigest()}.json"
    return root / filename


def _heavy_checkpoint_envelope(
    context: dict[str, object],
    case_id: str,
    result: dict,
) -> dict:
    base = {
        "schema_version": "1.0.0",
        "profile": HEAVY_CHECKPOINT_PROFILE,
        "case_id": case_id,
        "context": context,
        "result": result,
    }
    return {**base, "checkpoint_sha256": _canonical_json_sha256(base)}


def _load_heavy_checkpoint(
    path: Path,
    context: dict[str, object],
    case_id: str,
) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    if not path.exists():
        return None, errors
    if path.is_symlink() or not path.is_file():
        return None, ["heavyweight checkpoint is not a regular file"]
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, [f"heavyweight checkpoint unreadable:{type(exc).__name__}:{exc}"]
    if not isinstance(envelope, dict):
        return None, ["heavyweight checkpoint is not an object"]
    checkpoint_sha256 = envelope.get("checkpoint_sha256")
    unsigned = {key: value for key, value in envelope.items() if key != "checkpoint_sha256"}
    if checkpoint_sha256 != _canonical_json_sha256(unsigned):
        errors.append("heavyweight checkpoint self-digest differs")
    if envelope.get("profile") != HEAVY_CHECKPOINT_PROFILE:
        errors.append("heavyweight checkpoint profile differs")
    if envelope.get("case_id") != case_id:
        errors.append("heavyweight checkpoint case ID differs")
    if envelope.get("context") != context:
        errors.append("heavyweight checkpoint context differs")
    result = envelope.get("result")
    if not isinstance(result, dict):
        errors.append("heavyweight checkpoint result is not an object")
        return None, errors
    validated = _validated_heavy_case_result(case_id, result)
    if validated.get("classification") != PASS or validated.get("pass") is not True:
        errors.append("heavyweight checkpoint result is not reusable")
    if validated.get("worker_execution") != HEAVY_WORKER_EXECUTION:
        errors.append("heavyweight checkpoint worker execution differs")
    if validated.get("worker_result_binding") != HEAVY_WORKER_RESULT_BINDING:
        errors.append("heavyweight checkpoint result binding differs")
    if validated.get("worker_script_sha256") != context.get("worker_script_sha256"):
        errors.append("heavyweight checkpoint worker script hash differs")
    if validated.get("worker_executable") != "scripts/test_release_graph.py":
        errors.append("heavyweight checkpoint worker executable differs")
    if validated.get("workspace_path_profile") != WORKSPACE_PATH_PROFILE:
        errors.append("heavyweight checkpoint workspace path profile differs")
    if validated.get("source_guard") != HEAVY_CASE_SOURCE_GUARD:
        errors.append("heavyweight checkpoint source guard differs")
    if validated.get("source_mutations") != []:
        errors.append("heavyweight checkpoint records source mutations")
    if validated.get("source_snapshot_root_before") != validated.get("source_snapshot_root_after"):
        errors.append("heavyweight checkpoint source roots differ")
    if errors:
        return None, errors
    reused = copy.deepcopy(validated)
    reused["checkpoint_profile"] = HEAVY_CHECKPOINT_PROFILE
    reused["checkpoint_sha256"] = checkpoint_sha256
    reused["checkpoint_reused"] = True
    reused["checkpoint_path"] = path.name
    return reused, []


def _write_heavy_checkpoint(
    path: Path,
    context: dict[str, object],
    case_id: str,
    result: dict,
) -> dict:
    stored = copy.deepcopy(result)
    stored["checkpoint_profile"] = HEAVY_CHECKPOINT_PROFILE
    stored["checkpoint_reused"] = False
    stored.pop("checkpoint_sha256", None)
    stored.pop("checkpoint_path", None)
    envelope = _heavy_checkpoint_envelope(context, case_id, stored)
    write_json(path, envelope)
    stored["checkpoint_sha256"] = envelope["checkpoint_sha256"]
    stored["checkpoint_path"] = path.name
    return stored


def _heavy_checkpoint_context(
    source: Path,
    source_inventory_root_sha256: str,
    case_timeout_seconds: int,
    workers: int,
) -> dict[str, object]:
    graph_value = json.loads((source / GRAPH_PATH).read_text(encoding="utf-8"))
    return {
        "profile": HEAVY_CHECKPOINT_PROFILE,
        "graph_id": graph_value.get("graph_id"),
        "graph_file_sha256": hashlib.sha256((source / GRAPH_PATH).read_bytes()).hexdigest(),
        "source_inventory_root_sha256": source_inventory_root_sha256,
        "worker_script_sha256": hashlib.sha256(
            (source / "scripts/test_release_graph.py").read_bytes()
        ).hexdigest(),
        "worker_execution": HEAVY_WORKER_EXECUTION,
        "worker_result_binding": HEAVY_WORKER_RESULT_BINDING,
        "case_isolation": HEAVY_CASE_ISOLATION,
        "source_guard": HEAVY_CASE_SOURCE_GUARD,
        "resource_scheduler": HEAVY_RESOURCE_SCHEDULER,
        "exclusive_cases": sorted(EXCLUSIVE_HEAVY_CASES),
        "case_timeout_seconds": case_timeout_seconds,
        "workers": workers,
        "workspace_path_profile": WORKSPACE_PATH_PROFILE,
        "tool_versions": collect_tool_versions(["python"]),
    }


def _safe_heavy_checkpoint_root(repo: Path, relative: Path) -> Path:
    if relative.is_absolute() or not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"unsafe heavyweight checkpoint root:{relative}")
    if any("\\" in part or ":" in part or "\x00" in part for part in relative.parts):
        raise ValueError(f"unsafe heavyweight checkpoint root:{relative}")
    current = repo
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"symlinked heavyweight checkpoint root:{relative}")
    resolved = (repo / relative).resolve(strict=False)
    try:
        resolved.relative_to(repo.resolve(strict=True))
    except ValueError as exc:
        raise ValueError(f"heavyweight checkpoint root escapes repository:{relative}") from exc
    return resolved


def _mutation_case_worker(case_id: str, candidate_text: str, result_text: str) -> int:
    """Execute one mutation from the sealed candidate script and persist its result."""
    result_path = Path(result_text)
    worker_script = Path(__file__).resolve(strict=True)
    worker_script_sha256 = hashlib.sha256(worker_script.read_bytes()).hexdigest()
    mutation_registry = dict(mutation_case_functions())
    try:
        result = _validated_mutation_case_result(
            case_id,
            _execute_mutation_candidate(
                Path(candidate_text),
                case_id,
                mutation_registry[case_id],
            ),
        )
    except BaseException as exc:  # noqa: BLE001 - persist every worker defect
        result = case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"])
    result["worker_execution"] = MUTATION_WORKER_EXECUTION
    result["worker_result_binding"] = MUTATION_WORKER_RESULT_BINDING
    result["worker_script_sha256"] = worker_script_sha256
    result["workspace_path_profile"] = WORKSPACE_PATH_PROFILE
    result_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(result_path, result)
    return 0


def _mutation_worker_command(
    candidate: Path,
    result_path: Path,
    case_id: str,
) -> tuple[list[str], str]:
    """Bind a mutation worker to the exact private candidate it evaluates."""
    worker_script = candidate / "scripts/test_release_graph.py"
    if worker_script.is_symlink() or not worker_script.is_file():
        raise FileNotFoundError(f"sealed mutation worker unavailable:{worker_script}")
    worker_script_sha256 = hashlib.sha256(worker_script.read_bytes()).hexdigest()
    return [
        sys.executable,
        str(worker_script.resolve(strict=True)),
        "--mutation-worker-case",
        case_id,
        "--mutation-worker-candidate",
        str(candidate),
        "--mutation-worker-result",
        str(result_path),
    ], worker_script_sha256


def run_mutation_case_isolated(
    source: Path,
    root: Path,
    case_id: str,
    timeout_seconds: int,
) -> dict:
    """Run one mutation in a killable process group with a durable bound result."""
    started = time.monotonic()
    worker_root = root / _compact_workspace_component("m", case_id)
    candidate = worker_root / "src"
    result_path = worker_root / "r.json"
    worker_log = worker_root / "w.log"
    worker_root.mkdir(parents=True, exist_ok=False)
    try:
        copy_repo(source, candidate)
        command, expected_worker_script_sha256 = _mutation_worker_command(
            candidate,
            result_path,
            case_id,
        )
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(worker_root, ignore_errors=True)
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"sealed mutation worker setup failed:{type(exc).__name__}:{exc}"],
            isolation=MUTATION_CASE_ISOLATION,
            worker_execution=MUTATION_WORKER_EXECUTION,
            worker_result_binding=MUTATION_WORKER_RESULT_BINDING,
        )

    with worker_log.open("wb") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=candidate,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            **_process_group_kwargs(),
        )
        try:
            process.wait(timeout=timeout_seconds)
            timed_out = False
            termination = "NOT_REQUIRED"
        except subprocess.TimeoutExpired:
            timed_out = True
            termination = _terminate_subprocess_tree(process)

    log_sha256 = hashlib.sha256(worker_log.read_bytes()).hexdigest()
    if timed_out:
        result = case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"mutation case timeout after {timeout_seconds}s"],
            isolation=MUTATION_CASE_ISOLATION,
            termination=termination,
            worker_exitcode=process.returncode,
            worker_log_sha256=log_sha256,
        )
    elif process.returncode != 0 or not result_path.is_file():
        result = case_result(
            case_id,
            INTERNAL_ERROR,
            errors=["mutation worker exited without a durable result"],
            isolation=MUTATION_CASE_ISOLATION,
            worker_exitcode=process.returncode,
            worker_log_sha256=log_sha256,
        )
    else:
        try:
            result = _validated_mutation_case_result(
                case_id,
                json.loads(result_path.read_text(encoding="utf-8")),
            )
            binding_errors: list[str] = []
            if result.get("worker_execution") != MUTATION_WORKER_EXECUTION:
                binding_errors.append("mutation worker execution boundary differs")
            if result.get("worker_result_binding") != MUTATION_WORKER_RESULT_BINDING:
                binding_errors.append("mutation worker result-binding boundary differs")
            if result.get("worker_script_sha256") != expected_worker_script_sha256:
                binding_errors.append("mutation worker script hash differs")
            if binding_errors:
                result = case_result(
                    case_id,
                    INTERNAL_ERROR,
                    errors=binding_errors,
                    observed_worker_script_sha256=result.get("worker_script_sha256"),
                )
            result["worker_exitcode"] = process.returncode
            result["worker_log_sha256"] = log_sha256
        except (OSError, json.JSONDecodeError) as exc:
            result = case_result(
                case_id,
                INTERNAL_ERROR,
                errors=[f"durable mutation result invalid:{type(exc).__name__}:{exc}"],
                worker_exitcode=process.returncode,
                worker_log_sha256=log_sha256,
            )

    result["isolation"] = MUTATION_CASE_ISOLATION
    result["worker_execution"] = MUTATION_WORKER_EXECUTION
    result["worker_result_binding"] = MUTATION_WORKER_RESULT_BINDING
    result["worker_script_sha256"] = expected_worker_script_sha256
    result["worker_executable"] = "scripts/test_release_graph.py"
    result["workspace_path_profile"] = WORKSPACE_PATH_PROFILE
    result["worker_workspace"] = worker_root.name
    result["worker_log_tail"] = _bounded_worker_log_tail(worker_log)
    result["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
    shutil.rmtree(worker_root, ignore_errors=True)
    return result


def run_independent_mutations(
    source: Path,
    root: Path,
    specifications: list[tuple[str, Callable[[Path], None]]],
    workers: int,
    timeout_seconds: int,
    checkpoint_root: Path,
    checkpoint_context: dict[str, object],
    reuse_checkpoints: bool,
) -> list[dict]:
    """Run every mutation as a bounded process and retain canonical result order."""
    case_ids = [case_id for case_id, _mutate in specifications]
    if not case_ids:
        return []
    bounded_workers = max(1, min(workers, len(case_ids), 8))
    print(
        f"release-graph adversarial scheduler: {len(case_ids)} isolated cases, "
        f"{bounded_workers} workers, {timeout_seconds}s per case",
        flush=True,
    )

    checkpoint_root.mkdir(parents=True, exist_ok=True)

    def run_one(case_id: str) -> dict:
        checkpoint_path = _mutation_checkpoint_path(checkpoint_root, case_id)
        if reuse_checkpoints:
            reused, checkpoint_errors = _load_mutation_checkpoint(
                checkpoint_path, checkpoint_context, case_id
            )
            if reused is not None:
                print(f"REUSE_MUTATION_CASE:{case_id}", flush=True)
                return reused
            if checkpoint_errors:
                checkpoint_path.unlink(missing_ok=True)
                print(
                    f"INVALIDATE_MUTATION_CHECKPOINT:{case_id}:{';'.join(checkpoint_errors[:3])}",
                    flush=True,
                )
        print(f"START_MUTATION_CASE:{case_id}", flush=True)
        result = run_mutation_case_isolated(source, root, case_id, timeout_seconds)
        if result.get("classification") in {PASS, EXPECTED_REJECTION} and result.get("pass") is True:
            result = _write_mutation_checkpoint(
                checkpoint_path, checkpoint_context, case_id, result
            )
        else:
            result["checkpoint_profile"] = MUTATION_CHECKPOINT_PROFILE
            result["checkpoint_reused"] = False
            result["checkpoint_sha256"] = None
            result["checkpoint_path"] = checkpoint_path.name
        print(
            f"END_MUTATION_CASE:{case_id}:{result.get('classification')}:{result.get('duration_ms')}",
            flush=True,
        )
        return result

    by_case: dict[str, dict] = {}
    if bounded_workers == 1:
        for case_id in case_ids:
            by_case[case_id] = run_one(case_id)
    else:
        with ThreadPoolExecutor(max_workers=bounded_workers, thread_name_prefix="release-graph-attack") as executor:
            futures = {case_id: executor.submit(run_one, case_id) for case_id in case_ids}
            for case_id, future in futures.items():
                by_case[case_id] = future.result()
    return [by_case[case_id] for case_id in case_ids]


def write_mini_tool(path: Path) -> None:
    path.write_text(
        r"""from __future__ import annotations
import argparse
import sys
from pathlib import Path, PureWindowsPath
p=argparse.ArgumentParser();p.add_argument('--input');p.add_argument('--output');p.add_argument('--fail-flag');p.add_argument('--mutate-input-on-fail', action='store_true');a=p.parse_args()
if a.fail_flag and Path(a.fail_flag).is_file():
 if a.mutate_input_on_fail:
  source_path=Path(a.input);source_path.write_text(source_path.read_text(encoding='utf-8')+'mutated\n',encoding='utf-8',newline='\n')
 print('deliberate stage failure: fail.flag present', file=sys.stderr)
 raise SystemExit(3)
source=Path(a.input).read_text(encoding='utf-8')
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(source,encoding='utf-8',newline='\n')
""",
        encoding="utf-8",
        newline="\n",
    )


def fixture_copy_isolation_case(source: Path, root: Path) -> dict:
    """Direct writes in a candidate must never alter the source repository."""
    fixture_source = root / "fixture-copy-isolation-source"
    fixture_candidate = root / "fixture-copy-isolation-candidate"
    try:
        fixture_source.mkdir(parents=True, exist_ok=False)
        source_file = fixture_source / "source.txt"
        source_file.write_text("source\n", encoding="utf-8", newline="\n")
        source_before = source_file.read_bytes()
        source_inode = source_file.stat().st_ino
        copy_repo(fixture_source, fixture_candidate)
        candidate_file = fixture_candidate / "source.txt"
        candidate_inode = candidate_file.stat().st_ino
        # Deliberately bypass atomic_write_text to model an uncontrolled checker.
        candidate_file.write_text("candidate mutation\n", encoding="utf-8", newline="\n")
        conditions = [
            FIXTURE_COPY_POLICY == "HERMETIC_METADATA_PRESERVING_COPY_V1",
            source_file.read_bytes() == source_before,
            candidate_file.read_bytes() != source_before,
            source_inode != candidate_inode,
            source_file.stat().st_nlink == 1,
            candidate_file.stat().st_nlink == 1,
        ]
        return case_result(
            "mutation-fixtures-have-no-shared-writable-inodes",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["mutation fixture shared writable storage with source"],
            source_inode=source_inode,
            candidate_inode=candidate_inode,
            source_link_count=source_file.stat().st_nlink,
            candidate_link_count=candidate_file.stat().st_nlink,
            fixture_copy_policy=FIXTURE_COPY_POLICY,
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "mutation-fixtures-have-no-shared-writable-inodes",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )


def source_drift_attribution_case(_source: Path, root: Path) -> dict:
    """Prove external drift and sealed-seed mutation are distinguishable."""
    live = root / "source-drift-live"
    sealed = root / "source-drift-sealed"
    try:
        (live / "config/release").mkdir(parents=True, exist_ok=False)
        (live / "source.txt").write_text("baseline\n", encoding="utf-8", newline="\n")
        graph = {
            "schema_version": "1.0.0",
            "input_sets": {
                "source": {
                    "include": ["source.txt"],
                    "exclude": [],
                    "files": {
                        "source.txt": {
                            "bytes": 9,
                            "sha256": hashlib.sha256(b"baseline\n").hexdigest(),
                        }
                    },
                }
            },
        }
        write_json(live / GRAPH_PATH, graph)
        baseline = locked_source_inventory(live)
        snapshot_inventory, acquisition_drift, acquisition_mismatch = acquire_stable_source_snapshot(
            live,
            sealed,
            baseline,
        )

        (live / "source.txt").write_text("external edit\n", encoding="utf-8", newline="\n")
        external_changes = inventory_delta(baseline, locked_source_inventory(live))
        sealed_after_external = inventory_delta(snapshot_inventory, locked_source_inventory(sealed))

        (sealed / "source.txt").write_text("suite mutation\n", encoding="utf-8", newline="\n")
        sealed_changes = inventory_delta(snapshot_inventory, locked_source_inventory(sealed))

        conditions = [
            not acquisition_drift,
            not acquisition_mismatch,
            [item["path"] for item in external_changes] == ["source.txt"],
            not sealed_after_external,
            [item["path"] for item in sealed_changes] == ["source.txt"],
            inventory_root_sha256(baseline) != inventory_root_sha256(locked_source_inventory(live)),
            inventory_root_sha256(snapshot_inventory) != inventory_root_sha256(locked_source_inventory(sealed)),
        ]
        return case_result(
            "source-drift-attribution-distinguishes-external-edit-from-suite-mutation",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["source-drift attribution boundary differed"],
            source_snapshot_isolation=SUITE_SOURCE_ISOLATION,
            external_changed_paths=[item["path"] for item in external_changes],
            sealed_changed_paths=[item["path"] for item in sealed_changes],
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "source-drift-attribution-distinguishes-external-edit-from-suite-mutation",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )


def canonical_baseline_fail_fast_case(source: Path, root: Path) -> dict:
    """Prove a stale canonical lock stops before any adversarial scheduler starts."""
    candidate = root / "canonical-baseline-fail-fast"
    try:
        copy_repo(source, candidate)
        stale_path = candidate / "scripts/release_source_closure.py"
        atomic_write_text(
            stale_path,
            stale_path.read_text(encoding="utf-8") + "\n# deliberate stale-lock probe\n",
        )
        report_path = candidate / "reports/baseline-fail-fast.json"
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/test_release_graph.py",
                "--repo",
                ".",
                "--json-output",
                str(report_path.relative_to(candidate)),
            ],
            cwd=candidate,
            text=True,
            capture_output=True,
            check=False,
            timeout=90,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        case_ids = [item.get("case_id") for item in report.get("results", [])]
        conditions = [
            completed.returncode == 3,
            report.get("classification") == FAIL,
            report.get("baseline_fail_fast") == BASELINE_FAIL_FAST,
            case_ids == [
                "stable-source-snapshot-acquisition",
                "canonical_graph_baseline",
                SOURCE_INTEGRITY_CASE_ID,
            ],
            report.get("errors") == ["canonical_graph_baseline"],
            "release-graph adversarial scheduler:" not in completed.stdout,
            "release-graph heavyweight scheduler:" not in completed.stdout,
        ]
        return case_result(
            "canonical-baseline-failure-stops-before-adversarial-scheduling",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["canonical baseline did not fail fast"],
            observed_returncode=completed.returncode,
            observed_case_ids=case_ids,
            observed_errors=report.get("errors", []),
            stdout_tail=completed.stdout[-1200:],
            stderr_tail=completed.stderr[-1200:],
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "canonical-baseline-failure-stops-before-adversarial-scheduling",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )


def concurrent_source_drift_attribution_case(source: Path, root: Path) -> dict:
    """Prove a concurrent edit is not falsely attributed to a child fixture."""
    candidate = root / "concurrent-source-drift-attribution"
    log_path = candidate / "nested.log"
    report_path = candidate / "reports/concurrent-drift.json"
    try:
        copy_repo(source, candidate)
        command = [
            sys.executable,
            "scripts/test_release_graph.py",
            "--repo",
            ".",
            "--json-output",
            str(report_path.relative_to(candidate)),
            "--heavy-case-timeout-seconds",
            "60",
            "--case",
            "heavyweight-process-tree-timeout-is-bounded",
            "--case",
            SOURCE_INTEGRITY_CASE_ID,
        ]
        with log_path.open("w", encoding="utf-8", newline="\n") as log_handle:
            process = subprocess.Popen(
                command,
                cwd=candidate,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                **_process_group_kwargs(),
            )
            deadline = time.monotonic() + 30
            marker = "release-graph adversarial case: heavyweight-process-tree-timeout-is-bounded"
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                log_handle.flush()
                observed = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
                if marker in observed:
                    break
                time.sleep(0.1)
            observed = log_path.read_text(encoding="utf-8") if log_path.is_file() else ""
            if marker not in observed:
                termination = _terminate_subprocess_tree(process)
                return case_result(
                    "concurrent-source-drift-is-attributed-without-blaming-suite-fixtures",
                    FAIL,
                    errors=["nested suite did not reach the post-snapshot heavyweight marker"],
                    termination=termination,
                    log_tail=observed[-1200:],
                )
            package_path = candidate / "package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["asklepios_concurrent_drift_probe"] = True
            atomic_write_text(package_path, json.dumps(package, indent=2) + "\n")
            try:
                process.wait(timeout=90)
            except subprocess.TimeoutExpired:
                termination = _terminate_subprocess_tree(process)
                return case_result(
                    "concurrent-source-drift-is-attributed-without-blaming-suite-fixtures",
                    FAIL,
                    errors=["nested concurrent-drift suite timed out"],
                    termination=termination,
                )
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        integrity = next(
            (item for item in report.get("results", []) if item.get("case_id") == SOURCE_INTEGRITY_CASE_ID),
            {},
        )
        concurrent_paths = [item.get("path") for item in integrity.get("concurrent_source_changes", [])]
        conditions = [
            process.returncode == 3,
            report.get("classification") == FAIL,
            integrity.get("classification") == FAIL,
            integrity.get("source_mutation_attribution") == "EXTERNAL_CONCURRENT_DRIFT",
            integrity.get("sealed_snapshot_changes") == [],
            concurrent_paths == ["package.json"],
        ]
        return case_result(
            "concurrent-source-drift-is-attributed-without-blaming-suite-fixtures",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["concurrent source drift attribution differed"],
            observed_returncode=process.returncode,
            source_mutation_attribution=integrity.get("source_mutation_attribution"),
            concurrent_changed_paths=concurrent_paths,
            sealed_snapshot_changes=integrity.get("sealed_snapshot_changes"),
            log_tail=log_path.read_text(encoding="utf-8")[-1200:] if log_path.is_file() else "",
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "concurrent-source-drift-is-attributed-without-blaming-suite-fixtures",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )


def checkpoint_case(source: Path, root: Path) -> dict:
    mini = root / "checkpoint-reuse-and-invalidation"
    mini.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "scripts/release_graph_core.py", mini / "release_graph_core.py")
    shutil.copy2(source / "scripts/run_release_graph.py", mini / "run_release_graph.py")
    write_mini_tool(mini / "tool.py")
    (mini / "a.txt").write_text("a1\n", encoding="utf-8")
    (mini / "c.txt").write_text("c1\n", encoding="utf-8")
    (mini / "package.json").write_text(json.dumps({"scripts": {"noop": "echo noop"}}, indent=2) + "\n", encoding="utf-8")
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "mini-checkpoint-graph",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "input_sets": {
            "a": {"include": ["a.txt", "tool.py", "run_release_graph.py", "release_graph_core.py", "package.json"], "exclude": [], "files": {}},
            "c": {"include": ["c.txt"], "exclude": [], "files": {}},
        },
        "managed_package_scripts": {"noop": "echo noop"},
        "stages": [
            {"id": "a", "command": [sys.executable, "tool.py", "--input", "a.txt", "--output", "out/a.txt"], "needs": [], "input_sets": ["a"], "outputs": ["out/a.txt"], "failure_classification": "FAIL", "read_only": True},
            {"id": "b", "command": [sys.executable, "tool.py", "--input", "out/a.txt", "--output", "out/b.txt", "--fail-flag", "fail.flag"], "needs": ["a"], "input_sets": ["a"], "outputs": ["out/b.txt"], "failure_classification": "FAIL", "read_only": True},
            {"id": "c", "command": [sys.executable, "tool.py", "--input", "c.txt", "--output", "out/c.txt"], "needs": [], "input_sets": ["c"], "outputs": ["out/c.txt"], "failure_classification": "FAIL", "read_only": True},
        ],
        "targets": {"all": {"terminal_stages": ["b", "c"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "graph.json", graph)
    receipts = mini / "receipts"

    def execute(summary: str, *, no_reuse: bool = False) -> tuple[int, dict]:
        command = [sys.executable, "run_release_graph.py", "--repo", ".", "--graph", "graph.json", "--target", "all", "--receipt-dir", str(receipts), "--summary-output", summary]
        if no_reuse:
            command.append("--no-reuse")
        completed = subprocess.run(command, cwd=mini, text=True, capture_output=True, check=False)
        payload = json.loads((mini / summary).read_text(encoding="utf-8")) if (mini / summary).is_file() else {}
        payload["stdout_tail"] = completed.stdout[-1000:]
        payload["stderr_tail"] = completed.stderr[-1000:]
        return completed.returncode, payload

    try:
        rc1, first = execute("first.json", no_reuse=True)
        rc2, second = execute("second.json")
        # Change only input set a and re-lock that set. Stage c must remain reusable.
        (mini / "a.txt").write_text("a2\n", encoding="utf-8")
        graph = json.loads((mini / "graph.json").read_text(encoding="utf-8"))
        graph = lock_input_sets(mini, graph, ["a"])
        write_json(mini / "graph.json", graph)
        rc3, third = execute("third.json")
        # A failed b receipt cannot satisfy the chain; after correction, execution resumes.
        (mini / "fail.flag").write_text("fail\n", encoding="utf-8")
        rc4, failed = execute("failed.json", no_reuse=True)
        failed_receipt = json.loads((receipts / "b.json").read_text(encoding="utf-8"))
        failed_diagnostics = failed_receipt.get("diagnostics", {})
        failed_log_path = mini / str(failed_diagnostics.get("combined_log_path", ""))
        failed_log = failed_log_path.read_text(encoding="utf-8") if failed_log_path.is_file() else ""
        (mini / "fail.flag").unlink()
        rc5, resumed = execute("resumed.json")
        second_map = {item["stage"]: item for item in second.get("results", [])}
        third_map = {item["stage"]: item for item in third.get("results", [])}
        resumed_map = {item["stage"]: item for item in resumed.get("results", [])}
        conditions = [
            rc1 == 0 and first.get("classification") == PASS,
            rc2 == 0 and all(second_map.get(stage, {}).get("reused") for stage in ("a", "b", "c")),
            rc3 == 0 and not third_map.get("a", {}).get("reused") and not third_map.get("b", {}).get("reused") and third_map.get("c", {}).get("reused"),
            rc4 != 0 and failed.get("first_invalid_stage") == "b" and failed.get("classification") == FAIL,
            failed_receipt.get("errors") == ["stage command exited:3"],
            failed_diagnostics.get("combined_log_sha256") and "deliberate stage failure" in failed_log,
            any("deliberate stage failure" in line for line in failed_diagnostics.get("tail", [])),
            rc5 == 0 and resumed.get("classification") == PASS and resumed_map.get("c", {}).get("reused"),
        ]
        return case_result(
            "checkpoint-reuse-invalidation-and-resume",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["checkpoint behavior differed"],
            first=first,
            second=second,
            third=third,
            failed=failed,
            resumed=resumed,
        )
    except Exception as exc:  # noqa: BLE001
        return case_result("checkpoint-reuse-invalidation-and-resume", INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"])


def independent_failure_collection_case(source: Path, root: Path) -> dict:
    """A failed clean read-only branch must not hide failures or passes on independent branches."""
    mini = root / "independent-failure-collection"
    mini.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "scripts/release_graph_core.py", mini / "release_graph_core.py")
    shutil.copy2(source / "scripts/run_release_graph.py", mini / "run_release_graph.py")
    write_mini_tool(mini / "tool.py")
    (mini / "a.txt").write_text("a\n", encoding="utf-8")
    (mini / "c.txt").write_text("c\n", encoding="utf-8")
    (mini / "fail.flag").write_text("fail\n", encoding="utf-8")
    (mini / "package.json").write_text(json.dumps({"scripts": {"noop": "echo noop"}}, indent=2) + "\n", encoding="utf-8")
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "mini-independent-diagnostic-graph",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "input_sets": {
            "a": {"include": ["a.txt", "fail.flag", "tool.py", "run_release_graph.py", "release_graph_core.py", "package.json"], "exclude": [], "files": {}},
            "c": {"include": ["c.txt"], "exclude": [], "files": {}},
        },
        "managed_package_scripts": {"noop": "echo noop"},
        "stages": [
            {"id": "a", "command": [sys.executable, "tool.py", "--input", "a.txt", "--output", "out/a.txt"], "needs": [], "input_sets": ["a"], "outputs": ["out/a.txt"], "failure_classification": "FAIL", "read_only": True},
            {"id": "b", "command": [sys.executable, "tool.py", "--input", "a.txt", "--output", "out/b.txt", "--fail-flag", "fail.flag"], "needs": ["a"], "input_sets": ["a"], "outputs": [{"path": "out/b.txt", "required": False}], "failure_classification": "FAIL", "read_only": True},
            {"id": "b-child", "command": [sys.executable, "tool.py", "--input", "a.txt", "--output", "out/b-child.txt"], "needs": ["b"], "input_sets": ["a"], "outputs": ["out/b-child.txt"], "failure_classification": "FAIL", "read_only": True},
            {"id": "c", "command": [sys.executable, "tool.py", "--input", "c.txt", "--output", "out/c.txt"], "needs": [], "input_sets": ["c"], "outputs": ["out/c.txt"], "failure_classification": "FAIL", "read_only": True},
            {"id": "c-child", "command": [sys.executable, "tool.py", "--input", "out/c.txt", "--output", "out/c-child.txt"], "needs": ["c"], "input_sets": ["c"], "outputs": ["out/c-child.txt"], "failure_classification": "FAIL", "read_only": True},
        ],
        "targets": {"all": {"terminal_stages": ["b-child", "c-child"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "graph.json", graph)
    command = [
        sys.executable, "run_release_graph.py", "--repo", ".", "--graph", "graph.json",
        "--target", "all", "--receipt-dir", "receipts", "--summary-output", "summary.json",
        "--no-reuse", "--collect-independent-failures",
    ]
    try:
        completed = subprocess.run(command, cwd=mini, text=True, capture_output=True, check=False)
        summary = json.loads((mini / "summary.json").read_text(encoding="utf-8"))
        result_map = {item["stage"]: item for item in summary.get("results", [])}
        conditions = [
            completed.returncode == 3,
            summary.get("classification") == FAIL,
            summary.get("diagnostic_mode") is True,
            summary.get("first_invalid_stage") == "b",
            summary.get("failed_stages") == ["b"],
            summary.get("failure_count") == 1,
            summary.get("blocked_stage_count") == 1,
            len(summary.get("failed_stage_details", [])) == 1,
            summary.get("failed_stage_details", [{}])[0].get("stage") == "b",
            summary.get("failed_stage_details", [{}])[0].get("combined_log_sha256") is not None,
            len(summary.get("blocked_stage_details", [])) == 1,
            summary.get("blocked_stage_details", [{}])[0].get("stage") == "b-child",
            summary.get("blocked_stage_details", [{}])[0].get("blocked_by") == ["b"],
            result_map.get("a", {}).get("classification") == PASS,
            result_map.get("b", {}).get("classification") == FAIL,
            result_map.get("b-child", {}).get("executed") is False,
            result_map.get("b-child", {}).get("blocked_by") == ["b"],
            result_map.get("c", {}).get("classification") == PASS,
            result_map.get("c-child", {}).get("classification") == PASS,
            (mini / "out/c-child.txt").is_file(),
            not (mini / "out/b-child.txt").exists(),
        ]
        return case_result(
            "independent-read-only-failures-are-collected-without-running-dependents",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["independent failure collection behavior differed"],
            summary=summary,
            stdout_tail=completed.stdout[-2000:],
            stderr_tail=completed.stderr[-2000:],
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "independent-read-only-failures-are-collected-without-running-dependents",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )


def unsafe_failure_stops_collection_case(source: Path, root: Path, *, mutate_input: bool) -> dict:
    """Diagnostic collection must stop at write failures and read-only input mutation."""
    case_id = (
        "read-only-input-mutation-stops-diagnostic-sweep"
        if mutate_input
        else "write-stage-failure-stops-diagnostic-sweep"
    )
    mini = root / case_id
    mini.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "scripts/release_graph_core.py", mini / "release_graph_core.py")
    shutil.copy2(source / "scripts/run_release_graph.py", mini / "run_release_graph.py")
    write_mini_tool(mini / "tool.py")
    (mini / "a.txt").write_text("a\n", encoding="utf-8")
    (mini / "c.txt").write_text("c\n", encoding="utf-8")
    (mini / "fail.flag").write_text("fail\n", encoding="utf-8")
    (mini / "package.json").write_text(
        json.dumps({"scripts": {"noop": "echo noop"}}, indent=2) + "\n",
        encoding="utf-8",
    )
    failing_command = [
        sys.executable,
        "tool.py",
        "--input",
        "a.txt",
        "--output",
        "out/failing.txt",
        "--fail-flag",
        "fail.flag",
    ]
    if mutate_input:
        failing_command.append("--mutate-input-on-fail")
    graph = {
        "schema_version": "1.0.0",
        "graph_id": f"mini-{case_id}",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "input_sets": {
            "a": {
                "include": [
                    "a.txt", "fail.flag", "tool.py", "run_release_graph.py",
                    "release_graph_core.py", "package.json",
                ],
                "exclude": [],
                "files": {},
            },
            "c": {"include": ["c.txt"], "exclude": [], "files": {}},
        },
        "managed_package_scripts": {"noop": "echo noop"},
        "stages": [
            {
                "id": "failing",
                "command": failing_command,
                "needs": [],
                "input_sets": ["a"],
                "outputs": [{"path": "out/failing.txt", "required": False}],
                "failure_classification": "FAIL",
                "read_only": bool(mutate_input),
            },
            {
                "id": "independent",
                "command": [
                    sys.executable, "tool.py", "--input", "c.txt", "--output", "out/independent.txt",
                ],
                "needs": [],
                "input_sets": ["c"],
                "outputs": ["out/independent.txt"],
                "failure_classification": "FAIL",
                "read_only": True,
            },
        ],
        "targets": {"all": {"terminal_stages": ["failing", "independent"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "graph.json", graph)
    command = [
        sys.executable,
        "run_release_graph.py",
        "--repo",
        ".",
        "--graph",
        "graph.json",
        "--target",
        "all",
        "--receipt-dir",
        "receipts",
        "--summary-output",
        "summary.json",
        "--no-reuse",
        "--collect-independent-failures",
    ]
    try:
        completed = subprocess.run(command, cwd=mini, text=True, capture_output=True, check=False)
        summary = json.loads((mini / "summary.json").read_text(encoding="utf-8"))
        result_map = {item["stage"]: item for item in summary.get("results", [])}
        failure_errors = result_map.get("failing", {}).get("errors", [])
        conditions = [
            completed.returncode == 3,
            summary.get("classification") == FAIL,
            summary.get("first_invalid_stage") == "failing",
            result_map.get("failing", {}).get("classification") == FAIL,
            "independent" not in result_map,
            not (mini / "out/independent.txt").exists(),
        ]
        if mutate_input:
            conditions.extend([
                any(error.startswith("read-only stage changed locked inputs:") for error in failure_errors),
                (mini / "a.txt").read_text(encoding="utf-8") == "a\nmutated\n",
            ])
        else:
            conditions.append(not any(error.startswith("read-only stage changed locked inputs:") for error in failure_errors))
        return case_result(
            case_id,
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["unsafe failure did not stop diagnostic collection"],
            summary=summary,
            stdout_tail=completed.stdout[-2000:],
            stderr_tail=completed.stderr[-2000:],
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"])


def write_failure_stops_collection_case(source: Path, root: Path) -> dict:
    return unsafe_failure_stops_collection_case(source, root, mutate_input=False)


def read_only_mutation_stops_collection_case(source: Path, root: Path) -> dict:
    return unsafe_failure_stops_collection_case(source, root, mutate_input=True)


def internal_error_receipt_case(source: Path, root: Path) -> dict:
    mini = root / "internal-error-receipt"
    mini.mkdir(parents=True, exist_ok=False)
    shutil.copy2(source / "scripts/release_graph_core.py", mini / "release_graph_core.py")
    shutil.copy2(source / "scripts/run_release_graph.py", mini / "run_release_graph.py")
    (mini / "input.txt").write_text("input\n", encoding="utf-8")
    (mini / "package.json").write_text(json.dumps({"scripts": {"noop": "echo noop"}}, indent=2) + "\n", encoding="utf-8")
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "mini-internal-error-graph",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "input_sets": {
            "source": {
                "include": ["input.txt", "run_release_graph.py", "release_graph_core.py", "package.json"],
                "exclude": [],
                "files": {},
            },
        },
        "managed_package_scripts": {"noop": "echo noop"},
        "stages": [
            {
                "id": "crash",
                "command": ["__asklepios_missing_executable__"],
                "needs": [],
                "input_sets": ["source"],
                "outputs": [{"path": "never-created.txt", "required": False}],
                "failure_classification": "FAIL",
                "read_only": True,
            },
        ],
        "targets": {"all": {"terminal_stages": ["crash"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "graph.json", graph)
    command = [
        sys.executable, "run_release_graph.py", "--repo", ".", "--graph", "graph.json",
        "--target", "all", "--receipt-dir", "receipts", "--summary-output", "summary.json",
    ]
    try:
        first = subprocess.run(command, cwd=mini, text=True, capture_output=True, check=False)
        summary = json.loads((mini / "summary.json").read_text(encoding="utf-8"))
        receipt = json.loads((mini / "receipts/crash.json").read_text(encoding="utf-8"))
        first_hash = receipt.get("receipt_sha256")
        second = subprocess.run(command, cwd=mini, text=True, capture_output=True, check=False)
        second_summary = json.loads((mini / "summary.json").read_text(encoding="utf-8"))
        second_receipt = json.loads((mini / "receipts/crash.json").read_text(encoding="utf-8"))
        conditions = [
            first.returncode == 4,
            summary.get("classification") == INTERNAL_ERROR,
            summary.get("first_invalid_stage") == "crash",
            len(summary.get("failed_stage_details", [])) == 1,
            summary.get("failed_stage_details", [{}])[0].get("stage") == "crash",
            receipt.get("classification") == INTERNAL_ERROR,
            receipt.get("exit_status") == 4,
            receipt_valid(receipt),
            second.returncode == 4,
            second_summary.get("results", [{}])[-1].get("reused") is False,
            receipt_valid(second_receipt),
            first_hash != second_receipt.get("receipt_sha256"),
        ]
        return case_result(
            "internal-error-receipt-is-durable-and-not-reusable",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["internal-error receipt behavior differed"],
            observed_classification=summary.get("classification"),
            first_returncode=first.returncode,
            second_returncode=second.returncode,
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "internal-error-receipt-is-durable-and-not-reusable",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )



def scenario_hermetic_case(source: Path, root: Path) -> dict:
    """Prove locked uncommitted source is overlaid and failures are attributed."""
    mini = root / "scenario-hermetic-isolation"
    (mini / "scripts").mkdir(parents=True, exist_ok=False)
    (mini / "config/release").mkdir(parents=True)
    for name in ("release_graph_core.py", "run_scenario_contract_gate.py"):
        shutil.copy2(source / "scripts" / name, mini / "scripts" / name)

    # Import the exact canonical gate contract instead of maintaining a second
    # hand-written copy in the adversarial harness.  Any production gate change
    # therefore changes the fixture automatically and cannot create a stale test
    # approximation.
    canonical_scripts = dict(SCENARIO_GATE_CANONICAL_SCRIPTS)
    expected_outputs = tuple(SCENARIO_GATE_EXPECTED_OUTPUTS)
    fake_npm = mini / "fake_npm.py"
    fake_npm.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path, PureWindowsPath
script = sys.argv[2] if len(sys.argv) > 2 and sys.argv[1] == 'run' else '<invalid>'
if Path('.asklepios').exists():
 print('ambient checkpoint directory leaked into hermetic workspace', file=sys.stderr)
 raise SystemExit(9)
if Path('source.txt').read_text(encoding='utf-8') != 'overlay-v2\\n':
 print('locked working-tree overlay was not applied', file=sys.stderr)
 raise SystemExit(8)
print(f'fake npm subgate:{script}')
if os.environ.get('ASKLEPIOS_FAKE_FAIL') == script:
 print(f'synthetic failure for {script}', file=sys.stderr)
 raise SystemExit(7)
outputs = %r
for relative in outputs:
 path = Path(relative); path.parent.mkdir(parents=True, exist_ok=True)
 path.write_text(f'{relative}:deterministic\\n', encoding='utf-8', newline='\\n')
""" % (expected_outputs,),
        encoding="utf-8",
        newline="\n",
    )
    fake_npm.chmod(0o755)
    (mini / "source.txt").write_text("committed-v1\n", encoding="utf-8", newline="\n")
    package_scripts = dict(canonical_scripts)
    package_scripts.update({
        "check:scenario-contract-gate": "python scripts/run_scenario_contract_gate.py --repo . --mode check",
        "verify:scenario-contracts": "python scripts/run_scenario_contract_gate.py --repo . --mode write",
    })
    (mini / "package.json").write_text(
        json.dumps({"scripts": package_scripts}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "mini-scenario-hermetic-graph",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "input_sets": {
            "orchestration": {
                "include": ["package.json", "scripts/release_graph_core.py", "scripts/run_scenario_contract_gate.py", "fake_npm.py"],
                "exclude": [],
                "files": {},
            },
            "scenario-source": {"include": ["source.txt"], "exclude": [], "files": {}},
        },
        "managed_package_scripts": package_scripts,
        "stages": [{
            "id": "scenario.contracts",
            "command": ["npm", "run", "check:scenario-contract-gate"],
            "needs": [],
            "input_sets": ["orchestration", "scenario-source"],
            "outputs": ["reports/scenario-contract-gate.json"],
            "read_only": True,
            "failure_classification": "FAIL",
        }],
        "targets": {"scenario": {"terminal_stages": ["scenario.contracts"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "config/release/RELEASE_GRAPH.json", graph)
    subprocess.run(["git", "init", "--quiet"], cwd=mini, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=mini, check=True)
    subprocess.run(["git", "config", "user.name", "Hermetic Test"], cwd=mini, check=True)
    subprocess.run(["git", "add", "-A"], cwd=mini, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "fixture"], cwd=mini, check=True)
    (mini / "node_modules").mkdir()
    (mini / ".asklepios/release-receipts").mkdir(parents=True)
    (mini / ".asklepios/release-receipts/ambient.json").write_text("{}\n", encoding="utf-8")

    # Simulate a reviewed package applied but not committed yet.  Both the source
    # byte and its graph lock live only in the working tree.
    (mini / "source.txt").write_text("overlay-v2\n", encoding="utf-8", newline="\n")
    graph = json.loads((mini / "config/release/RELEASE_GRAPH.json").read_text(encoding="utf-8"))
    graph = lock_input_sets(mini, graph, ["scenario-source"])
    write_json(mini / "config/release/RELEASE_GRAPH.json", graph)

    command = [
        sys.executable,
        "scripts/run_scenario_contract_gate.py",
        "--repo", ".",
        "--npm-executable", str(fake_npm),
        "--json-output", "reports/scenario-contract-gate.json",
        "--mode", "write",
    ]
    try:
        success = subprocess.run(command, cwd=mini, text=True, capture_output=True, check=False)
        success_report = json.loads((mini / "reports/scenario-contract-gate.json").read_text(encoding="utf-8"))
        failed_env = os.environ.copy()
        failed_env["ASKLEPIOS_FAKE_FAIL"] = "assure:scenario-core"
        failure = subprocess.run(command, cwd=mini, env=failed_env, text=True, capture_output=True, check=False)
        failure_report = json.loads((mini / "reports/scenario-contract-gate.json").read_text(encoding="utf-8"))
        failed_result = next(
            (item for item in failure_report.get("steps", []) if item.get("id") == "assure:scenario-core"),
            {},
        )
        conditions = [
            success.returncode == 0,
            success_report.get("classification") == PASS,
            success_report.get("isolation") == "DETACHED_GIT_WORKTREE_WITH_LOCKED_OVERLAY_V2",
            success_report.get("locked_overlay_files", 0) >= 5,
            len(success_report.get("steps", [])) == len(canonical_scripts),
            all((mini / relative).is_file() for relative in expected_outputs),
            failure.returncode == 3,
            failure_report.get("classification") == FAIL,
            failure_report.get("first_invalid_step") == "assure:scenario-core",
            failed_result.get("exit_status") == 7,
            any("synthetic failure" in line for line in failed_result.get("stderr_tail", [])),
        ]
        return case_result(
            "scenario-contract-gate-is-hermetic-and-attributed",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["hermetic scenario behavior differed"],
            successful_run=success_report,
            failed_run=failure_report,
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "scenario-contract-gate-is-hermetic-and-attributed",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )



def decision_artifact_harness_cwd_case(source: Path, root: Path) -> dict:
    """The artifact mutation harness must be independent of the caller working directory."""
    mini = root / "decision-artifact-harness-cwd"
    external = root / "decision-artifact-external-cwd"
    external.mkdir(parents=True, exist_ok=False)
    paths = [
        Path("config/facility-decision/ASK-D-001.json"),
        Path("scripts/check_facility_decision_artifacts.py"),
        Path("scripts/check_facility_decision_artifacts.mjs"),
        Path("scripts/test_facility_decision_artifact_mutations.py"),
        Path("scripts/release_result.py"),
        *[
            Path("examples/facility-decision") / name
            for name in (
                "README.md",
                "alternate-session.json",
                "demo-projection.json",
                "instructor-projection.json",
                "learner-projection.json",
                "manifest.json",
                "reference-session.json",
                "teaching-projection.json",
            )
        ],
    ]
    try:
        for relative in paths:
            target = mini / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / relative, target)
        command = [
            sys.executable,
            str((mini / "scripts/test_facility_decision_artifact_mutations.py").resolve()),
            "--repo", str(mini.resolve()),
            "--json-output", "reports/cwd-independent-artifact-mutations.json",
        ]
        completed = subprocess.run(
            command,
            cwd=external,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        report_path = mini / "reports/cwd-independent-artifact-mutations.json"
        report = json.loads(report_path.read_text(encoding="utf-8")) if report_path.is_file() else {}
        case_map = {item.get("case_id"): item for item in report.get("results", [])}
        conditions = [
            completed.returncode == 0,
            report.get("classification") == PASS,
            report.get("status") == PASS,
            report.get("cases") == 15,
            report.get("fixture_inventory_mode") == "MANIFEST_DECLARED_CLOSED_REGULAR_FILE_INVENTORY_V1",
            report.get("checker_result_mode") == "UNIQUE_REPORT_FILES_NOT_STDOUT_V1",
            report.get("accepted_forgery_count") == 0,
            report.get("single_checker_only_rejections") == 0,
            (case_map.get("checker_stdout_noise_tolerated") or {}).get("pass") is True,
            (case_map.get("checker_stdout_noise_tolerated") or {}).get("classification") == PASS,
            (case_map.get("ambient_artifact_directory_rejected") or {}).get("pass") is True,
            (case_map.get("ambient_artifact_directory_rejected") or {}).get("classification") == EXPECTED_REJECTION,
        ]
        return case_result(
            "decision-artifact-mutation-harness-is-cwd-independent-and-attributed",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["decision artifact harness depended on caller CWD or lost attribution"],
            report=report,
            stdout_tail=completed.stdout.splitlines()[-30:],
            stderr_tail=completed.stderr.splitlines()[-30:],
        )
    except subprocess.TimeoutExpired as exc:
        return case_result(
            "decision-artifact-mutation-harness-is-cwd-independent-and-attributed",
            INTERNAL_ERROR,
            errors=["decision artifact harness timed out after 180 seconds"],
            stdout_tail=(exc.stdout or "").splitlines()[-30:],
            stderr_tail=(exc.stderr or "").splitlines()[-30:],
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "decision-artifact-mutation-harness-is-cwd-independent-and-attributed",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )

def build_reproducibility_case(source: Path, root: Path) -> dict:
    """Prove the double build is isolated, deterministic, and diagnostically complete."""
    mini = root / "build-reproducibility-isolation"
    (mini / "scripts").mkdir(parents=True, exist_ok=False)
    (mini / "config/release").mkdir(parents=True)
    (mini / "tool-bin").mkdir(parents=True)
    for name in (
        "release_graph_core.py",
        "release_result.py",
        "run_release_build_reproducibility.py",
    ):
        shutil.copy2(source / "scripts" / name, mini / "scripts" / name)

    provenance = mini / "scripts/build_facility_decision_provenance.py"
    provenance.write_text(
        """#!/usr/bin/env python3
import argparse
import json
from pathlib import Path, PureWindowsPath
p=argparse.ArgumentParser();p.add_argument('--repo');p.add_argument('--subject-dir');p.add_argument('--output');a=p.parse_args()
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'status':'PASS'},sort_keys=True)+chr(10),encoding='utf-8')
Path('provenance-was-run.marker').write_text('yes'+chr(10),encoding='utf-8')
""",
        encoding="utf-8",
        newline="\n",
    )
    provenance.chmod(0o755)

    fake_npm_program = mini / "tool-bin/fake_npm.py"
    fake_npm_program.write_text(
        """import sys
from pathlib import Path, PureWindowsPath
if len(sys.argv) != 3 or sys.argv[1] != 'run' or sys.argv[2] not in {'build:generate','build:typecheck','build:bundle'}:
 print('unexpected fake npm invocation:'+repr(sys.argv[1:]),file=sys.stderr);raise SystemExit(11)
script=sys.argv[2]
if Path('ambient-untracked.txt').exists():
 print('ambient untracked file leaked into build sandbox',file=sys.stderr);raise SystemExit(9)
if script == 'build:typecheck' and 'FAIL' in Path('source.txt').read_text(encoding='utf-8'):
 print('synthetic TypeScript error: restricted projection field',file=sys.stderr);raise SystemExit(7)
if script == 'build:bundle':
 source=Path('source.txt').read_text(encoding='utf-8')
 out=Path('dist/index.html');out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text('built:'+source,encoding='utf-8')
print('fake deterministic step complete:'+script)
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_npm = mini / "tool-bin/npm"
    fake_npm.write_text(
        """#!/usr/bin/env python3
import runpy
from pathlib import Path, PureWindowsPath
runpy.run_path(str(Path(__file__).with_name('fake_npm.py')), run_name='__main__')
""",
        encoding="utf-8",
        newline="\n",
    )
    fake_npm.chmod(0o755)
    fake_npm_cmd = mini / "tool-bin/npm.cmd"
    fake_npm_cmd.write_text(
        '@echo off\r\npython "%~dp0fake_npm.py" %*\r\n',
        encoding="utf-8",
        newline="",
    )
    (mini / "source.txt").write_text("fixture-source\n", encoding="utf-8", newline="\n")
    (mini / "package.json").write_text(
        json.dumps({"scripts": {"build:generate": "fake-generate", "build:typecheck": "fake-typecheck", "build:bundle": "fake-bundle", "noop": "echo noop"}}, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "mini-build-reproducibility-graph",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "input_sets": {
            "build": {
                "include": [
                    "source.txt", "package.json", "tool-bin/fake_npm.py", "tool-bin/npm", "tool-bin/npm.cmd",
                    "scripts/release_graph_core.py", "scripts/release_result.py",
                    "scripts/run_release_build_reproducibility.py",
                    "scripts/build_facility_decision_provenance.py",
                ],
                "exclude": [],
                "files": {},
            },
        },
        "managed_package_scripts": {"noop": "echo noop"},
        "stages": [{
            "id": "noop",
            "command": ["npm", "run", "noop"],
            "needs": [],
            "input_sets": ["build"],
            "outputs": [],
            "read_only": True,
            "failure_classification": "FAIL",
        }],
        "targets": {"noop": {"terminal_stages": ["noop"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "config/release/RELEASE_GRAPH.json", graph)
    subprocess.run(["git", "init", "--quiet"], cwd=mini, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=mini, check=True)
    subprocess.run(["git", "config", "user.name", "Build Test"], cwd=mini, check=True)
    subprocess.run(["git", "add", "-A"], cwd=mini, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "fixture"], cwd=mini, check=True)
    (mini / "node_modules").mkdir()
    (mini / "ambient-untracked.txt").write_text("must not leak\n", encoding="utf-8", newline="\n")
    command = [
        sys.executable, "scripts/run_release_build_reproducibility.py", "--repo", ".",
        "--json-output", "reports/repro.json",
        "--provenance-output", "reports/provenance.json",
    ]
    environment = os.environ.copy()
    environment["PATH"] = str((mini / "tool-bin").resolve()) + os.pathsep + environment.get("PATH", "")
    try:
        success = subprocess.run(command, cwd=mini, env=environment, text=True, capture_output=True, check=False)
        success_report = json.loads((mini / "reports/repro.json").read_text(encoding="utf-8"))
        success_dist = (mini / "dist/index.html").read_text(encoding="utf-8") if (mini / "dist/index.html").is_file() else ""
        marker = mini / "provenance-was-run.marker"
        provenance_ran_on_success = marker.is_file()
        marker.unlink(missing_ok=True)
        shutil.rmtree(mini / "dist", ignore_errors=True)
        (mini / "source.txt").write_text("FAIL fixture-source\n", encoding="utf-8", newline="\n")
        failure = subprocess.run(command, cwd=mini, env=environment, text=True, capture_output=True, check=False)
        failure_report = json.loads((mini / "reports/repro.json").read_text(encoding="utf-8"))
        conditions = [
            success.returncode == 0,
            success_report.get("classification") == PASS,
            success_report.get("build_mode") == "TWO_ISOLATED_REVIEWED_SOURCE_SNAPSHOTS_V2",
            success_report.get("source_inventory_mode") == "GIT_TRACKED_PLUS_RELEASE_LOCKED_INPUTS_V1",
            success_report.get("files_compared") == 1,
            success_report.get("first_build", {}).get("classification") == PASS,
            success_report.get("second_build", {}).get("classification") == PASS,
            len(success_report.get("first_build", {}).get("steps", [])) == 3,
            len(success_report.get("second_build", {}).get("steps", [])) == 3,
            success_report.get("first_build_root_sha256") == success_report.get("second_build_root_sha256"),
            success_report.get("provenance", {}).get("status") == PASS,
            provenance_ran_on_success,
            success_dist == "built:fixture-source\n",
            failure.returncode == 3,
            failure_report.get("classification") == FAIL,
            failure_report.get("first_build", {}).get("failed_step") == "build:typecheck",
            failure_report.get("second_build", {}).get("failed_step") == "build:typecheck",
            failure_report.get("provenance", {}).get("status") == "NOT_RUN_BUILD_FAILED",
            not marker.exists(),
            not (mini / "dist").exists(),
            any("synthetic TypeScript error" in line for line in failure_report.get("first_build", {}).get("tail", [])),
            any("synthetic TypeScript error" in line for line in failure_report.get("second_build", {}).get("tail", [])),
            not any("provenance generation failed" in item for item in failure_report.get("errors", [])),
        ]
        return case_result(
            "double-build-is-hermetic-deterministic-and-diagnostic",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["double-build behavior differed"],
            successful_run=success_report,
            failed_run=failure_report,
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "double-build-is-hermetic-deterministic-and-diagnostic",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )

def evidence_join_case(source: Path, root: Path) -> dict:
    """Prove the evidence join authenticates receipts and current outputs."""
    mini = root / "evidence-join-authentication"
    mini.mkdir(parents=True, exist_ok=False)
    for name in (
        "release_graph_core.py",
        "release_result.py",
        "run_release_graph.py",
        "join_release_graph_evidence.py",
    ):
        shutil.copy2(source / "scripts" / name, mini / name)
    write_mini_tool(mini / "tool.py")
    (mini / "input.txt").write_text("joined evidence\n", encoding="utf-8", newline="\n")
    (mini / "package.json").write_text(json.dumps({"scripts": {}}, indent=2) + "\n", encoding="utf-8", newline="\n")
    python = sys.executable
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "mini-evidence-join-graph",
        "classifications": ["PASS", "EXPECTED_REJECTION", "FAIL", "INTERNAL_ERROR"],
        "truth_boundaries": {
            "patient_care_use": "PROHIBITED",
            "operational_timing": "NOT_CALIBRATED",
            "concrete_treatments_admitted": 0,
            "production_ready": False,
        },
        "production_designation": "NOT_GRANTED",
        "input_sets": {
            "source": {
                "include": [
                    "input.txt", "tool.py", "release_graph_core.py", "release_result.py",
                    "run_release_graph.py", "join_release_graph_evidence.py", "package.json",
                ],
                "exclude": [],
                "files": {},
            },
        },
        "managed_package_scripts": {},
        "stages": [
            {
                "id": "prepare",
                "command": [python, "tool.py", "--input", "input.txt", "--output", "out/value.txt"],
                "needs": [],
                "input_sets": ["source"],
                "outputs": ["out/value.txt"],
                "failure_classification": "FAIL",
                "read_only": True,
            },
            {
                "id": "release.runtime-evidence-join",
                "command": [
                    python, "join_release_graph_evidence.py", "--repo", ".", "--graph", "graph.json",
                    "--scope", "runtime", "--target", "canonical-runtime", "--receipt-dir", "receipts",
                    "--json-output", "joined.json",
                ],
                "needs": ["prepare"],
                "input_sets": ["source"],
                "outputs": ["joined.json"],
                "failure_classification": "FAIL",
                "read_only": True,
            },
        ],
        "targets": {"canonical-runtime": {"terminal_stages": ["release.runtime-evidence-join"]}},
    }
    graph = lock_input_sets(mini, graph)
    write_json(mini / "graph.json", graph)
    runner = [
        python, "run_release_graph.py", "--repo", ".", "--graph", "graph.json",
        "--target", "canonical-runtime", "--receipt-dir", "receipts", "--no-reuse",
        "--summary-output", "summary.json",
    ]
    direct_join = [
        python, "join_release_graph_evidence.py", "--repo", ".", "--graph", "graph.json",
        "--scope", "runtime", "--target", "canonical-runtime", "--receipt-dir", "receipts",
    ]
    try:
        completed = subprocess.run(runner, cwd=mini, text=True, capture_output=True, check=False)
        summary = json.loads((mini / "summary.json").read_text(encoding="utf-8"))
        joined = json.loads((mini / "joined.json").read_text(encoding="utf-8"))
        receipt_path_value = mini / "receipts/prepare.json"
        original_receipt = json.loads(receipt_path_value.read_text(encoding="utf-8"))

        forged = dict(original_receipt)
        forged["classification"] = "FAIL"
        write_json(receipt_path_value, forged)
        forged_run = subprocess.run(
            [*direct_join, "--json-output", "forged.json"],
            cwd=mini, text=True, capture_output=True, check=False,
        )
        forged_report = json.loads((mini / "forged.json").read_text(encoding="utf-8"))

        write_json(receipt_path_value, original_receipt)
        (mini / "out/value.txt").write_text("tampered output\n", encoding="utf-8", newline="\n")
        output_run = subprocess.run(
            [*direct_join, "--json-output", "tampered-output.json"],
            cwd=mini, text=True, capture_output=True, check=False,
        )
        output_report = json.loads((mini / "tampered-output.json").read_text(encoding="utf-8"))

        conditions = [
            completed.returncode == 0,
            summary.get("classification") == PASS,
            joined.get("classification") == PASS,
            joined.get("authenticated_receipt_count") == 1,
            joined.get("patient_care_authority_granted") is False,
            joined.get("operational_timing_calibrated") is False,
            forged_run.returncode != 0,
            forged_report.get("classification") == FAIL,
            any("receipt invalid or missing:prepare" in item for item in forged_report.get("errors", [])),
            output_run.returncode != 0,
            output_report.get("classification") == FAIL,
            any("receipt binding differs:prepare:output_root_sha256" in item for item in output_report.get("errors", [])),
        ]
        return case_result(
            "evidence-join-authenticates-receipts-and-current-outputs",
            PASS if all(conditions) else FAIL,
            errors=[] if all(conditions) else ["evidence join authentication behavior differed"],
            successful_join=joined,
            forged_receipt_result=forged_report,
            tampered_output_result=output_report,
        )
    except Exception as exc:  # noqa: BLE001
        return case_result(
            "evidence-join-authenticates-receipts-and-current-outputs",
            INTERNAL_ERROR,
            errors=[f"{type(exc).__name__}:{exc}"],
        )



def per_case_source_guard_case(_source: Path, root: Path) -> dict:
    """Prove an accidental per-case source write is detected and contained."""
    original = root / "source-guard-original"
    candidate = root / "source-guard-candidate"
    (original / "config/release").mkdir(parents=True, exist_ok=False)
    (original / "locked.txt").write_text("reviewed\n", encoding="utf-8", newline="\n")
    graph = {
        "schema_version": "1.0.0",
        "graph_id": "source-guard-mini-graph",
        "input_sets": {
            "source": {
                "include": ["locked.txt"],
                "exclude": [],
                "files": {
                    "locked.txt": {
                        "bytes": len(b"reviewed\n"),
                        "sha256": hashlib.sha256(b"reviewed\n").hexdigest(),
                    }
                },
            }
        },
        "stages": [],
        "targets": {},
    }
    write_json(original / GRAPH_PATH, graph)
    original_before = locked_source_inventory(original)
    copy_repo(original, candidate)
    candidate_before = locked_source_inventory(candidate)
    (candidate / "locked.txt").write_text("unexpected write\n", encoding="utf-8", newline="\n")
    candidate_after = locked_source_inventory(candidate)
    original_after = locked_source_inventory(original)
    changes = inventory_delta(candidate_before, candidate_after)
    conditions = [
        original_before == original_after,
        len(changes) == 1,
        changes[0].get("path") == "locked.txt",
        changes[0].get("change_kind") == "CONTENT_OR_MODE_CHANGED",
    ]
    return case_result(
        "per-case-source-mutation-guard-is-contained-and-attributed",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["per-case source mutation guard did not contain and attribute the write"],
        guard=HEAVY_CASE_SOURCE_GUARD,
        detected_changes=changes,
        original_root_before=inventory_root_sha256(original_before),
        original_root_after=inventory_root_sha256(original_after),
    )


def mutation_process_timeout_case(source: Path, root: Path) -> dict:
    """Prove a hung mutation worker and its nested validator tree are terminated."""
    fixture_source = root / "mutation-timeout-source"
    fixture_run = root / "mutation-timeout-run"
    pid_path = root / "mutation-timeout-pids.txt"
    copy_repo(source, fixture_source)
    checker = fixture_source / "scripts/check_release_graph.py"
    checker.write_text(
        """from __future__ import annotations
import os
import pathlib
import subprocess
import sys
import time
pid_path = pathlib.Path(%r)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(600)'])
pid_path.write_text(f'{os.getpid()} {child.pid}', encoding='utf-8')
time.sleep(600)
""" % str(pid_path),
        encoding="utf-8",
        newline="\n",
    )
    started = time.monotonic()
    observed = run_mutation_case_isolated(
        fixture_source,
        fixture_run,
        "attestation-stage-bypassed",
        3,
    )
    elapsed = time.monotonic() - started
    pids: list[int] = []
    if pid_path.is_file():
        try:
            pids = [int(value) for value in pid_path.read_text(encoding="utf-8").split()]
        except ValueError:
            pids = []
    descendants_alive = [pid for pid in pids if _pid_alive(pid)]
    reap_deadline = time.monotonic() + 5.0
    while descendants_alive and time.monotonic() < reap_deadline:
        time.sleep(0.1)
        descendants_alive = [pid for pid in pids if _pid_alive(pid)]
    conditions = [
        observed.get("classification") == INTERNAL_ERROR,
        any("mutation case timeout after 3s" in str(error) for error in observed.get("errors", [])),
        observed.get("termination") in {"TERMINATED", "KILLED", "ALREADY_EXITED"},
        not descendants_alive,
        elapsed < 15,
    ]
    return case_result(
        "mutation-worker-process-tree-timeout-is-bounded",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["mutation worker timeout containment differed"],
        observed_result=observed,
        descendant_pids=pids,
        descendants_alive=descendants_alive,
        elapsed_ms=round(elapsed * 1000, 3),
        mutation_case_isolation=MUTATION_CASE_ISOLATION,
    )


def mutation_checkpoint_reuse_and_invalidation_case(source: Path, root: Path) -> dict:
    """Prove exact mutation results resume and every identity change invalidates them."""
    checkpoint_root = root / "mc" / "cp"
    source_root = inventory_root_sha256(locked_source_inventory(source))
    context = _mutation_checkpoint_context(source, source_root, 30)
    specification = [mutation_case_functions()[0]]
    first = run_independent_mutations(
        source,
        root / "mc" / "a",
        specification,
        1,
        30,
        checkpoint_root,
        context,
        True,
    )[0]
    second = run_independent_mutations(
        source,
        root / "mc" / "b",
        specification,
        1,
        30,
        checkpoint_root,
        context,
        True,
    )[0]
    case_id = specification[0][0]
    checkpoint_path = _mutation_checkpoint_path(checkpoint_root, case_id)
    changed_context = dict(context)
    changed_context["graph_file_sha256"] = "0" * 64
    changed_result, changed_errors = _load_mutation_checkpoint(
        checkpoint_path, changed_context, case_id
    )

    envelope = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    forged = copy.deepcopy(envelope)
    forged["result"]["classification"] = FAIL
    forged["result"]["status"] = FAIL
    forged["result"]["pass"] = False
    unsigned = {key: value for key, value in forged.items() if key != "checkpoint_sha256"}
    forged["checkpoint_sha256"] = _canonical_json_sha256(unsigned)
    write_json(checkpoint_path, forged)
    forged_result, forged_errors = _load_mutation_checkpoint(
        checkpoint_path, context, case_id
    )

    conditions = [
        first.get("classification") == EXPECTED_REJECTION,
        first.get("checkpoint_reused") is False,
        isinstance(first.get("checkpoint_sha256"), str),
        second.get("classification") == EXPECTED_REJECTION,
        second.get("checkpoint_reused") is True,
        first.get("checkpoint_sha256") == second.get("checkpoint_sha256"),
        changed_result is None,
        any("context differs" in error for error in changed_errors),
        forged_result is None,
        any("not reusable" in error for error in forged_errors),
    ]
    return case_result(
        "mutation-checkpoint-reuse-and-invalidation",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["mutation checkpoint reuse or invalidation differed"],
        first_result=first,
        second_result=second,
        changed_context_errors=changed_errors,
        forged_result_errors=forged_errors,
        checkpoint_profile=MUTATION_CHECKPOINT_PROFILE,
    )



def heavy_checkpoint_reuse_and_invalidation_case(source: Path, root: Path) -> dict:
    """Prove valid heavyweight checkpoints reuse and every bound drift invalidates."""
    fixture = root / "hc"
    checkpoint_root = fixture / "cp"
    fixture.mkdir(parents=True, exist_ok=False)
    source_root = inventory_root_sha256(locked_source_inventory(source))
    context = _heavy_checkpoint_context(source, source_root, 30, 1)
    case_id = "heavyweight-result-case-id-mismatch-is-rejected"

    first = run_heavy_cases_isolated(
        source,
        fixture / "a",
        [case_id],
        1,
        30,
        checkpoint_root,
        context,
        True,
    )[0]
    second = run_heavy_cases_isolated(
        source,
        fixture / "b",
        [case_id],
        1,
        30,
        checkpoint_root,
        context,
        True,
    )[0]

    checkpoint_path = _heavy_checkpoint_path(checkpoint_root, case_id)
    changed_context = copy.deepcopy(context)
    changed_context["graph_file_sha256"] = "0" * 64
    changed_result, changed_errors = _load_heavy_checkpoint(
        checkpoint_path, changed_context, case_id
    )

    envelope = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    forged = copy.deepcopy(envelope)
    forged["result"]["classification"] = FAIL
    forged["result"]["status"] = FAIL
    forged["result"]["pass"] = False
    unsigned = {key: value for key, value in forged.items() if key != "checkpoint_sha256"}
    forged["checkpoint_sha256"] = _canonical_json_sha256(unsigned)
    write_json(checkpoint_path, forged)
    forged_result, forged_errors = _load_heavy_checkpoint(
        checkpoint_path, context, case_id
    )

    conditions = [
        first.get("classification") == PASS,
        first.get("checkpoint_reused") is False,
        isinstance(first.get("checkpoint_sha256"), str),
        second.get("classification") == PASS,
        second.get("checkpoint_reused") is True,
        first.get("checkpoint_sha256") == second.get("checkpoint_sha256"),
        changed_result is None,
        any("context differs" in error for error in changed_errors),
        forged_result is None,
        any("not reusable" in error for error in forged_errors),
    ]
    return case_result(
        "heavy-checkpoint-reuse-and-invalidation",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["heavyweight checkpoint reuse or invalidation differed"],
        checkpoint_profile=HEAVY_CHECKPOINT_PROFILE,
        first_checkpoint_reused=first.get("checkpoint_reused"),
        second_checkpoint_reused=second.get("checkpoint_reused"),
        changed_context_errors=changed_errors,
        forged_result_errors=forged_errors,
    )


def portable_workspace_path_budget_case(_source: Path, _root: Path) -> dict:
    """Prove recursive assurance workspaces remain portable on Windows."""
    probe = _portable_workspace_path_probe()
    registry_ids = [
        *[case_id for case_id, _mutate in mutation_case_functions()],
        *list(heavy_case_functions_without_path_budget()),
    ]
    compact_names = [_compact_workspace_component("c", case_id) for case_id in registry_ids]
    conditions = [
        probe["deepest_heavy_length"] <= PORTABLE_WINDOWS_PATH_BUDGET,
        probe["deepest_mutation_length"] <= PORTABLE_WINDOWS_PATH_BUDGET,
        len(compact_names) == len(set(compact_names)),
        all(len(name) == 2 + WORKSPACE_COMPONENT_HASH_HEX for name in compact_names),
    ]
    return case_result(
        "portable-workspace-path-budget-is-enforced",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["portable assurance workspace path budget differed"],
        workspace_path_profile=WORKSPACE_PATH_PROFILE,
        workspace_component_hash_hex=WORKSPACE_COMPONENT_HASH_HEX,
        **probe,
    )


def heavy_case_functions_without_path_budget() -> dict[str, Callable[[Path, Path], dict]]:
    """Return heavyweight cases used to derive the path-budget registry."""
    return {
        "mutation-fixtures-have-no-shared-writable-inodes": fixture_copy_isolation_case,
        "source-drift-attribution-distinguishes-external-edit-from-suite-mutation": source_drift_attribution_case,
        "canonical-baseline-failure-stops-before-adversarial-scheduling": canonical_baseline_fail_fast_case,
        "concurrent-source-drift-is-attributed-without-blaming-suite-fixtures": concurrent_source_drift_attribution_case,
        "checkpoint-reuse-invalidation-and-resume": checkpoint_case,
        "independent-read-only-failures-are-collected-without-running-dependents": independent_failure_collection_case,
        "write-stage-failure-stops-diagnostic-sweep": write_failure_stops_collection_case,
        "read-only-input-mutation-stops-diagnostic-sweep": read_only_mutation_stops_collection_case,
        "internal-error-receipt-is-durable-and-not-reusable": internal_error_receipt_case,
        "scenario-contract-gate-is-hermetic-and-attributed": scenario_hermetic_case,
        "decision-artifact-mutation-harness-is-cwd-independent-and-attributed": decision_artifact_harness_cwd_case,
        "double-build-is-hermetic-deterministic-and-diagnostic": build_reproducibility_case,
        "evidence-join-authenticates-receipts-and-current-outputs": evidence_join_case,
        "heavyweight-process-tree-timeout-is-bounded": process_tree_termination_case,
        "mutation-worker-process-tree-timeout-is-bounded": mutation_process_timeout_case,
        "mutation-checkpoint-reuse-and-invalidation": mutation_checkpoint_reuse_and_invalidation_case,
        "heavy-checkpoint-reuse-and-invalidation": heavy_checkpoint_reuse_and_invalidation_case,
        "per-case-source-mutation-guard-is-contained-and-attributed": per_case_source_guard_case,
        "heavyweight-result-case-id-mismatch-is-rejected": heavyweight_result_case_id_guard_case,
        "heavyweight-worker-executes-sealed-source-snapshot": heavyweight_worker_snapshot_binding_case,
    }


def heavy_case_functions() -> dict[str, Callable[[Path, Path], dict]]:
    """Return heavyweight cases executed in fresh process groups."""
    return {
        **heavy_case_functions_without_path_budget(),
        "portable-workspace-path-budget-is-enforced": portable_workspace_path_budget_case,
    }


def _validated_heavy_case_result(case_id: str, result: object) -> dict:
    """Fail closed when a worker reports evidence for a different case ID."""
    if not isinstance(result, dict):
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"heavyweight worker result is not an object:{type(result).__name__}"],
        )
    observed = result.get("case_id")
    if observed != case_id:
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"heavyweight worker case ID differs:{observed}"],
            observed_case_id=observed,
        )
    return result


def heavyweight_result_case_id_guard_case(_source: Path, _root: Path) -> dict:
    """Prove a mislabeled durable worker result cannot enter joined evidence."""
    observed = _validated_heavy_case_result(
        "expected-heavy-case",
        case_result("different-heavy-case", PASS),
    )
    conditions = [
        observed.get("classification") == INTERNAL_ERROR,
        observed.get("case_id") == "expected-heavy-case",
        observed.get("observed_case_id") == "different-heavy-case",
        any("case ID differs" in str(error) for error in observed.get("errors", [])),
    ]
    return case_result(
        "heavyweight-result-case-id-mismatch-is-rejected",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["heavyweight result case-ID guard differed"],
    )


def _heavy_case_worker(case_id: str, source_text: str, root_text: str, result_text: str) -> int:
    """Run one heavyweight case and write a durable result file."""
    result_path = Path(result_text)
    worker_script = Path(__file__).resolve(strict=True)
    worker_script_sha256 = hashlib.sha256(worker_script.read_bytes()).hexdigest()
    try:
        result = _validated_heavy_case_result(
            case_id,
            heavy_case_functions()[case_id](Path(source_text), Path(root_text)),
        )
    except BaseException as exc:  # noqa: BLE001 - preserve all worker failures
        result = case_result(case_id, INTERNAL_ERROR, errors=[f"{type(exc).__name__}:{exc}"])
    result["worker_execution"] = HEAVY_WORKER_EXECUTION
    result["worker_result_binding"] = HEAVY_WORKER_RESULT_BINDING
    result["worker_script_sha256"] = worker_script_sha256
    result["workspace_path_profile"] = WORKSPACE_PATH_PROFILE
    result_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(result_path, result)
    return 0


def _process_group_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_subprocess_tree(process: subprocess.Popen, grace_seconds: float = 5.0) -> str:
    """Terminate a worker and every descendant, not only the direct child."""
    if process.poll() is not None:
        return "ALREADY_EXITED"
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=max(5, int(grace_seconds) + 2),
        )
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_seconds)
        return "TERMINATED"
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=max(5, int(grace_seconds) + 2),
            )
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            process.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            return "UNTERMINATED"
        return "KILLED"


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=10,
        )
        return f'"{pid}"' in completed.stdout
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_tree_termination_case(_source: Path, root: Path) -> dict:
    """Prove the process-group terminator removes a worker's descendant tree."""
    fixture = root / "process-tree-termination"
    fixture.mkdir(parents=True, exist_ok=False)
    child_pid_path = fixture / "child.pid"
    helper = fixture / "tree_helper.py"
    helper.write_text(
        """import os
import pathlib
import subprocess
import sys
import time

mode = sys.argv[1]
pidfile = pathlib.Path(sys.argv[2])
if mode == "child":
    pidfile.write_text(str(os.getpid()), encoding="utf-8")
    time.sleep(600)
else:
    subprocess.Popen([sys.executable, __file__, "child", str(pidfile)])
    time.sleep(600)
""",
        encoding="utf-8",
        newline="\n",
    )
    process = subprocess.Popen(
        [sys.executable, str(helper), "parent", str(child_pid_path)],
        cwd=fixture,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **_process_group_kwargs(),
    )
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not child_pid_path.is_file():
        time.sleep(0.05)
    if not child_pid_path.is_file():
        termination = _terminate_subprocess_tree(process)
        return case_result(
            "heavyweight-process-tree-timeout-is-bounded",
            FAIL,
            errors=["descendant PID was not observed"],
            termination=termination,
        )
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    termination = _terminate_subprocess_tree(process)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pid_alive(child_pid):
        time.sleep(0.05)
    conditions = [process.poll() is not None, not _pid_alive(child_pid), termination != "UNTERMINATED"]
    return case_result(
        "heavyweight-process-tree-timeout-is-bounded",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["heavyweight process tree survived termination"],
        child_pid=child_pid,
        termination=termination,
    )


def _heavy_worker_command(
    case_source: Path,
    worker_root: Path,
    result_path: Path,
    case_id: str,
) -> tuple[list[str], str]:
    """Bind the worker executable to the same sealed snapshot as its inputs.

    A long-running parent can have an older module loaded in memory while an
    editor changes the live working-tree script. Executing ``Path(__file__)``
    would mix two implementations in one receipt. The executable therefore
    comes from the per-case sealed source snapshot and is hash-bound below.
    """
    worker_script = case_source / "scripts/test_release_graph.py"
    if worker_script.is_symlink() or not worker_script.is_file():
        raise FileNotFoundError(f"sealed heavyweight worker unavailable:{worker_script}")
    worker_script_sha256 = hashlib.sha256(worker_script.read_bytes()).hexdigest()
    return [
        sys.executable,
        str(worker_script.resolve(strict=True)),
        "--heavy-worker-case",
        case_id,
        "--heavy-worker-source",
        str(case_source),
        "--heavy-worker-root",
        str(worker_root),
        "--heavy-worker-result",
        str(result_path),
    ], worker_script_sha256


def heavyweight_worker_snapshot_binding_case(source: Path, root: Path) -> dict:
    """Prove the worker executable cannot escape to the live working tree."""
    fixture = root / "heavy-worker-snapshot-binding"
    case_source = fixture / "source-snapshot"
    result_path = fixture / "result.json"
    fixture.mkdir(parents=True, exist_ok=False)
    copy_repo(source, case_source)
    command, expected_sha256 = _heavy_worker_command(
        case_source,
        fixture,
        result_path,
        "heavyweight-result-case-id-mismatch-is-rejected",
    )
    expected_script = (case_source / "scripts/test_release_graph.py").resolve(strict=True)
    live_script = Path(__file__).resolve(strict=True)
    conditions = [
        Path(command[1]) == expected_script,
        expected_script != live_script,
        expected_sha256 == hashlib.sha256(expected_script.read_bytes()).hexdigest(),
        command[2:4] == ["--heavy-worker-case", "heavyweight-result-case-id-mismatch-is-rejected"],
    ]
    return case_result(
        "heavyweight-worker-executes-sealed-source-snapshot",
        PASS if all(conditions) else FAIL,
        errors=[] if all(conditions) else ["heavyweight worker executable escaped sealed source snapshot"],
        worker_execution=HEAVY_WORKER_EXECUTION,
        worker_result_binding=HEAVY_WORKER_RESULT_BINDING,
        worker_script_sha256=expected_sha256,
    )


def run_heavy_case_isolated(source: Path, root: Path, case_id: str, timeout_seconds: int) -> dict:
    """Contain nested-process tests and hard-bound their wall-clock duration."""
    started = time.monotonic()
    worker_root = root / _compact_workspace_component("h", case_id)
    result_path = worker_root / "r.json"
    worker_log = worker_root / "w.log"
    case_source = worker_root / "src"
    worker_root.mkdir(parents=True, exist_ok=False)
    try:
        copy_repo(source, case_source)
        case_source_before = locked_source_inventory(case_source)
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(worker_root, ignore_errors=True)
        return case_result(
            case_id, INTERNAL_ERROR,
            errors=[f"per-case source snapshot failed:{type(exc).__name__}:{exc}"],
            isolation=HEAVY_CASE_ISOLATION,
            source_guard=HEAVY_CASE_SOURCE_GUARD,
        )
    try:
        command, expected_worker_script_sha256 = _heavy_worker_command(
            case_source,
            worker_root,
            result_path,
            case_id,
        )
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(worker_root, ignore_errors=True)
        return case_result(
            case_id,
            INTERNAL_ERROR,
            errors=[f"sealed heavyweight worker command failed:{type(exc).__name__}:{exc}"],
            isolation=HEAVY_CASE_ISOLATION,
            source_guard=HEAVY_CASE_SOURCE_GUARD,
            worker_execution=HEAVY_WORKER_EXECUTION,
            worker_result_binding=HEAVY_WORKER_RESULT_BINDING,
        )
    with worker_log.open("wb") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=case_source,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            **_process_group_kwargs(),
        )
        try:
            process.wait(timeout=timeout_seconds)
            timed_out = False
            termination = "NOT_REQUIRED"
        except subprocess.TimeoutExpired:
            timed_out = True
            termination = _terminate_subprocess_tree(process)
    if timed_out:
        result = case_result(
            case_id, INTERNAL_ERROR,
            errors=[f"heavyweight case timeout after {timeout_seconds}s"],
            isolation=HEAVY_CASE_ISOLATION,
            termination=termination,
            worker_exitcode=process.returncode,
            worker_log_sha256=hashlib.sha256(worker_log.read_bytes()).hexdigest(),
        )
    elif process.returncode != 0 or not result_path.is_file():
        result = case_result(
            case_id, INTERNAL_ERROR,
            errors=["heavyweight worker exited without a durable result"],
            isolation=HEAVY_CASE_ISOLATION,
            worker_exitcode=process.returncode,
            worker_log_sha256=hashlib.sha256(worker_log.read_bytes()).hexdigest(),
        )
    else:
        try:
            result = _validated_heavy_case_result(
                case_id,
                json.loads(result_path.read_text(encoding="utf-8")),
            )
            binding_errors: list[str] = []
            if result.get("worker_execution") != HEAVY_WORKER_EXECUTION:
                binding_errors.append("heavyweight worker execution boundary differs")
            if result.get("worker_result_binding") != HEAVY_WORKER_RESULT_BINDING:
                binding_errors.append("heavyweight worker result-binding boundary differs")
            if result.get("worker_script_sha256") != expected_worker_script_sha256:
                binding_errors.append("heavyweight worker script hash differs")
            if binding_errors:
                result = case_result(
                    case_id,
                    INTERNAL_ERROR,
                    errors=binding_errors,
                    observed_worker_script_sha256=result.get("worker_script_sha256"),
                )
            result["isolation"] = HEAVY_CASE_ISOLATION
            result["worker_exitcode"] = process.returncode
            result["worker_log_sha256"] = hashlib.sha256(worker_log.read_bytes()).hexdigest()
        except (OSError, json.JSONDecodeError) as exc:
            result = case_result(
                case_id, INTERNAL_ERROR,
                errors=[f"durable heavyweight result invalid:{type(exc).__name__}:{exc}"],
                isolation=HEAVY_CASE_ISOLATION,
                worker_exitcode=process.returncode,
                worker_log_sha256=hashlib.sha256(worker_log.read_bytes()).hexdigest(),
            )
    result["worker_execution"] = HEAVY_WORKER_EXECUTION
    result["worker_result_binding"] = HEAVY_WORKER_RESULT_BINDING
    result["worker_script_sha256"] = expected_worker_script_sha256
    result["worker_executable"] = "scripts/test_release_graph.py"
    result["workspace_path_profile"] = WORKSPACE_PATH_PROFILE
    result["worker_workspace"] = worker_root.name
    result["worker_log_tail"] = _bounded_worker_log_tail(worker_log)
    try:
        case_source_after = locked_source_inventory(case_source)
        source_mutations = inventory_delta(case_source_before, case_source_after)
    except Exception as exc:  # noqa: BLE001
        source_mutations = [{
            "path": "<inventory>",
            "change": "INVENTORY_ERROR",
            "before": None,
            "after": f"{type(exc).__name__}:{exc}",
        }]
    result["source_guard"] = HEAVY_CASE_SOURCE_GUARD
    result["source_snapshot_root_before"] = inventory_root_sha256(case_source_before)
    result["source_snapshot_root_after"] = inventory_root_sha256(case_source_after) if 'case_source_after' in locals() else None
    result["source_mutations"] = source_mutations
    if source_mutations:
        result["classification"] = FAIL
        result["status"] = FAIL
        result["pass"] = False
        result["errors"] = [
            *list(result.get("errors", [])),
            *[f"heavyweight case mutated its read-only source snapshot:{item.get('path')}" for item in source_mutations[:20]],
        ]
    result["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
    shutil.rmtree(worker_root, ignore_errors=True)
    return result



def run_heavy_cases_isolated(
    source: Path,
    root: Path,
    case_ids: list[str],
    workers: int,
    timeout_seconds: int,
    checkpoint_root: Path,
    checkpoint_context: dict[str, object],
    reuse_checkpoints: bool,
) -> list[dict]:
    """Run heavyweight cases with resource-aware deterministic scheduling.

    Ordinary isolated cases retain bounded parallelism. Cases that themselves
    fan out into many subprocesses run one at a time, preventing the assurance
    harness from turning host contention into false release failures.
    """
    if not case_ids:
        return []
    ordinary = [case_id for case_id in case_ids if case_id not in EXCLUSIVE_HEAVY_CASES]
    exclusive = [case_id for case_id in case_ids if case_id in EXCLUSIVE_HEAVY_CASES]
    bounded_workers = max(1, min(workers, len(ordinary) or 1, 4))
    print(
        f"release-graph heavyweight scheduler: {len(case_ids)} isolated cases, "
        f"{len(ordinary)} parallel-eligible, {len(exclusive)} exclusive fan-out, "
        f"{bounded_workers} ordinary workers",
        flush=True,
    )

    checkpoint_root.mkdir(parents=True, exist_ok=True)

    def run_one(case_id: str) -> dict:
        checkpoint_path = _heavy_checkpoint_path(checkpoint_root, case_id)
        if reuse_checkpoints:
            reused, checkpoint_errors = _load_heavy_checkpoint(
                checkpoint_path, checkpoint_context, case_id
            )
            if reused is not None:
                print(f"REUSE_HEAVY_CASE:{case_id}", flush=True)
                return reused
            if checkpoint_errors:
                checkpoint_path.unlink(missing_ok=True)
                print(
                    f"INVALIDATE_HEAVY_CHECKPOINT:{case_id}:{';'.join(checkpoint_errors[:3])}",
                    flush=True,
                )
        print(f"START_HEAVY_CASE:{case_id}", flush=True)
        result = run_heavy_case_isolated(source, root, case_id, timeout_seconds)
        if result.get("classification") == PASS and result.get("pass") is True:
            result = _write_heavy_checkpoint(
                checkpoint_path, checkpoint_context, case_id, result
            )
        else:
            checkpoint_path.unlink(missing_ok=True)
            result["checkpoint_profile"] = HEAVY_CHECKPOINT_PROFILE
            result["checkpoint_reused"] = False
            result["checkpoint_sha256"] = None
            result["checkpoint_path"] = checkpoint_path.name
        print(
            f"END_HEAVY_CASE:{case_id}:{result.get('classification')}:{result.get('duration_ms')}",
            flush=True,
        )
        return result

    by_case: dict[str, dict] = {}
    if ordinary:
        if bounded_workers == 1:
            for case_id in ordinary:
                by_case[case_id] = run_one(case_id)
        else:
            with ThreadPoolExecutor(max_workers=bounded_workers, thread_name_prefix="release-graph-heavy") as executor:
                futures = {
                    case_id: executor.submit(run_one, case_id)
                    for case_id in ordinary
                }
                for case_id, future in futures.items():
                    by_case[case_id] = future.result()
    for case_id in exclusive:
        by_case[case_id] = run_one(case_id)
    return [by_case[case_id] for case_id in case_ids]



def mutation_case_functions() -> list[tuple[str, Callable[[Path], None]]]:
    """Return the independently executed release-graph mutation registry."""
    return [
        ("attestation-stage-bypassed", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "arrival.runtime-tests").__setitem__("needs", ["arrival.artifact-boundary"]))),
        ("dual-static-gate-bypassed", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "decision.static-attacks").__setitem__("needs", ["decision.axiom-checker-attacks"]))),
        ("package-wrapper-drift", _mutate_package),
        ("workflow-command-duplication", _mutate_workflow),
        ("stale-input-lock", _mutate_locked_input),
        ("classification-vocabulary-widened", lambda repo: mutate_graph(repo, lambda g: g["classifications"].append("UNREVIEWED_RESULT"))),
        ("scenario-committed-output-gate-bypassed", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "scenario.contracts").__setitem__("command", ["npm", "run", "verify:scenario-contracts"]))),
        ("research-scenario-output-boundary-removed", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "scenario.research-generation").__setitem__("outputs", []))),
        ("scenario-experience-subgate-removed", _mutate_scenario_gate),
        ("scenario-workflow-target-drift", _mutate_scenario_workflow_target),
        ("example-workflow-target-drift", _mutate_example_workflow_target),
        ("unregistered-pull-request-workflow-rejected", _mutate_unregistered_pull_request_workflow),
        ("scenario-behavior-archive-output-removed", _mutate_scenario_behavior_archive_output_removed),
        ("scenario-behavior-archive-check-stage-removed", _mutate_scenario_behavior_archive_check_stage_removed),
        ("scenario-behavior-archive-attacks-detached", _mutate_scenario_behavior_archive_attacks_detached),
        ("scenario-behavior-archive-checker-lock-removed", _mutate_scenario_behavior_archive_checker_lock_removed),
        ("scenario-capability-ratchet-stage-removed", _mutate_scenario_ratchet_stage_removed),
        ("scenario-evolution-evidence-bypassed", _mutate_scenario_evolution_bypass),
        ("scenario-evolution-receipt-attacks-removed", _mutate_scenario_evolution_receipt_attacks_removed),
        ("scenario-genome-artifact-contract-removed", _mutate_scenario_genome_artifact_contract),
        ("scenario-evolution-duplicate-runner-rejected", _mutate_scenario_evolution_duplicate_runner),
        ("scenario-evolution-receipt-union-regression", _mutate_scenario_evolution_receipt_union_regression),
        ("production-behavioral-summary-projection-regression", _mutate_production_behavioral_summary_projection_regression),
        ("standalone-windows-shell-regression", _mutate_standalone_windows_shell),
        ("scenario-transitive-vocabulary-lock-removed", lambda repo: mutate_graph(repo, lambda g: g["input_sets"]["scenario-source"]["files"].pop("scripts/checkRepositoryVocabulary.ts", None))),
        ("scenario-transitive-fixture-lock-removed", _mutate_scenario_fixture_lock),
        ("standalone-gate-removed-from-package-rehearsal", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "final.arrival-evidence").__setitem__("needs", [item for item in graph_stage(g, "final.arrival-evidence")["needs"] if item != "standalone.contracts"]))),
        ("content-registry-gate-removed-from-package-rehearsal", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "final.arrival-evidence").__setitem__("needs", [item for item in graph_stage(g, "final.arrival-evidence")["needs"] if item != "content.registry-source"]))),
        ("application-typecheck-bypassed", lambda repo: mutate_graph(repo, lambda g: graph_stage(g, "build.double-reproducibility").__setitem__("needs", ["dependencies.npm-ci"]))),
        ("workflow-action-pin-weakened", _mutate_action_pin),
        ("build-isolation-marker-removed", _mutate_build_runner_marker),
        ("build-timeout-boundary-removed", _mutate_build_timeout_marker),
        ("artifact-authority-contract-removed", _mutate_artifact_authority_contract),
        ("artifact-independent-checker-removed", _mutate_artifact_independent_checker),
        ("artifact-authority-coverage-removed", _mutate_artifact_authority_coverage_removed),
        ("artifact-authority-broad-directory-output", _mutate_artifact_authority_broad_directory_output),
        ("artifact-authority-unclaimed-output", _mutate_artifact_authority_unclaimed_output),
        ("artifact-authority-second-writer", _mutate_artifact_authority_second_writer),
        ("generated-binding-authority-contract-removed", _mutate_generated_binding_authority_contract_removed),
        ("offline-release-raw-graph-artifact-cycle-reintroduced", _mutate_offline_raw_graph_artifact),
        ("offline-release-raw-graph-hash-cycle-reintroduced", _mutate_offline_raw_graph_hash),
        ("offline-release-graph-binding-mode-weakened", _mutate_offline_graph_binding_mode),
        ("offline-release-semantic-graph-contract-drift", _mutate_offline_graph_contract_drift),
        ("offline-release-identity-contract-removed", _mutate_offline_identity_contract_removed),
        ("offline-documentation-writer-ownership-expanded", _mutate_offline_writer_ownership_expanded),
        ("offline-documentation-verification-ownership-reduced", _mutate_offline_verification_ownership_reduced),
        ("offline-release-stage-claims-verification-document", _mutate_offline_stage_claims_verification_document),
        ("offline-release-case-registry-profile-weakened", _mutate_offline_case_registry_profile),
        ("offline-release-scheduler-profile-weakened", _mutate_offline_scheduler_profile),
        ("offline-release-source-guard-profile-weakened", _mutate_offline_source_guard_profile),
        ("offline-release-duplicate-case-id", _mutate_offline_duplicate_case_id),
        ("offline-release-worker-ceiling-widened", _mutate_offline_worker_ceiling),
        ("node-documentation-renderer-duplication-rejected", _mutate_duplicate_node_documentation_renderer),
        ("release-graph-partition-checkpoint-boundary-removed", _mutate_partition_checkpoint_marker),
        ("release-graph-mutation-partition-stage-removed", _mutate_graph_mutation_partition_stage_removed),
        ("release-graph-heavy-partition-stage-removed", _mutate_graph_heavy_partition_stage_removed),
        ("release-graph-partition-join-bypassed", _mutate_graph_partition_join_bypassed),
        ("release-graph-partition-join-attacks-output-removed", _mutate_graph_partition_join_attacks_output_removed),
        ("release-graph-mutation-checkpoint-profile-weakened", _mutate_mutation_checkpoint_profile),
        ("release-graph-heavy-checkpoint-profile-weakened", _mutate_heavy_checkpoint_profile),
        ("release-graph-mutation-process-isolation-weakened", _mutate_mutation_process_isolation),
        ("release-graph-mutation-worker-execution-boundary-weakened", _mutate_mutation_worker_execution_boundary),
        ("release-graph-mutation-worker-result-binding-weakened", _mutate_mutation_worker_result_binding),
        ("release-graph-mutation-worker-live-script-regression", _mutate_mutation_worker_live_script_regression),
        ("release-graph-mutation-case-timeout-weakened", _mutate_mutation_case_timeout),
        ("release-graph-mutation-validator-timeout-weakened", _mutate_mutation_validator_timeout),
        ("release-graph-heavy-resource-scheduler-removed", _mutate_heavy_resource_scheduler_marker),
        ("release-graph-heavy-default-worker-floor-widened", _mutate_heavy_default_worker_floor),
        ("release-graph-heavy-worker-execution-boundary-weakened", _mutate_heavy_worker_execution_boundary),
        ("release-graph-heavy-worker-result-binding-weakened", _mutate_heavy_worker_result_binding),
        ("release-graph-heavy-worker-live-script-regression", _mutate_heavy_worker_live_script_regression),
        ("release-graph-workspace-path-profile-weakened", _mutate_workspace_path_profile),
        ("release-graph-mutation-workspace-full-case-id-regression", _mutate_mutation_workspace_full_case_id),
        ("release-graph-heavy-workspace-full-case-id-regression", _mutate_heavy_workspace_full_case_id),
        ("release-graph-failed-case-diagnostics-removed", _mutate_failed_case_diagnostics_removed),
        ("engine-evolution-stabilizer-removed", _mutate_engine_evolution_stabilizer_removed),
        ("local-source-closure-contract-removed", _mutate_local_source_closure_contract_removed),
        ("suite-source-snapshot-contract-removed", _mutate_suite_source_snapshot_contract_removed),
        ("baseline-fail-fast-contract-removed", _mutate_baseline_fail_fast_contract_removed),
        ("heavy-source-guard-contract-removed", _mutate_heavy_source_guard_contract_removed),
        ("release-identity-release-policy-lock-removed", lambda repo: _remove_input_set_path(repo, "release-policy-source", "scripts/release_identity_common.py")),
        ("release-identity-scenario-lock-removed", lambda repo: _remove_input_set_path(repo, "scenario-source", "scripts/release_identity_common.py")),
        ("release-identity-standalone-lock-removed", lambda repo: _remove_input_set_path(repo, "standalone-source", "scripts/release_identity_common.py")),
        ("node-documentation-common-scenario-lock-removed", lambda repo: _remove_input_set_path(repo, "scenario-source", "scripts/engine_evolution_documentation_common.mjs")),
        ("python-transitive-local-import-unlocked", _mutate_python_transitive_source_unlocked),
        ("node-transitive-local-import-unlocked", _mutate_node_transitive_source_unlocked),
        ("release-source-closure-evidence-output-removed", _mutate_source_closure_report_output_removed),
        ("python-cache-ignore-boundary-removed", lambda repo: _remove_gitignore_boundary(repo, "__pycache__/")),
        ("release-receipt-ignore-boundary-removed", lambda repo: _remove_gitignore_boundary(repo, ".asklepios/release-receipts/")),
        ("mutation-checkpoint-ignore-boundary-removed", lambda repo: _remove_gitignore_boundary(repo, ".asklepios/release-graph-mutation-checkpoints/")),
        ("heavy-checkpoint-ignore-boundary-removed", lambda repo: _remove_gitignore_boundary(repo, ".asklepios/release-graph-heavy-checkpoints/")),
    ]


def common_partition_case_ids() -> tuple[str, ...]:
    """Cases repeated in both checkpointed partitions and authenticated by the join."""
    return (
        "stable-source-snapshot-acquisition",
        "canonical_graph_baseline",
        SOURCE_INTEGRITY_CASE_ID,
    )

def _case_inventory_sha256(case_ids: list[str]) -> str:
    payload = json.dumps(sorted(case_ids), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def emit_suite_report(source: Path, args: argparse.Namespace, results: list[dict]) -> int:
    """Write the canonical suite result through one deterministic exit path."""
    classification = suite_classification(results)
    report = {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "cases": len(results),
        "partition": getattr(args, "partition", "FULL"),
        "graph_id": json.loads((source / GRAPH_PATH).read_text(encoding="utf-8")).get("graph_id"),
        "graph_file_sha256": hashlib.sha256((source / GRAPH_PATH).read_bytes()).hexdigest(),
        "repository_inventory_root_before": getattr(args, "repository_inventory_root_before", inventory_root_sha256(locked_source_inventory(source))),
        "repository_inventory_root_after": getattr(args, "repository_inventory_root_after", inventory_root_sha256(locked_source_inventory(source))),
        "case_inventory_sha256": _case_inventory_sha256([str(item.get("case_id")) for item in results]),
        "mutation_workers": args.mutation_workers,
        "mutation_case_isolation": MUTATION_CASE_ISOLATION,
        "mutation_worker_execution": MUTATION_WORKER_EXECUTION,
        "mutation_worker_result_binding": MUTATION_WORKER_RESULT_BINDING,
        "mutation_validator_timeout_seconds": DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS,
        "mutation_case_timeout_seconds": args.mutation_case_timeout_seconds,
        "mutation_checkpoint_profile": MUTATION_CHECKPOINT_PROFILE,
        "mutation_checkpoint_context_sha256": args.mutation_checkpoint_context_sha256,
        "mutation_checkpoint_root": args.mutation_checkpoint_root.as_posix(),
        "mutation_checkpoint_reuse_enabled": not args.no_mutation_checkpoint_reuse,
        "mutation_checkpoints_reused": sum(
            1 for item in results if item.get("checkpoint_reused") is True
        ),
        "heavy_case_isolation": HEAVY_CASE_ISOLATION,
        "heavy_resource_scheduler": HEAVY_RESOURCE_SCHEDULER,
        "heavy_worker_execution": HEAVY_WORKER_EXECUTION,
        "heavy_worker_result_binding": HEAVY_WORKER_RESULT_BINDING,
        "heavy_checkpoint_profile": HEAVY_CHECKPOINT_PROFILE,
        "heavy_checkpoint_context_sha256": args.heavy_checkpoint_context_sha256,
        "heavy_checkpoint_root": args.heavy_checkpoint_root.as_posix(),
        "heavy_checkpoint_reuse_enabled": not args.no_heavy_checkpoint_reuse,
        "heavy_checkpoints_reused": sum(
            1 for item in results if item.get("checkpoint_reused") is True
            and item.get("case_id") in heavy_case_functions()
        ),
        "exclusive_heavy_cases": sorted(EXCLUSIVE_HEAVY_CASES),
        "heavy_case_timeout_seconds": args.heavy_case_timeout_seconds,
        "heavy_case_workers": args.heavy_case_workers,
        "workspace_path_profile": WORKSPACE_PATH_PROFILE,
        "portable_windows_path_budget": PORTABLE_WINDOWS_PATH_BUDGET,
        "workspace_path_probe": _portable_workspace_path_probe(),
        "partition_isolation": PARTITION_ISOLATION,
        "source_snapshot_isolation": SUITE_SOURCE_ISOLATION,
        "baseline_fail_fast": BASELINE_FAIL_FAST,
        "selected_cases": sorted(set(args.selected_cases or [])),
        "results": results,
        "errors": [item["case_id"] for item in results if item["classification"] in {FAIL, INTERNAL_ERROR}],
    }
    output = source / args.json_output
    write_json(output, report)
    visible_report = report if args.verbose_json else {
        "schema_version": report["schema_version"],
        "classification": report["classification"],
        "status": report["status"],
        "cases": report["cases"],
        "partition": report["partition"],
        "graph_id": report["graph_id"],
        "graph_file_sha256": report["graph_file_sha256"],
        "case_inventory_sha256": report["case_inventory_sha256"],
        "mutation_workers": report["mutation_workers"],
        "mutation_case_isolation": report["mutation_case_isolation"],
        "mutation_worker_execution": report["mutation_worker_execution"],
        "mutation_worker_result_binding": report["mutation_worker_result_binding"],
        "mutation_validator_timeout_seconds": report["mutation_validator_timeout_seconds"],
        "mutation_case_timeout_seconds": report["mutation_case_timeout_seconds"],
        "mutation_checkpoint_profile": report["mutation_checkpoint_profile"],
        "mutation_checkpoint_context_sha256": report["mutation_checkpoint_context_sha256"],
        "mutation_checkpoint_root": report["mutation_checkpoint_root"],
        "mutation_checkpoint_reuse_enabled": report["mutation_checkpoint_reuse_enabled"],
        "mutation_checkpoints_reused": report["mutation_checkpoints_reused"],
        "heavy_case_isolation": report["heavy_case_isolation"],
        "heavy_resource_scheduler": report["heavy_resource_scheduler"],
        "heavy_worker_execution": report["heavy_worker_execution"],
        "heavy_worker_result_binding": report["heavy_worker_result_binding"],
        "heavy_checkpoint_profile": report["heavy_checkpoint_profile"],
        "heavy_checkpoint_context_sha256": report["heavy_checkpoint_context_sha256"],
        "heavy_checkpoint_root": report["heavy_checkpoint_root"],
        "heavy_checkpoint_reuse_enabled": report["heavy_checkpoint_reuse_enabled"],
        "heavy_checkpoints_reused": report["heavy_checkpoints_reused"],
        "exclusive_heavy_cases": report["exclusive_heavy_cases"],
        "heavy_case_timeout_seconds": report["heavy_case_timeout_seconds"],
        "heavy_case_workers": report["heavy_case_workers"],
        "workspace_path_profile": report["workspace_path_profile"],
        "portable_windows_path_budget": report["portable_windows_path_budget"],
        "workspace_path_probe": report["workspace_path_probe"],
        "partition_isolation": report["partition_isolation"],
        "source_snapshot_isolation": report["source_snapshot_isolation"],
        "baseline_fail_fast": report["baseline_fail_fast"],
        "selected_cases": report["selected_cases"],
        "errors": report["errors"],
        "report_path": str(args.json_output),
        "failed_case_details": [
            {
                "case_id": item.get("case_id"),
                "classification": item.get("classification"),
                "errors": list(item.get("errors", []))[:10],
                "worker_exitcode": item.get("worker_exitcode"),
                "worker_log_sha256": item.get("worker_log_sha256"),
                "worker_log_tail": item.get("worker_log_tail"),
                "workspace_path_profile": item.get("workspace_path_profile"),
            }
            for item in results
            if item.get("classification") in {FAIL, INTERNAL_ERROR}
        ],
        "results": [
            {
                "case_id": item["case_id"],
                "classification": item["classification"],
                "pass": item.get("pass", False),
            }
            for item in results
        ],
    }
    print(json.dumps(visible_report, indent=2, sort_keys=True))
    return 0 if classification == PASS else (4 if classification == INTERNAL_ERROR else 3)

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    parser.add_argument("--verbose-json", action="store_true", help="Print the complete evidence report instead of a bounded summary.")
    parser.add_argument(
        "--mutation-workers",
        type=int,
        default=max(1, min(4, os.cpu_count() or 1)),
        help="Bounded worker count for independent isolated mutation fixtures (default: min(4, CPU count)).",
    )
    parser.add_argument(
        "--mutation-case-timeout-seconds",
        type=int,
        default=DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS,
        help="Hard timeout for each spawned mutation case.",
    )
    parser.add_argument(
        "--mutation-checkpoint-root",
        type=Path,
        default=DEFAULT_MUTATION_CHECKPOINT_ROOT,
        help="Repository-relative root for content-addressed per-case mutation checkpoints.",
    )
    parser.add_argument(
        "--no-mutation-checkpoint-reuse",
        action="store_true",
        help="Ignore valid mutation checkpoints while still replacing them with current results.",
    )
    parser.add_argument(
        "--clear-mutation-checkpoints",
        action="store_true",
        help="Delete the current content-addressed mutation checkpoint namespace before execution.",
    )
    parser.add_argument(
        "--heavy-checkpoint-root",
        type=Path,
        default=DEFAULT_HEAVY_CHECKPOINT_ROOT,
        help="Repository-relative root for content-addressed per-case heavyweight checkpoints.",
    )
    parser.add_argument(
        "--no-heavy-checkpoint-reuse",
        action="store_true",
        help="Ignore valid heavyweight checkpoints while still replacing them with current results.",
    )
    parser.add_argument(
        "--clear-heavy-checkpoints",
        action="store_true",
        help="Delete the current content-addressed heavyweight checkpoint namespace before execution.",
    )
    parser.add_argument(
        "--heavy-case-timeout-seconds",
        type=int,
        default=DEFAULT_HEAVY_CASE_TIMEOUT_SECONDS,
        help="Hard timeout for each spawned heavyweight case.",
    )
    parser.add_argument(
        "--heavy-case-workers",
        type=int,
        default=DEFAULT_HEAVY_CASE_WORKERS,
        help="Bounded worker count for independent spawned heavyweight cases.",
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="selected_cases",
        help="Run only the named case. Repeat to select multiple cases.",
    )
    parser.add_argument(
        "--skip-mutations",
        action="store_true",
        help="Run the heavyweight partition and common integrity ratchets only.",
    )
    parser.add_argument(
        "--skip-heavy",
        action="store_true",
        help="Run the mutation partition and common integrity ratchets only.",
    )
    parser.add_argument("--mutation-worker-case", help=argparse.SUPPRESS)
    parser.add_argument("--mutation-worker-candidate", help=argparse.SUPPRESS)
    parser.add_argument("--mutation-worker-result", help=argparse.SUPPRESS)
    parser.add_argument("--heavy-worker-case", help=argparse.SUPPRESS)
    parser.add_argument("--heavy-worker-source", help=argparse.SUPPRESS)
    parser.add_argument("--heavy-worker-root", help=argparse.SUPPRESS)
    parser.add_argument("--heavy-worker-result", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.mutation_worker_case:
        required = {
            "--mutation-worker-candidate": args.mutation_worker_candidate,
            "--mutation-worker-result": args.mutation_worker_result,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error(f"mutation worker arguments missing: {', '.join(missing)}")
        mutation_ids = {case_id for case_id, _mutate in mutation_case_functions()}
        if args.mutation_worker_case not in mutation_ids:
            parser.error(f"unknown mutation worker case: {args.mutation_worker_case}")
        return _mutation_case_worker(
            args.mutation_worker_case,
            str(args.mutation_worker_candidate),
            str(args.mutation_worker_result),
        )
    if args.heavy_worker_case:
        required = {
            "--heavy-worker-source": args.heavy_worker_source,
            "--heavy-worker-root": args.heavy_worker_root,
            "--heavy-worker-result": args.heavy_worker_result,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            parser.error(f"heavy worker arguments missing: {', '.join(missing)}")
        if args.heavy_worker_case not in heavy_case_functions():
            parser.error(f"unknown heavy worker case: {args.heavy_worker_case}")
        return _heavy_case_worker(
            args.heavy_worker_case,
            str(args.heavy_worker_source),
            str(args.heavy_worker_root),
            str(args.heavy_worker_result),
        )
    if args.mutation_workers < 1 or args.mutation_workers > 8:
        parser.error("--mutation-workers must be between 1 and 8")
    if args.mutation_case_timeout_seconds < 10 or args.mutation_case_timeout_seconds > 300:
        parser.error("--mutation-case-timeout-seconds must be between 10 and 300")
    if args.heavy_case_timeout_seconds < 10 or args.heavy_case_timeout_seconds > 900:
        parser.error("--heavy-case-timeout-seconds must be between 10 and 900")
    if args.heavy_case_workers < 1 or args.heavy_case_workers > 4:
        parser.error("--heavy-case-workers must be between 1 and 4")
    if args.skip_mutations and args.skip_heavy:
        parser.error("--skip-mutations and --skip-heavy cannot be used together")
    args.partition = (
        "HEAVY_ONLY" if args.skip_mutations
        else "MUTATIONS_ONLY" if args.skip_heavy
        else "FULL"
    )
    source = args.repo.resolve()
    source_inventory_before = locked_source_inventory(source)
    args.repository_inventory_root_before = inventory_root_sha256(source_inventory_before)
    mutation_checkpoint_context = _mutation_checkpoint_context(
        source,
        args.repository_inventory_root_before,
        args.mutation_case_timeout_seconds,
    )
    args.mutation_checkpoint_context_sha256 = _canonical_json_sha256(mutation_checkpoint_context)
    checkpoint_base = _safe_mutation_checkpoint_root(source, args.mutation_checkpoint_root)
    checkpoint_root = checkpoint_base / args.mutation_checkpoint_context_sha256
    if args.clear_mutation_checkpoints:
        shutil.rmtree(checkpoint_root, ignore_errors=True)
    heavy_checkpoint_context = _heavy_checkpoint_context(
        source,
        args.repository_inventory_root_before,
        args.heavy_case_timeout_seconds,
        args.heavy_case_workers,
    )
    args.heavy_checkpoint_context_sha256 = _canonical_json_sha256(heavy_checkpoint_context)
    heavy_checkpoint_base = _safe_heavy_checkpoint_root(source, args.heavy_checkpoint_root)
    heavy_checkpoint_root = heavy_checkpoint_base / args.heavy_checkpoint_context_sha256
    if args.clear_heavy_checkpoints:
        shutil.rmtree(heavy_checkpoint_root, ignore_errors=True)
    results: list[dict] = []

    with tempfile.TemporaryDirectory(
        prefix=PORTABLE_TEMP_PREFIX,
        dir=_portable_temp_parent(),
    ) as temp:
        root = Path(temp)
        sealed_source = root / "src"
        snapshot_inventory_before, acquisition_drift, snapshot_mismatch = acquire_stable_source_snapshot(
            source,
            sealed_source,
            source_inventory_before,
        )
        acquisition_ok = not acquisition_drift and not snapshot_mismatch
        results.append(case_result(
            "stable-source-snapshot-acquisition",
            PASS if acquisition_ok else FAIL,
            errors=[] if acquisition_ok else [
                *[f"concurrent source drift during snapshot acquisition:{item['path']}" for item in acquisition_drift[:20]],
                *[f"sealed snapshot differs from source:{item['path']}" for item in snapshot_mismatch[:20]],
            ],
            source_snapshot_isolation=SUITE_SOURCE_ISOLATION,
            source_inventory_root_sha256=inventory_root_sha256(source_inventory_before),
            snapshot_inventory_root_sha256=inventory_root_sha256(snapshot_inventory_before),
            concurrent_drift=acquisition_drift,
            snapshot_mismatch=snapshot_mismatch,
        ))
        if not acquisition_ok:
            return emit_suite_report(source, args, results)

        baseline = validate(sealed_source)
        baseline_ok = baseline.get("classification") == PASS
        results.append(case_result(
            "canonical_graph_baseline",
            PASS if baseline_ok else FAIL,
            errors=baseline.get("errors", []),
            observed_classification=baseline.get("classification"),
            source_snapshot_isolation=SUITE_SOURCE_ISOLATION,
            baseline_fail_fast=BASELINE_FAIL_FAST,
        ))
        # Do not spend minutes running adversarial branches against a graph whose
        # canonical lock is already invalid.  That creates noisy downstream errors
        # and can conceal the first actionable source-contract defect.
        if not baseline_ok:
            snapshot_after = locked_source_inventory(sealed_source)
            live_after = locked_source_inventory(source)
            snapshot_changes = inventory_delta(snapshot_inventory_before, snapshot_after)
            live_changes = inventory_delta(source_inventory_before, live_after)
            results.append(case_result(
                SOURCE_INTEGRITY_CASE_ID,
                PASS if not snapshot_changes and not live_changes else FAIL,
                errors=[
                    *[f"sealed source snapshot mutated before baseline exit:{item['path']}" for item in snapshot_changes[:20]],
                    *[f"concurrent locked-source drift observed before baseline exit:{item['path']}" for item in live_changes[:20]],
                ],
                locked_paths=len(source_inventory_before),
                source_mutation_attribution=(
                    "SEALED_SNAPSHOT_MUTATION" if snapshot_changes
                    else "EXTERNAL_CONCURRENT_DRIFT" if live_changes
                    else "NONE"
                ),
                sealed_snapshot_changes=snapshot_changes,
                concurrent_source_changes=live_changes,
            ))
            return emit_suite_report(source, args, results)

        mutation_root = root / "m"
        heavy_root = root / "h"
        mutation_root.mkdir(parents=True, exist_ok=False)
        heavy_root.mkdir(parents=True, exist_ok=False)
        mutation_specifications = mutation_case_functions()
        heavy_specifications = list(heavy_case_functions().items())
        known_case_ids = {
            "stable-source-snapshot-acquisition",
            "canonical_graph_baseline",
            SOURCE_INTEGRITY_CASE_ID,
            *(case_id for case_id, _ in mutation_specifications),
            *(case_id for case_id, _ in heavy_specifications),
        }
        selected = set(args.selected_cases or [])
        unknown = sorted(selected - known_case_ids)
        if unknown:
            parser.error(f"unknown --case values: {', '.join(unknown)}")
        if selected and "canonical_graph_baseline" not in selected:
            results = [
                item
                for item in results
                if item["case_id"] == "stable-source-snapshot-acquisition"
            ]
        selected_mutations = [] if args.skip_mutations else [item for item in mutation_specifications if not selected or item[0] in selected]
        # Keep process-heavy cases in a distinct fixture root. This prevents any
        # failed or externally interrupted mutation cleanup from invalidating the
        # parent directory used by checkpoint, build, and evidence-join cases.
        heavy_root.mkdir(parents=True, exist_ok=True)
        selected_heavy = [] if args.skip_heavy else [case_id for case_id, _case_fn in heavy_specifications if not selected or case_id in selected]
        for case_id in selected_heavy:
            print(f"release-graph adversarial case: {case_id}", flush=True)

        # The two partitions are read-only against the source repository and use
        # disjoint fixture roots. Run them concurrently so a complete adversarial
        # invocation is bounded by the slower partition instead of their sum.
        mutation_results: list[dict] = []
        heavy_results: list[dict] = []
        if selected_mutations and selected_heavy:
            with ThreadPoolExecutor(max_workers=2, thread_name_prefix="release-graph-partition") as partition_executor:
                mutation_future = partition_executor.submit(
                    run_independent_mutations, sealed_source, mutation_root, selected_mutations,
                    args.mutation_workers, args.mutation_case_timeout_seconds,
                    checkpoint_root, mutation_checkpoint_context,
                    not args.no_mutation_checkpoint_reuse
                )
                heavy_future = partition_executor.submit(
                    run_heavy_cases_isolated, sealed_source, heavy_root, selected_heavy,
                    args.heavy_case_workers, args.heavy_case_timeout_seconds,
                    heavy_checkpoint_root, heavy_checkpoint_context,
                    not args.no_heavy_checkpoint_reuse
                )
                mutation_results = mutation_future.result()
                heavy_results = heavy_future.result()
        elif selected_mutations:
            mutation_results = run_independent_mutations(
                sealed_source, mutation_root, selected_mutations,
                args.mutation_workers, args.mutation_case_timeout_seconds,
                checkpoint_root, mutation_checkpoint_context,
                not args.no_mutation_checkpoint_reuse
            )
        elif selected_heavy:
            heavy_results = run_heavy_cases_isolated(
                sealed_source, heavy_root, selected_heavy,
                args.heavy_case_workers, args.heavy_case_timeout_seconds,
                heavy_checkpoint_root, heavy_checkpoint_context,
                not args.no_heavy_checkpoint_reuse
            )
        results.extend(mutation_results)
        results.extend(heavy_results)

        snapshot_inventory_after = locked_source_inventory(sealed_source)

    if not selected or SOURCE_INTEGRITY_CASE_ID in selected:
        source_inventory_after = locked_source_inventory(source)
        args.repository_inventory_root_after = inventory_root_sha256(source_inventory_after)
        sealed_changes = inventory_delta(snapshot_inventory_before, snapshot_inventory_after)
        concurrent_changes = inventory_delta(source_inventory_before, source_inventory_after)
        attribution = (
            "SEALED_SNAPSHOT_MUTATION" if sealed_changes
            else "EXTERNAL_CONCURRENT_DRIFT" if concurrent_changes
            else "NONE"
        )
        results.append(case_result(
            SOURCE_INTEGRITY_CASE_ID,
            PASS if attribution == "NONE" else FAIL,
            errors=[
                *[f"release-graph attack suite mutated sealed source snapshot:{item['path']}" for item in sealed_changes[:20]],
                *[f"concurrent locked-source drift detected while release-graph suite ran:{item['path']}" for item in concurrent_changes[:20]],
            ],
            locked_paths=len(source_inventory_before),
            source_snapshot_isolation=SUITE_SOURCE_ISOLATION,
            source_mutation_attribution=attribution,
            source_inventory_root_before=inventory_root_sha256(source_inventory_before),
            source_inventory_root_after=inventory_root_sha256(source_inventory_after),
            sealed_inventory_root_before=inventory_root_sha256(snapshot_inventory_before),
            sealed_inventory_root_after=inventory_root_sha256(snapshot_inventory_after),
            sealed_snapshot_changes=sealed_changes,
            concurrent_source_changes=concurrent_changes,
            changed_paths=sorted({
                item["path"]
                for item in [*sealed_changes, *concurrent_changes]
            }),
        ))
    if not hasattr(args, "repository_inventory_root_after"):
        args.repository_inventory_root_after = inventory_root_sha256(locked_source_inventory(source))
    return emit_suite_report(source, args, results)


def _mutate_package(repo: Path) -> None:
    path = repo / "package.json"
    package = json.loads(path.read_text(encoding="utf-8"))
    package["scripts"]["verify:facility-arrival-runtime"] = "echo approximation"
    atomic_write_text(path, json.dumps(package, indent=2) + "\n")


def _mutate_workflow(repo: Path) -> None:
    path = repo / ".github/workflows/facility-arrival-ci.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "run: python scripts/run_release_graph.py --repo . --target ci-source --no-reuse",
        "run: npm run check:facility-arrival-source-attestations && python scripts/run_release_graph.py --repo . --target ci-source --no-reuse",
        1,
    )
    atomic_write_text(path, text)


def _mutate_locked_input(repo: Path) -> None:
    path = repo / "README.md"
    atomic_write_text(path, path.read_text(encoding="utf-8") + "\nrelease graph mutation\n")


def _mutate_action_pin(repo: Path) -> None:
    path = repo / ".github/workflows/scenario-contracts-ci.yml"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "actions/checkout@de0fac2e4500dabe0009e67214ff5f5447ce83dd",
        "actions/checkout@v4",
        1,
    )
    atomic_write_text(path, text)


def _mutate_build_runner_marker(repo: Path) -> None:
    path = repo / "scripts/run_release_build_reproducibility.py"
    text = path.read_text(encoding="utf-8").replace(
        "TWO_ISOLATED_REVIEWED_SOURCE_SNAPSHOTS_V2",
        "APPROXIMATE_BUILD_V0",
    )
    atomic_write_text(path, text)


def _mutate_build_timeout_marker(repo: Path) -> None:
    path = repo / "scripts/run_release_build_reproducibility.py"
    text = path.read_text(encoding="utf-8").replace(
        "DEFAULT_STEP_TIMEOUT_SECONDS",
        "UNBOUNDED_STEP_EXECUTION",
    )
    atomic_write_text(path, text)


def _mutate_artifact_authority_contract(repo: Path) -> None:
    mutate_graph(repo, lambda graph: graph.get("integrations", {}).pop("artifact_authority_contracts", None))


def _mutate_artifact_independent_checker(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        contract = graph["integrations"]["artifact_authority_contracts"]["facility-arrival-example-artifacts"]
        contract["independent_checkers"] = []
    mutate_graph(repo, mutate)


def _mutate_artifact_authority_coverage_removed(repo: Path) -> None:
    mutate_graph(repo, lambda graph: graph.get("integrations", {}).pop("artifact_authority_coverage", None))


def _mutate_artifact_authority_broad_directory_output(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        graph_stage(graph, "arrival.generate")["outputs"].append("examples/facility-arrival")
    mutate_graph(repo, mutate)


def _mutate_artifact_authority_unclaimed_output(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        graph_stage(graph, "scenario.research-generation")["outputs"].append(
            "public/data/research_sandbox/unclaimed.generated.json"
        )
    mutate_graph(repo, mutate)


def _mutate_artifact_authority_second_writer(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        graph_stage(graph, "scenario.research-generation")["outputs"].append(
            "public/data/scenario_core/verified_scenario_genome.json"
        )
    mutate_graph(repo, mutate)


def _mutate_generated_binding_authority_contract_removed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        graph["integrations"]["artifact_authority_contracts"].pop(
            "facility-arrival-generated-bindings", None
        )
    mutate_graph(repo, mutate)


def _mutate_offline_raw_graph_artifact(repo: Path) -> None:
    path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["artifact_inventory"].append({
        "name": "release_graph",
        "path": "config/release/RELEASE_GRAPH.json",
    })
    atomic_write_text(path, json.dumps(policy, indent=2) + "\n")
    relock_graph_input_sets(
        repo,
        ["orchestration", "scenario-source", "standalone-source", "release-policy-source"],
    )


def _mutate_offline_raw_graph_hash(repo: Path) -> None:
    path = repo / "public/data/scenario_core/offline_scenario_release.json"
    descriptor = json.loads(path.read_text(encoding="utf-8"))
    descriptor["release_graph"]["file_sha256"] = hashlib.sha256(
        (repo / "config/release/RELEASE_GRAPH.json").read_bytes()
    ).hexdigest()
    descriptor.pop("release_sha256", None)
    descriptor["release_sha256"] = hashlib.sha256(
        json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    atomic_write_text(path, json.dumps(descriptor, indent=2, sort_keys=True) + "\n")
    relock_graph_input_sets(repo, ["standalone-source"])


def _mutate_offline_graph_binding_mode(repo: Path) -> None:
    path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["release_graph_binding_mode"] = "RAW_FILE_SHA256_V0"
    atomic_write_text(path, json.dumps(policy, indent=2) + "\n")
    relock_graph_input_sets(
        repo,
        ["orchestration", "scenario-source", "standalone-source", "release-policy-source"],
    )


def _mutate_offline_graph_contract_drift(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph.__setitem__(
            "release_candidate",
            f"{graph.get('release_candidate', '')} semantic-contract-drift",
        ),
    )


def _mutate_offline_identity_contract_removed(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph.get("integrations", {}).pop("offline_release_identity_contract", None),
    )


def _mutate_offline_writer_ownership_expanded(repo: Path) -> None:
    path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["documentation_contract"]["writer_owned_surfaces"] = ["root", "standalone", "facility"]
    atomic_write_text(path, json.dumps(policy, indent=2, sort_keys=True) + "\n")
    relock_graph_input_sets(repo, ["orchestration", "scenario-source", "standalone-source", "release-policy-source"])


def _mutate_offline_verification_ownership_reduced(repo: Path) -> None:
    path = repo / "config/release/OFFLINE_SCENARIO_RELEASE.json"
    policy = json.loads(path.read_text(encoding="utf-8"))
    policy["documentation_contract"]["verification_only_surfaces"] = ["verified"]
    atomic_write_text(path, json.dumps(policy, indent=2, sort_keys=True) + "\n")
    relock_graph_input_sets(repo, ["orchestration", "scenario-source", "standalone-source", "release-policy-source"])


def _mutate_offline_stage_claims_verification_document(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        stage = graph_stage(graph, "offline.release-generate")
        stage["outputs"] = [*stage.get("outputs", []), "examples/facility-arrival/README.md"]
    mutate_graph(repo, mutate)


def _replace_offline_attack_contract(repo: Path, old: str, new: str) -> None:
    relative = "scripts/test_offline_scenario_release.py"
    path = repo / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"offline release attack contract marker absent:{old}")
    atomic_write_text(path, text.replace(old, new, 1))
    relock_input_sets_containing_path(repo, relative)


def _mutate_offline_case_registry_profile(repo: Path) -> None:
    _replace_offline_attack_contract(
        repo,
        'CASE_REGISTRY_PROFILE = "UNIQUE_DETERMINISTIC_CASE_REGISTRY_V1"',
        'CASE_REGISTRY_PROFILE = "UNVALIDATED_CASE_LIST_V0"',
    )


def _mutate_offline_scheduler_profile(repo: Path) -> None:
    _replace_offline_attack_contract(
        repo,
        'CASE_SCHEDULER_PROFILE = "BOUNDED_PARALLEL_ISOLATED_FIXTURES_V1"',
        'CASE_SCHEDULER_PROFILE = "UNBOUNDED_SHARED_FIXTURES_V0"',
    )


def _mutate_offline_source_guard_profile(repo: Path) -> None:
    _replace_offline_attack_contract(
        repo,
        'SOURCE_GUARD_PROFILE = "SOURCE_INVENTORY_PRESERVATION_RATCHET_V1"',
        'SOURCE_GUARD_PROFILE = "NO_SOURCE_GUARD_V0"',
    )


def _mutate_offline_duplicate_case_id(repo: Path) -> None:
    _replace_offline_attack_contract(
        repo,
        '        ("baseline", None, True),',
        '        ("baseline", None, True),\n        ("baseline", None, True),',
    )


def _mutate_offline_worker_ceiling(repo: Path) -> None:
    _replace_offline_attack_contract(repo, "MAX_WORKERS = 8", "MAX_WORKERS = 64")


def _mutate_engine_evolution_stabilizer_removed(repo: Path) -> None:
    path = repo / "scripts/stabilize_engine_evolution_release.py"
    path.unlink()


def _mutate_partition_checkpoint_marker(repo: Path) -> None:
    path = repo / "scripts/test_release_graph.py"
    text = path.read_text(encoding="utf-8").replace(
        "CHECKPOINTED_INDEPENDENT_MUTATION_AND_HEAVY_PARTITIONS_V2",
        "MONOLITHIC_UNCHECKPOINTED_PARTITIONS_V0",
        1,
    )
    atomic_write_text(path, text)


def _remove_graph_stage(repo: Path, stage_id: str) -> None:
    def mutate(graph: dict) -> None:
        graph["stages"] = [stage for stage in graph.get("stages", []) if stage.get("id") != stage_id]
    mutate_graph(repo, mutate)


def _mutate_graph_mutation_partition_stage_removed(repo: Path) -> None:
    _remove_graph_stage(repo, "orchestration.graph-attacks-mutations")


def _mutate_graph_heavy_partition_stage_removed(repo: Path) -> None:
    _remove_graph_stage(repo, "orchestration.graph-attacks-heavy")


def _mutate_graph_partition_join_bypassed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        graph_stage(graph, "orchestration.graph-attacks")["needs"] = ["orchestration.graph-attacks-mutations"]
    mutate_graph(repo, mutate)


def _mutate_graph_partition_join_attacks_output_removed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        stage = graph_stage(graph, "orchestration.graph-attacks")
        stage["outputs"] = [
            value for value in stage.get("outputs", [])
            if (value if isinstance(value, str) else value.get("path"))
            != "reports/release-graph-partition-join-mutations.json"
        ]
    mutate_graph(repo, mutate)


def _remove_gitignore_boundary(repo: Path, marker: str) -> None:
    path = repo / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines()
    if marker not in lines:
        raise RuntimeError(f"gitignore mutation marker absent:{marker}")
    lines.remove(marker)
    atomic_write_text(path, "\n".join(lines) + "\n")


def _mutate_mutation_checkpoint_profile(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'MUTATION_CHECKPOINT_PROFILE = "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1"',
        'MUTATION_CHECKPOINT_PROFILE = "UNAUTHENTICATED_CACHE_V0"',
    )


def _mutate_heavy_checkpoint_profile(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'HEAVY_CHECKPOINT_PROFILE = "CONTENT_ADDRESSED_PER_CASE_DURABLE_RESUME_V1"',
        'HEAVY_CHECKPOINT_PROFILE = "UNAUTHENTICATED_CACHE_V0"',
    )


def _mutate_mutation_process_isolation(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'MUTATION_CASE_ISOLATION = "SPAWNED_PROCESS_GROUP_WITH_DURABLE_RESULT_V1"',
        'MUTATION_CASE_ISOLATION = "THREAD_ONLY_UNBOUNDED_V0"',
    )


def _mutate_mutation_worker_execution_boundary(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'MUTATION_WORKER_EXECUTION = "SEALED_PER_CASE_MUTATION_SNAPSHOT_EXECUTABLE_V1"',
        'MUTATION_WORKER_EXECUTION = "LIVE_WORKING_TREE_EXECUTABLE_V0"',
    )


def _mutate_mutation_worker_result_binding(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'MUTATION_WORKER_RESULT_BINDING = "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1"',
        'MUTATION_WORKER_RESULT_BINDING = "UNBOUND_RESULT_V0"',
    )


def _mutate_mutation_worker_live_script_regression(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'worker_script = candidate / "scripts/test_release_graph.py"',
        'worker_script = Path(__file__).resolve()',
    )


def _mutate_mutation_case_timeout(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        "DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS = 90",
        "DEFAULT_MUTATION_CASE_TIMEOUT_SECONDS = 900",
    )


def _mutate_mutation_validator_timeout(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        "DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS = 60",
        "DEFAULT_MUTATION_VALIDATOR_TIMEOUT_SECONDS = 600",
    )


def _mutate_heavy_resource_scheduler_marker(repo: Path) -> None:
    path = repo / "scripts/test_release_graph.py"
    text = path.read_text(encoding="utf-8").replace(
        "RESOURCE_CLASS_AWARE_EXCLUSIVE_FANOUT_V1",
        "UNBOUNDED_HEAVY_FANOUT_V0",
        1,
    )
    atomic_write_text(path, text)


def _mutate_heavy_default_worker_floor(repo: Path) -> None:
    """Reject a load-sensitive default that fans heavyweight cases out again."""
    _replace_graph_attack_contract(
        repo,
        "DEFAULT_HEAVY_CASE_WORKERS = 1",
        "DEFAULT_HEAVY_CASE_WORKERS = 4",
    )


def _mutate_workspace_path_profile(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'WORKSPACE_PATH_PROFILE = "CONTENT_ADDRESSED_COMPACT_WORKSPACE_PATHS_V1"',
        'WORKSPACE_PATH_PROFILE = "FULL_CASE_IDS_IN_PATHS_V0"',
    )


def _mutate_mutation_workspace_full_case_id(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'worker_root = root / _compact_workspace_component("m", case_id)',
        'worker_root = root / f"{case_id}-process"',
    )


def _mutate_heavy_workspace_full_case_id(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'worker_root = root / _compact_workspace_component("h", case_id)',
        'worker_root = root / f"{case_id}-process"',
    )


def _mutate_failed_case_diagnostics_removed(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        '"failed_case_details": [',
        '"failed_case_details_removed": [',
    )


def _mutate_heavy_worker_execution_boundary(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'HEAVY_WORKER_EXECUTION = "SEALED_PER_CASE_SOURCE_SNAPSHOT_EXECUTABLE_V1"',
        'HEAVY_WORKER_EXECUTION = "LIVE_WORKING_TREE_EXECUTABLE_V0"',
    )


def _mutate_heavy_worker_result_binding(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'HEAVY_WORKER_RESULT_BINDING = "REGISTRY_KEY_AND_WORKER_SCRIPT_SHA256_V1"',
        'HEAVY_WORKER_RESULT_BINDING = "UNBOUND_RESULT_V0"',
    )


def _mutate_heavy_worker_live_script_regression(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'worker_script = case_source / "scripts/test_release_graph.py"',
        'worker_script = Path(__file__).resolve()',
    )


def _mutate_duplicate_node_documentation_renderer(repo: Path) -> None:
    path = repo / "scripts/check_offline_scenario_release.mjs"
    text = path.read_text(encoding="utf-8")
    text += "\nfunction expectedEvolutionBlock(ctx) { return String(ctx); }\n"
    atomic_write_text(path, text)


def _remove_input_set_path(repo: Path, set_id: str, relative: str) -> None:
    def mutate(graph: dict) -> None:
        specification = graph["input_sets"][set_id]
        specification["include"] = [
            value for value in specification.get("include", []) if value != relative
        ]
        specification.get("files", {}).pop(relative, None)

    mutate_graph(repo, mutate)


def _mutate_local_source_closure_contract_removed(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph.get("integrations", {}).pop("local_source_closure_contract", None),
    )


def _replace_graph_attack_contract(repo: Path, old: str, new: str) -> None:
    relative = "scripts/test_release_graph.py"
    path = repo / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise ValueError(f"release-graph attack contract marker absent:{old}")
    atomic_write_text(path, text.replace(old, new, 1))
    relock_input_sets_containing_path(repo, relative)


def _mutate_suite_source_snapshot_contract_removed(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'SOURCE_SNAPSHOT_ISOLATION = "STABLE_HERMETIC_SUITE_SOURCE_SNAPSHOT_WITH_PER_CASE_COPIES_V2"',
        'SOURCE_SNAPSHOT_ISOLATION = "DISABLED"',
    )


def _mutate_baseline_fail_fast_contract_removed(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'BASELINE_FAIL_FAST = "CANONICAL_BASELINE_FAILS_BEFORE_ADVERSARIAL_SCHEDULING_V1"',
        'BASELINE_FAIL_FAST = "DISABLED"',
    )


def _mutate_heavy_source_guard_contract_removed(repo: Path) -> None:
    _replace_graph_attack_contract(
        repo,
        'HEAVY_CASE_SOURCE_GUARD = "PER_CASE_LOCKED_SOURCE_INVENTORY_GUARD_V1"',
        'HEAVY_CASE_SOURCE_GUARD = "DISABLED"',
    )


def _mutate_python_transitive_source_unlocked(repo: Path) -> None:
    fixture = repo / "scripts/closure_unlocked_fixture.py"
    atomic_write_text(fixture, 'VALUE = "unlocked"\n')
    source = repo / "scripts/check_engine_evolution_documentation.py"
    atomic_write_text(source, source.read_text(encoding="utf-8") + "\nimport closure_unlocked_fixture\n")
    relock_graph_input_sets(
        repo,
        ["orchestration", "release-policy-source", "scenario-source", "standalone-source"],
    )


def _mutate_node_transitive_source_unlocked(repo: Path) -> None:
    fixture = repo / "scripts/closure-unlocked-node-fixture.mjs"
    atomic_write_text(fixture, 'export const value = "unlocked";\n')
    source = repo / "scripts/check_engine_evolution_documentation.mjs"
    atomic_write_text(
        source,
        source.read_text(encoding="utf-8") + "\nimport './closure-unlocked-node-fixture.mjs';\n",
    )
    relock_graph_input_sets(
        repo,
        ["orchestration", "release-policy-source", "scenario-source", "standalone-source"],
    )


def _mutate_source_closure_report_output_removed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        stage = graph_stage(graph, "orchestration.graph-attacks-mutations")
        stage["outputs"] = [
            value
            for value in stage.get("outputs", [])
            if (value if isinstance(value, str) else value.get("path"))
            != "reports/release-source-closure-mutations.json"
        ]

    mutate_graph(repo, mutate)


def _mutate_scenario_behavior_archive_output_removed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        stage = graph_stage(graph, "scenario.contracts")
        stage["outputs"] = [
            value
            for value in stage.get("outputs", [])
            if (value if isinstance(value, str) else value.get("path"))
            != "reports/scenario-behavior-archive.json"
        ]

    mutate_graph(repo, mutate)


def _mutate_scenario_behavior_archive_check_stage_removed(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph.__setitem__(
            "stages",
            [stage for stage in graph.get("stages", []) if stage.get("id") != "scenario.behavior-archive-check"],
        ),
    )


def _mutate_scenario_behavior_archive_attacks_detached(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph_stage(graph, "scenario.behavior-archive-attacks").__setitem__(
            "needs", ["scenario.contracts"]
        ),
    )


def _mutate_scenario_behavior_archive_checker_lock_removed(repo: Path) -> None:
    _remove_input_set_path(
        repo,
        "scenario-source",
        "scripts/check_scenario_behavior_archive.py",
    )


def _mutate_scenario_gate(repo: Path) -> None:
    path = repo / "scripts/run_scenario_contract_gate.py"
    text = path.read_text(encoding="utf-8").replace(
        '    "assure:scenario-experience": "tsx scripts/runScenarioExperienceAssurance.ts",\n',
        "",
        1,
    )
    atomic_write_text(path, text)


def _mutate_scenario_workflow_target(repo: Path) -> None:
    path = repo / ".github/workflows/scenario-contracts-ci.yml"
    text = path.read_text(encoding="utf-8").replace(
        "--target ci-scenario --no-reuse",
        "--target ci-runtime --no-reuse",
        1,
    )
    atomic_write_text(path, text)





def _mutate_example_workflow_target(repo: Path) -> None:
    path = repo / ".github/workflows/example-scenario-ci.yml"
    text = path.read_text(encoding="utf-8").replace(
        "--target ci-example-node --no-reuse",
        "--target ci-runtime --no-reuse",
        1,
    )
    atomic_write_text(path, text)
    relock_graph_input_sets(repo, ["orchestration"])


def _mutate_unregistered_pull_request_workflow(repo: Path) -> None:
    path = repo / ".github/workflows/unregistered-pr-bypass.yml"
    atomic_write_text(
        path,
        """name: unregistered-pr-bypass

on:
  pull_request:
    branches: [main]

permissions:
  contents: read

jobs:
  bypass:
    runs-on: ubuntu-latest
    steps:
      - run: echo bypass
""",
    )
    relock_graph_input_sets(repo, ["orchestration"])


def _mutate_scenario_ratchet_stage_removed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        removed = {"scenario.capability-ratchet", "scenario.capability-ratchet-attacks"}
        graph["stages"] = [stage for stage in graph["stages"] if stage.get("id") not in removed]
        graph_stage(graph, "scenario.evolution-evidence")["needs"] = ["scenario.contracts"]
    mutate_graph(repo, mutate)


def _mutate_scenario_evolution_bypass(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph_stage(graph, "scenario.generation-assurance").__setitem__(
            "needs", ["scenario.contracts"]
        ),
    )


def _mutate_scenario_evolution_receipt_attacks_removed(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        removed_stage = "scenario.evolution-evidence-attacks"
        graph["stages"] = [stage for stage in graph["stages"] if stage.get("id") != removed_stage]
        graph_stage(graph, "scenario.generation-assurance")["needs"] = ["scenario.evolution-evidence"]
        graph["targets"]["ci-example-integrated"]["terminal_stages"] = ["scenario.evolution-evidence"]
        for key in ("critical_package_rehearsal_stages", "required_scenario_evolution_stages"):
            values = graph.get("integrations", {}).get(key, [])
            graph["integrations"][key] = [value for value in values if value != removed_stage]
    mutate_graph(repo, mutate)


def _mutate_scenario_genome_artifact_contract(repo: Path) -> None:
    mutate_graph(
        repo,
        lambda graph: graph["integrations"]["artifact_authority_contracts"].pop(
            "verified-scenario-genome-artifact", None
        ),
    )


def _mutate_scenario_evolution_duplicate_runner(repo: Path) -> None:
    path = repo / "scripts/run_scenario_contract_gate.py"
    text = path.read_text(encoding="utf-8").replace(
        '    "generate:verified-scenario-package": "tsx scripts/generateVerifiedScenarioPackage.ts",',
        '    "generate:verified-scenario-package": "tsx scripts/generateVerifiedScenarioPackage.ts",\n'
        '    "check:verified-example": "npm run check:verified-example",',
        1,
    )
    atomic_write_text(path, text)
    relock_graph_input_sets(repo, ["scenario-source"])

def _mutate_scenario_evolution_receipt_union_regression(repo: Path) -> None:
    path = repo / "scripts/join_scenario_evolution_evidence.py"
    text = path.read_text(encoding="utf-8").replace(
        "REQUIRED_RECEIPT_STAGES = tuple(sorted(set(REPORT_STAGE_MAP.values()) | set(ARTIFACT_STAGE_MAP.values())))",
        "REQUIRED_RECEIPT_STAGES = tuple(sorted(set(REPORT_STAGE_MAP.values())))",
        1,
    )
    atomic_write_text(path, text)
    relock_graph_input_sets(repo, ["release-policy-source", "scenario-source"])


def _mutate_production_behavioral_summary_projection_regression(repo: Path) -> None:
    path = repo / "scripts/release_production_designation.py"
    text = path.read_text(encoding="utf-8").replace(
        "behavioral_summary = behavioral_policy_summary(behavioral)",
        "behavioral_summary = behavioral",
        1,
    )
    atomic_write_text(path, text)
    relock_graph_input_sets(repo, ["release-policy-source"])


def _mutate_scenario_fixture_lock(repo: Path) -> None:
    def mutate(graph: dict) -> None:
        specification = graph["input_sets"]["scenario-source"]
        path = "src/test-fixtures/researchBridge.fixture.ts"
        specification["include"] = [item for item in specification.get("include", []) if item != path]
        specification.get("files", {}).pop(path, None)
    mutate_graph(repo, mutate)

def _mutate_standalone_windows_shell(repo: Path) -> None:
    path = repo / ".github/workflows/facility-standalone-ci.yml"
    text = path.read_text(encoding="utf-8").replace(
        "  standalone-windows:\n    runs-on: windows-latest",
        "  standalone-windows:\n    runs-on: windows-latest\n    defaults:\n      run:\n        shell: bash",
        1,
    )
    atomic_write_text(path, text)


if __name__ == "__main__":
    raise SystemExit(main())
