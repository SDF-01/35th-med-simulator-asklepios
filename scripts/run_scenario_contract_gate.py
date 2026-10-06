#!/usr/bin/env python3
"""Run the complete scenario-contract gate in an isolated committed worktree.

Why this exists
---------------
The canonical release graph runs many generators and adversarial suites before
it reaches the legacy scenario contract.  Running the scenario vocabulary scan
inside that shared mutable checkout allowed transient receipts, reports and
Python caches from earlier stages to become accidental inputs.  The old npm
chain also exposed only one exit code, so a failure did not identify which of
its six child commands failed.

This gate makes the boundary explicit:
* verify every scenario leaf command against one canonical contract;
* execute from a detached worktree overlaid with the exact release-locked source bytes;
* reuse only the already-installed dependency directory;
* run each child command serially with deterministic environment settings;
* capture a durable per-step log, hashes, tails, exit status and timing;
* verify the complete generated-output inventory;
* copy validated outputs back atomically only after all steps pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from release_graph_core import GRAPH_PATH, load_graph, native_command, verify_input_set

sys.dont_write_bytecode = True

PASS = "PASS"
FAIL = "FAIL"
INTERNAL_ERROR = "INTERNAL_ERROR"

CANONICAL_SCRIPTS: dict[str, str] = {
    "generate:scenario-blueprints": "tsx scripts/compileScenarioBlueprints.ts",
    "test:scenario-core": "node --import tsx --test --test-concurrency=1 src/tests/scenarioCore*.test.ts",
    "assure:scenario-core": "tsx scripts/runScenarioContractAssurance.ts",
    "assure:scenario-experience": "tsx scripts/runScenarioExperienceAssurance.ts",
    "test:scenario-experience": "tsx scripts/testScenarioExperienceMutations.ts",
    "generate:verified-scenario-package": "tsx scripts/generateVerifiedScenarioPackage.ts",
    "validate:scenario-contracts": "tsx scripts/validateScenarioContractRelease.ts",
    "check:scenario-vocabulary": "tsx scripts/checkRepositoryVocabulary.ts",
}

STEPS = tuple(CANONICAL_SCRIPTS)
EXPECTED_OUTPUTS = (
    "config/scenario-contracts/ASK-A-001.json",
    "public/data/scenario_core/blueprint_catalog.json",
    "public/data/scenario_core/verified_scenario.json",
    "public/data/scenario_core/verified_scenario_package.json",
    "reports/scenario-blueprint-catalog.json",
    "reports/scenario-contract-assurance.json",
    "reports/scenario-experience-assurance.json",
    "reports/scenario-behavior-archive.json",
    "reports/scenario-experience-mutations.json",
    "reports/scenario-contracts-rc2-validation.json",
    "reports/scenario-package-generation.json",
)
TRANSIENT_MARKERS = (
    "eagain",
    "emfile",
    "enfile",
    "enospc",
    "enomem",
    "err_worker_out_of_memory",
    "resource temporarily unavailable",
    "worker thread",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(rendered, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def report_path(path: Path, root: Path) -> str:
    """Return a stable repo-relative path when possible, otherwise an absolute path."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 900,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = run(["git", *args], cwd=root, env=os.environ.copy(), timeout=120)
    if check and completed.returncode != 0:
        diagnostic = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git {' '.join(args)} failed:{completed.returncode}:{diagnostic}")
    return completed


def link_dependencies(source: Path, destination: Path) -> str:
    if not source.is_dir() or source.is_symlink():
        raise RuntimeError(f"dependency directory missing or unsafe:{source}")
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"sandbox dependency path already exists:{destination}")
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/d", "/s", "/c", "mklink", "/J", str(destination), str(source)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode == 0 and destination.is_dir():
            return "WINDOWS_DIRECTORY_JUNCTION"
    else:
        try:
            destination.symlink_to(source, target_is_directory=True)
            return "POSIX_DIRECTORY_SYMLINK"
        except OSError:
            pass
    # Fail-closed portability fallback. Copying is slower, but it prevents the
    # scenario sandbox from depending on platform-specific symlink privileges.
    shutil.copytree(source, destination, symlinks=True)
    return "ISOLATED_DIRECTORY_COPY"


def detach_dependencies(destination: Path, mode: str | None) -> None:
    """Detach the sandbox dependency mount without touching the shared source.

    ``git worktree remove --force`` is not trusted to distinguish a directory
    symlink or Windows junction from its target. The mount is therefore removed
    explicitly before Git is allowed to delete the worktree.
    """
    if not os.path.lexists(destination):
        return
    if destination.is_symlink() or mode == "POSIX_DIRECTORY_SYMLINK":
        destination.unlink()
        return
    if mode == "WINDOWS_DIRECTORY_JUNCTION":
        os.rmdir(destination)
        return
    if mode == "ISOLATED_DIRECTORY_COPY":
        shutil.rmtree(destination)
        return
    raise RuntimeError(f"unknown dependency detach mode:{mode}:{destination}")


