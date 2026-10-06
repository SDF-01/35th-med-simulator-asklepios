# RC3.6A.6 — Scenario experience and release convergence

## Purpose

This change set closes the failure classes exposed by draft PR #13 while moving the training engine toward a world-class engineering target: deterministic behavior, explicit authority boundaries, useful operational variation, strong interaction design, and failures that preserve enough evidence to be fixed rather than guessed at.

It does **not** grant clinical authority. Patient-care use remains prohibited, operational timing remains `NOT_CALIBRATED`, and concrete treatment admission remains blocked unless the declared evidence and independent-review requirements are satisfied.

## Release reliability changes

- Every application build is performed twice in separate copies of the Git-tracked source tree.
- The two builds share only the exact installed dependency tree, never generated source, Vite state, reports, receipts, or TypeScript build caches.
- Missing, empty, symlinked, or byte-divergent build output fails closed.
- Build and provenance logs are retained with hashes, bounded tails, platform commands, and secret redaction.
- Provenance cannot modify release-locked source.
- Windows executes npm command shims through an explicit `cmd.exe` boundary with deterministic argument quoting.
- Release input identity uses canonical UTF-8/LF bytes and rejects UTF-8 BOMs.
- The scenario contract gate executes in a detached Git worktree overlaid with the exact release-locked working-tree bytes, so a package cannot accidentally test the old commit instead of its applied changes.
- Content-registry, standalone, scenario, application typecheck, formal, and reproducibility gates are represented in the canonical release graph rather than duplicated in handwritten workflow sequences.

## Scenario Experience Contract

The new contract evaluates the parts of scenario quality the repository can establish without making unsupported clinical-realism claims.

It verifies:

- deterministic replay for the same seed;
- immutable protected clinical fields across operational variants;
- meaningful nonclinical variation in location, weather, visibility, communications, resources, and scheduled pressure events;
- deterministic strength-three covering arrays over every feasible reviewed factor tuple;
- explicit classification of infeasible tuples under declarative, auditable constraints;
- bounded coverage-search budgets that fail closed instead of hanging or silently weakening coverage;
- complete evidence and field-origin coverage;
- reachable, acyclic routes with exactly one terminal state;
- one unambiguous destination for each exposed route trigger;
- observable consequences, recovery paths, and debrief-ready summaries;
- explicit calibration limitations;
- separation between learner, instructor, and stakeholder projections.

The bounded assurance sweep currently covers thousands of deterministic seeds, every admitted topic, every required operational pair, and a certified strength-three covering array. The constraint engine also proves that impossible tuples are classified separately from uncovered feasible tuples. Mutation tests prove that protected-field changes, missing provenance, ambiguous routes, missing consequence visibility, missing recovery paths, and hidden calibration boundaries are rejected.

## Interaction improvements

The Facility Decision learner experience now includes:

- a clear current-focus panel;
- progress, elapsed-time, reassessment, order, and surge-event status;
- a route-safe structured submission flow;
- field-level errors and an accessible error summary;
- focus transfer to the first invalid field;
- deliberate confirmation for actions marked by the learner-safe projection;
- explanations for unavailable actions without exposing restricted answer data;
- operational-state, resource, order, result, and handoff views;
- role-gated instructor timeline and multidimensional review;
- no client-side role switcher capable of elevating learner access.

The Research Scenario Lab now presents the reproducible seed, operational fingerprint, route timeline, consequence and recovery expectations, evidence coverage, role boundary, and limitations together. The interface makes clear which variation is operational and which fields remain inherited and protected.

## Honest capability statement

The engine can produce many behaviorally distinct, reproducible **operational variants** of the currently admitted protected scenario template. It can vary exercise context and route pressure without inventing new clinical rules. It can prove where each mutable field came from, preserve protected fields byte-for-byte, expose a safe learner projection, and create a debriefable run trace.

It is not yet a clinically certified generator of arbitrary new patient-care scenarios. Expanding clinical content requires additional admitted templates, exact governing sources, contradiction review, provider-scope binding, calibration, and independent clinical attestation.
