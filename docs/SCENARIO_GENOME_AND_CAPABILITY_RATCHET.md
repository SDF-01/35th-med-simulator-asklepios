# Scenario Genome, Behavioral Quality-Diversity, and Capability Ratchet

## Purpose

RC3.8A.1 combines a deterministic scenario identity layer, an interpretable
behavioral quality-diversity archive, and a monotonic capability ratchet.  The
objective is to make scenario evolution auditable while preventing a later
change from silently reducing coverage, reproducibility, provenance,
behavioral diversity, or authority boundaries.

This implementation is a structural foundation.  It does **not** promote
clinical authority, human-behavior calibration, operational timing calibration,
patient physiology, causal effects, treatment effects, real-world frequencies,
or psychometric validity.

## Canonical scenario genome

The canonical writer is `scripts/build_scenario_genome.py`.  It compiles
`public/data/scenario_core/verified_scenario_genome.json` from the verified
scenario package, content registry, and the policy in
`config/scenario-genome/SCENARIO_GENOME_POLICY.json`.

The genome binds:

- the verified scenario and source scenario identifiers;
- the scenario package file and certificate hashes;
- the content-registry file hash and Merkle root;
- the exact evidence-record hashes consumed by the package;
- the writer, independent checker, and policy hashes;
- an interpretable structural behavior descriptor;
- a reachable, terminating directed-acyclic route topology;
- explicit authority and calibration boundaries.

Its identifier is content-derived.  The same governed inputs produce the same
`genome_id` and `genome_sha256`; changing a governed input produces a new
identity instead of silently rewriting an existing scenario.

The independent Node implementation in `scripts/check_scenario_genome.mjs`
reconstructs the artifact without importing the Python writer.  The mutation
suite rehashes semantic forgeries before checking them, so rejection cannot be
explained only by stale digests.

The route compiler rejects unreachable nodes, reachable nonterminal dead ends,
cycles, terminal nodes with outgoing edges, duplicate identifiers, and unsafe or
non-portable repository paths.  It computes reachability, longest-route depth,
branching, terminal count, and route hashes from the canonical package rather
than trusting values supplied by a generated artifact.

## Monotonic capability ratchet

`config/release/SCENARIO_CAPABILITY_RATCHET.json` records the accepted capability
floor.  `scripts/check_scenario_capability_ratchet.py` also contains a separately
compiled anchor and floor.  Lowering a JSON threshold and recomputing the JSON
self-hash is therefore insufficient to weaken the ratchet.

The current capability-ratchet epoch is **2**.  It protects, at minimum:

- 107 generated experience scenarios;
- 106 distinct operational contexts;
- strength-three feasible interaction coverage;
- all 1,543 required interactions covered;
- 5,760 feasible assignments represented by the coverage model;
- 12,519 experience checks and 16,207 independent checks;
- 640 scenario-contract cases and 499 distinct contract contexts;
- zero uncovered pair or interaction obligations;
- complete rejection of the declared fault challenges;
- a cycle-free route with zero unreachable nodes and zero reachable
  nonterminal dead ends;
- unchanged clinical, timing, patient-dynamics, and scoring authority boundaries.

It also protects the accepted behavioral archive baseline:

- 107 candidates and 107 distinct structural behavior signatures;
- 30 occupied behavior cells out of 30 cells observed in the governed domain;
- at least one candidate in every observed behavior cell;
- 30 deterministic archive elites;
- all 1,543 observed strength-three interactions represented;
- 107 candidates with at least one unique interaction contribution;
- zero behavior identities created only by narrative or provenance changes;
- an integer-only, nonclinical quality vector used for scenario selection only,
  never for learner scoring or clinical authority.

A capability increase requires an explicit ratchet-epoch update.  A decrease is
a release failure.

## One canonical artifact lifecycle

The release graph declares one writer and at least one independent read-only
checker for each governed scenario artifact family:

1. verified scenario package;
2. verified example documentation and manifest;
3. verified scenario genome;
4. behavioral quality-diversity archive.

The graph enforces the order:

```text
canonical generation
        -> independent verification
        -> adversarial mutations
        -> complete scenario contract
        -> behavioral archive reconstruction
        -> independent archive verification
        -> behavioral archive attacks
        -> capability ratchet
        -> ratchet attacks
        -> authenticated scenario-evolution evidence join
        -> receipt-forgery and stale-output attacks
```

