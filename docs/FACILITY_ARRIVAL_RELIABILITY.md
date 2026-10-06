# Facility Arrival Reliability RC3.3

## Purpose

This release adds a complete post-CUF/TFC receiving-facility training example to Project Asklepios. It begins with pre-arrival notification and field-handoff reconciliation and ends in one of four explicit terminal conditions:

- completed receiving handoff;
- source-defined unsafe discharge failure;
- source-defined unsafe tourniquet-action failure;
- authenticated exercise timeout.

The release is a **production-training reference**. It is not patient-care decision support.

## Source and authority boundary

The clinical presentation, hidden findings, source actions, source priorities, points, success conditions, failure conditions, and timeout are independently reconstructed from `ASK-D-001` in `src/content/scenarios.ts` and bound to the content-registry asset `template:ASK-D-001`.

The facility layer may add only exercise orchestration:

- reception and handoff workflow;
- operational timing;
- role and knowledge updates;
- diagnostic-result release timing;
- WIT process observations;
- alternate exercise branches;
- deterministic replay and AAR artifacts.

It may not add a clinical action, clinical point value, medication, dose, provider scope, physiology rule, or patient-care authorization.

## Single editable operational specification

`config/facility-arrival/ASK-D-001.json` is the sole editable facility profile. It deterministically generates:

- `src/facility-arrival/specification.generated.ts`;
- `config/facility-arrival/source-binding.generated.json`;
- `src/facility-arrival/bindings.generated.ts`;
- committed example and public reference artifacts.

The Python and Node checkers independently regenerate the expected TypeScript representation and reject any divergence.

## Replay model

Every accepted transition records:

- the session revision;
- command or event identity;
- actor identity;
- before-state SHA-256;
- full resulting state;
- after-state SHA-256;
- WIT process observation;
- clinical-score delta.

No terminal state, hidden finding, score, actor knowledge, or elapsed time may change outside an authenticated transition.

## Independent assurance

The release uses distinct implementations rather than one component certifying itself:

1. TypeScript runtime and local validator;
2. independently implemented TypeScript package checker;
3. file-only Python reconstruction;
4. file-only Node reconstruction;
5. Lean structural noninterference model;
6. final evidence-join validator.

Semantic mutations are rehashed before independent checking, so a forged package cannot pass merely by recomputing its own digests.

## Measured release obligations

The committed assurance suite requires:

- all 30 named semantic attacks rejected by both independent checkers;
- at least 25 globally rehashed attacks;
- complete coverage of 34 predeclared ordered pairs;
- complete coverage of seven predeclared ordered triples;
- bounded depth-nine exploration with no reachable active dead end;
- at least 250 abstract/runtime differential checks;
- witnesses for completion, timeout, unsafe discharge, and unsafe tourniquet failure;
- exact twelve-theorem Lean inventory with zero axioms, zero `sorry`, and zero `admit`;
- byte-identical output from two complete production builds;
- unchanged `package-lock.json`;
- exact changed-file allowlist and exact PR-head CI.

## Honest limitations

The following are deliberately not claimed:

- calibrated real-world distributions for diagnostic turnaround or surge timing;
- a continuous physiology model;
- concurrent multi-casualty staff and resource contention;
- calibrated human/team policies;
- causal identification of AAR counterfactuals;
- an end-to-end refinement proof between the executables and Lean;
- acceptance by a separately implemented proof kernel;
- accreditation for a specific wing intended use.

These limitations are machine-readable in the example manifest and AAR.

## Commands

```bash
npm run generate:facility-arrival
npm run verify:facility-arrival-runtime
npm run verify:scenario-contracts
npm run build
```

The final publication gate additionally requires the Lean axiom audit and two-build reproducibility report:

```bash
npm run finalize:facility-arrival-release
```


## Runtime module-resolution contract

Facility command-line entry points explicitly invoke `tsx --tsconfig tsconfig.app.json`. The static module-graph checker resolves every reachable import edge before dependency execution, and a live post-install smoke gate imports the complete facility runtime, produces the canonical session, and requires agreement between the runtime validator and the independently implemented TypeScript checker. A checker crash or malformed JSON report is a release failure, never a successful rejection.

## Release-tree hygiene

Python sources are compiled in memory so validation does not create `__pycache__` files. The content-registry audit writes to a temporary path, and the final changed-file boundary rejects any non-allowlisted generated file.
