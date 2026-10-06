#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
CHECKER = ROOT / "scripts/check_facility_arrival_axioms.py"
MANIFEST = json.loads((ROOT / "formal/FACILITY_ARRIVAL_TRUST_MANIFEST.json").read_text(encoding="utf-8"))
THEOREMS = MANIFEST["required_theorems"]


def clean_log() -> str:
    return "\n".join(f"'{name}' does not depend on any axioms" for name in THEOREMS) + "\n"


def execute(log: str, manifest: dict) -> tuple[bool, dict]:
    with tempfile.TemporaryDirectory(prefix="facility-axiom-test-") as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "audit.log"
        manifest_path = tmp_path / "manifest.json"
        output_path = tmp_path / "report.json"
        log_path.write_text(log, encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(CHECKER), str(log_path), "--manifest", str(manifest_path), "--output", str(output_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            report = {"status": "MALFORMED", "stdout": result.stdout, "stderr": result.stderr}
        return result.returncode == 0 and report.get("status") == "PASS", report


cases: list[dict[str, object]] = []


def case(case_id: str, log: str, manifest: dict, should_pass: bool) -> None:
    passed, report = execute(log, manifest)
    cases.append({
        "case_id": case_id,
        "pass": passed if should_pass else not passed,
        "checker_status": report.get("status"),
        "errors": report.get("errors", []),
    })


baseline = clean_log()
case("exact_zero_axiom_log", baseline, MANIFEST, True)
case("propext_rejected", baseline.replace("does not depend on any axioms", "depends on axioms: [propext]", 1), MANIFEST, False)
case("missing_theorem_rejected", baseline.replace(f"'{THEOREMS[0]}' does not depend on any axioms\n", "", 1), MANIFEST, False)
case("duplicate_theorem_rejected", baseline + f"'{THEOREMS[0]}' does not depend on any axioms\n", MANIFEST, False)
case("unexpected_theorem_rejected", baseline + "'ScenarioContracts.unreviewed_facility_theorem' does not depend on any axioms\n", MANIFEST, False)
case("sorry_axiom_rejected", baseline.replace(f"'{THEOREMS[1]}' does not depend on any axioms", f"'{THEOREMS[1]}' depends on axioms: [sorryAx]", 1), MANIFEST, False)
wide = copy.deepcopy(MANIFEST)
wide["per_theorem_axioms"][THEOREMS[0]] = ["propext"]
case("manifest_self_widening_rejected", baseline, wide, False)
case("malformed_line_rejected", baseline.replace(f"'{THEOREMS[2]}' does not depend on any axioms", f"'{THEOREMS[2]}' unknown result", 1), MANIFEST, False)
case("classical_choice_rejected", baseline.replace(f"'{THEOREMS[3]}' does not depend on any axioms", f"'{THEOREMS[3]}' depends on axioms: [Classical.choice]", 1), MANIFEST, False)

failed = [item["case_id"] for item in cases if not item["pass"]]
report = {"schema_version": "1.0.0", "status": "PASS" if not failed else "FAIL", "cases": len(cases), "errors": failed, "results": cases}
print(json.dumps(report, indent=2))
raise SystemExit(0 if not failed else 3)
