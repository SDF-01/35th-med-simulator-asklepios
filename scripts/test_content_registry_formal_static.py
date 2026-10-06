#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

ROOT = Path.cwd()
MODULE = ROOT / "formal/ScenarioContracts/ContentRegistry.lean"
AUDIT = ROOT / "formal/ContentRegistryAxiomAudit.lean"
MANIFEST = ROOT / "formal/CONTENT_REGISTRY_TRUST_MANIFEST.json"
ROOT_MODULE = ROOT / "formal/ScenarioContracts.lean"

THEOREM = re.compile(r"(?m)^\s*(?:@\[[^\]]+\]\s*)?theorem\s+([A-Za-z0-9_']+)")
AUDITED = re.compile(r"(?m)^#print\s+axioms\s+ScenarioContracts\.([A-Za-z0-9_']+)\s*$")
FIELD = re.compile(r"(?m)^\s{2}([A-Za-z_][A-Za-z0-9_]*)\s*:")
RESERVED = {"protected", "class", "final", "theorem", "axiom", "structure", "def", "opaque", "unsafe", "partial"}

EXPECTED_POLICY = {
    "generatedOperationalCapabilities": {
        "catalogDisplay": True,
        "preserveExistingContent": False,
        "operationalContext": True,
        "routing": True,
        "learnerPrompt": True,
        "citationReference": False,
        "aarDiscussion": False,
        "inheritedTemplateResearchSandbox": False,
        "defineNewClinicalRule": False,
        "defineScoringTruth": False,
        "definePhysiology": False,
    },
    "supportingEvidenceCapabilities": {
        "catalogDisplay": True,
        "preserveExistingContent": False,
        "operationalContext": False,
        "routing": False,
        "learnerPrompt": False,
        "citationReference": True,
        "aarDiscussion": True,
        "inheritedTemplateResearchSandbox": False,
        "defineNewClinicalRule": False,
        "defineScoringTruth": False,
        "definePhysiology": False,
    },
}

EXPECTED_DEFINITIONAL_THEOREMS = {
    "generated_content_cannot_define_clinical_rule":
        "generatedOperationalCapabilities RegistryCapability.defineNewClinicalRule = false",
    "generated_content_cannot_define_scoring_truth":
        "generatedOperationalCapabilities RegistryCapability.defineScoringTruth = false",
    "generated_content_cannot_define_physiology":
        "generatedOperationalCapabilities RegistryCapability.definePhysiology = false",
    "supporting_evidence_cannot_define_clinical_rule":
        "supportingEvidenceCapabilities RegistryCapability.defineNewClinicalRule = false",
    "supporting_evidence_cannot_define_scoring_truth":
        "supportingEvidenceCapabilities RegistryCapability.defineScoringTruth = false",
}


def strip_comments(text: str) -> str:
    out: list[str] = []
    i = 0
    depth = 0
    while i < len(text):
        if depth == 0 and text.startswith('--', i):
            end = text.find('\n', i)
            if end < 0:
                break
            out.append('\n')
            i = end + 1
            continue
        if text.startswith('/-', i):
            depth += 1
            i += 2
            continue
        if depth and text.startswith('-/', i):
            depth -= 1
            i += 2
            continue
        if depth:
            if text[i] == '\n':
                out.append('\n')
            i += 1
            continue
        out.append(text[i])
        i += 1
    if depth:
        raise ValueError('unterminated Lean block comment')
    return ''.join(out)


def block_between(text: str, marker: str) -> str:
    start = text.find(marker)
    if start < 0:
        return ''
    boundary = re.search(
        r"(?m)^\s*(?:inductive|abbrev|def|theorem|structure|example|end)\s+",
        text[start + len(marker):],
    )
    end = len(text) if boundary is None else start + len(marker) + boundary.start()
    return text[start:end]


def parse_constructors(text: str) -> list[str]:
    block = block_between(text, 'inductive RegistryCapability where')
    return re.findall(r"(?m)^\s*\|\s*([A-Za-z0-9_']+)\s*$", block)


def parse_policy(text: str, name: str) -> tuple[dict[str, bool], list[str]]:
    errors: list[str] = []
    block = block_between(text, f'def {name} : CapabilityPolicy')
    if not block:
        return {}, [f'policy missing:{name}']
    if re.search(r"(?m)^\s*\|\s*_\s*=>", block):
        errors.append(f'wildcard policy branch forbidden:{name}')
    entries: dict[str, bool] = {}
    for constructor, value in re.findall(
        r"(?m)^\s*\|\s*RegistryCapability\.([A-Za-z0-9_']+)\s*=>\s*(true|false)\s*$",
        block,
    ):
        if constructor in entries:
            errors.append(f'duplicate policy constructor:{name}:{constructor}')
        entries[constructor] = value == 'true'
    return entries, errors


def theorem_block(text: str, name: str) -> str:
    return block_between(text, f'theorem {name}')


def normalize_ws(text: str) -> str:
    return ' '.join(text.split())


