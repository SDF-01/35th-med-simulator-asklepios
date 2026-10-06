#!/usr/bin/env python3
"""Canonical RC3.8A.1 offline-scenario release writer and Python verifier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from offline_scenario_release_common import (
    compare_generated_release,
    load_release_context,
    validate_descriptor,
    validate_documentation_semantics,
    write_generated_release,
)
from scenario_genome_common import GenomeError, atomic_write_json, safe_repo_path

# The policy owns output locations; this literal is only the no-policy failure fallback.
FALLBACK_REPORT = "reports/offline-scenario-release.json"


def build_report(repo: Path, *, check: bool) -> dict[str, object]:
    context = load_release_context(repo)
    if check:
        descriptor, mismatches = compare_generated_release(repo, context)
    else:
        descriptor = write_generated_release(repo, context)
        mismatches = []
    errors = validate_descriptor(repo, context, descriptor)
    errors.extend(validate_documentation_semantics(repo, context))
    errors.extend(f"offline scenario release differs:{path}" for path in mismatches)
    classification = "PASS" if not errors else "FAIL"
    return {
        "schema_version": "1.2.0",
        "classification": classification,
        "status": classification,
        "mode": "check" if check else "write",
        "release_id": descriptor.get("release_id"),
        "release_sha256": descriptor.get("release_sha256"),
        "engine_evolution": descriptor.get("engine_evolution"),
        "genome_id": (descriptor.get("scenario_genome") or {}).get("genome_id") if isinstance(descriptor.get("scenario_genome"), dict) else None,
        "graph_id": (descriptor.get("release_graph") or {}).get("graph_id") if isinstance(descriptor.get("release_graph"), dict) else None,
        "capability_ratchet_epoch": (descriptor.get("capability_ratchet") or {}).get("ratchet_epoch") if isinstance(descriptor.get("capability_ratchet"), dict) else None,
        "technical_debt_ratchet_epoch": (descriptor.get("technical_debt_ratchet") or {}).get("ratchet_epoch") if isinstance(descriptor.get("technical_debt_ratchet"), dict) else None,
        "artifacts": len(descriptor.get("artifacts", [])) if isinstance(descriptor.get("artifacts"), list) else 0,
        "mismatches": sorted(set(mismatches)),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json-output")
    args = parser.parse_args()
    repo = args.repo.resolve()
    try:
        report = build_report(repo, check=args.check)
    except GenomeError as exc:
        report = {
            "schema_version": "1.2.0",
            "classification": "FAIL",
            "status": "FAIL",
            "mode": "check" if args.check else "write",
            "errors": [f"GenomeError:{exc}"],
        }
    except Exception as exc:  # noqa: BLE001 - convert checker defects into durable evidence
        report = {
            "schema_version": "1.2.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "mode": "check" if args.check else "write",
            "errors": [f"{type(exc).__name__}:{exc}"],
        }

    # Generation always emits its governed report. Check mode uses only the requested
    # report path, so adversarial fixtures cannot overwrite the generation evidence.
    try:
        if args.json_output:
            output_path = safe_repo_path(repo, args.json_output)
            atomic_write_json(output_path, report)
        elif not args.check:
            try:
                context = load_release_context(repo)
                output_path = safe_repo_path(repo, context["policy"]["report_path"])
            except GenomeError:
                output_path = safe_repo_path(repo, FALLBACK_REPORT)
            atomic_write_json(output_path, report)
    except Exception as exc:  # noqa: BLE001
        report = {
            "schema_version": "1.2.0",
            "classification": "INTERNAL_ERROR",
            "status": "INTERNAL_ERROR",
            "mode": "check" if args.check else "write",
            "errors": [f"report write failed:{type(exc).__name__}:{exc}"],
        }

    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report["classification"] == "PASS":
        return 0
    if report["classification"] == "INTERNAL_ERROR":
        return 4
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
