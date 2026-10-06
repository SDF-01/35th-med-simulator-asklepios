# Scenario generation engine

This release adds a constrained scenario-assembly path to Project Asklepios while preserving the existing multiplayer simulator and exercise catalog.

## Boundary

The evidence repository remains separate. It owns institutional acquisition, licensed text, the private SQLite index, embeddings, and retrieval models. The app receives only a compact citation bridge containing source metadata, evidence IDs, locators, hashes, and unscored topic prototypes.

## Current package path

1. Load and validate the citation-only bridge.
2. Select a reviewed scenario blueprint and its named source scenario.
3. Select a topic prototype and up to six citation references.
4. Choose operational context from finite reviewed pools using a deterministic seed.
5. Inherit the complete clinical and scoring scaffold from the source scenario.
6. Build a deterministic route and a field-level origin ledger.
7. Commit to source, evidence, atoms, stages, route, origins, and final package with SHA-256.
8. Require both the local validator and independently implemented checker to accept the package.
9. Expose the result only in `/research-sandbox`.

## Build-time proposal interface

A model may later propose candidate nonclinical option pools through the strict `ScenarioBuildProposal` schema. The proposal is not executable and is not admitted automatically. It requires a source-scenario hash, reviewer record, and an accepted status before it can be compiled into a blueprint.

The proposal cannot contain patients, vitals, injuries, expected or unsafe actions, scores, medication doses, provider scope, end conditions, or physiology rules.

## Assurance pipeline

The build runs:

- deterministic reproducibility checks;
- order-invariance checks;
- multi-seed contract sweeps;
- pairwise factor coverage;
- transformed-input relation checks;
- deliberate realistic fault challenges;
- a second TypeScript checker;
- a small Python artifact checker;
- Lean declaration compilation and an external Lean checker;
- TypeScript and Vite production builds.

## Current status

- Tier-3 research support only
- Clinical authority: `NOT_GRANTED`
- Scoring behavior: inherited from the source template and not generated
- Existing scored scenarios: unchanged
- Default production retriever: SQLite baseline
- Research sandbox retriever: configured candidate with baseline rollback

The earlier free-form research generator remains only for backwards-compatibility tests. The Scenario Contract Laboratory uses the template-locked package path.
