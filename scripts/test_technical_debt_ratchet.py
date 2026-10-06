#!/usr/bin/env python3
"""Adversarial tests for the monotonic technical-debt ratchet."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from scenario_genome_common import canonical_sha256, atomic_write_json

sys.dont_write_bytecode = True
FILES = (
    "config/release/TECHNICAL_DEBT_RATCHET.json",
    "config/release/TECHNICAL_DEBT_REGISTER.json",
    "config/release/RELEASE_GRAPH.json",
    "scripts/check_technical_debt_ratchet.py",
    "scripts/release_graph_core.py",
    "scripts/release_result.py",
    "scripts/scenario_genome_common.py",
)


def read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected object:{path}")
    return value


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")


def refresh_anchor(policy: dict[str, Any]) -> None:
    policy["ratchet_anchor_sha256"] = canonical_sha256({
        "ratchet_id": policy.get("ratchet_id"),
        "ratchet_epoch": policy.get("ratchet_epoch"),
        "register_id": policy.get("register_id"),
        "required_entry_floors": policy.get("required_entry_floors"),
        "required_final_stage_receipts": policy.get("required_final_stage_receipts"),
        "required_contract": policy.get("required_contract"),
    })


def prepare(source: Path, target: Path) -> None:
    for relative in FILES:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)


def run_checker(repo: Path) -> tuple[bool, dict[str, Any]]:
    completed = subprocess.run(
        [sys.executable, "scripts/check_technical_debt_ratchet.py", "--repo", ".", "--json-output", "reports/test.json"],
        cwd=repo,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
        timeout=60,
    )
    try:
        result = json.loads(completed.stdout)
    except Exception:
        result = {"classification": "INTERNAL_ERROR", "errors": [completed.stdout[-2000:]]}
    return completed.returncode == 0 and result.get("classification") == "PASS", {
        "exit_status": completed.returncode,
        "observed_classification": result.get("classification"),
        "checker_errors": result.get("errors", []),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--json-output", type=Path, default=Path("reports/technical-debt-ratchet-mutations.json"))
    args = parser.parse_args()
    source = args.repo.resolve()
    results: list[dict[str, Any]] = []

    def execute(case_id: str, mutate: Callable[[Path], None] | None, expected_pass: bool) -> None:
        with tempfile.TemporaryDirectory(prefix=f"asklepios-debt-ratchet-{case_id}-") as temporary:
            repo = Path(temporary) / "repo"
            prepare(source, repo)
            if mutate:
                mutate(repo)
            observed, diagnostics = run_checker(repo)
            passed = observed is expected_pass
            results.append({
                "case_id": case_id,
                "classification": "PASS" if expected_pass and passed else ("EXPECTED_REJECTION" if not expected_pass and passed else "FAIL"),
                "expected_pass": expected_pass,
                "observed_pass": observed,
                "pass": passed,
                **diagnostics,
            })

    policy_path = Path("config/release/TECHNICAL_DEBT_RATCHET.json")
    register_path = Path("config/release/TECHNICAL_DEBT_REGISTER.json")

    def edit(relative: Path, mutation: Callable[[dict[str, Any]], None]) -> Callable[[Path], None]:
        def apply(repo: Path) -> None:
            value = read(repo / relative)
            mutation(value)
            write(repo / relative, value)
        return apply

    execute("baseline", None, True)

    def remove_behavior_archive_entry(data: dict[str, Any]) -> None:
        data["entries"] = [entry for entry in data["entries"] if entry.get("debt_id") != "TD-BEHAVIOR-ARCHIVE-015"]

    def remove_behavior_archive_receipt(data: dict[str, Any]) -> None:
        receipts = data["final_evidence_contract"]["required_stage_receipts"]
        receipts.remove("scenario.behavior-archive-attacks")

    execute("behavior_archive_entry_removed", edit(register_path, remove_behavior_archive_entry), False)
    execute("behavior_archive_receipt_removed", edit(register_path, remove_behavior_archive_receipt), False)
    execute("closed_entry_removed", edit(register_path, lambda d: d["entries"].pop(0)), False)

    def reopen(entry: dict[str, Any]) -> None:
        entry["state"] = "OUT_OF_SCOPE"
        entry["release_blocker"] = False

    execute("closed_blocker_reclassified", edit(register_path, lambda d: reopen(d["entries"][0])), False)
    execute("entry_evidence_floor_removed", edit(register_path, lambda d: d["entries"][0]["evidence_stages"].pop()), False)
    execute("unratcheted_entry_added", edit(register_path, lambda d: d["entries"].append({
        "debt_id": "TD-UNRATCHETED-999", "title": "Unratcheted", "closure": "None",
        "release_blocker": False, "state": "OUT_OF_SCOPE", "evidence_stages": ["release.intended-use-policy"],
    })), False)
    execute("required_receipt_removed", edit(register_path, lambda d: d["final_evidence_contract"]["required_stage_receipts"].pop()), False)
    execute("unratcheted_receipt_added", edit(register_path, lambda d: d["final_evidence_contract"]["required_stage_receipts"].append("orchestration.graph-check")), False)
    execute("absolute_claim_enabled", edit(register_path, lambda d: d.__setitem__("absolute_debt_free_claim_permitted", True)), False)
    execute("terminal_stage_changed", edit(register_path, lambda d: d["final_evidence_contract"].__setitem__("terminal_evidence_stage", "final.graph-evidence")), False)

    def lower_and_reanchor(repo: Path) -> None:
        policy = read(repo / policy_path)
        policy["required_entry_floors"].pop("TD-RELEASE-GRAPH-001")
        refresh_anchor(policy)
        write(repo / policy_path, policy)

    execute("policy_floor_lowered_and_reanchored", lower_and_reanchor, False)

    def receipt_floor_lowered(repo: Path) -> None:
        policy = read(repo / policy_path)
        policy["required_final_stage_receipts"].pop()
        refresh_anchor(policy)
        write(repo / policy_path, policy)

    execute("policy_receipt_floor_lowered_and_reanchored", receipt_floor_lowered, False)
    execute("policy_missing", lambda repo: (repo / policy_path).unlink(), False)

    failures = [item["case_id"] for item in results if not item["pass"]]
    report = {
        "schema_version": "1.0.0",
        "classification": "PASS" if not failures else "FAIL",
        "status": "PASS" if not failures else "FAIL",
        "cases": len(results),
        "expected_rejections": sum(1 for item in results if not item["expected_pass"]),
        "accepted_regressions": sum(1 for item in results if not item["expected_pass"] and item["observed_pass"]),
        "errors": failures,
        "results": results,
        "anti_circular_note": "Lowering the JSON ratchet and recomputing its self-anchor is rejected by the independently compiled debt floor.",
    }
    output = args.json_output if args.json_output.is_absolute() else source / args.json_output
    atomic_write_json(output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if not failures else 3


if __name__ == "__main__":
    raise SystemExit(main())
