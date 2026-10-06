#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from release_result import finalize_adversarial_report

FILES = [
    "src/pages/FacilityDecisionSessionPage.tsx",
    "src/pages/FacilityDecisionIntegrityPage.tsx",
    "src/components/ui/Button.tsx",
    "src/index.css",
    "docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md",
    "scripts/check_facility_decision_accessibility.py",
]


def run(repo: Path) -> tuple[int, dict | None]:
    completed = subprocess.run(
        [sys.executable, "scripts/check_facility_decision_accessibility.py", "--repo", ".", "--json-output", "reports/a11y.json"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = None
    try:
        payload = json.loads(completed.stdout)
    except Exception:
        pass
    return completed.returncode, payload


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"marker missing:{old}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def replace_all(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"marker missing:{old}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


def remove_focus(repo: Path) -> None:
    for relative in (
        "src/pages/FacilityDecisionSessionPage.tsx",
        "src/pages/FacilityDecisionIntegrityPage.tsx",
        "src/components/ui/Button.tsx",
    ):
        path = repo / relative
        path.write_text(path.read_text(encoding="utf-8").replace("focus-visible:", "focus-removed:"), encoding="utf-8", newline="\n")


def append_status_focus(repo: Path) -> None:
    path = repo / "src/pages/FacilityDecisionSessionPage.tsx"
    path.write_text(
        path.read_text(encoding="utf-8") + "\n// statusRegion.current?.focus()\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json-output", default="reports/facility-decision-accessibility-mutations.json")
    args = parser.parse_args()
    source = Path(args.repo).resolve()
    results: list[dict] = []
    errors: list[str] = []
    cases = [
        ("baseline", None, True),
        ("status_live_removed", lambda repo: mutate(repo / FILES[0], 'role="status" aria-live="polite"', 'role="status" aria-live="off"'), False),
        ("form_label_removed", lambda repo: mutate(repo / FILES[0], 'aria-labelledby="decision-form-heading"', 'data-form-label="missing"'), False),
        (
            "native_submission_removed",
            lambda repo: mutate(
                repo / FILES[0],
                "onSubmit={(event: FormEvent<HTMLFormElement>) => {",
                "data-submit-handler={() => {",
            ),
            False,
        ),
        ("fieldset_removed", lambda repo: mutate(repo / FILES[0], "<fieldset", "<div"), False),
        ("focus_style_removed", remove_focus, False),
        ("positive_tabindex", lambda repo: mutate(repo / FILES[0], "tabIndex={-1}", "tabIndex={1}"), False),
        ("automatic_timer", lambda repo: (repo / FILES[0]).write_text((repo / FILES[0]).read_text(encoding="utf-8") + "\n// setInterval(() => advance(), 1000)\n", encoding="utf-8", newline="\n"), False),
        ("reduced_motion_removed", lambda repo: replace_all(repo / "src/index.css", "prefers-reduced-motion", "prefers-full-motion"), False),
        ("manual_protocol_removed", lambda repo: mutate(repo / FILES[4], "MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED", "MANUAL_VALIDATION_COMPLETE"), False),
        ("pretransition_validation_removed", lambda repo: mutate(repo / FILES[0], "validateFacilityDecisionSubmission(submission, context.profile)", "({ valid: true, errors: [] } as FacilityDecisionValidationResult)"), False),
        ("error_summary_removed", lambda repo: mutate(repo / FILES[0], 'aria-live="assertive"', 'aria-live="off"'), False),
        ("field_error_binding_removed", lambda repo: replace_all(repo / FILES[0], "aria-invalid={errors.length > 0 || undefined}", "data-invalid={errors.length > 0 || undefined}"), False),
        ("unavailable_decisions_native_disabled", lambda repo: mutate(repo / FILES[0], "aria-disabled={!action.enabled}", "disabled={!action.enabled}"), False),
        ("status_focus_theft", append_status_focus, False),
        ("deliberate_warning_removed", lambda repo: mutate(repo / FILES[0], 'aria-label="Deliberate confirmation required"', 'aria-label="Branch"'), False),
        ("state_dashboard_removed", lambda repo: mutate(repo / FILES[0], 'aria-label="Scenario state dashboard"', 'aria-label="Summary"'), False),
        (
            "instructor_timeline_bypasses_projection",
            lambda repo: mutate(
                repo / FILES[0],
                "const instructorTimeline = view.instructor?.decision_timeline ?? [];",
                "const instructorTimeline = session.decision_records;",
            ),
            False,
        ),
    ]

    for case_id, mutation, expected_pass in cases:
        with tempfile.TemporaryDirectory(prefix="asklepios-a11y-") as temporary:
            repo = Path(temporary) / "repo"
            for relative in FILES:
                destination = repo / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, destination)
            if mutation:
                mutation(repo)
            returncode, payload = run(repo)
            observed_pass = returncode == 0
            passed = observed_pass == expected_pass
            if not passed:
                errors.append(f"{case_id}:expected={expected_pass}:observed={observed_pass}")
            results.append({
                "case_id": case_id,
                "expected_pass": expected_pass,
                "observed_pass": observed_pass,
                "pass": passed,
                "checker_errors": payload.get("errors", []) if isinstance(payload, dict) else ["checker_internal_error"],
            })

    report = {
        "schema_version": "1.1.0",
        "status": "PASS" if not errors else "FAIL",
        "cases": len(results),
        "attacks": len(results) - 1,
        "results": results,
        "errors": errors,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=("baseline",))
    output = source / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
