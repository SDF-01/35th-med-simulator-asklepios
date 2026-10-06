#!/usr/bin/env python3
"""Validate the release technical-debt register in source and final-evidence modes."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from release_graph_core import canonical_json, load_graph, sha256_text, stage_map, write_json
from check_technical_debt_ratchet import COMPILED_REQUIRED_RECEIPTS
from release_policy_common import (
    authenticate_stage_receipt,
    load_release_json,
    receipt_directory,
    unique_nonempty_strings,
)
from release_result import FAIL, INTERNAL_ERROR, PASS, exit_code

REGISTER = "config/release/TECHNICAL_DEBT_REGISTER.json"
OUTPUTS = {
    "source": Path("reports/release-technical-debt-policy.json"),
    "final": Path("reports/release-technical-debt-final.json"),
}
DEBT_ID = re.compile(r"^TD-[A-Z0-9-]+-[0-9]{3}$")
ALLOWED_STATES = ["CLOSED", "ACCEPTED_RISK", "OUT_OF_SCOPE"]
PERMITTED_CLAIM = (
    "No known release-blocking technical debt remains within the machine-checked "
    "scope and current authenticated evidence."
)
# A single independently compiled monotonic receipt floor is consumed by both
# the ratchet validator and the source/final evidence validator. Keeping a
# second hand-maintained subset here previously allowed newly ratcheted stages
# to be omitted until an adversarial test found the drift.
CRITICAL_FINAL_EVIDENCE = frozenset(COMPILED_REQUIRED_RECEIPTS)



def validate(root: Path, mode: str, receipt_dir: Path | None = None) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    checks = 0

    def require(condition: bool, message: str) -> None:
        nonlocal checks
        checks += 1
        if not condition:
            errors.append(message)

    try:
        register = load_release_json(root, REGISTER, errors)
        graph = load_graph(root)
        if register is None:
            raise ValueError("technical-debt register missing")
        stages = stage_map(graph)

        require(register.get("schema_version") == "1.0.0", "technical-debt schema differs")
        require(register.get("register_id") == "asklepios-release-debt-v1", "technical-debt register ID differs")
        require(register.get("absolute_debt_free_claim_permitted") is False, "absolute debt-free claim was enabled")
        require(register.get("permitted_release_claim") == PERMITTED_CLAIM, "scoped technical-debt claim differs")
        require(register.get("states") == ALLOWED_STATES, "technical-debt state vocabulary differs")

        entries = register.get("entries")
        require(isinstance(entries, list) and bool(entries), "technical-debt entries missing")
        if not isinstance(entries, list):
            entries = []
        seen: set[str] = set()
        known_blockers = 0
        accepted_risks: list[str] = []
        out_of_scope: list[str] = []
        for index, value in enumerate(entries):
            require(isinstance(value, dict), f"technical-debt entry is not an object:{index}")
            if not isinstance(value, dict):
                continue
            debt_id = value.get("debt_id")
            require(isinstance(debt_id, str) and bool(DEBT_ID.fullmatch(debt_id)), f"technical-debt ID invalid:{debt_id}")
            require(debt_id not in seen, f"technical-debt ID duplicated:{debt_id}")
            if isinstance(debt_id, str):
                seen.add(debt_id)
            require(isinstance(value.get("title"), str) and bool(value["title"].strip()), f"technical-debt title missing:{debt_id}")
            require(isinstance(value.get("closure"), str) and bool(value["closure"].strip()), f"technical-debt closure missing:{debt_id}")
            require(isinstance(value.get("release_blocker"), bool), f"technical-debt blocker flag invalid:{debt_id}")
            state = value.get("state")
            require(state in ALLOWED_STATES, f"technical-debt state invalid:{debt_id}:{state}")
            evidence_stages = value.get("evidence_stages")
            require(unique_nonempty_strings(evidence_stages), f"technical-debt evidence stages invalid:{debt_id}")
            if isinstance(evidence_stages, list):
                for stage_id in evidence_stages:
                    require(stage_id in stages, f"technical-debt evidence stage absent:{debt_id}:{stage_id}")
            blocker = value.get("release_blocker") is True
            if blocker and state != "CLOSED":
                known_blockers += 1
                errors.append(f"release-blocking technical debt remains:{debt_id}:{state}")
            if state == "ACCEPTED_RISK":
                accepted_risks.append(str(debt_id))
                require(not blocker, f"release blocker cannot be accepted risk:{debt_id}")
            if state == "OUT_OF_SCOPE":
                out_of_scope.append(str(debt_id))
                require(not blocker, f"out-of-scope debt cannot be release blocker:{debt_id}")

        contract = register.get("final_evidence_contract")
        require(isinstance(contract, dict), "technical-debt final evidence contract missing")
        if not isinstance(contract, dict):
            contract = {}
        required_receipts = contract.get("required_stage_receipts")
        require(unique_nonempty_strings(required_receipts), "technical-debt required receipt inventory invalid")
        if not isinstance(required_receipts, list):
            required_receipts = []
        for stage_id in required_receipts:
            require(stage_id in stages, f"technical-debt final evidence stage absent:{stage_id}")
        for stage_id in sorted(CRITICAL_FINAL_EVIDENCE):
            require(stage_id in required_receipts, f"technical-debt critical final evidence missing:{stage_id}")
        terminal_stage = contract.get("terminal_evidence_stage")
        require(terminal_stage == "final.decision-evidence", "technical-debt terminal evidence stage differs")
        require(terminal_stage in required_receipts, "technical-debt terminal evidence is not required")
        require(contract.get("requires_current_graph_hash") is True, "technical-debt graph hash binding disabled")
        require(contract.get("requires_current_output_hashes") is True, "technical-debt output hash binding disabled")
        require(contract.get("stale_committed_reports_may_satisfy_gate") is False, "stale committed reports may satisfy technical-debt gate")

        authenticated: dict[str, Any] = {}
        chain_root: str | None = None
        if mode == "final":
            receipts_root = receipt_directory(root, graph, receipt_dir)
            evidence, stage_errors = authenticate_stage_receipt(
                root,
                graph,
                str(terminal_stage),
                receipt_dir=receipts_root,
            )
            errors.extend(stage_errors)
            chain = evidence.get("chain", {}) if isinstance(evidence, dict) else {}
            chain_root = evidence.get("receipt_chain_root_sha256") if isinstance(evidence, dict) else None
            for stage_id in required_receipts:
                stage_evidence = chain.get(stage_id)
                require(isinstance(stage_evidence, dict), f"technical-debt required receipt absent from authenticated chain:{stage_id}")
                checks_value = stage_evidence.get("checks", {}) if isinstance(stage_evidence, dict) else {}
                require(isinstance(checks_value, dict) and bool(checks_value) and all(checks_value.values()), f"technical-debt required receipt not authenticated:{stage_id}")
                if isinstance(stage_evidence, dict) and isinstance(checks_value, dict) and checks_value and all(checks_value.values()):
                    authenticated[stage_id] = stage_evidence
            require(len(authenticated) == len(required_receipts), "technical-debt final evidence is incomplete")

        classification = PASS if not errors else FAIL
        evidence_root = sha256_text(canonical_json({
            "register": register,
            "authenticated_receipts": {
                key: value.get("receipt_sha256") for key, value in sorted(authenticated.items())
            },
            "mode": mode,
            "terminal_evidence_stage": terminal_stage,
            "receipt_chain_root_sha256": chain_root,
        }))
        return {
            "schema_version": "1.0.0",
            "classification": classification,
            "status": classification,
            "mode": mode,
            "checks": checks,
            "register_id": register.get("register_id"),
            "entries": len(entries),
            "known_release_blockers_remaining": known_blockers,
            "accepted_risks": sorted(accepted_risks),
            "out_of_scope_items": sorted(out_of_scope),
            "absolute_debt_free_claim_permitted": False,
            "permitted_release_claim": PERMITTED_CLAIM,
            "required_receipt_count": len(required_receipts),
            "authenticated_receipt_count": len(authenticated),
            "authenticated_receipts": authenticated,
            "terminal_evidence_stage": terminal_stage,
            "receipt_chain_root_sha256": chain_root,
            "evidence_root_sha256": evidence_root,
            "errors": sorted(set(errors)),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "schema_version": "1.0.0",
            "classification": INTERNAL_ERROR,
            "status": INTERNAL_ERROR,
            "mode": mode,
            "checks": checks,
            "errors": [f"{type(exc).__name__}:{exc}"],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--mode", choices=sorted(OUTPUTS), required=True)
    parser.add_argument("--receipt-dir", type=Path)
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    report = validate(root, args.mode, args.receipt_dir)
    output = args.json_output or OUTPUTS[args.mode]
    write_json(root / output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report["classification"])


if __name__ == "__main__":
    raise SystemExit(main())
