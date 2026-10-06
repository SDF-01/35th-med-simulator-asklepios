#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path.cwd()
CHECKER = ROOT / "scripts/check_content_registry_axioms.py"
MANIFEST_PATH = ROOT / "formal/CONTENT_REGISTRY_TRUST_MANIFEST.json"
BASE_MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
THEOREMS = BASE_MANIFEST["required_theorems"]


def clean_log() -> str:
    return "\n".join(
        f"'{name}' does not depend on any axioms" for name in THEOREMS
    ) + "\n"


def run_checker(log: str, manifest: dict) -> tuple[bool, dict]:
    with tempfile.TemporaryDirectory(prefix="content-registry-axiom-test-") as tmp:
        tmp_path = Path(tmp)
        log_path = tmp_path / "audit.log"
        manifest_path = tmp_path / "manifest.json"
        log_path.write_text(log, encoding="utf-8")
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(CHECKER),
                str(log_path),
                "--manifest",
                str(manifest_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError:
            report = {
                "status": "MALFORMED_OUTPUT",
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        return result.returncode == 0 and report.get("status") == "PASS", report


cases: list[dict[str, object]] = []


def case(case_id: str, log: str, manifest: dict, should_pass: bool) -> None:
    passed, report = run_checker(log, manifest)
    cases.append(
        {
            "case_id": case_id,
            "pass": passed if should_pass else not passed,
            "checker_status": report.get("status"),
            "errors": report.get("errors", []),
        }
    )


baseline = clean_log()
case("exact_zero_axiom_log", baseline, BASE_MANIFEST, True)
case(
    "propext_rejected",
    baseline.replace(
        f"'{THEOREMS[0]}' does not depend on any axioms",
        f"'{THEOREMS[0]}' depends on axioms: [propext]",
        1,
    ),
    BASE_MANIFEST,
    False,
)
case(
    "missing_theorem_rejected",
    baseline.replace(f"'{THEOREMS[0]}' does not depend on any axioms\n", "", 1),
    BASE_MANIFEST,
    False,
)
case(
    "duplicate_theorem_rejected",
    baseline + f"'{THEOREMS[0]}' does not depend on any axioms\n",
    BASE_MANIFEST,
    False,
)
case(
    "unexpected_theorem_rejected",
    baseline + "'ScenarioContracts.unreviewed_theorem' does not depend on any axioms\n",
    BASE_MANIFEST,
    False,
)
case(
    "forbidden_sorry_axiom_rejected",
    baseline.replace(
        f"'{THEOREMS[1]}' does not depend on any axioms",
        f"'{THEOREMS[1]}' depends on axioms: [sorryAx]",
        1,
    ),
    BASE_MANIFEST,
    False,
)
wide_manifest = copy.deepcopy(BASE_MANIFEST)
wide_manifest["per_theorem_axioms"][THEOREMS[0]] = ["propext"]
case("manifest_self_widening_rejected", baseline, wide_manifest, False)
case(
    "malformed_known_theorem_line_rejected",
    baseline.replace(
        f"'{THEOREMS[2]}' does not depend on any axioms",
        f"'{THEOREMS[2]}' maybe has no axioms",
        1,
    ),
    BASE_MANIFEST,
    False,
)
case(
    "classical_choice_rejected",
    baseline.replace(
        f"'{THEOREMS[3]}' does not depend on any axioms",
        f"'{THEOREMS[3]}' depends on axioms: [Classical.choice]",
        1,
    ),
    BASE_MANIFEST,
    False,
)

model_rewrite = copy.deepcopy(BASE_MANIFEST)
model_rewrite["authority_policy_model"] = "manifest-defined"
case("manifest_policy_model_rewrite_rejected", baseline, model_rewrite, False)
proof_rewrite = copy.deepcopy(BASE_MANIFEST)
proof_rewrite["proof_mode_for_capability_denials"] = "decide"
case("manifest_proof_mode_rewrite_rejected", baseline, proof_rewrite, False)

failed = [item["case_id"] for item in cases if not item["pass"]]
report = {
    "schema_version": "1.0.0",
    "status": "PASS" if not failed else "FAIL",
    "cases": len(cases),
    "errors": failed,
    "results": cases,
}
print(json.dumps(report, indent=2))
raise SystemExit(0 if not failed else 3)