def check(module: str, audit: str, manifest: dict, root_module: str) -> list[str]:
    errors: list[str] = []
    try:
        clean = strip_comments(module)
    except ValueError as exc:
        return [str(exc)]

    declared = THEOREM.findall(clean)
    audited = AUDITED.findall(audit)
    expected = [name.rsplit('.', 1)[-1] for name in manifest.get('required_theorems', [])]
    if len(declared) != len(set(declared)):
        errors.append('duplicate theorem declaration')
    if sorted(declared) != sorted(expected):
        errors.append('manifest/theorem inventory mismatch')
    if sorted(audited) != sorted(expected):
        errors.append('axiom audit/theorem inventory mismatch')
    if manifest.get('per_theorem_axioms') != {
        f'ScenarioContracts.{name}': [] for name in expected
    }:
        errors.append('nonempty or malformed theorem axiom budget')
    if re.search(r"(^|[^A-Za-z0-9_])(sorry|admit)([^A-Za-z0-9_]|$)", clean):
        errors.append('incomplete proof placeholder')

    constructors = parse_constructors(clean)
    if len(constructors) != len(set(constructors)):
        errors.append('duplicate capability constructor')
    expected_constructors = set(next(iter(EXPECTED_POLICY.values())))
    if set(constructors) != expected_constructors:
        errors.append('capability constructor inventory mismatch')

    for policy_name, expected_policy in EXPECTED_POLICY.items():
        observed, policy_errors = parse_policy(clean, policy_name)
        errors.extend(policy_errors)
        if observed != expected_policy:
            errors.append(f'authority policy mismatch:{policy_name}')
        if set(observed) != set(constructors):
            errors.append(f'non-total authority policy:{policy_name}')

    for theorem_name, expected_statement in EXPECTED_DEFINITIONAL_THEOREMS.items():
        block = theorem_block(clean, theorem_name)
        if not block:
            errors.append(f'definitional theorem missing:{theorem_name}')
            continue
        normalized = normalize_ws(block)
        exact = normalize_ws(
            f'theorem {theorem_name} : {expected_statement} := rfl'
        )
        if normalized != exact:
            errors.append(f'definitional theorem changed:{theorem_name}')
        for token in ('simp', 'decide', 'native_decide', 'bv_decide', 'propext', 'Classical', 'Lean.ofReduceBool', 'Lean.trustCompiler'):
            if token in block:
                errors.append(f'forbidden proof mechanism:{theorem_name}:{token}')

    reserved_fields = sorted(set(FIELD.findall(clean)) & RESERVED)
    if reserved_fields:
        errors.append('reserved structure fields:' + ','.join(reserved_fields))

    lines = root_module.splitlines()
    import_line = 'import ScenarioContracts.ContentRegistry'
    if lines.count(import_line) != 1:
        errors.append('content registry root import count')
    else:
        position = lines.index(import_line)
        first_non_import = next(
            (index for index, line in enumerate(lines) if line.strip() and not line.startswith('import ')),
            len(lines),
        )
        if position >= first_non_import:
            errors.append('content registry import is not in the import block')
    return sorted(set(errors))


module = MODULE.read_text(encoding='utf-8')
audit = AUDIT.read_text(encoding='utf-8')
manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
root_module = ROOT_MODULE.read_text(encoding='utf-8')

cases: list[dict[str, object]] = []

def run_case(case_id: str, m: str, a: str, mf: dict, r: str, should_pass: bool) -> None:
    errors = check(m, a, mf, r)
    passed = (not errors) if should_pass else bool(errors)
    cases.append({'case_id': case_id, 'pass': passed, 'errors': errors})

run_case('reviewed_formal_source', module, audit, manifest, root_module, True)
run_case('missing_theorem_rejected', module.replace('theorem activated_content_preserves_authority', 'def activated_content_preserves_authority'), audit, manifest, root_module, False)
run_case('duplicate_theorem_rejected', module + '\ntheorem admitted_claim_has_identity : True := by trivial\n', audit, manifest, root_module, False)
run_case('missing_audit_entry_rejected', module, audit.replace('#print axioms ScenarioContracts.admitted_claim_has_identity\n', ''), manifest, root_module, False)
wide_manifest = copy.deepcopy(manifest)
wide_manifest['per_theorem_axioms'][wide_manifest['required_theorems'][0]] = ['propext']
run_case('widened_axiom_budget_rejected', module, audit, wide_manifest, root_module, False)
run_case('sorry_rejected', module + '\nexample : True := by sorry\n', audit, manifest, root_module, False)
run_case('decision_tactic_regression_rejected', module.replace(':= rfl', ':= by decide', 1), audit, manifest, root_module, False)
run_case('policy_bit_flip_rejected', module.replace('RegistryCapability.defineNewClinicalRule => false', 'RegistryCapability.defineNewClinicalRule => true', 1), audit, manifest, root_module, False)
run_case('policy_constructor_omission_rejected', module.replace('  | RegistryCapability.definePhysiology => false\n', '', 1), audit, manifest, root_module, False)
run_case('wildcard_policy_rejected', module.replace('  | RegistryCapability.definePhysiology => false\n', '  | _ => false\n', 1), audit, manifest, root_module, False)
run_case('theorem_statement_weakening_rejected', module.replace('generatedOperationalCapabilities RegistryCapability.defineNewClinicalRule = false := rfl', 'True := by trivial', 1), audit, manifest, root_module, False)
run_case('reserved_field_rejected', module.replace('integrityVerified : Bool', 'protected : Bool', 1), audit, manifest, root_module, False)
run_case('misplaced_root_import_rejected', module, audit, manifest, root_module.replace('import ScenarioContracts.ContentRegistry\n', '') + '\nimport ScenarioContracts.ContentRegistry\n', False)
run_case('comment_spoof_does_not_hide_policy_mutation', module.replace('RegistryCapability.defineScoringTruth => false', 'RegistryCapability.defineScoringTruth => true -- false', 1), audit, manifest, root_module, False)

failed = [case['case_id'] for case in cases if not case['pass']]
report = {
    'schema_version': '1.2.0',
    'status': 'PASS' if not failed else 'FAIL',
    'theorem_count': len(THEOREM.findall(strip_comments(module))),
    'authority_policy_constructors': len(parse_constructors(strip_comments(module))),
    'cases': len(cases),
    'errors': failed,
    'results': cases,
}
print(json.dumps(report, indent=2))
raise SystemExit(0 if not failed else 3)
