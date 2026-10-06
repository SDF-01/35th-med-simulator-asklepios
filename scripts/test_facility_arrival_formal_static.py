#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

ROOT = Path.cwd()
MODULE_PATH = ROOT / "formal/ScenarioContracts/FacilityArrival.lean"
AUDIT_PATH = ROOT / "formal/FacilityArrivalAxiomAudit.lean"
MANIFEST_PATH = ROOT / "formal/FACILITY_ARRIVAL_TRUST_MANIFEST.json"
ROOT_MODULE_PATH = ROOT / "formal/ScenarioContracts.lean"
THEOREM_RE = re.compile(r"(?m)^theorem\s+([A-Za-z0-9_']+)")
AUDIT_RE = re.compile(r"(?m)^#print axioms ScenarioContracts\.([A-Za-z0-9_']+)\s*$")


def strip_comments(text: str) -> str:
    output: list[str] = []
    index = 0
    depth = 0
    while index < len(text):
        if depth == 0 and text.startswith("--", index):
            end = text.find("\n", index)
            if end < 0:
                break
            output.append("\n")
            index = end + 1
            continue
        if text.startswith("/-", index):
            depth += 1
            index += 2
            continue
        if depth and text.startswith("-/", index):
            depth -= 1
            index += 2
            continue
        if depth:
            if text[index] == "\n":
                output.append("\n")
            index += 1
            continue
        output.append(text[index])
        index += 1
    if depth:
        raise ValueError("unterminated Lean block comment")
    return "".join(output)


def theorem_block(text: str, name: str) -> str:
    marker = f"theorem {name}"
    start = text.find(marker)
    if start < 0:
        return ""
    boundary = re.search(r"(?m)^\s*(?:inductive|def|theorem|structure|abbrev|example|end)\s+", text[start + len(marker):])
    end = len(text) if boundary is None else start + len(marker) + boundary.start()
    return text[start:end]


def check(module: str, audit: str, manifest: dict, root_module: str) -> list[str]:
    errors: list[str] = []
    try:
        clean = strip_comments(module)
    except ValueError as exc:
        return [str(exc)]
    expected_full = manifest.get("required_theorems", [])
    expected = [name.rsplit(".", 1)[-1] for name in expected_full]
    declared = THEOREM_RE.findall(clean)
    audited = AUDIT_RE.findall(audit)
    if len(declared) != len(set(declared)):
        errors.append("duplicate theorem declaration")
    if sorted(declared) != sorted(expected):
        errors.append("manifest/theorem inventory mismatch")
    if sorted(audited) != sorted(expected):
        errors.append("axiom audit/theorem inventory mismatch")
    if manifest.get("per_theorem_axioms") != {name: [] for name in expected_full}:
        errors.append("nonempty or malformed theorem axiom budget")
    if re.search(r"(^|[^A-Za-z0-9_])(sorry|admit)([^A-Za-z0-9_]|$)", clean):
        errors.append("incomplete proof placeholder")

    patch_start = clean.find("def applyFacilityOperationalPatch")
    patch_end = clean.find("theorem facility_operational_transition_preserves_clinical")
    patch_block = clean[patch_start:patch_end] if patch_start >= 0 and patch_end > patch_start else ""
    if "clinical := state.clinical" not in patch_block:
        errors.append("operational patch rewrites or omits clinical projection")

    semantic_definition_fragments = [
        "clinical := state.clinical",
        "| FacilityActionKind.operational => none",
        "| FacilityActionKind.operational => 0",
        "def facilityWitClinicalDirectiveAllowed (_observation : FacilityWitObservation) : Bool := false",
        "if diagnosticsReady then hiddenFindings else []",
        "| FacilityTerminalEvent.timeoutReached => FacilityTerminalStatus.timeout",
        "| FacilityTerminalEvent.unsafeSourceAction => FacilityTerminalStatus.failed",
        "| FacilityTerminalEvent.receivingHandoffCompleted => FacilityTerminalStatus.completed",
        "def facilityPatientCareUseAllowed : Bool := false",
    ]
    normalized_clean = " ".join(clean.split())
    for fragment in semantic_definition_fragments:
        if " ".join(fragment.split()) not in normalized_clean:
            errors.append(f"reviewed semantic definition changed:{fragment}")

    required_fragments = {
        "facility_operational_transition_preserves_clinical": "(applyFacilityOperationalPatch state patch).clinical = state.clinical := rfl",
        "facility_operational_action_has_no_source_binding": "facilitySourceBinding FacilityActionKind.operational = none := rfl",
        "facility_operational_action_has_zero_clinical_points": "facilityClinicalPoints FacilityActionKind.operational = 0 := rfl",
        "facility_wit_transition_preserves_clinical_score": "(applyFacilityWitObservation state observation).clinical.clinicalScore = state.clinical.clinicalScore := rfl",
        "facility_wit_observation_has_no_clinical_directive": "facilityWitClinicalDirectiveAllowed observation = false := rfl",
        "facility_hidden_findings_before_diagnostics_are_empty": "facilityVisibleHiddenFindings false hiddenFindings = [] := rfl",
        "facility_diagnostics_ready_reveals_exact_hidden_findings": "facilityVisibleHiddenFindings true hiddenFindings = hiddenFindings := rfl",
        "facility_timeout_event_maps_to_timeout_terminal": "applyFacilityTerminalEvent current FacilityTerminalEvent.timeoutReached = FacilityTerminalStatus.timeout := rfl",
        "facility_unsafe_event_maps_to_failed_terminal": "applyFacilityTerminalEvent current FacilityTerminalEvent.unsafeSourceAction = FacilityTerminalStatus.failed := rfl",
        "facility_handoff_event_maps_to_completed_terminal": "applyFacilityTerminalEvent current FacilityTerminalEvent.receivingHandoffCompleted = FacilityTerminalStatus.completed := rfl",
        "facility_production_training_prohibits_patient_care": "facilityPatientCareUseAllowed = false := rfl",
    }
    normalize = lambda value: " ".join(value.split())
    for theorem, fragment in required_fragments.items():
        block = theorem_block(clean, theorem)
        if not block or normalize(fragment) not in normalize(block):
            errors.append(f"reviewed theorem changed:{theorem}")
        if any(token in block for token in ("simp", "decide", "native_decide", "bv_decide", "Classical", "propext")):
            errors.append(f"unreviewed proof mechanism:{theorem}")
    replay = theorem_block(clean, "facility_operational_replay_preserves_clinical")
    for required in ("induction patches generalizing state", "facility_operational_transition_preserves_clinical", "Eq.trans"):
        if required not in replay:
            errors.append(f"replay proof missing:{required}")
    if "True :=" in clean or ": True :=" in clean:
        errors.append("tautological theorem surface forbidden")

    imports = root_module.splitlines()
    required_import = "import ScenarioContracts.FacilityArrival"
    if imports.count(required_import) != 1:
        errors.append("facility root import count")
    else:
        position = imports.index(required_import)
        first_non_import = next((i for i, line in enumerate(imports) if line.strip() and not line.startswith("import ")), len(imports))
        if position >= first_non_import:
            errors.append("facility import is not in the import block")
    return sorted(set(errors))


