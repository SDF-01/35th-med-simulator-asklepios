#!/usr/bin/env python3
"""Adversarially verify Facility Decision artifacts with two independent checkers.

The harness is intentionally hermetic:
- the fixture inventory is explicit rather than discovered from the caller CWD;
- the source baseline must pass both checkers before mutations are attempted;
- checker classification comes from their durable JSON reports, not noisy stdout;
- every checker is time-bounded and returns actionable diagnostics on harness faults.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from release_result import finalize_adversarial_report

BASE = Path("examples/facility-decision")
FIXTURE_POLICY = "MANIFEST_DECLARED_CLOSED_REGULAR_FILE_INVENTORY_V1"
CHECKER_RESULT_TRANSPORT = "UNIQUE_REPORT_FILES_NOT_STDOUT_V1"
ARTIFACT_FILES = (
    "README.md",
    "alternate-session.json",
    "demo-projection.json",
    "instructor-projection.json",
    "learner-projection.json",
    "manifest.json",
    "reference-session.json",
    "teaching-projection.json",
)
SUPPORT_FILES = (
    Path("config/facility-decision/ASK-D-001.json"),
    Path("scripts/check_facility_decision_artifacts.py"),
    Path("scripts/check_facility_decision_artifacts.mjs"),
)
CHECK_TIMEOUT_SECONDS = 90
Mutation = Callable[[Path], None]


@dataclass(frozen=True)
class CheckerResult:
    classification: str
    returncode: int | None
    payload: dict[str, Any] | None
    stdout_tail: list[str]
    stderr_tail: list[str]
    error: str | None = None


def canonical(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, (int, float)):
        return json.dumps(value, separators=(",", ":"))
    if isinstance(value, list):
        return "[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(json.dumps(key) + ":" + canonical(value[key]) for key in sorted(value)) + "}"
    raise TypeError(f"unsupported canonical value:{type(value).__name__}")


def sha_obj(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object:{path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8", newline="\n")


def tail(value: str, limit: int = 40) -> list[str]:
    return value.splitlines()[-limit:]


def expected_fixture_paths() -> tuple[Path, ...]:
    return tuple(BASE / name for name in ARTIFACT_FILES) + SUPPORT_FILES


def validate_source_fixture(source: Path) -> list[str]:
    errors: list[str] = []
    for relative in expected_fixture_paths():
        path = source / relative
        if not path.exists():
            errors.append(f"fixture path missing:{relative.as_posix()}")
        elif path.is_symlink():
            errors.append(f"fixture path is symlink:{relative.as_posix()}")
        elif not path.is_file():
            errors.append(f"fixture path is not a regular file:{relative.as_posix()}")

    artifact_root = source / BASE
    if artifact_root.is_dir():
        observed = sorted(path.name for path in artifact_root.iterdir())
        expected = sorted(ARTIFACT_FILES)
        if observed != expected:
            missing = sorted(set(expected) - set(observed))
            unexpected = sorted(set(observed) - set(expected))
            if missing:
                errors.append(f"fixture artifact inventory missing:{missing}")
            if unexpected:
                errors.append(f"fixture artifact inventory unexpected:{unexpected}")
    return errors


def copy_fixture(source: Path, destination: Path) -> None:
    errors = validate_source_fixture(source)
    if errors:
        raise ValueError("; ".join(errors))
    for relative in expected_fixture_paths():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, target)


def read_report(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def run_checker(repo: Path, command: list[str], report_relative: Path) -> CheckerResult:
    report_path = repo / report_relative
    report_path.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "LANG": "C.UTF-8",
    })
    try:
        completed = subprocess.run(
            command,
            cwd=repo,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return CheckerResult(
            classification="INTERNAL_ERROR",
            returncode=None,
            payload=None,
            stdout_tail=tail(exc.stdout or ""),
            stderr_tail=tail(exc.stderr or ""),
            error=f"checker timeout after {CHECK_TIMEOUT_SECONDS}s",
        )
    except OSError as exc:
        return CheckerResult(
            classification="INTERNAL_ERROR",
            returncode=None,
            payload=None,
            stdout_tail=[],
            stderr_tail=[],
            error=f"checker launch failed:{type(exc).__name__}:{exc}",
        )

    payload = read_report(report_path)
    status = payload.get("status") if isinstance(payload, dict) else None
    if completed.returncode == 0 and status == "PASS":
        classification = "PASS"
        error = None
    elif completed.returncode != 0 and status == "FAIL":
        classification = "REJECTED"
        error = None
    else:
        classification = "INTERNAL_ERROR"
        error = (
            f"checker/result disagreement:returncode={completed.returncode}:"
            f"report_status={status!r}:report_present={report_path.is_file()}"
        )
    return CheckerResult(
        classification=classification,
        returncode=int(completed.returncode),
        payload=payload,
        stdout_tail=tail(completed.stdout),
        stderr_tail=tail(completed.stderr),
        error=error,
    )


def run_both(repo: Path, report_prefix: str) -> tuple[CheckerResult, CheckerResult]:
    python_report = Path("reports") / f"{report_prefix}-python.json"
    node_report = Path("reports") / f"{report_prefix}-node.json"
    python_result = run_checker(
        repo,
        [sys.executable, "scripts/check_facility_decision_artifacts.py", "--repo", ".", "--json-output", python_report.as_posix()],
        python_report,
    )
    node_result = run_checker(
        repo,
        ["node", "scripts/check_facility_decision_artifacts.mjs", "--repo", ".", "--output", node_report.as_posix()],
        node_report,
    )
    return python_result, node_result


def checker_errors(result: CheckerResult) -> list[str]:
    if isinstance(result.payload, dict):
        errors = result.payload.get("errors", [])
        if isinstance(errors, list):
            return [str(value) for value in errors]
    return []


def checker_diagnostics(result: CheckerResult) -> dict[str, Any]:
    return {
        "classification": result.classification,
        "returncode": result.returncode,
        "error": result.error,
        "stdout_tail": result.stdout_tail,
        "stderr_tail": result.stderr_tail,
    }


def rebind(repo: Path) -> None:
    manifest_path = repo / BASE / "manifest.json"
    manifest = load(manifest_path)
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("manifest files inventory missing")
    for name in list(files):
        path = repo / BASE / str(name)
        content = path.read_bytes()
        files[name] = {"bytes": len(content), "sha256": sha_bytes(content)}
    body = dict(manifest)
    body.pop("manifest_binding_sha256", None)
    manifest["manifest_binding_sha256"] = sha_obj(body)
    write(manifest_path, manifest)


def mutate_json(repo: Path, name: str, operation: Callable[[dict[str, Any]], None]) -> None:
    path = repo / BASE / name
    value = load(path)
    operation(value)
    write(path, value)
    rebind(repo)


def mutate_manifest(repo: Path, operation: Callable[[dict[str, Any]], None]) -> None:
    path = repo / BASE / "manifest.json"
    manifest = load(path)
    operation(manifest)
    body = dict(manifest)
    body.pop("manifest_binding_sha256", None)
    manifest["manifest_binding_sha256"] = sha_obj(body)
    write(path, manifest)


def mutate_manifest_raw(repo: Path) -> None:
    path = repo / BASE / "manifest.json"
    manifest = load(path)
    manifest["files"]["learner-projection.json"]["sha256"] = "f" * 64
    body = dict(manifest)
    body.pop("manifest_binding_sha256", None)
    manifest["manifest_binding_sha256"] = sha_obj(body)
    write(path, manifest)


def mutate_readme(repo: Path) -> None:
    path = repo / BASE / "README.md"
    text = path.read_text(encoding="utf-8")
    marker = "/examples/facility-decision/learner"
    if marker not in text:
        raise ValueError("README learner route marker missing")
    path.write_text(text.replace(marker, "/removed/learner", 1), encoding="utf-8", newline="\n")
    rebind(repo)



def inject_checker_stdout_noise(repo: Path) -> None:
    """Prove verdicts come from unique durable reports, never stdout JSON."""
    python_path = repo / "scripts/check_facility_decision_artifacts.py"
    python_source = python_path.read_text(encoding="utf-8")
    future = "from __future__ import annotations\n"
    if future not in python_source:
        raise ValueError("Python checker future-import marker missing")
    python_path.write_text(
        python_source.replace(future, future + 'print("deliberate checker stdout noise")\n', 1),
        encoding="utf-8", newline="\n",
    )
    node_path = repo / "scripts/check_facility_decision_artifacts.mjs"
    node_path.write_text(
        'console.log("deliberate checker stdout noise");\n' + node_path.read_text(encoding="utf-8"),
        encoding="utf-8", newline="\n",
    )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json-output", default="reports/facility-decision-artifact-mutations.json")
    args = parser.parse_args()
    source = Path(args.repo).resolve()
    output = source / args.json_output
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    fixture_errors = validate_source_fixture(source)
    if fixture_errors:
        report = {
            "schema_version": "1.2.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "cases": 0,
            "attacks": 0,
            "results": [],
            "errors": fixture_errors,
        }
        write(output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    with tempfile.TemporaryDirectory(prefix="asklepios-decision-artifact-baseline-") as temporary:
        baseline_repo = Path(temporary) / "repo"
        copy_fixture(source, baseline_repo)
        baseline_python, baseline_node = run_both(baseline_repo, "baseline-preflight")
    if baseline_python.classification != "PASS" or baseline_node.classification != "PASS":
        report = {
            "schema_version": "1.2.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "cases": 0,
            "attacks": 0,
            "baseline_preflight": {
                "python": checker_diagnostics(baseline_python),
                "node": checker_diagnostics(baseline_node),
                "python_errors": checker_errors(baseline_python),
                "node_errors": checker_errors(baseline_node),
            },
            "results": [],
            "errors": ["source baseline did not pass both independent artifact checkers"],
        }
        write(output, report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 2

    cases: list[tuple[str, Mutation | None, bool]] = [
        ("baseline", None, True),
        ("checker_stdout_noise_tolerated", inject_checker_stdout_noise, True),
        ("learner_score_leak_rehashed", lambda repo: mutate_json(repo, "learner-projection.json", lambda value: value.__setitem__("normalized_source_score_bps", 10000)), False),
        ("learner_provenance_leak_rehashed", lambda repo: mutate_json(repo, "learner-projection.json", lambda value: value.__setitem__("source_binding", {})), False),
        ("patient_care_escalation_rehashed", lambda repo: mutate_manifest(repo, lambda manifest: manifest["authority"].__setitem__("patient_care_use", "GRANTED")), False),
        ("concrete_treatment_escalation_rehashed", lambda repo: mutate_manifest(repo, lambda manifest: manifest["authority"].__setitem__("concrete_treatment_activation", True)), False),
        ("collapsed_sequences_rehashed", lambda repo: mutate_manifest(repo, lambda manifest: manifest.__setitem__("alternate_sequence", copy.deepcopy(manifest["canonical_sequence"]))), False),
        ("canonical_root_forgery_rehashed", lambda repo: mutate_manifest(repo, lambda manifest: manifest.__setitem__("canonical_decision_root_sha256", "0" * 64)), False),
        ("reference_session_score_forgery_rehashed", lambda repo: mutate_json(repo, "reference-session.json", lambda value: value["facility_session"].__setitem__("normalized_score_bps", 9999)), False),
        ("reference_session_chain_forgery_rehashed", lambda repo: mutate_json(repo, "reference-session.json", lambda value: value.__setitem__("decision_chain_root_sha256", "a" * 64)), False),
        ("readme_route_removed_rehashed", mutate_readme, False),
        ("instructor_demo_escalation_rehashed", lambda repo: mutate_json(repo, "instructor-projection.json", lambda value: value.__setitem__("demo", {"autoplay_available": True})), False),
        ("demo_privilege_removed_rehashed", lambda repo: mutate_json(repo, "demo-projection.json", lambda value: value.pop("instructor", None)), False),
        ("manifest_file_hash_forgery", mutate_manifest_raw, False),
    ]

    with tempfile.TemporaryDirectory(prefix="asklepios-decision-artifact-inventory-") as temporary:
        ambient_repo = Path(temporary) / "repo"
        copy_fixture(source, ambient_repo)
        (ambient_repo / BASE / "unexpected-artifact-directory").mkdir()
        ambient_errors = validate_source_fixture(ambient_repo)
    ambient_rejected = any("fixture artifact inventory unexpected" in error for error in ambient_errors)
    results.append({
        "case_id": "ambient_artifact_directory_rejected",
        "classification": "EXPECTED_REJECTION" if ambient_rejected else "FAIL",
        "status": "EXPECTED_REJECTION" if ambient_rejected else "FAIL",
        "expected_pass": False,
        "pass": ambient_rejected,
        "errors": [] if ambient_rejected else ["ambient artifact directory was accepted"],
        "observed_errors": ambient_errors,
    })

    for case_id, mutation, expected_pass in cases:
        with tempfile.TemporaryDirectory(prefix="asklepios-decision-artifact-") as temporary:
            repo = Path(temporary) / "repo"
            copy_fixture(source, repo)
            try:
                if mutation is not None:
                    mutation(repo)
                python_result, node_result = run_both(repo, case_id)
            except Exception as exc:  # noqa: BLE001 - harness faults must be explicit evidence
                python_result = CheckerResult("INTERNAL_ERROR", None, None, [], [], f"mutation harness fault:{type(exc).__name__}:{exc}")
                node_result = CheckerResult("INTERNAL_ERROR", None, None, [], [], f"mutation harness fault:{type(exc).__name__}:{exc}")

        if expected_pass:
            passed = python_result.classification == "PASS" and node_result.classification == "PASS"
        else:
            passed = python_result.classification == "REJECTED" and node_result.classification == "REJECTED"
        if not passed:
            errors.append(
                f"{case_id}:expected_pass={expected_pass}:"
                f"python={python_result.classification}:node={node_result.classification}"
            )
        results.append({
            "case_id": case_id,
            "expected_pass": expected_pass,
            "python_classification": python_result.classification,
            "node_classification": node_result.classification,
            "pass": passed,
            "python_errors": checker_errors(python_result),
            "node_errors": checker_errors(node_result),
            "python_diagnostics": checker_diagnostics(python_result) if python_result.classification == "INTERNAL_ERROR" else None,
            "node_diagnostics": checker_diagnostics(node_result) if node_result.classification == "INTERNAL_ERROR" else None,
        })

    report: dict[str, Any] = {
        "schema_version": "1.2.0",
        "status": "PASS" if not errors else "FAIL",
        "cases": len(results),
        "attacks": sum(1 for result in results if result.get("expected_pass") is False),
        "globally_rehashed_attacks": 10,
        "fixture_inventory_mode": FIXTURE_POLICY,
        "checker_result_mode": CHECKER_RESULT_TRANSPORT,
        "checker_timeout_seconds": CHECK_TIMEOUT_SECONDS,
        "independent_rejection_policy": "EVERY_ATTACK_REJECTED_BY_BOTH_CHECKERS",
        "accepted_forgery_count": sum(
            1 for result in results
            if result.get("expected_pass") is False
            and result.get("python_classification") == "PASS"
            and result.get("node_classification") == "PASS"
        ),
        "single_checker_only_rejections": sum(
            1 for result in results
            if result.get("expected_pass") is False
            and {result.get("python_classification"), result.get("node_classification")} == {"PASS", "REJECTED"}
        ),
        "baseline_preflight": {
            "python": baseline_python.classification,
            "node": baseline_node.classification,
        },
        "results": results,
        "errors": errors,
    }
    report = finalize_adversarial_report(
        report, baseline_case_ids=("baseline", "checker_stdout_noise_tolerated")
    )
    write(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
