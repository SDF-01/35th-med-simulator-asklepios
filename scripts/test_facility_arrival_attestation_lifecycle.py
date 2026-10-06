#!/usr/bin/env python3
"""Adversarial tests for Facility Arrival verification-attestation lifecycle.

These tests distinguish generation from verification, require immutable check
attestations across repeated write-mode builds, and challenge stale or forged
attestations against the final release validator. A validator crash never counts
as a successful rejection.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any
from release_result import finalize_adversarial_report

SPEC_REPORT = Path("reports/facility-arrival-spec-compiler.json")
BINDING_REPORT = Path("reports/facility-arrival-bindings.json")
EXAMPLE_REPORT = Path("reports/facility-arrival-example-check.json")
OUTPUT = Path("reports/facility-arrival-attestation-lifecycle.json")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_canonical_utf8_lf(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        return ""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return ""
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()


def run(command: list[str], cwd: Path, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if completed.returncode != expect:
        raise RuntimeError(
            f"command status differs:{completed.returncode}!={expect}:"
            f"{' '.join(command)}\nSTDOUT:\n{completed.stdout[-3000:]}\nSTDERR:\n{completed.stderr[-3000:]}"
        )
    return completed


def verify_attestation(root: Path, report_path: Path, kind: str) -> list[str]:
    errors: list[str] = []
    try:
        report = json.loads((root / report_path).read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return [f"report unavailable:{report_path}:{exc}"]
    if report.get("status") != "PASS" or report.get("mode") != "check":
        errors.append(f"report not PASS/check:{report_path}")
    if report.get("attestation_kind") != "verification":
        errors.append(f"report not verification-scoped:{report_path}")
    claimed = report.get("attestation_sha256")
    payload = dict(report)
    payload.pop("attestation_sha256", None)
    observed = hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()
    if claimed != observed:
        errors.append(f"attestation digest mismatch:{report_path}")
    if kind == "spec":
        pairs = [
            (report.get("source"), report.get("source_file_sha256"), "spec source"),
            (report.get("target"), report.get("target_file_sha256"), "spec target"),
        ]
        if report.get("target_file_sha256") != report.get("expected_target_sha256"):
            errors.append("spec target differs from expected projection")
    elif kind == "binding":
        pairs = [
            (report.get("registry_path"), report.get("registry_file_sha256"), "registry", "raw_bytes_v1"),
            (report.get("scenario_source_path"), report.get("scenario_source_sha256"), "scenario source", str(report.get("scenario_source_hash_mode"))),
            (report.get("target_path"), report.get("target_file_sha256"), "binding TypeScript", "raw_bytes_v1"),
            (report.get("binding_json_path"), report.get("binding_json_file_sha256"), "binding JSON", "raw_bytes_v1"),
        ]
    elif kind == "example":
        hashes = report.get("file_sha256") if isinstance(report.get("file_sha256"), dict) else {}
        if report.get("files") != 10 or len(hashes) != 10:
            errors.append("example attestation file inventory differs")
        pairs = [(relative, expected, f"example:{relative}", "raw_bytes_v1") for relative, expected in sorted(hashes.items())]
    else:
        errors.append(f"unknown attestation kind:{kind}")
        pairs = []
    for item in pairs:
        if len(item) == 3:
            relative, expected, label = item
            mode = "raw_bytes_v1"
        else:
            relative, expected, label, mode = item
        if not isinstance(relative, str) or not isinstance(expected, str):
            errors.append(f"attested path/hash missing:{label}")
            continue
        path = root / relative
        observed = sha256_canonical_utf8_lf(path) if mode == "canonical_utf8_lf_v1" and path.is_file() else sha256_file(path) if path.is_file() else None
        if observed != expected:
            errors.append(f"current file hash differs:{label}")
    return errors


def validator_errors(root: Path) -> tuple[int, list[str], bool]:
    # Test-only fixtures isolate the attestation under challenge. They are
    # written only inside disposable temporary copies and never enter release
    # evidence or the committed repository.
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "facility-arrival-attestation-lifecycle.json").write_text(
        json.dumps({
            "schema_version": "1.0.0",
            "status": "PASS",
            "cases": 9,
            "failures": [],
            "properties": {
                "generation_cannot_overwrite_verification": True,
                "stale_inputs_rejected": True,
                "forged_digest_rejected": True,
                "validator_crashes_never_count_as_rejections": True,
            },
            "test_fixture_only": True,
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (reports / "facility-arrival-runtime-resolution.json").write_text(
        json.dumps({
            "schema_version": "1.0.0",
            "status": "PASS",
            "runtime": "tsx",
            "tsconfig": "tsconfig.app.json",
            "source_scenario_id": "ASK-D-001",
            "local_checks": "PASS",
            "independent_checks": "PASS",
            "errors": [],
            "test_fixture_only": True,
        }, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    output = root / "reports/attestation-lifecycle-validator-probe.json"
    completed = subprocess.run(
        [sys.executable, "scripts/validate_facility_arrival_release.py", "--repo", ".", "--runtime-only", "--output", str(output.relative_to(root))],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if not output.is_file():
        return completed.returncode, ["validator probe report missing"], False
    try:
        report = json.loads(output.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return completed.returncode, [f"validator probe malformed:{exc}"], False
    errors = report.get("errors") if isinstance(report.get("errors"), list) else []
    healthy = completed.returncode in {0, 3} and report.get("status") in {"PASS", "FAIL"}
    return completed.returncode, [str(item) for item in errors], healthy


def copy_repo(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns(".git", ".lake", "dist", "node_modules", "__pycache__", "*.pyc", "*.pyo"),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", default=str(OUTPUT))
    args = parser.parse_args()
    source = args.repo.resolve()
    results: list[dict[str, Any]] = []
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="asklepios-attestation-lifecycle-") as tmp:
        baseline = Path(tmp) / "baseline"
        copy_repo(source, baseline)
        run([sys.executable, "scripts/compile_facility_arrival_spec.py", "--repo", ".", "--check"], baseline)
        run([sys.executable, "scripts/build_facility_arrival_bindings.py", "--repo", ".", "--check"], baseline)
        run([sys.executable, "scripts/build_facility_arrival_example.py", "--repo", ".", "--check"], baseline)
        baseline_errors = (
            verify_attestation(baseline, SPEC_REPORT, "spec")
            + verify_attestation(baseline, BINDING_REPORT, "binding")
            + verify_attestation(baseline, EXAMPLE_REPORT, "example")
        )
        baseline_pass = not baseline_errors
        results.append({"case_id": "baseline_verified_attestations", "pass": baseline_pass, "errors": baseline_errors})
        if not baseline_pass:
            failures.append("baseline_verified_attestations")

        spec_before = (baseline / SPEC_REPORT).read_bytes()
        binding_before = (baseline / BINDING_REPORT).read_bytes()
        example_before = (baseline / EXAMPLE_REPORT).read_bytes()
        for _ in range(3):
            run([sys.executable, "scripts/compile_facility_arrival_spec.py", "--repo", "."], baseline)
            run([sys.executable, "scripts/build_facility_arrival_bindings.py", "--repo", "."], baseline)
            run([sys.executable, "scripts/build_facility_arrival_example.py", "--repo", "."], baseline)
        preserved = (
            (baseline / SPEC_REPORT).read_bytes() == spec_before
            and (baseline / BINDING_REPORT).read_bytes() == binding_before
            and (baseline / EXAMPLE_REPORT).read_bytes() == example_before
        )
        results.append({"case_id": "write_mode_cannot_overwrite_verification", "pass": preserved, "errors": [] if preserved else ["write mode changed a verification report"]})
        if not preserved:
            failures.append("write_mode_cannot_overwrite_verification")

        mutations = [
            ("stale_spec_source_rejected", "config/facility-arrival/ASK-D-001.json", "\n", {"spec compiler source attestation is stale"}),
            ("stale_generated_spec_rejected", "src/facility-arrival/specification.generated.ts", "\n// stale\n", {"spec compiler target attestation is stale"}),
            ("stale_scenario_source_rejected", "src/content/scenarios.ts", "\n// stale\n", {"scenario-source binding attestation is stale"}),
            ("stale_registry_rejected", "public/data/content_registry/content_registry.json", "\n", {"content-registry binding attestation is stale"}),
        ]
        for case_id, relative, suffix, expected_errors in mutations:
            target = Path(tmp) / case_id
            copy_repo(baseline, target)
            path = target / relative
            path.write_text(path.read_text(encoding="utf-8") + suffix, encoding="utf-8")
            code, errors, healthy = validator_errors(target)
            passed = healthy and code == 3 and set(errors) == expected_errors
            results.append({"case_id": case_id, "pass": passed, "validator_healthy": healthy, "returncode": code, "errors": errors[:12]})
            if not passed:
                failures.append(case_id)

        forged = Path(tmp) / "forged_attestation_digest_rejected"
        copy_repo(baseline, forged)
        report_path = forged / SPEC_REPORT
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report["source_file_sha256"] = "0" * 64
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        code, errors, healthy = validator_errors(forged)
        passed = healthy and code == 3 and set(errors) == {
            "spec compiler attestation digest invalid",
            "spec compiler source attestation is stale",
        }
        results.append({"case_id": "forged_attestation_digest_rejected", "pass": passed, "validator_healthy": healthy, "returncode": code, "errors": errors[:12]})
        if not passed:
            failures.append("forged_attestation_digest_rejected")

        forged_example = Path(tmp) / "forged_example_attestation_rejected"
        copy_repo(baseline, forged_example)
        report_path = forged_example / EXAMPLE_REPORT
        report_value = json.loads(report_path.read_text(encoding="utf-8"))
        report_value["file_sha256"]["examples/facility-arrival/README.md"] = "0" * 64
        report_path.write_text(json.dumps(report_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        example_errors = verify_attestation(forged_example, EXAMPLE_REPORT, "example")
        passed = "attestation digest mismatch:reports/facility-arrival-example-check.json" in example_errors and any(item.startswith("current file hash differs:example:") for item in example_errors)
        results.append({"case_id": "forged_example_attestation_rejected", "pass": passed, "errors": example_errors})
        if not passed:
            failures.append("forged_example_attestation_rejected")

    report = {
        "schema_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "failures": failures,
        "properties": {
            "generation_cannot_overwrite_verification": any(item["case_id"] == "write_mode_cannot_overwrite_verification" and item["pass"] for item in results),
            "stale_inputs_rejected": all(item["pass"] for item in results if item["case_id"].startswith("stale_")),
            "forged_digest_rejected": any(item["case_id"] == "forged_attestation_digest_rejected" and item["pass"] for item in results),
            "example_attestation_forgery_rejected": any(item["case_id"] == "forged_example_attestation_rejected" and item["pass"] for item in results),
            "validator_crashes_never_count_as_rejections": all(item.get("validator_healthy", True) for item in results),
        },
        "results": results,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=("baseline_verified_attestations", "write_mode_cannot_overwrite_verification"))
    output = source / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
