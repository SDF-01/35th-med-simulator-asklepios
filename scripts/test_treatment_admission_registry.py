#!/usr/bin/env python3
from __future__ import annotations
import argparse, copy, hashlib, json, os, shutil, subprocess, sys, tempfile
from pathlib import Path
from typing import Any, Callable


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def rehash(registry: dict[str, Any]) -> None:
    body = dict(registry); body.pop('registry_sha256', None)
    registry['registry_sha256'] = hashlib.sha256(canonical(body)).hexdigest()

def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')

def run(repo: Path) -> tuple[int, str]:
    commands = [
        [sys.executable, 'scripts/check_treatment_admission_registry.py', '--repo', '.', '--mode', 'check', '--json-output', 'reports/treatment-admission-registry.json'],
        ['node', 'scripts/check_treatment_admission_registry.mjs', '--repo', '.', '--json-output', 'reports/treatment-admission-registry-node.json'],
    ]
    combined: list[str] = []
    returncode = 0
    for command in commands:
        process = subprocess.run(command, cwd=repo, text=True, capture_output=True, timeout=45)
        returncode = max(returncode, process.returncode)
        combined.append(process.stdout)
        combined.append(process.stderr)
    return returncode, ''.join(combined)[-4000:]

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument('--repo', default='.'); parser.add_argument('--json-output', default='reports/treatment-admission-registry-mutations.json'); args = parser.parse_args()
    root = Path(args.repo).resolve()
    baseline = json.loads((root / 'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json').read_text())
    source = json.loads((root / 'config/facility-decision/ASK-D-001.json').read_text())
    projection = json.loads((root / 'public/data/scenario_library/treatment-admission.json').read_text())
    cases: list[tuple[str, bool, Callable[[Path, dict[str, Any], dict[str, Any], dict[str, Any]], None]]] = []
    cases.append(('baseline', True, lambda *_: None))
    cases.append(('state_order_weakened', False, lambda _r, reg, _s, _p: (reg['state_order'].pop(), rehash(reg))))
    cases.append(('direct_care_promoted', False, lambda _r, reg, _s, _p: (reg['boundaries'].__setitem__('direct_patient_care', 'PERMITTED'), rehash(reg))))
    cases.append(('blocked_treatment_activated', False, lambda _r, reg, _s, _p: (reg['entries'][0].__setitem__('simulation_admitted', True), reg['entries'][0].__setitem__('concrete_treatment_allowed', True), rehash(reg))))
    cases.append(('admitted_with_missing_requirements', False, lambda _r, reg, src, _p: (reg['entries'][0].__setitem__('current_state', 'SIMULATION_ADMITTED'), reg['entries'][0].__setitem__('simulation_admitted', True), reg['entries'][0].__setitem__('concrete_treatment_allowed', True), src['treatment_policies'][0].__setitem__('concrete_treatment_allowed', True), rehash(reg))))
    cases.append(('source_profile_action_drift', False, lambda _r, _reg, src, _p: src['treatment_policies'][0].__setitem__('facility_action_id', 'different_action')))
    cases.append(('source_inventory_removed', False, lambda _r, _reg, src, _p: src['treatment_policies'].pop()))
    cases.append(('missing_requirements_removed', False, lambda _r, reg, _s, _p: (reg['entries'][0].__setitem__('missing_requirements', []), rehash(reg))))
    cases.append(('projection_choice_promoted', False, lambda _r, _reg, _s, proj: proj['entries'][0].__setitem__('learner_choice_status', 'AVAILABLE')))
    cases.append(('projection_root_forged', False, lambda _r, _reg, _s, proj: proj.__setitem__('projection_sha256', '0' * 64)))
    cases.append(('duplicate_treatment_id', False, lambda _r, reg, _s, _p: (reg['entries'].append(copy.deepcopy(reg['entries'][0])), rehash(reg))))
    cases.append(('unsafe_projection_path', False, lambda _r, reg, _s, _p: (reg.__setitem__('public_projection_path', '../escape.json'), rehash(reg))))
    results=[]; accepted=0
    with tempfile.TemporaryDirectory(prefix='asklepios-treatment-admission-') as temporary:
      base = Path(temporary) / 'base'; shutil.copytree(root, base, ignore=shutil.ignore_patterns('.git','node_modules','.asklepios','__pycache__','*.pyc'))
      for case_id, expected_pass, mutate in cases:
        fixture = Path(temporary) / case_id; shutil.copytree(base, fixture)
        reg=copy.deepcopy(baseline); src=copy.deepcopy(source); proj=copy.deepcopy(projection)
        try: mutate(fixture, reg, src, proj)
        except Exception as exc: results.append({'case_id':case_id,'classification':'INTERNAL_ERROR','pass':False,'error':str(exc)}); continue
        write(fixture/'config/scenario-science/TREATMENT_ADMISSION_REGISTRY.json', reg); write(fixture/'config/facility-decision/ASK-D-001.json', src); write(fixture/'public/data/scenario_library/treatment-admission.json', proj)
        code, detail=run(fixture); observed=code==0; passed=observed==expected_pass
        if not expected_pass and observed: accepted += 1
        results.append({'case_id':case_id,'classification':'PASS' if expected_pass and observed else 'EXPECTED_REJECTION' if (not expected_pass and not observed) else 'FAIL','pass':passed,'observed_pass':observed,'detail':detail[-1000:]})
    errors=[item['case_id'] for item in results if not item['pass']]
    report={'schema_version':'1.0.0','classification':'PASS' if not errors else 'FAIL','status':'PASS' if not errors else 'FAIL','cases':len(results),'attacks':len(results)-1,'accepted_attacks':accepted,'errors':errors,'results':results}
    write(root/args.json_output, report); print(json.dumps(report, indent=2)); return 0 if not errors else 3
if __name__=='__main__': raise SystemExit(main())
