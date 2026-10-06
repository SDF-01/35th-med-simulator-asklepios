# Facility Arrival formal proof scope

The module `formal/ScenarioContracts/FacilityArrival.lean` proves twelve narrow properties of a small formal transition model.

## Proven

- operational patches preserve the clinical projection;
- operational actions have no source-clinical binding;
- operational actions contribute zero clinical points;
- WIT process observations preserve the clinical score;
- WIT observations cannot contain a clinical directive in the formal type;
- hidden findings are empty before diagnostic readiness;
- diagnostic readiness releases exactly the inherited hidden findings;
- timeout maps to the timeout terminal state;
- an unsafe source action maps to failure;
- receiving handoff maps to completion;
- the production-training policy prohibits patient-care use;
- replaying any list of operational patches preserves the clinical projection.

## Not proven

The Lean model does not establish:

- clinical correctness of `ASK-D-001`;
- empirical realism of exercise timing or human behavior;
- claim-level entailment for external citations;
- equivalence of every TypeScript/Python execution to the Lean semantics;
- unbounded liveness;
- concurrent-resource behavior;
- patient-care suitability.

## Trust policy

Publication requires:

- exactly twelve audited declarations;
- an empty axiom list for every declaration;
- no unexpected or duplicate declaration;
- no `sorry`, `admit`, or custom axiom;
- a successful Lean kernel build;
- successful fresh-environment replay;
- agreement between the independently encoded checker policy and `FACILITY_ARRIVAL_TRUST_MANIFEST.json`.

The static negative suite also rejects theorem surfaces that are intentionally tautological or disconnected from the reviewed transition functions.
