# Facility-arrival canonical interactive scenario

[Open the self-contained offline Facility Arrival scenario](playable.html). It runs locally in a modern browser with no server or network request.

## Four playable offline role-model teamwork challenges

The single offline file includes four selectable, fully playable role-model examples. Each profile keeps the same source-bound clinical template and changes only the operational teamwork route:

- **Direct handoff baseline** — complete the normal closed-loop receiving workflow.
- **Communications relay** — establish an intermediate relay and confirm receipt before the final handoff.
- **Resource coordination** — coordinate a constrained resource and confirm ownership before the final handoff.
- **Relay and resource coordination** — establish the relay first, then coordinate the constrained resource, then close the handoff.

Open `playable.html`, choose a challenge at the top, and use manual actions, **Watch autoplay**, or **Complete canonical replay**. Relay and resource actions carry zero clinical points. They are structural training behaviors, not clinically calibrated timing or treatment authority.

This is the current start-to-finish Project Asklepios example for the **post-CUF/TFC receiving phase**. It begins when a field-stabilized casualty arrives at a constrained base clinic and ends with a closed-loop transfer to the next level of care.

- Browser route: [`/examples/facility-arrival`](/examples/facility-arrival)
- Source template: `ASK-D-001`
- Facility profile: `BASE_CLINIC_TRAUMA_RECEPTION_RC3_3`
- Terminal status: `completed`
- Score: `100.00%`
- Session SHA-256: `5d22d201964725a31c36f27b1cfc5c671869917dcc3a887d7bbcba6bcc5d26f0`
- Content-registry root: `9db5b82df90426da8c1543b9ef67464dec59aff90d9731a5be26fff83f621841`

<!-- asklepios-offline-evolution:start -->
## Engine evolution binding

This artifact is bound to **RC3.8A.1** (`ASK-OFFLINE-RC3.8A.1`), the evidence-calibrated evolution that adds a deterministic Scenario Genome, true behavioral-policy diversity, a balanced operational scenario pack, stakeholder scorecards, a fail-closed treatment-admission pipeline, dual monotonic ratchets, differential documentation verification, and graph-receipt-bound scenario-evolution evidence.

- Engine evolution profile: `SCENARIO_SCIENCE_BEHAVIORAL_DIVERSITY_STAKEHOLDER_SCORECARD_TREATMENT_ADMISSION_PLAIN_LANGUAGE_DUAL_RATCHETS_V8`
- Scenario Genome: `ASK-GENOME-528E11A5CC61EE45` (`53b695595dd7d053cac1468992db51cb5519d4761a6cf644a895ee008e2fe8ff`)
- Capability ratchet: `asklepios-scenario-capability-ratchet-v1`, epoch `5` (`870a94620630dc6fc4a41f3d13120ea45527966676d72e69bd5b460bee45218e`)
- Technical-debt ratchet: `asklepios-technical-debt-ratchet-v1`, epoch `8` (`84d04484d51e79944b3079889d0eed50841f9588422e0f9928c3840822b5fb91`)
- Canonical release graph: `asklepios-rc3.8a.1-scenario-science-stakeholder-graph` with `122` stages and `26` targets
- Behavioral quality-diversity: the ratcheted archive preserves 107 unique structural behavior signatures across all 30 observed behavior cells; its integer quality vector selects scenario representatives only and never scores learners.
- Behavioral policy diversity: 107 operational contexts are quotient-checked into four genuinely different decision-policy classes; wording, names, provenance, and seeds cannot claim novelty by themselves.
- Operational scenario pack: 12 reviewed scenarios are balanced three-per-profile across direct handoff, communication relay, resource coordination, and dual-constraint coordination.
- Four playable offline role-model teamwork challenges: the standalone file lets the user select and play direct handoff, communications relay, resource coordination, or the combined relay-and-resource route; added teamwork actions carry zero clinical points.
- Source-conformance scorecard: four reference scorecards expose evidence by competency dimension, preserve a hard safety gate, and return INSUFFICIENT_EVIDENCE rather than fabricated precision; they are not psychometrically validated proficiency scores.
- Treatment-admission pipeline: two treatment concepts remain DISCOVERED, zero are SIMULATION_ADMITTED, and zero active learner treatment choices are allowed until exact source spans, applicability, scope, and SME review are complete.
- Plain-language release translation: every release must state what changed for learners, instructors, reviewers, and maintainers, plus what remains uncalibrated or prohibited.
- Scenario-science telemetry: event traces are privacy-bounded, append-only, and hash-chained; they create calibration evidence without silently promoting exercise timing or learner scoring.
- Release-identity DAG: `ACYCLIC_SEMANTIC_PROJECTION_V1` contract `0f202ff8af5bacd6817f93443e1d8cf4573524f4c676e9d1701d9c50b783fb8e`
- Truth boundary: clinical authority `NOT_GRANTED`; operational calibration `NOT_CALIBRATED`; patient-care use `PROHIBITED`; human-team behavior `STRUCTURAL_ONLY_NOT_CALIBRATED`; patient dynamics `SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY`; quality-vector use `SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING`.

