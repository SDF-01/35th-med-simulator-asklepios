#!/usr/bin/env python3
"""Adversarial tests for the canonical public artifact boundary."""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from release_result import finalize_adversarial_report


def load_checker(path: Path):
    spec = importlib.util.spec_from_file_location("facility_artifact_boundary", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("artifact-boundary checker could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def copy_fixture(source: Path, target: Path) -> None:
    for rel in [
        "examples/facility-arrival/interaction.json",
        "examples/facility-arrival/aar.json",
        "examples/facility-arrival/manifest.json",
        "public/data/facility_arrival/reference-session.json",
        "public/data/facility_arrival/reference-aar.json",
        "public/data/facility_arrival/reference-manifest.json",
    ]:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dst)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args()
    source = args.repo.resolve()
    checker = load_checker(source / "scripts/check_facility_arrival_artifact_boundary.py")
    results = []
    failures = []
    with tempfile.TemporaryDirectory(prefix="asklepios-artifact-boundary-") as temp:
        base = Path(temp) / "base"
        copy_fixture(source, base)
        cases = [
            "baseline",
            "legacy_session",
            "legacy_aar",
            "generic_manifest",
            "unexpected_public_file",
            "session_content_mismatch",
            "missing_canonical_file",
            "symlink_replacement",
            "transient_generation_report",
        ]
        for case_id in cases:
            target = Path(temp) / case_id
            shutil.copytree(base, target)
            if case_id == "legacy_session":
                shutil.copy2(target / "public/data/facility_arrival/reference-session.json", target / "public/data/facility_arrival/reference_session.json")
            elif case_id == "legacy_aar":
                shutil.copy2(target / "public/data/facility_arrival/reference-aar.json", target / "public/data/facility_arrival/reference_aar.json")
            elif case_id == "generic_manifest":
                shutil.copy2(target / "public/data/facility_arrival/reference-manifest.json", target / "public/data/facility_arrival/manifest.json")
            elif case_id == "unexpected_public_file":
                (target / "public/data/facility_arrival/unreviewed.json").write_text("{}\n", encoding="utf-8")
            elif case_id == "session_content_mismatch":
                path = target / "public/data/facility_arrival/reference-session.json"
                path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
            elif case_id == "missing_canonical_file":
                (target / "public/data/facility_arrival/reference-aar.json").unlink()
            elif case_id == "symlink_replacement":
                path = target / "public/data/facility_arrival/reference-manifest.json"
                path.unlink()
                path.symlink_to(target / "examples/facility-arrival/manifest.json")
            elif case_id == "transient_generation_report":
                path = target / "reports/facility-arrival-generation.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}\n", encoding="utf-8")
            report = checker.validate(target)
            expected_pass = case_id == "baseline"
            passed = (report["status"] == "PASS") == expected_pass
            if not passed:
                failures.append(case_id)
            results.append({
                "case_id": case_id,
                "pass": passed,
                "checker_status": report["status"],
                "errors": report["errors"][:8],
            })
    final = {
        "schema_version": "1.0.0",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "failures": failures,
        "results": results,
    }
    final = finalize_adversarial_report(final, baseline_case_ids=("baseline",))
    print(json.dumps(final, indent=2, sort_keys=True))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
