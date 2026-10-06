#!/usr/bin/env python3
from __future__ import annotations
import copy, json, re
from pathlib import Path
from release_result import finalize_adversarial_report

ROOT=Path.cwd()
MODULE_PATH=ROOT/'formal/ScenarioContracts/FacilityDecisionIntegrity.lean'
AUDIT_PATH=ROOT/'formal/FacilityDecisionIntegrityAxiomAudit.lean'
MANIFEST_PATH=ROOT/'formal/FACILITY_DECISION_INTEGRITY_TRUST_MANIFEST.json'
ROOT_PATH=ROOT/'formal/ScenarioContracts.lean'
THEOREM_RE=re.compile(r"(?m)^theorem\s+([A-Za-z0-9_']+)")
AUDIT_RE=re.compile(r"(?m)^#print axioms ScenarioContracts\.([A-Za-z0-9_']+)\s*$")


def strip_comments(text:str)->str:
 out=[];i=0;depth=0
 while i<len(text):
  if depth==0 and text.startswith('--',i):
   end=text.find('\n',i);out.append('\n');i=len(text) if end<0 else end+1;continue
  if text.startswith('/-',i):depth+=1;i+=2;continue
  if depth and text.startswith('-/',i):depth-=1;i+=2;continue
  if depth:
   if text[i]=='\n':out.append('\n')
   i+=1;continue
  out.append(text[i]);i+=1
 if depth:raise ValueError('unterminated Lean block comment')
 return ''.join(out)


def theorem_block(text:str,name:str)->str:
 marker=f'theorem {name}';start=text.find(marker)
 if start<0:return ''
 boundary=re.search(r"(?m)^\s*(?:inductive|def|theorem|structure|abbrev|example|end)\s+",text[start+len(marker):])
 end=len(text) if boundary is None else start+len(marker)+boundary.start()
 return text[start:end]


def check(module:str,audit:str,manifest:dict,root:str)->list[str]:
 errors=[]
 try:clean=strip_comments(module)
 except ValueError as exc:return [str(exc)]
 expected_full=manifest.get('required_theorems',[]);expected=[x.rsplit('.',1)[-1] for x in expected_full]
 declared=THEOREM_RE.findall(clean);audited=AUDIT_RE.findall(audit)
 if len(declared)!=len(set(declared)):errors.append('duplicate theorem declaration')
 if sorted(declared)!=sorted(expected):errors.append('manifest/theorem inventory mismatch')
 if sorted(audited)!=sorted(expected):errors.append('axiom audit/theorem inventory mismatch')
 if manifest.get('per_theorem_axioms')!={name:[] for name in expected_full}:errors.append('nonempty or malformed theorem axiom budget')
 if re.search(r'(^|[^A-Za-z0-9_])(sorry|admit)([^A-Za-z0-9_]|$)',clean):errors.append('incomplete proof placeholder')
 if 'True :=' in clean or ': True :=' in clean:errors.append('tautological theorem surface forbidden')
 normalized=' '.join(clean.split())
 semantic=[
  'clinical := state.clinical',
  '| DecisionTreatmentRuleStatus.notAdjudicated => false',
  'providerInScope && patientEligible && sourceAttested',
  '| DecisionOrderStatus.absent => false',
  '| DecisionOrderStatus.queued => false',
  '| DecisionOrderStatus.completed => true',
  '(_lastActionId : Nat)',
  'receiverAcknowledged && questionsOffered && senderConfirmed',
  'def decisionPatientCareUseAllowed : Bool := false',
 ]
 for fragment in semantic:
  if ' '.join(fragment.split()) not in normalized:errors.append(f'reviewed semantic definition changed:{fragment}')
 exact_rfl={
 'decision_operational_transition_preserves_clinical':'(applyDecisionOperationalPatch state patch).clinical = state.clinical := rfl',
 'decision_learner_projection_ignores_instructor_score':'projectDecisionLearnerView clinical elapsed observations rightScore provenance := rfl',
 'decision_learner_projection_ignores_provenance':'projectDecisionLearnerView clinical elapsed observations score rightProvenance := rfl',
 'decision_unadjudicated_treatment_is_blocked':'providerInScope patientEligible sourceAttested = false := rfl',
 'decision_missing_scope_blocks_treatment':'false patientEligible sourceAttested = false := rfl',
 'decision_missing_eligibility_blocks_treatment':'true false sourceAttested = false := rfl',
 'decision_missing_source_attestation_blocks_treatment':'true true false = false := rfl',
 'decision_absent_order_blocks_result':'decisionResultVisible DecisionOrderStatus.absent = false := rfl',
 'decision_queued_order_blocks_result':'decisionResultVisible DecisionOrderStatus.queued = false := rfl',
 'decision_completed_order_allows_result':'decisionResultVisible DecisionOrderStatus.completed = true := rfl',
 'decision_world_event_independent_of_action_identity':'decisionSecondCasualtyVisible elapsed rightAction := rfl',
 'decision_handoff_without_ack_is_blocked':'decisionHandoffTransferred false questionsOffered senderConfirmed = false := rfl',
 'decision_handoff_without_questions_is_blocked':'decisionHandoffTransferred true false senderConfirmed = false := rfl',
 'decision_handoff_without_sender_confirmation_is_blocked':'decisionHandoffTransferred true true false = false := rfl',
 'decision_complete_closed_loop_handoff_transfers':'decisionHandoffTransferred true true true = true := rfl',
 'decision_training_prohibits_patient_care':'decisionPatientCareUseAllowed = false := rfl',
 }
 norm=lambda x:' '.join(x.split())
 for name,fragment in exact_rfl.items():
  block=theorem_block(clean,name)
  if not block or norm(fragment) not in norm(block):errors.append(f'reviewed theorem changed:{name}')
  if any(token in block for token in ('simp','native_decide','bv_decide','Classical','propext','Lean.ofReduceBool')):errors.append(f'unreviewed proof mechanism:{name}')
 replay=theorem_block(clean,'decision_operational_replay_preserves_clinical')
 for req in ('induction patches generalizing state','decision_operational_transition_preserves_clinical','Eq.trans'):
  if req not in replay:errors.append(f'replay proof missing:{req}')
 lines=root.splitlines();required='import ScenarioContracts.FacilityDecisionIntegrity'
 if lines.count(required)!=1:errors.append('decision-integrity root import count')
 else:
  pos=lines.index(required);first_non=next((i for i,l in enumerate(lines) if l.strip() and not l.startswith('import ')),len(lines))
  if pos>=first_non:errors.append('decision-integrity import is not in import block')
 return sorted(set(errors))