- Canonical-writer rule: each governed artifact has one writer and at least one independently implemented read-only verifier.
- Receipt rule: a committed `PASS` report is insufficient; final evidence must bind current graph, stage configuration, inputs, and output hashes.
- Release-identity rule: the offline descriptor binds an acyclic semantic graph projection rather than the graph's raw file hash, while the graph independently locks the descriptor.
- Route topology: the Scenario Genome admits only reachable, terminating, cycle-free routes with zero nonterminal dead ends.
- Technical-debt rule: reviewed blocker classifications, evidence floors, and final receipt requirements cannot be silently weakened.
- Regression rule: future epochs may raise demonstrated floors but cannot lower them without an explicit reviewed epoch change and renewed evidence.

The Scenario Genome is a structural identity and provenance artifact. It does not establish clinical certification, empirical timing, human-behavior calibration, treatment effect, dynamic physiology, psychometric validity, or suitability for direct patient care.
<!-- asklepios-offline-evolution:end -->

## Complete simulated learner interaction

| Seq | Time | Type | Interaction |
|---:|---:|---|---|
| 1 | 0s | system_event | Pre-arrival notification received |
| 2 | 45s | learner_action | Receive casualty and reconcile the field handoff |
| 3 | 135s | learner_action | Perform primary assessment |
| 4 | 165s | learner_action | Establish continuous monitoring |
| 5 | 225s | learner_action | Document differential diagnosis |
| 6 | 255s | learner_action | Order chest imaging |
| 7 | 255s | system_event | Second casualty reported inbound |
| 8 | 285s | learner_action | Order relevant labs |
| 9 | 315s | learner_action | Address source-defined pain-management objective |
| 10 | 345s | learner_action | Acknowledge the surge notice and confirm receiving-team roles |
| 11 | 390s | learner_action | Document findings and plan |
| 12 | 465s | learner_action | Advance to the next scheduled diagnostic event |
| 13 | 465s | system_event | Ordered imaging and laboratory results are available |
| 14 | 525s | learner_action | Review returned results and reassess the casualty |
| 15 | 585s | learner_action | Escalate disposition / consult |
| 16 | 645s | learner_action | Complete the receiving handoff to the next level of care |

## Alternate branches

The interactive page can also produce an explicit source-bound timeout, unsafe discharge failure, and unsafe tourniquet-action failure. Each branch is event-sourced and independently replayable.

## WIT and learner separation

WIT observations remain process-only and carry no clinical directive or clinical points. Hidden source findings remain unavailable to the learner until the authenticated diagnostics-ready event occurs.

## Evidence and calibration boundary

Clinical actions and points come only from the inherited ASK-D-001 repository template. The JTS and USAF records in `source-truth.json` frame continuum-of-care and inspection-process scope; they are not used as a hidden clinical-rule generator. Diagnostic timing and the pass threshold are explicitly marked `NOT_CALIBRATED` exercise-design values.

## Rebuild and verify

```bash
npm run generate:facility-arrival
npm run verify:facility-arrival
python3 scripts/check_facility_arrival_example.py --repo .
node scripts/check_facility_arrival_example.mjs --repo .
```

## Open validity obligations

- claim_level_clinical_entailment
- real_world_frequency_calibration
- human_team_policy_calibration
- facility_specific_workflow_calibration
- continuous_physiology_model
- concurrent_multi_casualty_resource_contention
- causal_identification_for_counterfactual_aar
- executable_to_lean_refinement
- independent_proof_kernel_acceptance
- formal_vva_for_specific_wing_intended_use
