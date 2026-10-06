#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any

BASE = Path('examples/facility-decision')
MANIFEST = BASE / 'manifest.json'
REPORT = Path('reports/facility-decision-artifacts-python.json')
MODES = {
    'learner-projection.json': 'learner_assessment',
    'teaching-projection.json': 'learner_teaching',
    'instructor-projection.json': 'instructor',
    'demo-projection.json': 'stakeholder_demo',
}
RESTRICTED = {
    'instructor','demo','normalized_source_score_bps','source_binding','facility_certificate',
    'wit_observations','profile_authority','source_action_id','source_origin',
    'autoplay_available','completed_replay_available','branch_controls',
}


def canonical_json(value: Any) -> str:
    if value is None: return 'null'
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value, str): return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, int): return str(value)
    if isinstance(value, float):
        if not value == value or value in (float('inf'), float('-inf')): raise ValueError('nonfinite')
        if value == 0: return '0'
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, list): return '[' + ','.join(canonical_json(item) for item in value) + ']'
    if isinstance(value, dict):
        return '{' + ','.join(json.dumps(str(key), ensure_ascii=False) + ':' + canonical_json(value[key]) for key in sorted(value)) + '}'
    raise TypeError(type(value).__name__)


def sha_obj(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding='utf-8'))


def walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from walk_keys(child)
    elif isinstance(value, list):
        for child in value: yield from walk_keys(child)


def verify_session(session: dict[str, Any], label: str, errors: list[str], check) -> None:
    root = session.get('decision_root_sha256')
    without = dict(session); without.pop('decision_root_sha256', None)
    check(root == sha_obj(without), f'{label}:decision root mismatch')
    records = session.get('decision_records', [])
    submissions = {item.get('submission_id'): item for item in session.get('submissions', [])}
    prior = sha_obj([])
    for index, record in enumerate(records, 1):
        check(record.get('sequence') == index, f'{label}:record sequence:{index}')
        check(record.get('prior_record_sha256') == prior, f'{label}:record predecessor:{index}')
        rec = dict(record); digest = rec.pop('record_sha256', None)
        check(digest == sha_obj(rec), f'{label}:record hash:{index}')
        sub = submissions.get(record.get('submission_id'))
        check(sub is not None and record.get('payload_sha256') == sha_obj(sub), f'{label}:payload hash:{index}')
        prior = str(digest)
    check(session.get('decision_chain_root_sha256') == prior, f'{label}:chain root mismatch')
    check(session.get('facility_session', {}).get('final_state', {}).get('terminal_status') == 'completed', f'{label}:terminal status')
    check(session.get('facility_session', {}).get('normalized_score_bps') == 10000, f'{label}:source score')
    check(session.get('handoff', {}).get('responsibility_transferred_at_seconds') is not None, f'{label}:handoff incomplete')
    check(not session.get('facility_session', {}).get('final_state', {}).get('unsafe_source_action_ids'), f'{label}:unsafe action present')


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--repo',default='.'); parser.add_argument('--json-output',default=REPORT.as_posix()); args=parser.parse_args()
    repo=Path(args.repo).resolve(); errors=[]; checks=0
    def check(condition: bool, message: str):
        nonlocal checks; checks += 1
        if not condition: errors.append(message)

    required = [MANIFEST, BASE/'reference-session.json', BASE/'alternate-session.json', BASE/'README.md', *[BASE/p for p in MODES]]
    for rel in required: check((repo/rel).is_file(), f'missing:{rel.as_posix()}')
    if errors:
        manifest={}
    else:
        manifest=load(repo/MANIFEST)
        binding=manifest.get('manifest_binding_sha256'); body=dict(manifest); body.pop('manifest_binding_sha256',None)
        check(binding == sha_obj(body), 'manifest binding mismatch')
        for name, meta in manifest.get('files',{}).items():
            path=repo/BASE/name
            check(path.is_file(), f'manifest file missing:{name}')
            if path.is_file():
                data=path.read_bytes(); check(len(data)==meta.get('bytes'), f'manifest bytes:{name}'); check(sha_bytes(data)==meta.get('sha256'), f'manifest hash:{name}')
        profile=load(repo/'config/facility-decision/ASK-D-001.json')
        check(manifest.get('profile_id')==profile.get('profile_id'),'profile binding')
        check(manifest.get('source_scenario_id')=='ASK-D-001','scenario binding')
        check(manifest.get('authority')==profile.get('authority'),'authority binding')
        check(profile.get('authority',{}).get('patient_care_use')=='PROHIBITED','patient care escalated')
        check(profile.get('authority',{}).get('concrete_treatment_activation') is False,'treatment activated')
        canonical=load(repo/BASE/'reference-session.json'); alternate=load(repo/BASE/'alternate-session.json')
        verify_session(canonical,'canonical',errors,check); verify_session(alternate,'alternate',errors,check)
        check(canonical.get('decision_root_sha256')==manifest.get('canonical_decision_root_sha256'),'canonical root binding')
        check(alternate.get('decision_root_sha256')==manifest.get('alternate_decision_root_sha256'),'alternate root binding')
        check([item.get('decision_id') for item in canonical.get('submissions',[])]==manifest.get('canonical_sequence'),'canonical sequence binding')
        check([item.get('decision_id') for item in alternate.get('submissions',[])]==manifest.get('alternate_sequence'),'alternate sequence binding')
        check(manifest.get('canonical_sequence') != manifest.get('alternate_sequence'), 'reference sequences collapsed')
        for name, mode in MODES.items():
            view=load(repo/BASE/name); check(view.get('ui_mode')==mode,f'projection mode:{name}')
            keys=set(walk_keys(view))
            if mode.startswith('learner_'):
                check(not keys.intersection(RESTRICTED), f'learner leakage:{name}:{sorted(keys.intersection(RESTRICTED))}')
                check('instructor' not in view and 'demo' not in view,f'learner privileged block:{name}')
            if mode=='instructor': check(isinstance(view.get('instructor'),dict) and 'demo' not in view,'instructor projection boundary')
            if mode=='stakeholder_demo': check(isinstance(view.get('instructor'),dict) and isinstance(view.get('demo'),dict),'demo projection boundary')
        readme=(repo/BASE/'README.md').read_text(encoding='utf-8')
        for route in manifest.get('role_routes',{}).values(): check(route in readme,f'README route missing:{route}')
        check('NOT_CALIBRATED' in readme,'README calibration limit missing')
        check('patient-care' in readme.lower(),'README patient-care boundary missing')

    report={'schema_version':'1.0.0','status':'PASS' if not errors else 'FAIL','checks':checks,'release_id':manifest.get('release_id') if isinstance(manifest,dict) else None,'errors':sorted(set(errors))}
    out=repo/args.json_output; out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n'); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if not errors else 1
if __name__=='__main__': raise SystemExit(main())