The example GitHub Actions workflow no longer runs hand-written generator and
checker sequences.  Every pull-request job invokes one release-graph target.
The graph validator also discovers every `pull_request` or
`pull_request_target` workflow and requires exact registration, preventing an
unregistered PR workflow from becoming a weaker bypass lane.

## Regression classes made fail-closed

The graph and adversarial suites reject:

- a pull-request workflow missing from the canonical workflow inventory;
- workflow job or target drift;
- unpinned third-party actions;
- a scenario writer or checker removed from the graph;
- a governed artifact without an authority contract;
- a scenario checker that can write governed inputs;
- a checker that does not depend on its canonical writer;
- a capability floor reduced, including a reanchored policy forgery;
- a ratchet or evidence-join stage bypassed by later scenario stages;
- a missing, forged, failed, stale, wrong-graph, or wrong-stage receipt being
  accepted as scenario-evolution evidence;
- a cycle, unreachable route node, or reachable nonterminal dead end;
- generated documentation or manifest drift;
- authority, treatment, calibration, probability, or real-world-frequency
  promotion inside the genome;
- a narrative-only or provenance-only variant being counted as a new behavior;
- a duplicate structural behavior signature being admitted as novel;
- an archive cell, elite, interaction contribution, or quality component being
  accepted without deterministic reconstruction;
- a quality vector being promoted from scenario selection into learner scoring,
  clinical scoring, or patient-care authority;
- Linux-only test fixtures that omit the Windows `npm.cmd` execution path.

## Behavioral quality-diversity archive

`src/scenario-core/qualityDiversity.ts` derives a structural behavior descriptor
from the governed scenario package.  The descriptor intentionally excludes
names, prose, citations, hashes, and other presentation or provenance fields.
Two scenarios therefore do not become behaviorally distinct merely because
their wording or source metadata differs.

The descriptor captures interpretable properties such as route topology,
branching, critical-path depth, information release, resource pressure, role
coupling, unsafe-branch proximity, and recovery opportunities.  It is mapped to
a deterministic archive cell.  Each cell retains a deterministic elite using
an integer-only nonclinical quality vector.

The archive is not a learner score.  Its authority boundary is:

```text
Quality-vector use: SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING
```

The Python checker independently reconstructs the archive and the mutation
suite rejects duplicate signatures, cosmetic diversity, cell drift, elite
forgery, archive-root forgery, clinical scoring promotion, and removal of the
selection-only boundary.

## Evidence join

`scripts/join_scenario_evolution_evidence.py` authenticates the required reports
and governed artifacts into `reports/scenario-evolution-evidence.json`.  The join
records the genome identity, all report and artifact hashes, the authority
boundary, and a deterministic evidence root.

When invoked by the release graph, report hashes are not sufficient.  The join
also requires the current authenticated release receipt for every report-producing
predecessor stage.  Each receipt must have a valid self-digest, match the current
graph and stage configuration, report `PASS` with exit status zero, and bind the
exact current output inventory and output-root hash.  The adversarial suite
separately rejects missing receipts, forged receipt hashes, stale outputs,
wrong-graph identities, failed receipts, and stage-configuration forgeries.

The join is evidence for the exact tree and exact release execution only.  A
changed report, artifact, genome, policy, checker, stage definition, graph, or
receipt invalidates the evidence root and requires a new run.

## Commands

Generate all governed scenario artifacts:

```bash
npm run generate:verified-scenario
```

Run the complete scenario-evolution boundary:

```bash
npm run verify:scenario-evolution
```

Run the graph-governed release rehearsal:

```bash
npm run rehearse:release-package
```

## Current truth boundary

```text
Clinical authority:          NOT_GRANTED
Patient-care use:            PROHIBITED
Human-team behavior:         STRUCTURAL_ONLY_NOT_CALIBRATED
Operational calibration:     NOT_CALIBRATED
Patient dynamics:            SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY
Scoring behavior:            inherited_unchanged
Quality-vector use:          SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING
Deployment scope:            research_sandbox_only for the genome artifact
```

The next scientific evolution must add adjudicated claim-level evidence,
empirical timing data, and validated psychometric scoring without weakening
these boundaries.  Behavioral quality-diversity is now implemented as a
structural selection layer; it is not yet an empirical human-behavior model.
