#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from portable_test_workspace import WORKSPACE_PROFILE, compact_case_name, temporary_workspace

POLICY = Path('config/scenario-science/BEHAVIORAL_DIVERSITY_POLICY.json')
ARCHIVE = Path('reports/scenario-behavioral-equivalence.json')
CHECKER = Path('scripts/check_scenario_behavioral_equivalence.py')

def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def rehash_policy(value: dict[str, Any]) -> None:
    body = dict(value); body.pop('policy_sha256', None); value['policy_sha256'] = sha(body)

def rehash_archive(value: dict[str, Any]) -> None:
    body = dict(value); body.pop('archive_root_sha256', None); value['archive_root_sha256'] = sha(body)

def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + '\n', encoding='utf-8', newline='\n')

def run(repo: Path) -> tuple[int, dict[str, Any]]:
    output = repo / 'reports/test-result.json'
    completed = subprocess.run(
        [sys.executable, str(repo / CHECKER), '--repo', str(repo), '--json-output', 'reports/test-result.json'],
        cwd=repo, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env={**os.environ, 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONUTF8':'1'}, timeout=30,
    )
    try: result = json.loads(output.read_text(encoding='utf-8'))
    except Exception: result = {'classification':'INTERNAL_ERROR','errors':[completed.stdout[-2000:]]}
    return completed.returncode, result

def mutate_policy_floor(repo: Path) -> None:
    p=json.loads((repo/POLICY).read_text()); p['ratchet_floors']['minimum_policy_equivalence_classes']=1; rehash_policy(p); write(repo/POLICY,p)

def mutate_archive_root(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['archive_root_sha256']='0'*64; write(repo/ARCHIVE,a)

def mutate_context_hash(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['candidates'][0]['context_signature_sha256']='0'*64; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_policy_hash(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['candidates'][0]['policy_signature_sha256']='1'*64; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_profile_relabel(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['candidates'][0]['operational_behavior_profile_id']='RESOURCE_COORDINATION_REQUIRED'; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_class_member(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['equivalence_classes'][0]['candidate_ids']=a['equivalence_classes'][0]['candidate_ids'][1:]; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_remove_class(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['equivalence_classes']=a['equivalence_classes'][:-1]; a['summary']['policy_equivalence_classes']-=1; a['summary']['unique_policy_signatures']-=1; a['summary']['context_only_variant_count']+=1; a['summary']['policy_novelty_ratio_bps']=(len(a['equivalence_classes'])*10000)//len(a['candidates']); rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_narrative_novelty(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['summary']['narrative_or_provenance_only_changes_create_policy_novelty']=True; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_authority(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['truth_boundaries']['clinical_authority']='GRANTED'; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_duplicate_candidate(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['candidates'].append(copy.deepcopy(a['candidates'][0])); a['summary']['candidate_count']+=1; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_summary(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['summary']['policy_equivalence_classes']=99; rehash_archive(a); write(repo/ARCHIVE,a)

def mutate_unknown_profile(repo: Path) -> None:
    a=json.loads((repo/ARCHIVE).read_text()); a['candidates'][0]['operational_behavior_profile_id']='UNREVIEWED_PROFILE'; rehash_archive(a); write(repo/ARCHIVE,a)

CASES: list[tuple[str, bool, str | None, Callable[[Path], None] | None]] = [
    ('baseline', True, None, None),
    ('policy-floor-lowering-rehashed', False, 'policy compiled anchor differs', mutate_policy_floor),
    ('archive-root-forgery', False, 'archive root differs', mutate_archive_root),
    ('context-signature-forgery-rehashed', False, 'context signature differs', mutate_context_hash),
    ('policy-signature-forgery-rehashed', False, 'policy signature differs', mutate_policy_hash),
    ('profile-relabeling-rehashed', False, 'collapses reviewed operational profiles', mutate_profile_relabel),
    ('class-member-omission-rehashed', False, 'candidate inventory differs', mutate_class_member),
    ('policy-class-removal-rehashed', False, 'class inventory differs from candidates', mutate_remove_class),
    ('narrative-novelty-promotion-rehashed', False, 'archive summary differs', mutate_narrative_novelty),
    ('clinical-authority-escalation-rehashed', False, 'archive authority boundaries differ', mutate_authority),
    ('duplicate-candidate-rehashed', False, 'candidate duplicated', mutate_duplicate_candidate),
    ('summary-inflation-rehashed', False, 'archive summary differs', mutate_summary),
    ('unknown-operational-profile-rehashed', False, 'operational profile differs', mutate_unknown_profile),
]

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--repo',type=Path,default=Path('.')); parser.add_argument('--json-output',default='reports/scenario-behavioral-equivalence-mutations.json'); args=parser.parse_args()
    source=args.repo.resolve(); results=[]; errors=[]
    with temporary_workspace('ask-be-') as workspace:
        template=workspace/'template';
        for rel in [POLICY,ARCHIVE,CHECKER]:
            target=template/rel; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(source/rel,target)
        for case_id, expected_pass, required_error, mutation in CASES:
            repo=workspace/compact_case_name(case_id); shutil.copytree(template,repo)
            if mutation: mutation(repo)
            code,result=run(repo); observed=result.get('classification')=='PASS' and code==0
            messages=[str(x) for x in result.get('errors',[])]
            passed=(observed==expected_pass and (required_error is None or any(required_error in item for item in messages)))
            classification='PASS' if expected_pass and passed else ('EXPECTED_REJECTION' if not expected_pass and passed else 'FAIL')
            results.append({'case_id':case_id,'classification':classification,'expected_pass':expected_pass,'observed_pass':observed,'required_error':required_error,'checker_errors':messages,'pass':passed})
            if not passed: errors.append(f'{case_id} did not meet expectation')
    report={'schema_version':'1.0.0','classification':'PASS' if not errors else 'FAIL','cases':len(results),'attacks':len(results)-1,'accepted_attacks':sum(1 for r in results[1:] if r['observed_pass']),'workspace_profile':WORKSPACE_PROFILE,'errors':errors,'results':results}
    out=(source/args.json_output).resolve(); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,indent=2,sort_keys=True)); return 0 if not errors else 3
if __name__=='__main__': sys.exit(main())
