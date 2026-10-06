#!/usr/bin/env python3
"""Monotonic, independently compiled technical-debt ratchet."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from typing import Any
from release_graph_core import load_graph, stage_map
from scenario_genome_common import GenomeError, atomic_write_json, canonical_sha256, load_object, safe_repo_path
sys.dont_write_bytecode = True
POLICY_PATH = "config/release/TECHNICAL_DEBT_RATCHET.json"
REGISTER_PATH = "config/release/TECHNICAL_DEBT_REGISTER.json"
COMPILED_RATCHET_ID = "asklepios-technical-debt-ratchet-v1"
COMPILED_RATCHET_EPOCH = 8
COMPILED_REQUIRED_CONTRACT = {'absolute_debt_free_claim_permitted': False,
 'maximum_accepted_risks': 0,
 'permitted_release_claim': 'No known release-blocking technical debt remains within the machine-checked '
                            'scope and current authenticated evidence.',
 'requires_current_graph_hash': True,
 'requires_current_output_hashes': True,
 'stale_committed_reports_may_satisfy_gate': False,
 'terminal_evidence_stage': 'final.decision-evidence'}
COMPILED_ENTRY_FLOORS: dict[str, dict[str, Any]] = {'TD-BEHAVIOR-ARCHIVE-015': {'evidence_stages': ['scenario.contracts',
                                                 'scenario.behavior-archive-check',
                                                 'scenario.behavior-archive-attacks',
                                                 'scenario.capability-ratchet-attacks',
                                                 'scenario.evolution-evidence'],
                             'release_blocker': True,
                             'state': 'CLOSED'},
 'TD-BUILD-003': {'evidence_stages': ['build.app-typecheck', 'build.double-reproducibility'],
                  'release_blocker': True,
                  'state': 'CLOSED'},
 'TD-CANONICAL-STAKEHOLDER-TREATMENT-018': {'evidence_stages': ['scenario.treatment-admission',
                                                                'scenario.treatment-admission-check',
                                                                'scenario.treatment-admission-attacks',
                                                                'scenario.stakeholder-product',
                                                                'scenario.stakeholder-product-check',
                                                                'scenario.stakeholder-product-attacks',
                                                                'scenario.capability-ratchet-attacks',
                                                                'scenario.evolution-evidence'],
                                            'release_blocker': True,
                                            'state': 'CLOSED'},
 'TD-DEBT-RATCHET-012': {'evidence_stages': ['release.debt-ratchet', 'release.debt-ratchet-attacks'],
                         'release_blocker': True,
                         'state': 'CLOSED'},
 'TD-DIRECT-PATIENT-CARE-007': {'evidence_stages': ['release.intended-use-policy'],
                                'release_blocker': False,
                                'state': 'OUT_OF_SCOPE'},
 'TD-ENGINE-DOCS-009': {'evidence_stages': ['standalone.generate',
                                            'standalone.contracts',
                                            'scenario.engine-evolution-docs-python',
                                            'scenario.engine-evolution-docs-node',
                                            'scenario.engine-evolution-doc-attacks',
                                            'scenario.evolution-evidence'],
                        'release_blocker': True,
                        'state': 'CLOSED'},
 'TD-HUB-SECURITY-008': {'evidence_stages': ['hub.security-source', 'hub.security-attacks', 'hub.runtime-smoke'],
                         'release_blocker': True,
                         'state': 'CLOSED'},
 'TD-INTENDED-USE-005': {'evidence_stages': ['release.intended-use-policy', 'release.intended-use-attacks'],
                         'release_blocker': True,
                         'state': 'CLOSED'},
 'TD-NODE-CHECKER-CLI-010': {'evidence_stages': ['scenario.node-checker-cli-attacks'],
                             'release_blocker': True,
                             'state': 'CLOSED'},
 'TD-OFFLINE-RELEASE-013': {'evidence_stages': ['offline.release-python',
                                                'offline.release-node',
                                                'offline.release-attacks'],
                            'release_blocker': True,
                            'state': 'CLOSED'},
 'TD-PLAIN-LANGUAGE-019': {'evidence_stages': ['scenario.plain-language-summary',
                                               'scenario.plain-language-summary-check',
                                               'scenario.plain-language-summary-attacks',
                                               'scenario.capability-ratchet-attacks',
                                               'scenario.evolution-evidence'],
                           'release_blocker': True,
                           'state': 'CLOSED'},
 'TD-REAL-CLINICAL-TIMING-006': {'evidence_stages': ['simulation.timing-assurance'],
                                 'release_blocker': False,
                                 'state': 'OUT_OF_SCOPE'},
 'TD-RELEASE-GRAPH-001': {'evidence_stages': ['orchestration.graph-check', 'orchestration.graph-attacks'],
                          'release_blocker': True,
                          'state': 'CLOSED'},
 'TD-SCENARIO-EVIDENCE-002': {'evidence_stages': ['scenario.contracts', 'scenario.release-validation'],
                              'release_blocker': True,
                              'state': 'CLOSED'},
 'TD-SCENARIO-EVOLUTION-EVIDENCE-014': {'evidence_stages': ['scenario.evolution-evidence',
                                                            'scenario.evolution-evidence-attacks'],
                                        'release_blocker': True,
                                        'state': 'CLOSED'},
 'TD-SCENARIO-SCIENCE-016': {'evidence_stages': ['scenario.behavioral-policy',
                                                 'scenario.behavioral-policy-attacks',
                                                 'scenario.science-foundation',
                                                 'scenario.science-foundation-check',
                                                 'scenario.science-foundation-attacks',
                                                 'scenario.capability-ratchet-attacks',
                                                 'scenario.evolution-evidence'],
                             'release_blocker': True,
                             'state': 'CLOSED'},
 'TD-STAKEHOLDER-PRODUCT-017': {'evidence_stages': ['scenario.stakeholder-product',
                                                    'scenario.stakeholder-product-check',
                                                    'scenario.stakeholder-product-attacks',
                                                    'scenario.capability-ratchet-attacks',
                                                    'scenario.evolution-evidence'],
                                'release_blocker': True,
                                'state': 'CLOSED'},
 'TD-TIMING-004': {'evidence_stages': ['simulation.timing-assurance', 'simulation.timing-attacks'],
                   'release_blocker': True,
                   'state': 'CLOSED'},
 'TD-VERIFIED-EXAMPLE-HARNESS-011': {'evidence_stages': ['scenario.verified-example-attacks',
                                                         'scenario.node-checker-cli-attacks'],
                                     'release_blocker': True,
                                     'state': 'CLOSED'}}
COMPILED_REQUIRED_RECEIPTS = {'arrival.runtime-evidence-join',
 'build.app-typecheck',
 'build.double-reproducibility',
 'content.registry-source',
 'decision.artifact-attacks',
 'final.decision-evidence',
 'formal.exact-audit',
 'hub.runtime-smoke',
 'hub.security-attacks',
 'offline.release-attacks',
 'release.debt-ratchet',
 'release.debt-ratchet-attacks',
 'release.intended-use-attacks',
 'release.simulation-quality-attacks',
 'scenario.behavior-archive-attacks',
 'scenario.behavior-archive-check',
 'scenario.behavioral-policy',
 'scenario.behavioral-policy-attacks',
 'scenario.capability-ratchet-attacks',
 'scenario.contracts',
 'scenario.engine-evolution-doc-attacks',
 'scenario.evolution-evidence',
 'scenario.evolution-evidence-attacks',
 'scenario.node-checker-cli-attacks',
 'scenario.plain-language-summary',
 'scenario.plain-language-summary-attacks',
 'scenario.plain-language-summary-check',
 'scenario.release-validation',
 'scenario.science-foundation',
 'scenario.science-foundation-attacks',
 'scenario.science-foundation-check',
 'scenario.stakeholder-product',
 'scenario.stakeholder-product-attacks',
 'scenario.stakeholder-product-check',
 'scenario.treatment-admission',
 'scenario.treatment-admission-attacks',
 'scenario.treatment-admission-check',
 'scenario.verified-example-attacks',
 'simulation.timing-assurance',
 'standalone.contracts'}
COMPILED_RATCHET_ANCHOR = '84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91'

def policy_anchor(policy: dict[str, Any]) -> str:
    return canonical_sha256({
        "ratchet_id": policy.get("ratchet_id"), "ratchet_epoch": policy.get("ratchet_epoch"),
        "register_id": policy.get("register_id"), "required_entry_floors": policy.get("required_entry_floors"),
        "required_final_stage_receipts": policy.get("required_final_stage_receipts"),
        "required_contract": policy.get("required_contract"),
    })

def validate(repo: Path) -> dict[str, Any]:
    repo=repo.resolve(strict=True); errors=[]; checks=0
    def require(condition: bool, message: str) -> None:
        nonlocal checks; checks += 1
        if not condition: errors.append(message)
    policy=load_object(safe_repo_path(repo,POLICY_PATH)); register=load_object(safe_repo_path(repo,REGISTER_PATH)); graph=load_graph(repo); stages=stage_map(graph)
    require(policy.get("schema_version")=="1.0.0","technical-debt ratchet schema differs")
    require(policy.get("ratchet_id")==COMPILED_RATCHET_ID,"technical-debt ratchet ID differs")
    require(policy.get("ratchet_epoch")==COMPILED_RATCHET_EPOCH,"technical-debt ratchet epoch differs")
    require(policy.get("register_id")=="asklepios-release-debt-v1","technical-debt ratchet register ID differs")
    require(policy.get("required_entry_floors")==COMPILED_ENTRY_FLOORS,"technical-debt ratchet entry floor differs from compiled floor")
    require(set(policy.get("required_final_stage_receipts",[]))==COMPILED_REQUIRED_RECEIPTS,"technical-debt ratchet receipt floor differs from compiled floor")
    require(policy.get("required_contract")==COMPILED_REQUIRED_CONTRACT,"technical-debt ratchet contract differs from compiled floor")
    observed=policy_anchor(policy); require(observed==policy.get("ratchet_anchor_sha256"),"technical-debt ratchet self-anchor mismatch"); require(observed==COMPILED_RATCHET_ANCHOR,"technical-debt ratchet anchor differs from compiled monotonic anchor")
    require(register.get("register_id")==policy.get("register_id"),"technical-debt register identity differs at ratchet")
    require(register.get("absolute_debt_free_claim_permitted") is False,"absolute debt-free claim was enabled at ratchet")
    require(register.get("permitted_release_claim")==COMPILED_REQUIRED_CONTRACT["permitted_release_claim"],"technical-debt permitted claim differs at ratchet")
    entries=register.get("entries") if isinstance(register.get("entries"),list) else []
    ids=[e.get("debt_id") for e in entries if isinstance(e,dict)]; require(len(ids)==len(set(ids)),"technical-debt register has duplicate IDs")
    entry_map={e.get("debt_id"):e for e in entries if isinstance(e,dict) and isinstance(e.get("debt_id"),str)}
    require(set(entry_map)==set(COMPILED_ENTRY_FLOORS),"technical-debt register inventory differs from ratcheted inventory")
    accepted=0
    for debt_id,floor in sorted(COMPILED_ENTRY_FLOORS.items()):
        entry=entry_map.get(debt_id,{}); require(entry.get("state")==floor["state"],f"technical-debt state regressed:{debt_id}"); require(entry.get("release_blocker") is floor["release_blocker"],f"technical-debt blocker classification regressed:{debt_id}")
        evidence=entry.get("evidence_stages") if isinstance(entry.get("evidence_stages"),list) else []; require(set(evidence)>=set(floor["evidence_stages"]),f"technical-debt evidence floor regressed:{debt_id}")
        for stage_id in floor["evidence_stages"]: require(stage_id in stages,f"ratcheted technical-debt evidence stage absent:{debt_id}:{stage_id}")
        accepted += int(entry.get("state")=="ACCEPTED_RISK")
    require(accepted<=COMPILED_REQUIRED_CONTRACT["maximum_accepted_risks"],"technical-debt accepted-risk budget exceeded")
    fc=register.get("final_evidence_contract") if isinstance(register.get("final_evidence_contract"),dict) else {}; rs=fc.get("required_stage_receipts") if isinstance(fc.get("required_stage_receipts"),list) else []
    require(set(rs)==COMPILED_REQUIRED_RECEIPTS,"technical-debt final receipt inventory differs from ratcheted inventory")
    for stage_id in COMPILED_REQUIRED_RECEIPTS: require(stage_id in stages,f"ratcheted technical-debt final stage absent:{stage_id}")
    for key in ("requires_current_graph_hash","requires_current_output_hashes","stale_committed_reports_may_satisfy_gate","terminal_evidence_stage"): require(fc.get(key)==COMPILED_REQUIRED_CONTRACT[key],f"technical-debt final contract regressed:{key}")
    classification="PASS" if not errors else "FAIL"
    return {"schema_version":"1.0.0","classification":classification,"status":classification,"ratchet_id":COMPILED_RATCHET_ID,"ratchet_epoch":COMPILED_RATCHET_EPOCH,"ratchet_anchor_sha256":observed,"entry_count":len(entry_map),"required_receipt_count":len(rs),"accepted_risks":accepted,"checks":checks,"errors":sorted(set(errors)),"truth_boundary":policy.get("truth_boundary")}

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument("--repo",type=Path,default=Path(".")); p.add_argument("--json-output",type=Path,default=Path("reports/technical-debt-ratchet.json")); a=p.parse_args(); repo=a.repo.resolve()
    try: report=validate(repo)
    except (GenomeError,FileNotFoundError,json.JSONDecodeError,UnicodeDecodeError,ValueError,KeyError,TypeError) as exc: report={"schema_version":"1.0.0","classification":"FAIL","status":"FAIL","errors":[f"{type(exc).__name__}:{exc}"]}
    except Exception as exc: report={"schema_version":"1.0.0","classification":"INTERNAL_ERROR","status":"INTERNAL_ERROR","errors":[f"{type(exc).__name__}:{exc}"]}
    output=a.json_output if a.json_output.is_absolute() else repo/a.json_output; atomic_write_json(output,report); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if report["classification"]=="PASS" else (4 if report["classification"]=="INTERNAL_ERROR" else 3)
if __name__=="__main__": raise SystemExit(main())
