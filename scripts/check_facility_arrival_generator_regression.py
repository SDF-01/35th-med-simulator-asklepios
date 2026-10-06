#!/usr/bin/env python3
"""Reject Facility Arrival generator drift before expensive release stages.

The Python implementation is the only artifact writer.  The TypeScript
implementation is an independently encoded, read-only differential checker.
This gate validates that role separation, durable parity evidence, canonical
public paths, and truth-boundary wording remain intact.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def load_object(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("top-level JSON value is not an object")
        return value
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{label} unavailable:{type(exc).__name__}:{exc}")
        return {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--output", default="reports/facility-arrival-generator-regression.json")
    args = parser.parse_args()
    root = args.repo.resolve()
    source = root / "scripts/generateFacilityArrivalArtifacts.ts"
    canonical_source = root / "scripts/build_facility_arrival_example.py"
    errors: list[str] = []

    try:
        text = source.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        text = ""
        errors.append(f"TypeScript parity source unavailable:{type(exc).__name__}:{exc}")
    try:
        canonical_text = canonical_source.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        canonical_text = ""
        errors.append(f"Python canonical source unavailable:{type(exc).__name__}:{exc}")

    offline_notice = (
        "[Open the self-contained offline Facility Arrival scenario](playable.html). "
        "It runs locally in a modern browser with no server or network request."
    )
    required_fragments = [
        r"\`NOT_CALIBRATED\` exercise-design values",
        "# Facility-arrival canonical interactive scenario",
        offline_notice,
        "const check = process.argv.includes('--check');",
        "if (!check)",
        "TypeScript Facility Arrival generation is verification-only",
        "generator_role: 'INDEPENDENT_TYPESCRIPT_CHECKER'",
        "canonical_writer: 'PYTHON_BUILD_FACILITY_ARRIVAL_EXAMPLE'",
        "./engine_evolution_documentation_common.mjs",
        "renderEvolutionBlock(evolutionContext",
        "graphContractSha256(evolutionContext.graph)",
        "classification: mismatches.length === 0 ? 'PASS' : 'FAIL'",
        "mode: 'check'",
        "--json-output",
        "outputRelative.startsWith('reports/')",
        "if (mismatches.length > 0) process.exitCode = 1;",
        "## Complete simulated learner interaction",
        "## Evidence and calibration boundary",
        "## Open validity obligations",
        "resolve(publicBase, 'reference-session.json')",
        "resolve(publicBase, 'reference-aar.json')",
        "resolve(publicBase, 'reference-manifest.json')",
    ]
    for fragment in required_fragments:
        if fragment not in text:
            errors.append(f"reviewed TypeScript parity fragment missing:{fragment}")
    if offline_notice not in canonical_text:
        errors.append("Python canonical generator omits offline standalone route")

    # The TS implementation may write only its repository-local parity report.
    # It must never write the canonical example or public artifacts.
    forbidden_write_fragments = [
        "function graphContractProjection",
        "function graphContractSha256",
        "function renderEvolutionBlock",
        "writeFileSync(path, content",
        "writeFileSync(resolve(base",
        "writeFileSync(resolve(publicBase",
        "mkdirSync(base",
        "mkdirSync(publicBase",
    ]
    for fragment in forbidden_write_fragments:
        if fragment in text:
            errors.append(f"TypeScript parity checker retains artifact write capability:{fragment}")
    if "writeFileSync(outputPath" not in text:
        errors.append("TypeScript parity report is not durably written")

    # Prevent the historical template-literal syntax regression.
    if re.search(r"(?<!\\)`NOT_CALIBRATED(?<!\\)`", text):
        errors.append("unescaped NOT_CALIBRATED Markdown backticks in TypeScript template literal")

    forbidden_output_fragments = [
        "resolve(publicBase, 'reference_session.json')",
        "resolve(publicBase, 'reference_aar.json')",
        "resolve(publicBase, 'manifest.json')",
        "reports/facility-arrival-generation.json",
    ]
    for fragment in forbidden_output_fragments:
        if fragment in text:
            errors.append(f"noncanonical generated artifact path:{fragment}")

    package = load_object(root / "package.json", errors, "package manifest")
    graph = load_object(root / "config/release/RELEASE_GRAPH.json", errors, "release graph")
    scripts = package.get("scripts") if isinstance(package.get("scripts"), dict) else {}
    managed = graph.get("managed_package_scripts") if isinstance(graph.get("managed_package_scripts"), dict) else {}
    required_scripts = (
        "check:facility-arrival-generator-parity",
        "generate:facility-arrival",
        "check:facility-arrival-source-attestations",
    )
    for name in required_scripts:
        if name not in managed:
            errors.append(f"release graph omits managed generator script:{name}")
        elif scripts.get(name) != managed.get(name):
            errors.append(f"package script differs from canonical release graph:{name}")

    parity = str(managed.get("check:facility-arrival-generator-parity", ""))
    generation = str(managed.get("generate:facility-arrival", ""))
    attestations = str(managed.get("check:facility-arrival-source-attestations", ""))
    if "generateFacilityArrivalArtifacts.ts --check" not in parity:
        errors.append("independent TypeScript parity command is not check-only")
    if "--json-output reports/facility-arrival-generator-parity.json" not in parity:
        errors.append("independent TypeScript parity evidence is not durable")
    if "build_facility_arrival_example.py --repo ." not in generation:
        errors.append("canonical generation does not use the Python writer")
    if "npm run check:facility-arrival-generator-parity" not in generation:
        errors.append("canonical generation omits independent parity verification")
    if "build_facility_arrival_example.py --repo . --check" not in attestations:
        errors.append("source attestations omit canonical Python verification")
    if "npm run check:facility-arrival-generator-parity" not in attestations:
        errors.append("source attestations omit independent TypeScript parity")

    for script_name, command in scripts.items():
        if isinstance(command, str) and "generateFacilityArrivalArtifacts.ts" in command:
            if script_name != "check:facility-arrival-generator-parity" or "--check" not in command:
                errors.append(f"TypeScript parity implementation invoked outside check-only role:{script_name}")

    forbidden_claims = [
        "empirically calibrated timing",
        "patient-care use is permitted",
        "automatic clinical rule generation: enabled",
    ]
    lower = text.casefold()
    for phrase in forbidden_claims:
        if phrase.casefold() in lower:
            errors.append(f"forbidden generator claim:{phrase}")

    checks = (
        len(required_fragments)
        + 1
        + len(forbidden_write_fragments)
        + 1
        + 1
        + len(forbidden_output_fragments)
        + len(required_scripts)
        + 6
        + len(forbidden_claims)
    )
    report = {
        "schema_version": "1.1.0",
        "classification": "PASS" if not errors else "FAIL",
        "status": "PASS" if not errors else "FAIL",
        "source": source.relative_to(root).as_posix() if source.is_relative_to(root) else str(source),
        "canonical_writer": canonical_source.relative_to(root).as_posix(),
        "checks": checks,
        "regression": "rc3.3.5-ci-portability-and-canonical-artifact-boundary",
        "generator_role_boundary": "rc3.6a.8.2-canonical-writer-independent-checker",
        "errors": sorted(set(errors)),
    }
    output = root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 3


if __name__ == "__main__":
    raise SystemExit(main())
