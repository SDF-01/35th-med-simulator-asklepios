#!/usr/bin/env python3
"""Source-contract assurance for a facilitator-led healthcare simulation experience."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from release_graph_core import read_json, write_json
from release_policy_common import load_release_json, unique_nonempty_strings
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

PROFILE = "config/release/SIMULATION_QUALITY_PROFILE.json"
OUTPUT = Path("reports/simulation-quality-assurance.json")


def validate(root: Path) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    try:
        profile = load_release_json(root, PROFILE, errors)
        if profile is None:
            raise ValueError("simulation quality profile missing")
        require(profile.get("schema_version") == "1.0.0", "simulation quality schema differs")
        require(profile.get("scope") == "reviewed_healthcare_simulation_scenarios", "simulation quality scope differs")
        domains = profile.get("required_domains", {})
        expected_domains = {
            "outcomes_and_objectives",
            "prebriefing",
            "facilitation",
            "scenario_design",
            "learner_experience",
            "debriefing",
            "evaluation",
            "operations",
        }
        require(set(domains) == expected_domains, "simulation quality domain inventory differs")
        for domain in sorted(expected_domains):
            spec = domains.get(domain, {})
            require(spec.get("required") is True, f"simulation quality domain disabled:{domain}")
            if "required_elements" in spec:
                require(unique_nonempty_strings(spec.get("required_elements")), f"simulation quality required elements invalid:{domain}")

        minimum = profile.get("minimum_engine_evidence", {})
        require(isinstance(minimum.get("multiple_valid_routes"), int) and minimum["multiple_valid_routes"] >= 2, "multiple-valid-route minimum weakened")
        require(isinstance(minimum.get("unsafe_branches"), int) and minimum["unsafe_branches"] >= 2, "unsafe-branch minimum weakened")
        require(minimum.get("reachable_active_dead_ends") == 0, "reachable dead ends permitted")
        require(minimum.get("required_strength_three_coverage_ratio") == 1.0, "strength-three coverage weakened")
        require(minimum.get("learner_answer_leakage_findings") == 0, "learner answer leakage permitted")

        manual = profile.get("manual_validation", {})
        for key in ("facilitator_pilot", "representative_learner_review", "accessibility_user_validation", "educational_effectiveness_study"):
            require(isinstance(manual.get(key), str) and "REQUIRED" in manual[key], f"manual validation boundary missing:{key}")

        lab = (root / "src/pages/ResearchScenarioLabPage.tsx").read_text(encoding="utf-8")
        for marker in (
            "Prebrief and objectives",
            "After-action review",
            "Interactive route rehearsal",
            "the route never advances automatically",
            "aria-live=\"polite\"",
            "Reset route",
            "fictionalization_notice",
            "training_objectives",
            "aar_teaching_points",
        ):
            require(marker in lab, f"scenario laboratory experience marker missing:{marker}")

        learner = (root / "src/pages/FacilityDecisionSessionPage.tsx").read_text(encoding="utf-8")
        for marker in (
            "aria-invalid",
            "aria-live=\"assertive\"",
            "errorSummary.current?.focus()",
            "requires_deliberate_confirmation",
            "Information staleness",
            "Closed-loop handoff state",
            "active,",
            "queued",
        ):
            require(marker in learner, f"learner experience marker missing:{marker}")
        require(".high_risk" not in learner, "restricted high_risk field leaked into learner UI")

        experience = (root / "src/scenario-core/experience.ts").read_text(encoding="utf-8")
        for marker in (
            "pathToTerminal",
            "allReachTerminal",
            "meaningful_branch",
            "profile_requirements_preserved",
            "successful_route_count",
            "experience.profile_requirements",
            "unsafe",
            "training_objectives",
            "aar_teaching_points",
            "protectedScenarioProjection",
        ):
            require(marker.lower() in experience.lower(), f"scenario experience contract marker missing:{marker}")

        decision_fixtures = (root / "src/facility-decision/fixtures.ts").read_text(encoding="utf-8")
        decision_tests = (root / "src/tests/facilityDecisionIntegrity.test.ts").read_text(encoding="utf-8")
        require("FACILITY_DECISION_ALTERNATE_SEQUENCE" in decision_fixtures, "alternate valid decision route contract missing")
        require("two materially different valid decision orderings complete" in decision_tests, "multiple valid decision-route proof missing")
        require("assertHealthy(canonical)" in decision_tests and "assertHealthy(alternate)" in decision_tests, "multiple valid decision-route health assertions missing")

        # Existing reports are informative at source preflight only. Their live
        # authenticity is established later through stage receipts.
        informative: dict[str, str] = {}
        for relative in (
            "reports/scenario-experience-assurance.json",
            "reports/facility-decision-accessibility.json",
            "reports/facility-arrival-standalone.json",
        ):
            try:
                report = read_json(root / relative)
                informative[relative] = str(report.get("classification", report.get("status", "UNKNOWN")))
            except Exception:
                informative[relative] = "MISSING"

        classification = PASS if not errors else FAIL
        return {
            "schema_version":"1.0.0",
            "classification":classification,
            "status":classification,
            "evidence_mode":"SOURCE_CONTRACT_ONLY_LIVE_RECEIPTS_REQUIRED_AT_FINAL_GATE",
            "checks":checks,
            "scope": profile.get("scope"),
            "required_domains":sorted(expected_domains),
            "learner_answer_leakage_findings": minimum.get("learner_answer_leakage_findings"),
            "reachable_active_dead_ends": minimum.get("reachable_active_dead_ends"),
            "multiple_valid_routes": minimum.get("multiple_valid_routes"),
            "unsafe_branches": minimum.get("unsafe_branches"),
            "strength_three_coverage_ratio": minimum.get("required_strength_three_coverage_ratio"),
            "informative_committed_report_states":informative,
            "manual_program_validation_required":True,
            "errors":sorted(set(errors)),
        }
    except Exception as exc:  # noqa: BLE001
        return {"schema_version":"1.0.0","classification":INTERNAL_ERROR,"status":INTERNAL_ERROR,"checks":checks,"errors":sorted(set(errors+[f"{type(exc).__name__}:{exc}"]))}


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repo",type=Path,default=Path(".")); parser.add_argument("--json-output",type=Path,default=OUTPUT); args=parser.parse_args(); root=args.repo.resolve(); report=validate(root); write_json(root/args.json_output,report); print(json.dumps(report,indent=2,sort_keys=True)); return exit_code(report["classification"])
if __name__ == "__main__": raise SystemExit(main())
