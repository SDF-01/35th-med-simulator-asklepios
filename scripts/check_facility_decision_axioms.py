#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

EXPECTED_THEOREMS = [
    'ScenarioContracts.decision_operational_transition_preserves_clinical',
    'ScenarioContracts.decision_learner_projection_ignores_instructor_score',
    'ScenarioContracts.decision_learner_projection_ignores_provenance',
    'ScenarioContracts.decision_unadjudicated_treatment_is_blocked',
    'ScenarioContracts.decision_missing_scope_blocks_treatment',
    'ScenarioContracts.decision_missing_eligibility_blocks_treatment',
    'ScenarioContracts.decision_missing_source_attestation_blocks_treatment',
    'ScenarioContracts.decision_absent_order_blocks_result',
    'ScenarioContracts.decision_queued_order_blocks_result',
    'ScenarioContracts.decision_completed_order_allows_result',
    'ScenarioContracts.decision_world_event_independent_of_action_identity',
    'ScenarioContracts.decision_handoff_without_ack_is_blocked',
    'ScenarioContracts.decision_handoff_without_questions_is_blocked',
    'ScenarioContracts.decision_handoff_without_sender_confirmation_is_blocked',
    'ScenarioContracts.decision_complete_closed_loop_handoff_transfers',
    'ScenarioContracts.decision_operational_replay_preserves_clinical',
    'ScenarioContracts.decision_training_prohibits_patient_care',
]
EXPECTED_AXIOMS = {name: [] for name in EXPECTED_THEOREMS}
FORBIDDEN = ['sorryAx','Classical.choice','Quot.sound','Lean.trustCompiler','Lean.ofReduceBool']
NO_AXIOMS = 'does not depend on any axioms'
WITH_AXIOMS = re.compile(r'^depends on axioms:\s*\[([^\]]*)\]\s*$', re.I)


def split_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped:
        return None
    if stripped.startswith("'"):
        end = stripped.find("'", 1)
        if end < 0:
            return None
        name, rest = stripped[1:end], stripped[end+1:].strip()
    else:
        pieces = stripped.split(maxsplit=1)
        if len(pieces) != 2:
            return None
        name, rest = pieces
    return (name, rest) if name.startswith('ScenarioContracts.') else None


def parse(text: str) -> tuple[dict[str, list[str]], list[str]]:
    observed: dict[str, list[str]] = {}
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        parsed = split_line(line)
        if parsed is None:
            folded = line.casefold()
            if 'ScenarioContracts.' in line and ('depends on axioms' in folded or NO_AXIOMS in folded):
                errors.append(f'malformed theorem audit line:{number}')
            continue
        name, rest = parsed
        if rest.casefold() == NO_AXIOMS:
            axioms: list[str] = []
        else:
            match = WITH_AXIOMS.match(rest)
            if not match:
                errors.append(f'malformed theorem audit result:{name}')
                continue
            raw = match.group(1).strip()
            axioms = [] if not raw else [item.strip() for item in raw.split(',') if item.strip()]
        if name in observed:
            errors.append(f'duplicate theorem audit entry:{name}')
        else:
            observed[name] = axioms
    return observed, errors


def validate(log_text: str, manifest: dict) -> dict:
    errors: list[str] = []
    if manifest.get('required_theorems') != EXPECTED_THEOREMS:
        errors.append('manifest theorem inventory differs from independent checker')
    if manifest.get('per_theorem_axioms') != EXPECTED_AXIOMS:
        errors.append('manifest axiom budget differs from independent zero-axiom policy')
    if manifest.get('forbidden_dependencies') != FORBIDDEN:
        errors.append('manifest forbidden dependency policy differs')
    if manifest.get('module') != 'ScenarioContracts.FacilityDecisionIntegrity':
        errors.append('manifest module differs')
    if manifest.get('formal_root_module') != 'ScenarioContracts':
        errors.append('manifest root module differs')
    observed, parse_errors = parse(log_text)
    errors.extend(parse_errors)
    expected_set, observed_set = set(EXPECTED_THEOREMS), set(observed)
    for theorem in sorted(expected_set - observed_set): errors.append(f'theorem missing:{theorem}')
    for theorem in sorted(observed_set - expected_set): errors.append(f'unexpected theorem audit entry:{theorem}')
    for theorem in EXPECTED_THEOREMS:
        if theorem in observed and observed[theorem]:
            errors.append(f'axiom budget mismatch:{theorem}:{",".join(observed[theorem])}')
    folded = log_text.casefold()
    for dependency in FORBIDDEN:
        if dependency.casefold() in folded:
            errors.append(f'forbidden dependency:{dependency}')
    return {
        'schema_version':'1.0.0',
        'status':'PASS' if not errors else 'FAIL',
        'policy':'independently encoded exact zero-axiom budget',
        'theorems_expected':len(EXPECTED_THEOREMS),
        'theorems_observed':len(observed),
        'per_theorem_axioms':observed,
        'errors':sorted(set(errors)),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('log')
    parser.add_argument('--manifest',default='formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json')
    parser.add_argument('--output',default='reports/facility-decision-axiom-check.json')
    args=parser.parse_args(argv)
    report=validate(Path(args.log).read_text(encoding='utf-8',errors='replace'),json.loads(Path(args.manifest).read_text()))
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0 if report['status']=='PASS' else 3

if __name__=='__main__': raise SystemExit(main())
