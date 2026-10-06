#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable
from release_result import finalize_adversarial_report

REPORT = Path('reports/facility-decision-validity-boundary-mutations.json')
FILES = [
    Path('config/facility-decision/VALIDITY_BOUNDARIES.json'),
    Path('config/facility-decision/ASK-D-001.json'),
    Path('README.md'),
    Path('examples/facility-decision/README.md'),
    Path('docs/FACILITY_DECISION_ACCESSIBILITY_PROTOCOL.md'),
    Path('scripts/check_facility_decision_validity_boundaries.py'),
]
Mutation = Callable[[Path], None]


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8', newline='\n')


def mutate_domain_status(domain: str, status: str) -> Mutation:
    def apply(repo: Path) -> None:
        path = repo / FILES[0]
        data = load(path); data['domains'][domain]['status'] = status; write(path, data)
    return apply


def remove_requirement(domain: str, requirement: str) -> Mutation:
    def apply(repo: Path) -> None:
        path = repo / FILES[0]
        data = load(path); data['domains'][domain]['activation_requirements'].remove(requirement); write(path, data)
    return apply


def profile_edit(path_parts: list[str], value: Any) -> Mutation:
    def apply(repo: Path) -> None:
        path = repo / FILES[1]
        data = load(path); node = data
        for key in path_parts[:-1]: node = node[key]
        node[path_parts[-1]] = value; write(path, data)
    return apply


def inject_public_claim(repo: Path) -> None:
    path = repo / 'examples/facility-decision/README.md'
    path.write_text(path.read_text(encoding='utf-8') + '\nThis learner decision caused the outcome.\n', encoding='utf-8', newline='\n')


def remove_domain(repo: Path) -> None:
    path = repo / FILES[0]
    data = load(path); data['domains'].pop('causal_aar'); write(path, data)


CASES: list[tuple[str, Mutation]] = [
    ('operational_calibration_status_escalation', mutate_domain_status('operational_calibration', 'CALIBRATED')),
    ('treatment_legitimacy_status_escalation', mutate_domain_status('treatment_legitimacy', 'CLINICALLY_VALIDATED')),
    ('human_behavior_status_escalation', mutate_domain_status('human_team_behavior', 'CALIBRATED')),
    ('patient_dynamics_status_escalation', mutate_domain_status('patient_dynamics', 'VALIDATED_DYNAMIC_PHYSIOLOGY')),
    ('claim_entailment_status_escalation', mutate_domain_status('claim_entailment', 'ENTAILMENT_PROVEN')),
    ('causal_aar_status_escalation', mutate_domain_status('causal_aar', 'CAUSAL_EFFECT_IDENTIFIED')),
    ('formal_refinement_status_escalation', mutate_domain_status('executable_formal_refinement', 'FULL_REFINEMENT_PROVEN')),
    ('accessibility_status_escalation', mutate_domain_status('accessibility', 'WCAG_2_2_AA_CONFORMANT')),
    ('production_status_escalation', mutate_domain_status('production_operations', 'SIGNED_PRODUCTION_READY')),
    ('calibration_evidence_requirement_removed', remove_requirement('operational_calibration', 'held_out_evaluation')),
    ('treatment_attestation_requirement_removed', remove_requirement('treatment_legitimacy', 'independent_attestation')),
    ('causal_identification_requirement_removed', remove_requirement('causal_aar', 'identification_assumptions')),
    ('domain_removed', remove_domain),
    ('profile_patient_care_escalation', profile_edit(['authority', 'patient_care_use'], 'GRANTED')),
    ('profile_concrete_treatment_activation', profile_edit(['authority', 'concrete_treatment_activation'], True)),
    ('profile_operational_calibration_promotion', profile_edit(['authority', 'operational_parameters_calibrated'], True)),
    ('profile_dynamic_physiology_promotion', profile_edit(['operational_model', 'patient_observation_policy', 'dynamic_physiology_validated'], True)),
    ('unsupported_causal_public_claim', inject_public_claim),
]


def copy_fixture(source: Path, target: Path) -> None:
    for rel in FILES:
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / rel, dest)


def run(repo: Path) -> tuple[str, list[str]]:
    completed = subprocess.run(
        [sys.executable, 'scripts/check_facility_decision_validity_boundaries.py', '--repo', '.', '--json-output', 'reports/result.json'],
        cwd=repo, text=True, capture_output=True,
    )
    try:
        payload = json.loads(completed.stdout)
    except Exception:
        return 'INTERNAL_ERROR', [completed.stderr[-500:] or completed.stdout[-500:]]
    if completed.returncode == 0 and payload.get('status') == 'PASS': return 'PASS', payload.get('errors', [])
    if completed.returncode != 0 and payload.get('status') == 'FAIL' and isinstance(payload.get('errors'), list): return 'REJECTED', payload['errors']
    return 'INTERNAL_ERROR', payload.get('errors', []) if isinstance(payload, dict) else []


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--repo', default='.'); parser.add_argument('--json-output', default=REPORT.as_posix()); args=parser.parse_args()
    repo = Path(args.repo).resolve(); errors=[]; results=[]
    status, detail = run(repo)
    results.append({'case_id': 'baseline', 'classification': status, 'pass': status == 'PASS', 'checker_errors': detail})
    if status != 'PASS': errors.append('baseline did not pass')
    for case_id, mutation in CASES:
        with tempfile.TemporaryDirectory(prefix='asklepios-validity-boundary-') as temp:
            candidate = Path(temp) / 'repo'; candidate.mkdir(); copy_fixture(repo, candidate); mutation(candidate)
            observed, detail = run(candidate); passed = observed == 'REJECTED'
            if not passed: errors.append(f'{case_id}:expected=REJECTED:observed={observed}')
            results.append({'case_id': case_id, 'classification': observed, 'pass': passed, 'checker_errors': detail})
    report = {
        'schema_version': '1.0.0', 'status': 'PASS' if not errors else 'FAIL',
        'cases': len(results), 'attacks': len(CASES),
        'accepted_escalations': sum(1 for row in results[1:] if row['classification'] == 'PASS'),
        'internal_errors': sum(1 for row in results[1:] if row['classification'] == 'INTERNAL_ERROR'),
        'results': results, 'errors': errors,
    }
    report = finalize_adversarial_report(report, baseline_case_ids=("baseline",))
    out = repo / args.json_output; out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(report, indent=2, sort_keys=True)+'\n', encoding='utf-8', newline='\n'); print(json.dumps(report, indent=2, sort_keys=True)); return 0 if not errors else 3


if __name__ == '__main__': raise SystemExit(main())
