#!/usr/bin/env python3
"""Run the source-bound content-registry runtime contract with attributed logs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

DEFAULT_OUTPUT = Path(".asklepios/content-registry/runtime-report.json")
SUBGATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("registry-audit", ("python", "scripts/audit_content_registry.py")),
    ("registry-semantic-attacks", ("python", "scripts/test_content_registry_mutations.py")),
    ("extension-import-transactions", ("python", "scripts/test_content_imports.py")),
    ("formal-static-attacks", ("python", "scripts/test_content_registry_formal_static.py")),
    ("axiom-checker-attacks", ("python", "scripts/test_content_registry_axiom_checker.py")),
    ("extension-ledger-audit", ("python", "scripts/audit_content_extensions.py")),
    ("independent-node-registry-check", ("node", "scripts/check_content_registry.mjs")),
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


def python_syntax_audit(root: Path) -> dict[str, Any]:
    failures: list[str] = []
    checked = 0
    for path in sorted((root / "scripts").glob("*.py")):
        checked += 1
        try:
            compile(path.read_text(encoding="utf-8"), path.as_posix(), "exec")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{path.relative_to(root).as_posix()}:{type(exc).__name__}:{exc}")
    return {"checked": checked, "errors": failures}


def resolve_command(parts: tuple[str, ...]) -> list[str]:
    if parts[0] == "python":
        return [os.environ.get("ASKLEPIOS_PYTHON", sys.executable), *parts[1:]]
    executable = shutil.which(parts[0])
    if executable is None:
        raise RuntimeError(f"required executable missing:{parts[0]}")
    return [executable, *parts[1:]]


def run_logged(command: list[str], *, root: Path, log_path: Path) -> tuple[int, list[str], float]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
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
    return status, tail, time.monotonic() - started


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

    syntax = python_syntax_audit(root)
    results.append({
        "subgate": "python-source-syntax",
        "classification": PASS if not syntax["errors"] else FAIL,
        "checked": syntax["checked"],
        "errors": syntax["errors"],
    })
    if syntax["errors"]:
        classification = FAIL
        errors.extend(syntax["errors"])

    try:
        if classification == PASS:
            for index, (subgate, parts) in enumerate(SUBGATES, start=1):
                command = resolve_command(parts)
                log_path = output.parent / "logs" / f"{index:02d}-{subgate}.log"
                print(f"\n######## content-registry subgate {index}/{len(SUBGATES)}: {subgate} ########", flush=True)
                status, tail, duration = run_logged(command, root=root, log_path=log_path)
                result = {
                    "subgate": subgate,
                    "classification": PASS if status == 0 else FAIL,
                    "exit_status": status,
                    "command": command,
                    "duration_seconds": round(duration, 3),
                    "log_path": report_path(log_path, root),
                    "log_sha256": sha256_file(log_path),
                    "log_bytes": log_path.stat().st_size,
                    "log_tail": tail[-40:],
                }
                results.append(result)
                if status != 0:
                    classification = FAIL
                    errors.append(f"content-registry subgate failed:{subgate}:exit={status}")
                    break
    except Exception as exc:  # noqa: BLE001
        classification = INTERNAL_ERROR
        errors.append(f"{type(exc).__name__}:{exc}")

    report = {
        "schema_version": "1.0.0",
        "classification": classification,
        "status": classification,
        "subgates": results,
        "failed_subgate": next((item["subgate"] for item in results if item["classification"] != PASS), None),
        "errors": sorted(set(errors)),
    }
    write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True), flush=True)
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
