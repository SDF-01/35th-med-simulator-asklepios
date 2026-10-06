#!/usr/bin/env python3
"""Static, fail-closed accessibility and interaction-contract checker.

This checker does not claim WCAG conformance. It protects source-level invariants
that must be present before the documented manual keyboard, screen-reader,
contrast, reflow, motion, and human-factors protocols are executed.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPORT = Path("reports/facility-decision-accessibility.json")
SESSION = Path("src/pages/FacilityDecisionSessionPage.tsx")
OVERVIEW = Path("src/pages/FacilityDecisionIntegrityPage.tsx")
BUTTON = Path("src/components/ui/Button.tsx")
PROTOCOL = Path("docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md")
CSS = Path("src/index.css")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--json-output", default=REPORT.as_posix())
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    errors: list[str] = []
    checks = 0

    def check(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    for relative in (SESSION, OVERVIEW, BUTTON, PROTOCOL, CSS):
        check((repo / relative).is_file(), f"missing:{relative}")

    if not errors:
        session = (repo / SESSION).read_text(encoding="utf-8")
        overview = (repo / OVERVIEW).read_text(encoding="utf-8")
        button = (repo / BUTTON).read_text(encoding="utf-8")
        protocol = (repo / PROTOCOL).read_text(encoding="utf-8")
        css = (repo / CSS).read_text(encoding="utf-8")

        check("<main" in session and "<h1" in session, "session landmark or h1 missing")
        check(
            '<form' in session
            and 'aria-labelledby="decision-form-heading"' in session
            and 'aria-describedby="decision-form-help"' in session,
            "decision form not named/described",
        )
        native_submit = re.search(
            r"onSubmit=\{\(\s*[A-Za-z_$][\w$]*(?:\s*:[^)]*)?\s*\)\s*=>\s*\{",
            session,
        )
        check(
            native_submit is not None and "event.preventDefault()" in session and "noValidate" in session,
            "native form submission handling missing",
        )
        check("<label htmlFor={id}" in session, "input labels missing")
        check("<fieldset" in session and "<legend" in session, "multi-choice fieldset/legend missing")
        check(
            'role="status" aria-live="polite" aria-atomic="true"' in session,
            "status announcement region incomplete",
        )
        check(
            'role="alert"' in session and 'aria-live="assertive"' in session and "errorSummary.current?.focus()" in session,
            "focusable validation error summary missing",
        )
        check(
            "aria-invalid={errors.length > 0 || undefined}" in session and "aria-describedby={describedBy}" in session,
            "per-field error semantics incomplete",
        )
        check(
            "validateFacilityDecisionSubmission(submission, context.profile)" in session
            and "if (!result.valid)" in session,
            "contract validation is not performed before transition application",
        )
        check("formHeading.current?.focus()" in session, "decision-form focus transition missing")
        check(
            "statusRegion.current?.focus()" not in session and "const statusRegion" not in session,
            "polite status updates must not steal keyboard focus",
        )
        check(
            "aria-disabled={!action.enabled}" in session
            and re.search(r"(?<!aria-)disabled=\{!action\.enabled\}", session) is None
            and "if (!next.enabled)" in session,
            "unavailable decisions are not focusable and behaviorally guarded",
        )
        check(
            'aria-label="Deliberate confirmation required"' in session
            and "not a recommendation" in session
            and "Confirm and submit deliberate branch" in session,
            "deliberate high-consequence branch warning is incomplete",
        )
        check(
            'aria-label="Scenario state dashboard"' in session
            and "Available now" in session
            and "Reassessment" in session,
            "scenario orientation dashboard missing",
        )
        check(
            'aria-label="Decision choices"' in session
            and "action.category" in session
            and "decision-availability-" in session,
            "decision choices lack category or availability context",
        )
        check(
            "Available at {formatTime(result.available_at_seconds)}" in session
            and "Placed" in session and "Started" in session and "Due" in session,
            "order/result timing presentation incomplete",
        )
        check(
            "lg:sticky lg:top-4 lg:self-start" in session,
            "desktop operational context panel is not persistently visible",
        )
        check(
            "Decision timeline" in session
            and "const instructorTimeline = view.instructor?.decision_timeline ?? []" in session
            and "instructorTimeline.map" in session
            and "session.decision_records" not in session,
            "instructor decision timeline missing",
        )
        check(
            "Safety events:" in session and "Calibration:" in session,
            "terminal multidimensional review lacks safety/calibration context",
        )
        check(
            "focus-visible:" in session and "focus-visible:" in overview and "focus-visible:" in button,
            "visible focus styling missing",
        )
        check("min-h-11" in button and "min-h-12" in button, "shared button target size floor missing")
        check(
            "aria-disabled:cursor-not-allowed" in button and "aria-disabled:opacity-55" in button,
            "shared aria-disabled styling missing",
        )
        check(
            "tabIndex={1}" not in session
            and "tabIndex={2}" not in session
            and not re.search(r"tabIndex=\{[1-9]", session),
            "positive tabindex forbidden",
        )
        check("draggable=" not in session and "onDrag" not in session, "drag-only interaction introduced")
        check("autoFocus" not in session, "automatic focus side effect introduced")
        check("setInterval(" not in session and "setTimeout(" not in session, "automatic learner time advance introduced")
        check('type="submit"' in session and 'type="button"' in session, "form button types incomplete")
        check(
            'aria-label="Initial observations"' in session and 'aria-label="Resource workload"' in session,
            "structured status groups lack accessible names",
        )
        check("prefers-reduced-motion" in css, "reduced-motion CSS missing")
        check(
            "WCAG 2.2" in protocol and "MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED" in protocol,
            "manual accessibility protocol incomplete",
        )
        for required in (
            "Manual keyboard protocol",
            "Screen-reader protocol",
            "Contrast, reflow, and motion protocol",
            "Human-factors protocol",
        ):
            check(required in protocol, f"protocol section missing:{required}")

    report = {
        "schema_version": "1.1.0",
        "classification": "PASS" if not errors else "FAIL",
        "status": "PASS" if not errors else "FAIL",
        "automated_source_status": "PASS" if not errors else "FAIL",
        "manual_accessibility_validation": "REQUIRED_NOT_EXECUTED",
        "wcag_conformance_claim": "NOT_MADE",
        "checks": checks,
        "errors": sorted(set(errors)),
    }
    output = repo / args.json_output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
