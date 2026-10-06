# RC3.6A.5 canonical release-graph closure

RC3.6A.5 closes the package-to-live orchestration defects discovered after RC3.6A.4. It is a release candidate, not a grant of clinical or production authority. Patient-care use remains prohibited, operational timing remains `NOT_CALIBRATED`, no concrete treatment is admitted, and the graph records `production_designation: NOT_GRANTED`.

## What changed

A single machine-readable graph now owns the reusable release sequence. Its 62 stages and 13 targets define commands, predecessor edges, locked input domains, expected outputs, read-only policy, and failure classification. The graph is the source checked by npm wrappers, both GitHub Actions workflows, package rehearsal, publisher execution, and the final evidence join.

The canonical Facility Arrival chain now orders:

1. artifact generation;
2. public artifact-boundary validation;
3. the complete `check:facility-arrival-source-attestations` command;
4. runtime, Python, and Node verification;
5. semantic, sequence, state-space, lifecycle, artifact-boundary, and cross-platform attacks;
6. static validation and static mutation attacks;
7. authenticated runtime evidence joining.

The cross-layer calibration checker binds the real `second_casualty_inbound` Facility Arrival event to the decision-integrity calibration record. It independently distinguishes a missing record, status promotion, clock disagreement, missing exercise-assumption limitation, and action-trigger regression.

## Checkpoint and evidence model

Every graph stage emits a content-addressed local receipt containing the graph and stage identities, resolved command, input root, dependency receipt roots, output inventory and root, tool versions, exit status, classification, and timestamps. Reuse is fail-closed: any input, command, dependency, tool, output, or receipt change invalidates the stage and its downstream branch.

The evidence join does not trust summary files. It re-authenticates predecessor receipts, graph identity, commands, dependency links, current outputs, and all participating input locks. Deliberate forged-receipt and changed-output tests are rejected. The evidence join explicitly grants neither patient-care authority nor operational calibration.

## Result vocabulary

Every assurance result uses only:

- `PASS` for a healthy baseline or a successful meta-test;
- `EXPECTED_REJECTION` for a deliberate mutation rejected with the required diagnostic;
- `FAIL` for an accepted mutation or a real contract failure;
- `INTERNAL_ERROR` when the assurance mechanism itself cannot form a verdict.

Deliberate checker-crash challenges retain `observed_classification: INTERNAL_ERROR` while the outer meta-test passes only when that crash is not miscounted as a semantic rejection.

## Current source-level evidence

- Canonical graph consistency: 900 checks, `PASS`.
- Graph adversarial suite: 10 cases, including checkpoint invalidation and receipt/output authentication, `PASS`.
- Facility Arrival static boundary: 156 checks, `PASS`.
- Facility Arrival static attacks: 20 attacks, zero accepted mutations, zero internal errors.
- Decision Integrity static boundary: 134 checks, `PASS`.
- Decision Integrity static attacks: 24 attacks, zero accepted mutations, zero internal errors.
- Scientific-admission boundary: 863 checks, `PASS`.
- Evidence-promotion boundary: 338 checks, `PASS`; 47 attacks, zero internal errors.
- Facility Arrival sequence assurance: 30 cases, all 34 required ordered pairs and all 7 selected triples covered.
- Facility Arrival bounded exploration: 63,690 transitions, `PASS`.
- Decision Integrity bounded exploration: 493,866 semantic states and 940,403 transitions, no reachable active dead ends, `PASS`.
- Source preflight: 132 checks, `READY_FOR_LIVE_GATES`.

## Remaining authoritative gates

The package publisher must still execute the exact extracted-package rehearsal on a fresh authenticated clone. That graph performs the locked npm installation, TypeScript runtime and differential checks, complete Lean build and fresh replay, two normalized production builds with byte comparison, final evidence joins, and then pushes the exact validated commit for Linux and Windows CI.

A pull request and successful CI run may establish software-release evidence. They do not promote the system into patient-care decision support, calibrate exercise timings, admit a treatment, establish WCAG conformance, or create signed deployment provenance.
