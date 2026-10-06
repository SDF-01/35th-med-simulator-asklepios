#!/usr/bin/env python3
"""Run the exact Lean trust-boundary audit and emit compatible evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from check_facility_decision_axioms import validate as validate_decision_axioms
from release_graph_core import canonical_json, sha256_file, sha256_text, utc_now, write_json
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

OUTPUT = Path("reports/facility-decision-axiom-check.json")
LOG = Path("reports/facility-decision-axiom-audit.log")
AUDITS = [
    Path("formal/AxiomAudit.lean"),
    Path("formal/FacilityArrivalAxiomAudit.lean"),
    Path("formal/FacilityDecisionIntegrityAxiomAudit.lean"),
]
DECISION_AUDIT = Path("formal/FacilityDecisionIntegrityAxiomAudit.lean")
STATIC_ATTACKS = [
    ["python", "scripts/test_facility_arrival_formal_static.py"],
    ["python", "scripts/test_facility_arrival_axiom_checker.py"],
    ["python", "scripts/test_facility_decision_formal_static.py"],
    ["python", "scripts/test_facility_decision_axiom_checker.py"],
]


def _run(command: list[str], root: Path, environment: dict[str, str]) -> dict[str, Any]:
    if command[0] == "python":
        command = [os.environ.get("ASKLEPIOS_PYTHON", shutil.which("python3") or shutil.which("python") or "python3"), *command[1:]]
    completed = subprocess.run(command, cwd=root, env=environment, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=OUTPUT)
    parser.add_argument("--log-output", type=Path, default=LOG)
    args = parser.parse_args()
    root = args.repo.resolve()
    started = utc_now()
    errors: list[str] = []
    results: list[dict[str, Any]] = []
    classification = PASS
    decision_log_text = ""

    try:
        required_sources = [Path("lean-toolchain"), Path("lakefile.lean"), Path("lake-manifest.json"), *AUDITS]
        for required in required_sources:
            path = root / required
            if not path.is_file() or path.is_symlink():
                errors.append(f"formal source missing or unsafe:{required.as_posix()}")
        lake = shutil.which("lake")
        if lake is None:
            errors.append("Lean lake executable missing")
        environment = os.environ.copy()
        environment.update({"TZ": "UTC", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"})

        if not errors:
            for command in STATIC_ATTACKS:
                result = _run(command, root, environment)
                result["kind"] = "static-adversarial-contract"
                results.append(result)
                if result["returncode"] != 0:
                    errors.append(f"formal static attack suite failed:{' '.join(command)}")

            formal_commands: list[tuple[list[str], str, Path | None]] = [
                ([lake or "lake", "build"], "lean-complete-build", None),
                ([lake or "lake", "env", "leanchecker", "--fresh", "ScenarioContracts"], "lean-fresh-environment-check", None),
            ]
            formal_commands.extend(
                ([lake or "lake", "env", "lean", audit.as_posix()], "lean-exact-audit", audit)
                for audit in AUDITS
            )
            for command, kind, audit in formal_commands:
                result = _run(command, root, environment)
                result["kind"] = kind
                result["audit"] = None if audit is None else audit.as_posix()
                results.append(result)
                if audit == DECISION_AUDIT:
                    decision_log_text = f"{result['stdout']}{result['stderr']}"
                if result["returncode"] != 0:
                    errors.append(f"formal command failed:{' '.join(command)}")
    except Exception as exc:  # noqa: BLE001
        classification = INTERNAL_ERROR
        errors.append(f"{type(exc).__name__}:{exc}")

    log_path = root / args.log_output
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(decision_log_text, encoding="utf-8", newline="\n")

    # Keep the live report schema consumed by the independent release validator.
    try:
        manifest = json.loads((root / "formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json").read_text(encoding="utf-8"))
        axiom_report = validate_decision_axioms(decision_log_text, manifest)
        errors.extend(axiom_report.get("errors", []))
    except Exception as exc:  # noqa: BLE001
        axiom_report = {
            "schema_version": "1.0.0",
            "status": "FAIL",
            "policy": "independently encoded exact zero-axiom budget",
            "theorems_expected": 17,
            "theorems_observed": 0,
            "per_theorem_axioms": {},
            "errors": [f"axiom checker internal error:{type(exc).__name__}:{exc}"],
        }
        errors.extend(axiom_report["errors"])
        classification = INTERNAL_ERROR

    if classification != INTERNAL_ERROR:
        classification = PASS if not errors else FAIL

    source_inventory = {
        path.as_posix(): {"sha256": sha256_file(root / path), "bytes": (root / path).stat().st_size}
        for path in [Path("lean-toolchain"), Path("lakefile.lean"), Path("lake-manifest.json"), *AUDITS]
        if (root / path).is_file()
    }
    command_evidence = [
        {
            "kind": result["kind"],
            "audit": result.get("audit"),
            "command": result["command"],
            "returncode": result["returncode"],
            "stdout_sha256": hashlib.sha256(str(result.get("stdout", "")).encode()).hexdigest(),
            "stderr_sha256": hashlib.sha256(str(result.get("stderr", "")).encode()).hexdigest(),
        }
        for result in results
    ]
    report = dict(axiom_report)
    report.update({
        "classification": classification,
        "status": classification,
        "started_at": started,
        "completed_at": utc_now(),
        "formal_source_inventory": source_inventory,
        "formal_source_root_sha256": sha256_text(canonical_json(source_inventory)),
        "commands": command_evidence,
        "log_sha256": sha256_file(log_path),
        "axiom_audit_count": len(AUDITS),
        "patient_care_authority_granted": False,
        "operational_timing_calibrated": False,
        "errors": sorted(set(errors)),
    })
    write_json(root / args.json_output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(classification)


if __name__ == "__main__":
    raise SystemExit(main())
