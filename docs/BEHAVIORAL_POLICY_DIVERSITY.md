# Behavioral Policy Diversity v1

## Purpose

This layer separates **operational context diversity** from **decision-policy diversity**.

Changing a location, weather description, random seed, citation bundle, or learner-facing wording can create a different scenario package without creating a different problem-solving policy. The behavioral-equivalence archive therefore uses two independent signatures:

- **Context signature** — reviewed operational setting values.
- **Policy signature** — protected scenario truth, route topology and operational semantics, action policy, information-release policy, and terminal policy.

Only the policy signature defines a behavioral equivalence class.

## Current finding

Before reviewed operational behavior profiles were added, all 107 generated scenarios occupied 107 distinct contexts but collapsed to one policy class. That proved the engine had strong context/combinatorial diversity but had not yet established behavioral diversity.

The first policy-diversity increment introduces four nonclinical operational route families:

1. `DIRECT_HANDOFF_BASELINE`
2. `COMMUNICATION_RELAY_REQUIRED`
3. `RESOURCE_COORDINATION_REQUIRED`
4. `DUAL_CONSTRAINT_RELAY_AND_COORDINATION`

The current 107-scenario archive now reports:

- 107 unique context signatures;
- 4 policy equivalence classes;
- all 4 reviewed operational behavior profiles represented;
- 103 context-only variants;
- 373 basis points of policy novelty (`4 / 107`);
- no change to clinical truth, treatment authority, scoring, or timing calibration.

## Structural semantics

Learner-facing labels and route-node IDs are intentionally excluded from the policy quotient. A stable `operational_semantic` field distinguishes reviewed behavior such as communications relay from resource coordination even when the graph shapes are otherwise identical.

This prevents both false positives:

- different prose being counted as new behavior;
- different reviewed operational behaviors being collapsed because they happen to use the same number of route nodes.

## Ratchet

`BEHAVIORAL_DIVERSITY_POLICY.json` establishes a monotonic floor:

- at least 107 candidates;
- at least 107 context signatures;
- at least 4 policy equivalence classes;
- all four reviewed profiles represented;
- no narrative-only, provenance-only, seed-only, or context-only novelty promotion;
- no profile relabeling without a corresponding policy difference.

The independent Python checker reconstructs candidate and class identities, context and policy hashes, grouping, profile-to-class mapping, archive summary, archive root, authority boundaries, and policy floors.

## Scientific boundary

This is **structural behavioral diversity**, not evidence that human teams will behave differently in real exercises. Empirical behavioral validity remains `NOT_ESTABLISHED`, human-team behavior remains `STRUCTURAL_ONLY_NOT_CALIBRATED`, and operational timing remains `NOT_CALIBRATED`.

## Next expansion

Future policy classes should be admitted only when they introduce a reviewed difference in at least one of these dimensions:

- information-release topology;
- role coupling or handoff dependency;
- resource queue and capacity behavior;
- recovery opportunities after an error;
- interrupt and world-event interaction;
- valid-route topology;
- unsafe-branch proximity;
- reassessment burden.

Adding arbitrary route steps solely to increase the class count is prohibited.
