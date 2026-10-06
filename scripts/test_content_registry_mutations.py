#!/usr/bin/env python3
from __future__ import annotations
import copy, json, tempfile
from pathlib import Path
from content_registry_core import refresh_registry_hashes, validate_registry, sha256_json

ROOT=Path.cwd()
BASE=json.loads((ROOT/'public/data/content_registry/content_registry.json').read_text(encoding='utf-8'))

def rehash(value): return refresh_registry_hashes(value)
def rejected(value): return validate_registry(value,ROOT)['status']=='FAIL'

cases=[]
def case(name, mutate, rehash_after=True):
    value=copy.deepcopy(BASE); mutate(value)
    if rehash_after: value=rehash(value)
    ok=rejected(value)
    cases.append({'case_id':name,'rejected':ok})

def drop_template(d): d['assets']=[a for a in d['assets'] if a.get('asset_id')!='template:ASK-A-002']; d['counts']['assets']-=1; d['counts']['assets_by_kind']['protected_template']-=1
def duplicate_asset(d): d['assets'].append(copy.deepcopy(d['assets'][0])); d['counts']['assets']+=1
def source_forgery(d): d['assets'][0]['source']['file_sha256']='0'*64
def evidence_escalation(d):
    a=next(x for x in d['assets'] if x['kind']=='research_evidence_reference'); a['capabilities'].append('define_new_clinical_rule')
def deploy_seed(d): next(x for x in d['assets'] if x['kind']=='scenario_seed')['status']='deployable'
def self_certify(d):
    a=d['evidence_attestations'][0]; a.update({'relation':'SUPPORTS','entailment_status':'VERIFIED','human_review_status':'APPROVED','independent_verifiers':['generator']})
def admit_claim(d): d['claim_candidates'][0]['admission_status']='ADMITTED'
def unknown_evidence(d): d['claim_candidates'][0]['evidence_asset_ids'].append('evidence:unknown')
def licensed_text(d): d['assets'][0]['metadata']['licensed_text']='forbidden'
def force_active(d): d['compatibility_profiles'][0]['activation_status']='ACTIVE'
def remove_attestation(d): d['evidence_attestations'].pop(); d['counts']['evidence_attestations']-=1
def truth_bit(d): d['claim_candidates'][0]['support_bit']=True
def path_traversal(d): d['source_snapshot']['source_files'][0]['path']='../secret'
def boundary_escalation(d): d['release_boundary']['clinical_authority']='GRANTED'
def root_forgery(d): d['roots']['registry_merkle_root']='f'*64

for name,fn,reh in [
 ('drop_protected_template',drop_template,True),('duplicate_asset_id',duplicate_asset,True),
 ('forged_source_hash_with_rehash',source_forgery,True),('research_capability_escalation',evidence_escalation,True),
 ('seed_deployability_escalation',deploy_seed,True),('evidence_self_certification',self_certify,True),
 ('claim_admitted_without_review',admit_claim,True),('claim_unknown_evidence',unknown_evidence,True),
 ('licensed_text_in_public_registry',licensed_text,True),('forced_engine_activation',force_active,True),
 ('removed_attestation',remove_attestation,True),('unreviewed_truth_bit',truth_bit,True),
 ('source_path_traversal',path_traversal,True),('clinical_boundary_escalation',boundary_escalation,True),
 ('forged_registry_root',root_forgery,False),
]: case(name,fn,reh)

errors=[row['case_id'] for row in cases if not row['rejected']]
report={'schema_version':'1.0.0','status':'PASS' if not errors else 'FAIL','cases':len(cases),'passed':len(cases)-len(errors),'errors':errors,'results':cases,'anti_circular_note':'Semantic attacks are rehashed before validation; rejection cannot rely only on stale digests.'}
print(json.dumps(report,indent=2))
raise SystemExit(0 if not errors else 3)
