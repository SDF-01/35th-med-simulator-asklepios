# Canonical verified example scenario

> **Training research sandbox only. Clinical authority is NOT GRANTED.** The inherited source template is not clinically certified, the citations are identity-verified reference records only, and this example is not medical guidance.

- **Example ID:** `ASK-EXAMPLE-RC3-2`
- **Scenario ID:** `ASK-V-F3A6E77080`
- **Source template:** `ASK-A-001`
- **Scenario package SHA-256:** `7765e691316a19a0c4dd89622947f21ff153f87e7bd807963e7af519153d3388`
- **Content registry root:** `9db5b82df90426da8c1543b9ef67464dec59aff90d9731a5be26fff83f621841`
- **Example manifest SHA-256:** `d0eaf01761228bececea1fd3af9969472534ddd94458779bc9bac63bd19d25a1`

Machine-readable bindings: [`manifest.json`](manifest.json).
Authoritative source artifact for this example: [`public/data/scenario_core/verified_scenario_package.json`](../../public/data/scenario_core/verified_scenario_package.json).

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

## Learner-facing brief

### Flightline Fragmentation Casualty After Missile Warning — Operational Variant

Fictional training scenario. Follow local medical authority and current approved guidance. Operational details were varied inside an allowlisted template; the inherited clinical scaffold and scoring were not changed by this example release.

- **Setting:** flightline maintenance lane
- **Weather:** clear with cold crosswind
- **Visibility:** Variable
- **Communications:** degraded
- **Resources:** overwhelmed

### Initial casualty presentation

Conscious male lying supine near equipment. Yelling in pain. Obvious bleeding from right thigh. Rapid, shallow breathing. Clutching chest but primary visible injury is lower extremity.

- **Patient:** `P1` — Maintenance Airman
- **Mechanism:** Fragmentation wound from nearby blast
- **Initial vitals:** `{"bp_diastolic": 58, "bp_systolic": 92, "gcs": 14, "hr": 128, "rr": 28, "spo2": 91, "temp_c": "36.2"}`

## Decision route

The compiled route has **7 nodes**, **7 edges**, and terminal node(s) `complete`.

| From | Trigger | To | Priority |
|---|---|---|---:|
| `briefing` | `start` | `approach` | 100 |
| `approach` | `arrive` | `contact` | 100 |
| `contact` | `facilitator_event` | `pressure` | 100 |
| `contact` | `handoff_ready` | `resource-coordination` | 90 |
| `pressure` | `handoff_ready` | `resource-coordination` | 100 |
| `resource-coordination` | `handoff_ready` | `handoff` | 100 |
| `handoff` | `close` | `complete` | 100 |

## Certificate checks

| Check | Result |
|---|---|
| `protected_fields_unchanged` | **PASS** |
| `route_has_reachable_terminal` | **PASS** |
| `route_has_no_dead_end` | **PASS** |
| `field_origins_complete` | **PASS** |
| `evidence_scope_preserved` | **PASS** |
| `stage_chain_contiguous` | **PASS** |
| `stage_payloads_verified` | **PASS** |

## Citation identity ledger

> The records below establish source identity and chain of custody. They do **not** yet establish claim-level entailment, contradiction clearance, or clinical authority.

1. **Blood far forward: A cross-sectional analysis of prehospital transfusion practices in the Canadian Armed Forces**. *Injury*. DOI `10.1016/j.injury.2024.111771`.
   - Locator: Introduction
   - Evidence ID: `els_793b1a1a5b33ed88-chunk-0001-5a45546e7d`
   - Chunk SHA-256: `5a45546e7ddd90680572569bd6f73fb85b31b4b8e88a1af8d80e5d7d3824389f`
   - Source-file SHA-256: `0fe1eed2161595cc94a08865f180688a86219d1e369163be02600673bd18bcbb`
   - Status: `PASS` identity, `REFERENCE_ONLY`, entailment `NOT_ADJUDICATED`, contradiction `NOT_SEARCHED`, human review `NOT_REVIEWED`
2. **Blood far forward: A cross-sectional analysis of prehospital transfusion practices in the Canadian Armed Forces**. *Injury*. DOI `10.1016/j.injury.2024.111771`.
   - Locator: Results > Initiation of prehospital transfusion; Results > Types of blood products and adjuncts; Results > Delivery and monitoring of prehospital transfusion; Results > Indications for and use of transfusion adjuncts; Results > Resuscitation targets to halt ongoing transfusion
   - Evidence ID: `els_793b1a1a5b33ed88-chunk-0005-1182b1d2b1`
   - Chunk SHA-256: `1182b1d2b1d165c3c5b3956978efc9322c92c4e793f762948a60d8e8f46c4e2a`
   - Source-file SHA-256: `0fe1eed2161595cc94a08865f180688a86219d1e369163be02600673bd18bcbb`
   - Status: `PASS` identity, `REFERENCE_ONLY`, entailment `NOT_ADJUDICATED`, contradiction `NOT_SEARCHED`, human review `NOT_REVIEWED`
3. **Prehospital emergency finger thoracostomy in compensated obstructive shock: Benefits and outcomes**. *Injury*. DOI `10.1016/j.injury.2025.112331`.
   - Locator: Background
   - Evidence ID: `els_0a990bd7b22f1362-chunk-0001-08cdbaefa7`
   - Chunk SHA-256: `08cdbaefa7f4432728262cc1fe7827b4d04ff442b1c93ab0fad0aa129d752e1a`
   - Source-file SHA-256: `77dbac7a70daa858d49f65a1c1733246943dd89d29af0c2fa26aa957904168d5`
   - Status: `PASS` identity, `REFERENCE_ONLY`, entailment `NOT_ADJUDICATED`, contradiction `NOT_SEARCHED`, human review `NOT_REVIEWED`
