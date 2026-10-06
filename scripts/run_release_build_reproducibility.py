#!/usr/bin/env python3
"""Build twice in isolated source snapshots and retain actionable evidence.

The release build is treated as a deterministic experiment rather than a single
opaque ``npm run build`` call.  Each pass receives the same reviewed source
inventory, the same locked dependency tree, a minimal deterministic environment,
and an isolated cache/output directory.  Every subgate has a redacted durable log.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from collections import deque
from pathlib import Path
from typing import Any, Iterable, Mapping

from release_graph_core import (
    GRAPH_PATH,
    canonical_json,
    collect_input_files,
    load_graph,
    native_command,
    sha256_file,
    sha256_text,
    utc_now,
    write_json,
)
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

REPORT = Path("reports/facility-decision-build-reproducibility.json")
PROVENANCE = Path("reports/facility-decision-build-provenance.json")
LOG_ROOT = Path(".asklepios/build-reproducibility")
BUILD_MODE = "TWO_ISOLATED_REVIEWED_SOURCE_SNAPSHOTS_V2"
SOURCE_INVENTORY_MODE = "GIT_TRACKED_PLUS_RELEASE_LOCKED_INPUTS_V1"
ENVIRONMENT_POLICY = "MINIMAL_ALLOWLISTED_REPRODUCIBLE_ENVIRONMENT_V1"
BUILD_STEPS = ("build:generate", "build:typecheck", "build:bundle")
DEFAULT_STEP_TIMEOUT_SECONDS = 15 * 60
DEFAULT_PROVENANCE_TIMEOUT_SECONDS = 5 * 60
_TOKEN_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[pousr]_[A-Za-z0-9_]+"),
    re.compile(r"npm_[A-Za-z0-9_]+"),
    re.compile(r"(?i)(authorization\s*:\s*(?:token|bearer)\s+)[^\s]+"),
)
_SECRET_NAME = re.compile(r"(?i)(token|secret|password|passwd|credential|private[_-]?key|auth)")


def tree_manifest(directory: Path) -> dict[str, dict[str, int | str]]:
    if not directory.is_dir():
        raise ValueError(f"build directory missing:{directory}")
    result: dict[str, dict[str, int | str]] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"build symlink forbidden:{path}")
        if not path.is_file():
            continue
        relative = path.relative_to(directory).as_posix()
        result[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    if not result:
        raise ValueError(f"build directory empty:{directory}")
    return result


def source_snapshot(root: Path, graph: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for set_id in sorted(graph["input_sets"]):
        for path, digest in collect_input_files(root, graph["input_sets"][set_id]).items():
            prior = result.get(path)
            if prior is not None and prior != digest:
                raise ValueError(f"source snapshot collision:{path}")
            result[path] = digest
    return dict(sorted(result.items()))


def git_tracked_paths(root: Path) -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"cannot enumerate tracked build inputs:{detail}")
    return sorted(item.decode("utf-8", errors="strict") for item in completed.stdout.split(b"\0") if item)


def reviewed_source_paths(root: Path, graph: Mapping[str, Any]) -> list[str]:
    """Return only Git-tracked or content-locked paths.

    This admits newly applied, not-yet-committed package files only when they are
    already named and hashed by a release input set. Ambient receipts, editor
    files, caches, and arbitrary untracked content remain invisible to the build.
    """
    paths = set(git_tracked_paths(root))
    for specification in graph["input_sets"].values():
        files = specification.get("files", {})
        if isinstance(files, dict):
            paths.update(str(item) for item in files)
    paths.discard("dist")
    return sorted(paths)


def copy_source_tree(root: Path, destination: Path, relative_paths: Iterable[str]) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for relative in relative_paths:
        source = root / relative
        target = destination / relative
        if source.is_symlink():
            raise RuntimeError(f"reviewed build input is a symlink:{relative}")
        if not source.is_file():
            raise RuntimeError(f"reviewed build input is missing:{relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def link_dependencies(source: Path, target: Path) -> str:
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError("node_modules is absent or unsafe; run npm ci before the reproducibility gate")
    if target.exists() or target.is_symlink():
        raise RuntimeError(f"sandbox dependency path already exists:{target}")
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd.exe", "/d", "/s", "/c", subprocess.list2cmdline(["mklink", "/J", str(target), str(source)])],
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0 or not target.is_dir():
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(f"cannot create node_modules junction:{completed.returncode}:{detail}")
        return "WINDOWS_DIRECTORY_JUNCTION"
    target.symlink_to(source, target_is_directory=True)
    return "POSIX_DIRECTORY_SYMLINK"


def clear_shared_tool_caches(installed: Path) -> list[str]:
    """Remove known mutable tool caches before each pass.

    The package payload remains untouched.  Only cache directories inside the
    installed dependency tree are removed, preventing pass one from warming a
    cache that pass two did not begin with.
    """
    removed: list[str] = []
    for relative in (".vite", ".cache", ".tmp"):
        path = installed / relative
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
            removed.append(relative)
        elif path.exists() or path.is_symlink():
            path.unlink(missing_ok=True)
            removed.append(relative)
    return removed


def git_source_date_epoch(root: Path) -> str:
    completed = subprocess.run(
        ["git", "log", "-1", "--format=%ct"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value.isdigit() else "0"


def deterministic_build_timestamp(source_date_epoch: str) -> str:
    from datetime import datetime, timezone
    try:
        epoch = max(0, int(source_date_epoch))
    except ValueError:
        epoch = 0
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def deterministic_environment(root: Path, started: str) -> dict[str, str]:
    del started  # Wall-clock time must never enter a reproducible production build.
    allowed = (
        "PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "SystemRoot", "WINDIR",
        "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "LOCALAPPDATA", "APPDATA",
    )
    environment = {key: os.environ[key] for key in allowed if key in os.environ}
    source_date_epoch = git_source_date_epoch(root)
    environment.update({
        "CI": "true",
        "NODE_ENV": "production",
        "TZ": "UTC",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "SOURCE_DATE_EPOCH": source_date_epoch,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "npm_config_audit": "false",
        "npm_config_fund": "false",
        "npm_config_update_notifier": "false",
        "ASKLEPIOS_BUILD_STARTED_AT": deterministic_build_timestamp(source_date_epoch),
    })
    if "ASKLEPIOS_PYTHON" in os.environ:
        environment["ASKLEPIOS_PYTHON"] = os.environ["ASKLEPIOS_PYTHON"]
    return environment


def secret_values(environment: Mapping[str, str]) -> list[str]:
    values: set[str] = set()
    for key, value in os.environ.items():
        if _SECRET_NAME.search(key) and len(value) >= 8:
            values.add(value)
    for key, value in environment.items():
        if _SECRET_NAME.search(key) and len(value) >= 8:
            values.add(value)
    return sorted(values, key=len, reverse=True)


def redact_text(value: str, secrets: Iterable[str]) -> str:
    text = value
    for pattern in _TOKEN_PATTERNS:
        if pattern.groups:
            text = pattern.sub(lambda match: match.group(1) + "<REDACTED>", text)
        else:
            text = pattern.sub("<REDACTED>", text)
    for secret in secrets:
        text = text.replace(secret, "<REDACTED_ENV_VALUE>")
    return text


def terminate_process_tree(process: subprocess.Popen[str]) -> str:
    """Terminate a timed-out command and its descendants without touching the caller."""
    if process.poll() is not None:
        return "ALREADY_EXITED"
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            text=True,
            capture_output=True,
            check=False,
        )
        return f"WINDOWS_TASKKILL:{completed.returncode}"
    try:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
            return "POSIX_PROCESS_GROUP_SIGTERM"
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            return "POSIX_PROCESS_GROUP_SIGKILL"
    except ProcessLookupError:
        return "PROCESS_GROUP_ALREADY_EXITED"


def run_logged(
    canonical_command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    log_path: Path,
    secrets: Iterable[str],
    timeout_seconds: int,
) -> dict[str, Any]:
    if not isinstance(timeout_seconds, int) or timeout_seconds < 1:
        raise ValueError("command timeout must be a positive integer")
    execution_command = native_command(canonical_command)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tail: deque[str] = deque(maxlen=120)
    reader_errors: list[str] = []
    timed_out = False
    termination = "NOT_REQUIRED"
    with log_path.open("w", encoding="utf-8", newline="\n") as handle:
        popen_options: dict[str, Any] = {}
        if os.name == "nt":
            popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_options["start_new_session"] = True
        process = subprocess.Popen(
            execution_command,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            **popen_options,
        )
        assert process.stdout is not None

        def consume() -> None:
            try:
                for raw in process.stdout:
                    line = redact_text(raw, secrets)
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    handle.write(line)
                    handle.flush()
                    tail.append(line.rstrip("\r\n"))
            except Exception as exc:  # noqa: BLE001 - surfaced in the stage result
                reader_errors.append(f"{type(exc).__name__}:{exc}")

        reader = threading.Thread(target=consume, name="asklepios-build-log-reader", daemon=True)
        reader.start()
        try:
            returncode = int(process.wait(timeout=timeout_seconds))
        except subprocess.TimeoutExpired:
            timed_out = True
            termination = terminate_process_tree(process)
            returncode = 124
            timeout_line = redact_text(
                f"COMMAND TIMEOUT after {timeout_seconds}s; termination={termination}\n",
                secrets,
            )
            sys.stdout.write(timeout_line)
            sys.stdout.flush()
            handle.write(timeout_line)
            handle.flush()
            tail.append(timeout_line.rstrip("\r\n"))
        finally:
            reader.join(timeout=10)
            process.stdout.close()
        if reader.is_alive():
            reader_errors.append("log reader did not terminate")
            returncode = 124
            timed_out = True
    return {
        "canonical_command": canonical_command,
        "execution_command": execution_command,
        "returncode": returncode,
        "timed_out": timed_out,
        "timeout_seconds": timeout_seconds,
        "termination": termination,
        "reader_errors": reader_errors,
        "log_path": log_path.as_posix(),
        "log_sha256": sha256_file(log_path),
        "log_bytes": log_path.stat().st_size,
        "tail": list(tail),
        "redaction_mode": "KNOWN_TOKEN_PATTERNS_AND_SECRET_ENV_VALUES_V1",
    }


def run_build_pipeline(
    snapshot: Path,
    installed: Path,
    environment: dict[str, str],
    log_root: Path,
    label: str,
    npm_executable: str,
    secrets: Iterable[str],
    step_timeout_seconds: int,
) -> dict[str, Any]:
    cache_removals = clear_shared_tool_caches(installed)
    steps: list[dict[str, Any]] = []
    failed_step: str | None = None
    for index, script in enumerate(BUILD_STEPS, start=1):
        result = run_logged(
            [npm_executable, "run", script],
            cwd=snapshot,
            environment=environment,
            log_path=log_root / f"{label}-{index:02d}-{script.replace(':', '-')}.log",
            secrets=secrets,
            timeout_seconds=step_timeout_seconds,
        )
        result["script"] = script
        result["classification"] = PASS if result["returncode"] == 0 else FAIL
        steps.append(result)
        if result["returncode"] != 0:
            failed_step = script
            break

    manifest: dict[str, Any] = {}
    output_error: str | None = None
    if failed_step is None:
        try:
            manifest = tree_manifest(snapshot / "dist")
        except Exception as exc:  # noqa: BLE001
            output_error = f"{type(exc).__name__}:{exc}"
    tail = steps[-1]["tail"] if steps else []
    return {
        "classification": PASS if failed_step is None and output_error is None else FAIL,
        "failed_step": failed_step,
        "output_error": output_error,
        "steps": steps,
        "tail": tail,
        "cache_removals": cache_removals,
        "manifest": manifest,
        "manifest_root_sha256": sha256_text(canonical_json(manifest)),
    }


def compact_build(build: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in build.items() if key != "manifest"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=REPORT)
    parser.add_argument("--provenance-output", type=Path, default=PROVENANCE)
    parser.add_argument("--log-root", type=Path, default=LOG_ROOT)
    parser.add_argument("--npm-executable", default="npm")
    parser.add_argument("--step-timeout-seconds", type=int, default=DEFAULT_STEP_TIMEOUT_SECONDS)
    parser.add_argument("--provenance-timeout-seconds", type=int, default=DEFAULT_PROVENANCE_TIMEOUT_SECONDS)
    parser.add_argument("--keep-sandboxes", action="store_true")
    args = parser.parse_args()

    root = args.repo.resolve()
    report_path = args.json_output if args.json_output.is_absolute() else root / args.json_output
    provenance_path = args.provenance_output if args.provenance_output.is_absolute() else root / args.provenance_output
    log_root = args.log_root if args.log_root.is_absolute() else root / args.log_root
    errors: list[str] = []
    classification = PASS
    started = utc_now()
    first: dict[str, Any] = {}
    second: dict[str, Any] = {}
    changed_sources: list[str] = []
    dependency_modes: list[str] = []
    provenance: dict[str, Any] = {"status": "NOT_RUN", "returncode": None, "tail": []}
    source_paths: list[str] = []
    environment: dict[str, str] = {}
    temporary_parent: Path | None = None

    shutil.rmtree(root / "dist", ignore_errors=True)
    provenance_path.unlink(missing_ok=True)
    shutil.rmtree(log_root, ignore_errors=True)
    log_root.mkdir(parents=True, exist_ok=True)

    try:
        graph = load_graph(root, GRAPH_PATH)
        before_sources = source_snapshot(root, graph)
        source_paths = reviewed_source_paths(root, graph)
        installed = root / "node_modules"
        environment = deterministic_environment(root, started)
        secrets = secret_values(environment)
        temporary_parent = Path(tempfile.mkdtemp(prefix="asklepios-reproducible-build-"))
        first_root = temporary_parent / "first-source"
        second_root = temporary_parent / "second-source"
        copy_source_tree(root, first_root, source_paths)
        copy_source_tree(root, second_root, source_paths)
        dependency_modes.append(link_dependencies(installed, first_root / "node_modules"))
        dependency_modes.append(link_dependencies(installed, second_root / "node_modules"))

        first = run_build_pipeline(
            first_root, installed, environment, log_root, "first", args.npm_executable, secrets,
            args.step_timeout_seconds,
        )
        second = run_build_pipeline(
            second_root, installed, environment, log_root, "second", args.npm_executable, secrets,
            args.step_timeout_seconds,
        )

        for label, build in (("first", first), ("second", second)):
            if build.get("failed_step"):
                step = str(build["failed_step"])
                failed = next(item for item in build["steps"] if item["script"] == step)
                errors.append(
                    f"{label} production build failed:step={step}:exit={failed['returncode']}:log={failed['log_path']}"
                )
            elif build.get("output_error"):
                errors.append(f"{label} production build output invalid:{build['output_error']}")

        first_manifest = first.get("manifest", {})
        second_manifest = second.get("manifest", {})
        if first_manifest and second_manifest:
            first_keys, second_keys = set(first_manifest), set(second_manifest)
            errors.extend(f"build file missing on second pass:{item}" for item in sorted(first_keys - second_keys))
            errors.extend(f"unexpected build file on second pass:{item}" for item in sorted(second_keys - first_keys))
            errors.extend(
                f"build byte identity differs:{item}"
                for item in sorted(first_keys & second_keys)
                if first_manifest[item] != second_manifest[item]
            )
            if not errors:
                shutil.copytree(first_root / "dist", root / "dist")

        if not errors and (root / "dist").is_dir():
            provenance_command = [
                os.environ.get("ASKLEPIOS_PYTHON", sys.executable),
                "scripts/build_facility_decision_provenance.py",
                "--repo", ".",
                "--subject-dir", "dist",
                "--output", str(args.provenance_output),
            ]
            provenance = run_logged(
                provenance_command,
                cwd=root,
                environment=environment,
                log_path=log_root / "provenance.log",
                secrets=secrets,
                timeout_seconds=args.provenance_timeout_seconds,
            )
            provenance["status"] = PASS if provenance["returncode"] == 0 else FAIL
            if provenance["returncode"] != 0:
                errors.append(
                    f"build provenance generation failed:exit={provenance['returncode']}:log={provenance['log_path']}"
                )
            elif not provenance_path.is_file():
                errors.append("build provenance command succeeded without output")

        # Measure the repository only after every build-related command,
        # including provenance generation, has completed.
        after_sources = source_snapshot(root, graph)
        changed_sources = sorted(
            path for path in set(before_sources) | set(after_sources)
            if before_sources.get(path) != after_sources.get(path)
        )
        if changed_sources:
            errors.append(f"production build mutated locked source:{changed_sources}")
            shutil.rmtree(root / "dist", ignore_errors=True)
            provenance_path.unlink(missing_ok=True)
        classification = PASS if not errors else FAIL
    except Exception as exc:  # noqa: BLE001
        classification = INTERNAL_ERROR
        errors.append(f"{type(exc).__name__}:{exc}")
    finally:
        if temporary_parent is not None and not args.keep_sandboxes:
            shutil.rmtree(temporary_parent, ignore_errors=True)

    first_manifest = first.get("manifest", {})
    second_manifest = second.get("manifest", {})
    if classification != PASS:
        shutil.rmtree(root / "dist", ignore_errors=True)
        provenance_path.unlink(missing_ok=True)
        if provenance.get("status") == "NOT_RUN":
            provenance["status"] = "NOT_RUN_BUILD_FAILED" if classification == FAIL else "NOT_RUN_INTERNAL_ERROR"

    primary_failure: str | None = None
    if errors:
        primary_failure = errors[0]
    report = {
        "schema_version": "2.0.0",
        "classification": classification,
        "status": classification,
        "build_mode": BUILD_MODE,
        "source_inventory_mode": SOURCE_INVENTORY_MODE,
        "environment_policy": ENVIRONMENT_POLICY,
        "environment_keys": sorted(environment),
        "source_date_epoch": environment.get("SOURCE_DATE_EPOCH"),
        "reviewed_source_files": len(source_paths),
        "dependency_link_modes": dependency_modes,
        "build_steps": list(BUILD_STEPS),
        "step_timeout_seconds": args.step_timeout_seconds,
        "provenance_timeout_seconds": args.provenance_timeout_seconds,
        "files_compared": len(set(first_manifest) | set(second_manifest)),
        "first_build_root_sha256": first.get("manifest_root_sha256", sha256_text(canonical_json({}))),
        "second_build_root_sha256": second.get("manifest_root_sha256", sha256_text(canonical_json({}))),
        "source_mutations": changed_sources,
        "primary_failure": primary_failure,
        "first_build": compact_build(first),
        "second_build": compact_build(second),
        "provenance": provenance,
        "errors": sorted(set(errors)),
        "first_manifest": first_manifest,
        "second_manifest": second_manifest,
    }
    write_json(report_path, report)

    summary = {key: value for key, value in report.items() if key not in {"first_manifest", "second_manifest"}}
    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