module = MODULE_PATH.read_text(encoding="utf-8")
audit = AUDIT_PATH.read_text(encoding="utf-8")
manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
root_module = ROOT_MODULE_PATH.read_text(encoding="utf-8")
cases: list[dict[str, object]] = []


def run(case_id: str, m: str, a: str, mf: dict, r: str, should_pass: bool) -> None:
    errors = check(m, a, mf, r)
    cases.append({"case_id": case_id, "pass": (not errors) if should_pass else bool(errors), "errors": errors})


run("reviewed_formal_source", module, audit, manifest, root_module, True)
run("clinical_projection_mutation_rejected", module.replace("clinical := state.clinical", "clinical := { protectedHash := 0, clinicalScore := 0 }", 1), audit, manifest, root_module, False)
run("operational_binding_escalation_rejected", module.replace("| FacilityActionKind.operational => none", "| FacilityActionKind.operational => some 1", 1), audit, manifest, root_module, False)
run("operational_points_escalation_rejected", module.replace("| FacilityActionKind.operational => 0", "| FacilityActionKind.operational => 1", 1), audit, manifest, root_module, False)
run("wit_directive_escalation_rejected", module.replace("Bool := false", "Bool := true", 1), audit, manifest, root_module, False)
run("early_hidden_findings_rejected", module.replace("if diagnosticsReady then hiddenFindings else []", "hiddenFindings", 1), audit, manifest, root_module, False)
run("timeout_semantics_removed_rejected", module.replace("| FacilityTerminalEvent.timeoutReached => FacilityTerminalStatus.timeout", "| FacilityTerminalEvent.timeoutReached => current", 1), audit, manifest, root_module, False)
run("unsafe_semantics_removed_rejected", module.replace("| FacilityTerminalEvent.unsafeSourceAction => FacilityTerminalStatus.failed", "| FacilityTerminalEvent.unsafeSourceAction => current", 1), audit, manifest, root_module, False)
run("patient_care_authorization_rejected", module.replace("def facilityPatientCareUseAllowed : Bool := false", "def facilityPatientCareUseAllowed : Bool := true", 1), audit, manifest, root_module, False)
run("proof_hole_rejected", module + "\nexample : True := by sorry\n", audit, manifest, root_module, False)
run("tautology_rejected", module + "\ntheorem facility_fake : True := by trivial\n", audit, manifest, root_module, False)
run("missing_theorem_rejected", module.replace("theorem facility_handoff_event_maps_to_completed_terminal", "def facility_handoff_event_maps_to_completed_terminal", 1), audit, manifest, root_module, False)
run("missing_audit_entry_rejected", module, audit.replace("#print axioms ScenarioContracts.facility_handoff_event_maps_to_completed_terminal\n", "", 1), manifest, root_module, False)
wide = copy.deepcopy(manifest)
wide["per_theorem_axioms"][wide["required_theorems"][0]] = ["propext"]
run("widened_axiom_budget_rejected", module, audit, wide, root_module, False)
run("misplaced_root_import_rejected", module, audit, manifest, root_module.replace("import ScenarioContracts.FacilityArrival\n", "") + "\nimport ScenarioContracts.FacilityArrival\n", False)

failed = [item["case_id"] for item in cases if not item["pass"]]
report = {"schema_version": "1.0.0", "status": "PASS" if not failed else "FAIL", "theorem_count": len(THEOREM_RE.findall(strip_comments(module))), "cases": len(cases), "errors": failed, "results": cases}
print(json.dumps(report, indent=2))
raise SystemExit(0 if not failed else 3)
