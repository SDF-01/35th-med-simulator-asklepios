#!/usr/bin/env python3
"""Run the complete standalone Facility Arrival contract with attributed logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

DEFAULT_OUTPUT = Path(".asklepios/facility-standalone/gate-report.json")
SUBGATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("deterministic-generator-check", ("python", "scripts/build_facility_arrival_standalone.py", "--repo", ".", "--check")),
    ("independent-artifact-check", ("python", "scripts/check_facility_arrival_standalone.py", "--repo", ".")),
    ("semantic-mutation-attacks", ("python", "scripts/test_facility_arrival_standalone_mutations.py", "--repo", ".")),
    ("node-runtime-contract", ("node", "scripts/test_facility_arrival_standalone_runtime.mjs", "--repo", ".")),
    ("minimal-dom-ui-contract", ("node", "scripts/test_facility_arrival_standalone_ui.mjs", "--repo", ".")),
)
REQUIRED_REPORTS = (
    Path("reports/facility-arrival-standalone.json"),
    Path("reports/facility-arrival-standalone-mutations.json"),
    Path("reports/facility-arrival-standalone-runtime.json"),
    Path("reports/facility-arrival-standalone-ui.json"),
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def report_path(path: Path, root: Path) -> str:
    """Return a stable repo-relative path when possible, otherwise an absolute path."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_command(parts: tuple[str, ...]) -> list[str]:
    if parts[0] == "python":
        return [os.environ.get("ASKLEPIOS_PYTHON", sys.executable), *parts[1:]]
    executable = shutil.which(parts[0])
    if executable is None:
        raise RuntimeError(f"required executable missing:{parts[0]}")
    return [executable, *parts[1:]]


def run_logged(command: list[str], *, root: Path, log_path: Path) -> tuple[int, list[str]]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    tail: list[str] = []
    environment = os.environ.copy()
    environment.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1", "TZ": "UTC"})
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
            tail.append(line.rstrip("\r\n"))
            if len(tail) > 80:
                del tail[:-80]
        status = int(process.wait())
    return status, tail


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    root = args.repo.resolve()
    output = args.json_output if args.json_output.is_absolute() else root / args.json_output
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    classification = PASS

    try:
        for index, (subgate, parts) in enumerate(SUBGATES, start=1):
            command = resolve_command(parts)
            log_path = output.parent / "logs" / f"{index:02d}-{subgate}.log"
            print(f"\n######## standalone subgate {index}/{len(SUBGATES)}: {subgate} ########", flush=True)
            status, tail = run_logged(command, root=root, log_path=log_path)
            result = {
                "subgate": subgate,
                "classification": PASS if status == 0 else FAIL,
                "exit_status": status,
                "command": list(parts),
                "execution_boundary": "RUNTIME_EXECUTABLE_RESOLUTION_EXCLUDED_FROM_CANONICAL_EVIDENCE",
                "log_path": report_path(log_path, root),
                "log_sha256": sha256_file(log_path),
                "log_bytes": log_path.stat().st_size,
                "log_tail": tail[-40:],
            }
            results.append(result)
            if status != 0:
                classification = FAIL
                errors.append(f"standalone subgate failed:{subgate}:exit={status}")
                break

        if classification == PASS:
            for relative in REQUIRED_REPORTS:
                path = root / relative
                if not path.is_file():
                    errors.append(f"standalone report missing:{relative.as_posix()}")
                    continue
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"standalone report invalid:{relative.as_posix()}:{type(exc).__name__}:{exc}")
                    continue
                if report.get("status") != PASS:
                    errors.append(f"standalone report is not PASS:{relative.as_posix()}:{report.get('status')}")
            if errors:
                classification = FAIL
    except Exception as exc:  # noqa: BLE001
        classification = INTERNAL_ERROR
        errors.append(f"{type(exc).__name__}:{exc}")

    report = {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "subgates": results,
        "failed_subgate": next((item["subgate"] for item in results if item["classification"] != PASS), None),
        "required_reports": [path.as_posix() for path in REQUIRED_REPORTS],
        "errors": sorted(set(errors)),
    }
    write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