def script_contract_errors(root: Path) -> list[str]:
    try:
        package = json.loads((root / "package.json").read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"package.json unavailable:{type(exc).__name__}:{exc}"]
    scripts = package.get("scripts")
    if not isinstance(scripts, dict):
        return ["package scripts object missing"]
    errors: list[str] = []
    for name, expected in CANONICAL_SCRIPTS.items():
        observed = scripts.get(name)
        if observed != expected:
            errors.append(f"scenario script differs:{name}:expected={expected!r}:observed={observed!r}")
    return errors


def output_inventory(root: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    inventory: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for relative in EXPECTED_OUTPUTS:
        path = root / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"scenario output missing or unsafe:{relative}")
            continue
        inventory[relative] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return dict(sorted(inventory.items())), errors


def copy_outputs(source: Path, destination: Path) -> None:
    for relative in EXPECTED_OUTPUTS:
        source_path = source / relative
        target_path = destination / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = target_path.with_name(f".{target_path.name}.tmp-{os.getpid()}")
        shutil.copyfile(source_path, temporary)
        os.replace(temporary, target_path)


def locked_overlay_paths(root: Path, graph_path: Path) -> tuple[dict[str, Any], list[str]]:
    graph = load_graph(root, graph_path)
    stage = next((item for item in graph["stages"] if item.get("id") == "scenario.contracts"), None)
    if not isinstance(stage, dict):
        raise RuntimeError("scenario.contracts stage missing from release graph")
    errors: list[str] = []
    paths: set[str] = set()
    for set_id in stage.get("input_sets", []):
        specification = graph["input_sets"][set_id]
        errors.extend(verify_input_set(root, set_id, specification))
        paths.update(str(item) for item in specification.get("files", {}))
    if errors:
        raise RuntimeError(f"scenario release locks differ:{sorted(set(errors))}")
    return graph, sorted(paths)


def overlay_locked_inputs(root: Path, sandbox: Path, relative_paths: list[str]) -> None:
    for relative in relative_paths:
        source = root / relative
        target = sandbox / relative
        if source.is_symlink() or not source.is_file():
            raise RuntimeError(f"locked scenario input missing or unsafe:{relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.overlay-{os.getpid()}")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)


