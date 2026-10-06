# Facility decision integrity RC3.6A

This example begins after CUF/TFC when the field-stabilized casualty reaches a constrained receiving clinic. It demonstrates structured assessment, explicit diagnostic orders, source-limited results, resource queues, time-driven operational events, closed-loop handoff, and role-specific information projections.

## Role-bound routes

- Learner assessment: `/examples/facility-decision/learner`
- Learner teaching: `/examples/facility-decision/teaching`
- Instructor review: `/examples/facility-decision/instructor`
- Stakeholder demonstration: `/examples/facility-decision/demo`

The learner routes do not expose live score, source points, source-origin labels, WIT observations, provenance hashes, autoplay, completed replay, or correctness labels. Instructor and demonstration routes are separate entry points.

## Reference outcomes

- Canonical sequence: completed with 100% inherited source-action coverage.
- Alternate sequence: completed with the same inherited source-action coverage through a materially different admissible ordering.
- Concrete medication, dose, route, procedure, tourniquet-change, and treatment-effect content: blocked.

## Rebuild and verify

```bash
npm run generate:facility-decision-contracts
npm run generate:facility-decision-artifacts
npm run verify:facility-decision
```

## Validity boundary

This is a production-training reference, not patient-care decision support. Clinical actions and scoring remain inherited from ASK-D-001. Operational timings remain `NOT_CALIBRATED`, continuous physiology remains unvalidated, and a future authenticated server boundary is required before route roles can be treated as a security boundary.
