# Formal contract scope

The Lean package proves abstract properties of the scenario architecture:

- an operational overlay cannot modify the inherited clinical record;
- scoring and action-count fields are preserved by overlay construction;
- supporting evidence does not gain access to protected fields;
- the canonical finite route contains its start and terminal stages;
- route extension preserves previously reachable stages;
- field-origin coverage composes and is preserved by restriction;
- acceptance flags imply the individual protected-field, route, origin, and stage checks.

These theorems concern the formal model under `formal/ScenarioContracts/`. The concrete JSON package is checked separately by the TypeScript and Python checkers.

The formal package does not prove:

- that a source scenario is clinically correct;
- that SHA-256 is collision-free;
- that the TypeScript runtime implements every Lean definition by refinement;
- that any generated scenario is suitable for direct patient care.

CI builds the Lean declarations and invokes an external Lean type checker with incomplete proofs forbidden.