def npm_invocation(executable: str, script_name: str) -> list[str]:
    candidate = Path(executable)
    if candidate.suffix.lower() == ".py":
        command = [sys.executable, str(candidate), "run", script_name]
    else:
        command = [executable, "run", script_name]
    return native_command(command)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/scenario-contract-gate.json"))
    parser.add_argument("--graph", type=Path, default=GRAPH_PATH)
    parser.add_argument("--npm-executable", default=("npm.cmd" if os.name == "nt" else "npm"))
    parser.add_argument("--mode", choices=("write", "check"), default="write")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--keep-sandbox", action="store_true")
    args = parser.parse_args()

    root = args.repo.resolve()
    output_path = args.json_output if args.json_output.is_absolute() else root / args.json_output
    graph_path = args.graph if args.graph.is_absolute() else root / args.graph
    errors = script_contract_errors(root)
    report: dict[str, Any] = {
        "schema_version": "1.1.0",
        "classification": FAIL if errors else PASS,
        "mode": args.mode,
        "isolation": "DETACHED_GIT_WORKTREE_WITH_LOCKED_OVERLAY_V2",
        "canonical_scripts": CANONICAL_SCRIPTS,
        "steps": [],
        "outputs": {},
        "errors": errors,
    }
    if errors:
        write_json(output_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3

    sandbox_parent = Path(tempfile.mkdtemp(prefix="asklepios-scenario-contract-"))
    sandbox = sandbox_parent / "repo"
    worktree_added = False
    log_root = root / ".asklepios" / "scenario-contract-logs"
    log_root.mkdir(parents=True, exist_ok=True)
    try:
        _graph, overlay_paths = locked_overlay_paths(root, graph_path)
        report["locked_overlay_files"] = len(overlay_paths)
        top = Path(git(root, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if top != root:
            raise RuntimeError(f"repository root differs from Git top level:{top}")
        status = git(root, "status", "--porcelain=v1", "--untracked-files=all").stdout.splitlines()
        # The parent release graph is intentionally allowed to be dirty here: its
        # earlier generators and checkpoint receipts are exactly the contamination
        # this detached-worktree boundary excludes.  Source integrity is enforced
        # by the graph input locks before this stage executes.
        report["shared_workspace_status"] = status
        report["shared_workspace_dirty_count"] = len(status)
        head = git(root, "rev-parse", "HEAD").stdout.strip()
        tree = git(root, "rev-parse", "HEAD^{tree}").stdout.strip()
        report["source_commit"] = head
        report["source_tree"] = tree
        added = git(root, "worktree", "add", "--detach", "--force", str(sandbox), head, check=False)
        if added.returncode != 0:
            raise RuntimeError(f"git worktree add failed:{added.returncode}:{(added.stderr or added.stdout).strip()}")
        worktree_added = True
        overlay_locked_inputs(root, sandbox, overlay_paths)
        dependency_mode = link_dependencies(root / "node_modules", sandbox / "node_modules")
        report["dependency_mode"] = dependency_mode

        env = os.environ.copy()
        env.update({
            "CI": "1",
            "TZ": "UTC",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TERM": env.get("TERM") or "dumb",
            "NO_COLOR": "1",
            "FORCE_COLOR": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "npm_config_audit": "false",
            "npm_config_fund": "false",
            "npm_config_update_notifier": "false",
        })
        transient_retry_used = False
        for index, script_name in enumerate(STEPS, start=1):
            canonical_command = ["npm", "run", script_name]
            command = npm_invocation(args.npm_executable, script_name)
            started = time.monotonic()
            completed = run(command, cwd=sandbox, env=env, timeout=args.timeout_seconds)
            combined = f"{completed.stdout}\n{completed.stderr}".lower()
            transient = completed.returncode != 0 and any(marker in combined for marker in TRANSIENT_MARKERS)
            attempts = 1
            if transient:
                transient_retry_used = True
                attempts = 2
                completed = run(command, cwd=sandbox, env=env, timeout=args.timeout_seconds)
            duration_ms = round((time.monotonic() - started) * 1000)
            stdout = completed.stdout or ""
            stderr = completed.stderr or ""
            log_path = log_root / f"{index:02d}-{script_name.replace(':', '-')}.log"
            log_path.write_text(
                stdout + ("\n--- STDERR ---\n" if stderr else "") + stderr,
                encoding="utf-8",
                newline="\n",
            )
            step = {
                "id": script_name,
                "script": CANONICAL_SCRIPTS[script_name],
                "canonical_command": canonical_command,
                "execution_command": command,
                "attempts": attempts,
                "duration_ms": duration_ms,
                "exit_status": completed.returncode,
                "classification": PASS if completed.returncode == 0 else FAIL,
                "stdout_sha256": sha256_bytes(stdout.encode("utf-8")),
                "stderr_sha256": sha256_bytes(stderr.encode("utf-8")),
                "stdout_tail": stdout.splitlines()[-80:],
                "stderr_tail": stderr.splitlines()[-80:],
                "log_path": report_path(log_path, root),
            }
            report["steps"].append(step)
            print(json.dumps({
                "scenario_contract_step": script_name,
                "classification": step["classification"],
                "exit_status": completed.returncode,
            }, sort_keys=True), flush=True)
            if completed.returncode != 0:
                report["classification"] = FAIL
                report["first_invalid_step"] = script_name
                report["errors"].append(f"scenario contract step failed:{script_name}:exit={completed.returncode}")
                report["transient_retry_used"] = transient_retry_used
                write_json(output_path, report)
                print(json.dumps(report, indent=2, sort_keys=True))
                return 3

        inventory, output_errors = output_inventory(sandbox)
        report["outputs"] = inventory
        report["errors"].extend(output_errors)
        report["transient_retry_used"] = transient_retry_used
        if output_errors:
            report["classification"] = FAIL
            write_json(output_path, report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 3

        if args.mode == "check":
            current_inventory, current_errors = output_inventory(root)
            report["errors"].extend(current_errors)
            for relative, expected in inventory.items():
                if current_inventory.get(relative) != expected:
                    report["errors"].append(f"committed scenario output differs:{relative}")
        else:
            copy_outputs(sandbox, root)

        if report["errors"]:
            report["classification"] = FAIL
            write_json(output_path, report)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 3
        report["classification"] = PASS
        write_json(output_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except subprocess.TimeoutExpired as exc:
        report["classification"] = FAIL
        report["errors"].append(f"scenario contract command timed out:{exc.cmd}")
        write_json(output_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 3
    except Exception as exc:  # noqa: BLE001
        report["classification"] = INTERNAL_ERROR
        report["errors"].append(f"{type(exc).__name__}:{exc}")
        write_json(output_path, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 4
    finally:
        try:
            detach_dependencies(sandbox / "node_modules", dependency_mode)
        except Exception as exc:  # noqa: BLE001 - cleanup must not erase the primary result
            report.setdefault("cleanup_errors", []).append(f"dependency detach failed:{type(exc).__name__}:{exc}")
            write_json(output_path, report)
        if worktree_added:
            git(root, "worktree", "remove", "--force", str(sandbox), check=False)
            git(root, "worktree", "prune", check=False)
        if not args.keep_sandbox:
            shutil.rmtree(sandbox_parent, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
