#!/usr/bin/env python3
"""Dependency-free static release boundary for Facility Decision Integrity.

The checker validates domain constraints locally and delegates orchestration
identity to the canonical release graph.  It intentionally does not duplicate
CI command sequences or infer clinical authority from successful software tests.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from check_release_graph import validate as validate_release_graph
from release_graph_core import GRAPH_PATH, load_graph, stage_map, target_stage_ids
from release_result import FAIL, PASS, exit_code

REPORT = Path("reports/facility-decision-release-static.json")
EXPECTED_ROUTES = {
    "/examples/facility-decision": "FacilityDecisionIntegrityPage",
    "/examples/facility-decision/learner": "FacilityDecisionLearnerPage",
    "/examples/facility-decision/teaching": "FacilityDecisionTeachingPage",
    "/examples/facility-decision/instructor": "FacilityDecisionInstructorPage",
    "/examples/facility-decision/demo": "FacilityDecisionDemoPage",
}
EXPECTED_CORE_FILES = [
    "src/facility-decision/types.ts",
    "src/facility-decision/contracts.generated.ts",
    "src/facility-decision/fixtures.ts",
    "src/facility-decision/runtime.ts",
    "src/facility-decision/index.ts",
    "src/facility-decision-checker/verify.ts",
]
REQUIRED_SOURCE_STAGES = [
    "decision.contracts-check",
    "decision.integrity",
    "decision.semantic-attacks",
    "decision.sequence-assurance",
    "decision.state-exploration",
    "decision.role-boundaries",
    "decision.role-boundary-attacks",
    "decision.accessibility",
    "decision.accessibility-attacks",
    "decision.validity-boundaries",
    "decision.validity-boundary-attacks",
    "decision.scientific-admission",
    "decision.scientific-admission-attacks",
    "decision.evidence-promotion",
    "decision.evidence-promotion-attacks",
    "decision.formal-static-attacks",
    "decision.axiom-checker-attacks",
    "decision.static-validator",
    "decision.static-attacks",
    "decision.release-validator-attacks",
    "decision.source-preflight",
]
REQUIRED_RUNTIME_STAGES = [
    "decision.typecheck",
    "decision.runtime-tests",
    "decision.artifact-generation-check",
    "decision.differential",
    "decision.artifacts-python",
    "decision.artifacts-node",
    "decision.artifact-attacks",
    "release.runtime-evidence-join",
]


def _load_json(root: Path, relative: str, errors: list[str]) -> dict[str, Any]:
    path = root / relative
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid JSON:{relative}:{type(exc).__name__}:{exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"JSON root is not an object:{relative}")
        return {}
    return value


def validate(repo: Path) -> dict[str, Any]:
    root = repo.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    required = [
        "package.json",
        "config/release/RELEASE_GRAPH.json",
        "config/facility-decision/ASK-D-001.json",
        "config/facility-decision/VALIDITY_BOUNDARIES.json",
        "config/facility-decision/EVIDENCE_PROMOTION_REGISTRY.json",
        "src/App.tsx",
        "src/pages/FacilityDecisionIntegrityPage.tsx",
        "src/pages/FacilityDecisionSessionPage.tsx",
        "src/facility-decision/runtime.ts",
        "src/facility-decision-checker/verify.ts",
        "src/tests/facilityDecisionIntegrity.test.ts",
        "scripts/generateFacilityDecisionArtifacts.ts",
        "scripts/test_facility_decision_artifact_mutations.py",
        "scripts/build_facility_decision_provenance.py",
        "scripts/validate_facility_decision_release.py",
        "docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md",
        "formal/ScenarioContracts.lean",
        "formal/ScenarioContracts/FacilityDecisionIntegrity.lean",
        "formal/FacilityDecisionIntegrityAxiomAudit.lean",
        "formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json",
        "tsconfig.facility-decision-core.json",
        ".github/workflows/facility-decision-integrity-ci.yml",
    ]
    for relative in required:
        path = root / relative
        require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0, f"missing or unsafe:{relative}")
    if errors:
        return {
            "schema_version": "1.1.0",
            "classification": FAIL,
            "status": FAIL,
            "checks": checks,
            "errors": sorted(set(errors)),
        }

    graph_report = validate_release_graph(root, GRAPH_PATH)
    require(graph_report.get("classification") == PASS, "canonical release graph consistency failed")
    try:
        graph = load_graph(root, GRAPH_PATH)
        stages = stage_map(graph)
        source_plan = target_stage_ids(graph, "facility-decision-source")
        runtime_plan = target_stage_ids(graph, "canonical-runtime")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"canonical release graph unavailable:{type(exc).__name__}:{exc}")
        graph = {"managed_package_scripts": {}, "truth_boundaries": {}}
        stages = {}
        source_plan = []
        runtime_plan = []

    truth = graph.get("truth_boundaries", {})
    require(truth.get("patient_care_use") == "PROHIBITED", "graph patient-care boundary changed")
    require(truth.get("operational_timing") == "NOT_CALIBRATED", "graph operational timing was promoted")
    require(truth.get("concrete_treatments_admitted") == 0, "graph concrete treatment admission changed")
    require(truth.get("production_ready") is False, "graph production-ready flag was promoted")
    require(graph.get("production_designation") == "NOT_GRANTED", "graph production designation changed")

    for stage_id in REQUIRED_SOURCE_STAGES:
        require(stage_id in source_plan, f"decision source assurance omits stage:{stage_id}")
    for stage_id in REQUIRED_RUNTIME_STAGES:
        require(stage_id in runtime_plan, f"decision runtime assurance omits stage:{stage_id}")
    source_positions = [source_plan.index(item) for item in REQUIRED_SOURCE_STAGES if item in source_plan]
    runtime_positions = [runtime_plan.index(item) for item in REQUIRED_RUNTIME_STAGES if item in runtime_plan]
    require(source_positions == sorted(source_positions), "decision source stage order differs")
    require(runtime_positions == sorted(runtime_positions), "decision runtime stage order differs")
    require(stages.get("decision.static-attacks", {}).get("needs") == ["decision.static-validator"], "decision static attacks bypass validator")
    require(stages.get("decision.typecheck", {}).get("needs") == ["decision.source-preflight"], "decision runtime bypasses source preflight")
    require(stages.get("release.runtime-evidence-join", {}).get("needs") == ["decision.artifact-attacks"], "runtime evidence join is detached")

    package = _load_json(root, "package.json", errors)
    scripts = package.get("scripts", {}) if isinstance(package, dict) else {}
    require(isinstance(scripts, dict), "package scripts missing")
    managed = graph.get("managed_package_scripts", {})
    for name in [
        "check:facility-decision-contracts",
        "check:facility-decision-integrity",
        "test:facility-decision-mutations",
        "check:facility-decision-release-static",
        "test:facility-decision-release-static",
        "preflight:facility-decision-release",
        "typecheck:facility-decision-core",
        "test:facility-decision-runtime",
        "check:facility-decision-artifacts-generation",
        "check:facility-decision-differential",
        "test:facility-decision-artifact-mutations",
        "verify:facility-decision-source",
        "verify:facility-decision-runtime",
        "verify:facility-decision",
        "finalize:facility-decision-release",
    ]:
        require(name in scripts, f"package script missing:{name}")
        if name in managed:
            require(scripts.get(name) == managed.get(name), f"package script differs:{name}")
    require(scripts.get("verify:facility-decision") == "npm run release:graph -- --target canonical-runtime", "combined verification graph target differs")
    require(scripts.get("finalize:facility-decision-release") == "npm run release:graph -- --target publisher-full", "release finalizer graph target differs")
    require("generate:facility-decision" not in str(scripts.get("build", "")), "production build mutates decision artifacts")

    profile = _load_json(root, "config/facility-decision/ASK-D-001.json", errors)
    validity = _load_json(root, "config/facility-decision/VALIDITY_BOUNDARIES.json", errors)
    authority = profile.get("authority", {}) if isinstance(profile, dict) else {}
    require(authority.get("patient_care_use") == "PROHIBITED", "decision profile patient-care boundary changed")
    require(authority.get("concrete_treatment_activation") is False, "decision profile concrete treatment activation changed")
    calibration_records = profile.get("operational_model", {}).get("world_events", []) if isinstance(profile, dict) else []
    second = next((item for item in calibration_records if isinstance(item, dict) and item.get("event_id") == "second_casualty_inbound"), None)
    require(second is not None, "calibration record missing:second_casualty_inbound")
    if isinstance(second, dict):
        require(second.get("at_elapsed_seconds") == 240, f"decision calibration time changed:second_casualty_inbound:{second.get('at_elapsed_seconds')}")
        require(second.get("calibration_status") == "NOT_CALIBRATED", f"decision calibration status changed:second_casualty_inbound:{second.get('calibration_status')}")
        note = str(second.get("note", "")).casefold()
        require("exercise-design" in note and "independent" in note, "decision exercise-assumption note missing:second_casualty_inbound")
    require(validity.get("patient_care_use") == "PROHIBITED", "validity patient-care boundary changed")
    required_domains = {
        "operational_calibration",
        "treatment_legitimacy",
        "human_team_behavior",
        "patient_dynamics",
        "claim_entailment",
        "causal_aar",
        "executable_formal_refinement",
        "accessibility",
        "production_operations",
    }
    require(set(validity.get("domains", {})) == required_domains, "validity domain inventory differs")

    app = (root / "src/App.tsx").read_text(encoding="utf-8")
    for route, component in EXPECTED_ROUTES.items():
        pattern = rf'<Route\s+path="{re.escape(route)}"\s+element=\{{<{component}\s*/>\}}\s*/>'
        require(len(re.findall(pattern, app)) == 1, f"route missing or duplicated:{route}:{component}")
    session_page = (root / "src/pages/FacilityDecisionSessionPage.tsx").read_text(encoding="utf-8")
    overview_page = (root / "src/pages/FacilityDecisionIntegrityPage.tsx").read_text(encoding="utf-8")
    require("useSearchParams" not in session_page, "role selectable from query string")
    require(".high_risk" not in session_page, "decision UI reads restricted high-risk field")
    require(
        "action.requires_deliberate_confirmation" in session_page
        and "selectedAction.requires_deliberate_confirmation" in session_page,
        "decision UI deliberate-confirmation projection missing",
    )
    decision_types = (root / "src/facility-decision/types.ts").read_text(encoding="utf-8")
    decision_runtime = (root / "src/facility-decision/runtime.ts").read_text(encoding="utf-8")
    decision_tests = (root / "src/tests/facilityDecisionIntegrity.test.ts").read_text(encoding="utf-8")
    require("completed_decision_count: number" in decision_types, "learner-safe progress field missing")
    require("decision_timeline: Array<Pick<FacilityDecisionRecord" in decision_types, "instructor-safe timeline field missing")
    require("completed_decision_count: session.completed_decision_ids.length" in decision_runtime, "learner-safe progress projection missing")
    require("decision_timeline: session.decision_records.map" in decision_runtime, "instructor-safe timeline projection missing")
    require("const completedCount = view.completed_decision_count" in session_page, "decision UI bypasses learner-safe progress projection")
    require("const instructorTimeline = view.instructor?.decision_timeline ?? []" in session_page, "decision UI omits instructor-safe timeline projection")
    require("session.decision_records" not in session_page, "decision UI reads raw decision records")
    require("learner progress uses the role-safe projection" in decision_tests, "learner-safe progress regression test missing")
    require("instructor timeline is projected deliberately" in decision_tests, "instructor-safe timeline regression test missing")
    require(re.search(r"\bset(?:Mode|Role)\s*\(", overview_page, re.I) is None, "overview contains client role switcher")

    readme = (root / "README.md").read_text(encoding="utf-8")
    start = "<!-- asklepios-facility-decision:start -->"
    end = "<!-- asklepios-facility-decision:end -->"
    require(readme.count(start) == 1 and readme.count(end) == 1, "README decision block markers differ")
    block = ""
    if start in readme and end in readme and readme.index(start) < readme.index(end):
        block = readme[readme.index(start): readme.index(end) + len(end)]
    for route in EXPECTED_ROUTES:
        require(route in block, f"README decision route missing:{route}")
    require("direct patient care and clinical decision support remain prohibited" in block.casefold(), "README patient-care boundary missing")
    require("healthcare simulation and training use is permitted within the validated release scope" in block.casefold() and "simulated patient-care workflows are permitted within the validated simulation scope" in block.casefold(), "README intended-use disclaimer missing")
    require("NOT_CALIBRATED" in block, "README calibration boundary missing")

    formal_root = (root / "formal/ScenarioContracts.lean").read_text(encoding="utf-8").splitlines()
    required_import = "import ScenarioContracts.FacilityDecisionIntegrity"
    require(formal_root.count(required_import) == 1, "formal decision import count differs")
    if required_import in formal_root:
        first_non_import = next((index for index, line in enumerate(formal_root) if line.strip() and not line.startswith("import ")), len(formal_root))
        require(formal_root.index(required_import) < first_non_import, "formal decision import not in import block")

    artifact_attack_source = (root / "scripts/test_facility_decision_artifact_mutations.py").read_text(encoding="utf-8")
    for marker in (
        'FIXTURE_POLICY = "MANIFEST_DECLARED_CLOSED_REGULAR_FILE_INVENTORY_V1"',
        'CHECKER_RESULT_TRANSPORT = "UNIQUE_REPORT_FILES_NOT_STDOUT_V1"',
        "checker_stdout_noise_tolerated",
        "ambient_artifact_directory_rejected",
        "payload = read_report(report_path)",
    ):
        require(marker in artifact_attack_source, f"artifact mutation harness hardening missing:{marker}")
    require("BASE.glob(" not in artifact_attack_source, "artifact mutation harness uses ambient glob discovery")
    require("json.loads(completed.stdout)" not in artifact_attack_source, "artifact mutation harness trusts stdout verdicts")

    generator = (root / "scripts/generateFacilityDecisionArtifacts.ts").read_text(encoding="utf-8")
    provenance = (root / "scripts/build_facility_decision_provenance.py").read_text(encoding="utf-8")
    validator = (root / "scripts/validate_facility_decision_release.py").read_text(encoding="utf-8")
    accessibility = (root / "docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md").read_text(encoding="utf-8")
    require("checkMode" in generator and "if (checkMode)" in generator, "artifact write/check separation missing")
    require("CLOSED_REGULAR_FILE_INVENTORY_V1" in generator and "readdirSync(outputDir)" in generator, "artifact generator closed inventory missing")
    require("ATOMIC_RENAME_NO_SYMLINK_V1" in generator and "renameSync(temporary, path)" in generator, "artifact generator atomic write policy missing")
    require("status.isSymbolicLink() || !status.isFile()" in generator, "artifact generator symlink guard missing")
    require("'signature_status': 'UNSIGNED'" in provenance, "provenance signature state changed")
    require("'claim_scope': 'BUILD_IDENTITY_ONLY'" in provenance, "provenance claim scope changed")
    require("choices=['source-preflight','release']" in validator, "release validator mode separation missing")
    require("'READY_FOR_LIVE_GATES'" in validator, "source preflight truth state missing")
    require("MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED" in accessibility, "manual accessibility requirement missing")
    require("must not claim WCAG 2.2 AA conformance" in accessibility, "unsupported WCAG claim boundary missing")

    core = _load_json(root, "tsconfig.facility-decision-core.json", errors)
    require(core.get("extends") == "./tsconfig.app.json", "core tsconfig base differs")
    require(core.get("files") == EXPECTED_CORE_FILES, "core tsconfig file inventory differs")
    require(core.get("include") == [], "core tsconfig inherits broad include")
    require(core.get("exclude") == [], "core tsconfig exclude differs")
    options = core.get("compilerOptions", {})
    require(options.get("types") == [], "core tsconfig ambient type inventory is not closed")
    require(options.get("noEmit") is True, "core tsconfig noEmit differs")

    classification = PASS if not errors else FAIL
    return {
        "schema_version": "1.1.0",
        "classification": classification,
        "status": classification,
        "checks": checks,
        "graph_checks": graph_report.get("checks", 0),
        "source_stages": len(source_plan),
        "runtime_stages": len(runtime_plan),
        "production_designation": graph.get("production_designation"),
        "errors": sorted(set(errors)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=REPORT)
    args = parser.parse_args()
    root = args.repo.resolve()
    report = validate(root)
    output = root / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