module=MODULE_PATH.read_text();audit=AUDIT_PATH.read_text();manifest=json.loads(MANIFEST_PATH.read_text());root=ROOT_PATH.read_text()
cases=[]
def run(cid,m,a,mf,r,should):
 e=check(m,a,mf,r);cases.append({'case_id':cid,'pass':(not e) if should else bool(e),'errors':e})
run('reviewed_formal_source',module,audit,manifest,root,True)
run('clinical_projection_mutation_rejected',module.replace('clinical := state.clinical','clinical := { protectedHash := 0, clinicalScore := 0 }',1),audit,manifest,root,False)
run('treatment_self_adjudication_rejected',module.replace('| DecisionTreatmentRuleStatus.notAdjudicated => false','| DecisionTreatmentRuleStatus.notAdjudicated => true',1),audit,manifest,root,False)
run('missing_scope_bypass_rejected',module.replace('providerInScope && patientEligible && sourceAttested','patientEligible && sourceAttested',1),audit,manifest,root,False)
run('result_without_order_rejected',module.replace('| DecisionOrderStatus.absent => false','| DecisionOrderStatus.absent => true',1),audit,manifest,root,False)
run('world_event_action_coupling_rejected',module.replace('(_lastActionId : Nat)', '(lastActionId : Nat)',1).replace('decide (240 ≤ elapsedSeconds)','decide (240 ≤ elapsedSeconds + lastActionId)',1),audit,manifest,root,False)
run('handoff_ack_bypass_rejected',module.replace('receiverAcknowledged && questionsOffered && senderConfirmed','questionsOffered && senderConfirmed',1),audit,manifest,root,False)
run('patient_care_authorization_rejected',module.replace('def decisionPatientCareUseAllowed : Bool := false','def decisionPatientCareUseAllowed : Bool := true',1),audit,manifest,root,False)
run('proof_hole_rejected',module+'\nexample : True := by sorry\n',audit,manifest,root,False)
run('tautology_rejected',module+'\ntheorem decision_fake : True := by trivial\n',audit,manifest,root,False)
run('missing_theorem_rejected',module.replace('theorem decision_complete_closed_loop_handoff_transfers','def decision_complete_closed_loop_handoff_transfers',1),audit,manifest,root,False)
run('missing_audit_entry_rejected',module,audit.replace('#print axioms ScenarioContracts.decision_complete_closed_loop_handoff_transfers\n','',1),manifest,root,False)
wide=copy.deepcopy(manifest);wide['per_theorem_axioms'][wide['required_theorems'][0]]=['propext'];run('widened_axiom_budget_rejected',module,audit,wide,root,False)
run('misplaced_import_rejected',module,audit,manifest,root.replace('import ScenarioContracts.FacilityDecisionIntegrity\n','')+'\nimport ScenarioContracts.FacilityDecisionIntegrity\n',False)
failed=[x['case_id'] for x in cases if not x['pass']]
report={'schema_version':'1.0.0','status':'PASS' if not failed else 'FAIL','theorem_count':len(THEOREM_RE.findall(strip_comments(module))),'cases':len(cases),'errors':failed,'results':cases}
report=finalize_adversarial_report(report,baseline_case_ids=('reviewed_formal_source',))
out=ROOT/'reports/facility-decision-formal-static.json'
out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(report,indent=2));raise SystemExit(0 if not failed else 3)