4. **Amputation versus limb salvage after gunshot wounds and combat injuries: Considerations for an integrative concept of surgical care and rehabilitation therapy**. *Injury*. DOI `10.1016/j.injury.2025.112535`.
   - Locator: The acute care phase
   - Evidence ID: `els_85e3017962aa3214-chunk-0003-47c49b3dd8`
   - Chunk SHA-256: `47c49b3dd8d0911c6959fdc17024d83b635f2861a9379d01e49fd7d2411f8d4b`
   - Source-file SHA-256: `39925032b64e18924758b60a9818516b84d35d5fa078048438f0acea929eded4`
   - Status: `PASS` identity, `REFERENCE_ONLY`, entailment `NOT_ADJUDICATED`, contradiction `NOT_SEARCHED`, human review `NOT_REVIEWED`
5. **Association of fission 1 with multiple organ dysfunction syndrome after multiple trauma: A prospective case control study**. *The American Journal of Emergency Medicine*. DOI `10.1016/j.ajem.2025.06.050`.
   - Locator: 2; 2 > 2.1; 2 > 2.2; 2 > 2.3
   - Evidence ID: `els_b4d5e9284c3d7e59-chunk-0002-35345f37e7`
   - Chunk SHA-256: `35345f37e76646ee08b7aca65fd8aebc508df9f500b5182742d9d451915bd2cb`
   - Source-file SHA-256: `d60695a1341acb6f3a29c2fd0d2b2749f0540eabd530372b0849a91f51cf3550`
   - Status: `PASS` identity, `REFERENCE_ONLY`, entailment `NOT_ADJUDICATED`, contradiction `NOT_SEARCHED`, human review `NOT_REVIEWED`
6. **A multidisciplinary emergency protocol reduces revascularization time in major upper and lower limb replantations**. *Injury*. DOI `10.1016/j.injury.2025.112729`.
   - Locator: Material and methods; Material and methods > All patients were managed according to the Ruihua Protocol > Prehospital phase; Material and methods > All patients were managed according to the Ruihua Protocol > In-hospital phase > ER (Emergency Room)-to-Or; Material and methods > All patients were managed according to the Ruihua Protocol > In-hospital phase > OR preparation; Material and methods > All patients were managed according to the Ruihua Protocol > In-hospital phase > Surgery; Material and methods > Follow-up; Material and methods > Statistical analysis
   - Evidence ID: `els_f73b3240e4c54f49-chunk-0002-2cf4284e48`
   - Chunk SHA-256: `2cf4284e48dbd30dad816c1f963e1532179ccfe38faf328825867de3e838a463`
   - Source-file SHA-256: `c1909a4044b00b457c42dc6acdc7443ed5a08570588194608550edd3718d12c6`
   - Status: `PASS` identity, `REFERENCE_ONLY`, entailment `NOT_ADJUDICATED`, contradiction `NOT_SEARCHED`, human review `NOT_REVIEWED`

## What this example demonstrates

- **source_template_binding — DEMONSTRATED:** The example resolves to the protected-template registry asset and source file hash.
- **protected_projection_preservation — DEMONSTRATED:** The scenario certificate reports identical base and output protected hashes.
- **deterministic_package_certificate — DEMONSTRATED:** The existing scenario-contract generator and independent checkers bind the package hash.
- **citation_identity_provenance — DEMONSTRATED:** Every citation matches a registry evidence asset, source asset, and identity-only attestation.
- **authority_non_escalation — DEMONSTRATED:** The example remains research-sandbox-only with supporting-only evidence and inherited scoring.

## Open validity gates

These are deliberately visible so the README example cannot be mistaken for a clinically certified or real-world-calibrated simulator.

- **clinical_template_certification — OPEN:** Independent clinical certification of the inherited source template.
- **claim_level_evidence_entailment — OPEN:** Atomic scenario claims have not yet been adjudicated against exact source spans.
- **contradiction_search — OPEN:** Contradictory or superseding sources have not yet been exhaustively reviewed.
- **real_world_operational_calibration — OPEN:** Generated operational frequencies are not calibrated against held-out real-world data.
- **human_policy_calibration — OPEN:** Actor and learner behavior models are not calibrated against observed team behavior.
- **executable_to_formal_refinement — OPEN:** The executable implementation is not yet mechanized as a refinement of the Lean model.
- **independent_proof_kernel — OPEN:** A compatible separately implemented proof kernel has not accepted the full release.
- **multi_template_clinical_breadth — OPEN:** This example is based on one inherited clinical template.
- **training_effectiveness_validation — OPEN:** Learner outcome and instructor usability studies remain open.

## Rebuild and independently verify

```bash
python3 scripts/build_verified_example_scenario.py --repo . --check
python3 scripts/check_verified_example_scenario.py --repo .
node scripts/check_verified_example_scenario.mjs
python3 scripts/test_verified_example_scenario.py
npm run verify:scenario-contracts
```

The Python and Node checkers independently reconstruct the bindings from the source package and content registry. The mutation suite includes rehashed semantic forgeries so a stale digest is not the only reason an attack is rejected.

## Next refinement gate

The next engine release should compile compatibility-approved registry assets into additional deterministic scenario specifications. It must not activate a profile unless field origins are complete, citation claims are adjudicated where required, independent checkers agree, and the authority boundary remains unchanged.
