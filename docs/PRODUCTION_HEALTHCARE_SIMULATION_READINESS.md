# Production Healthcare Simulation Readiness

## Intended use

Project Asklepios is designed for facilitator-led healthcare simulation and training. It may simulate patient-care workflows, team coordination, diagnostic queues, handoffs, resource constraints, unsafe choices, and time-driven exercise events when those scenarios are inside the reviewed and validated release scope.

Healthcare simulation and training use is permitted within the validated release scope. Direct patient care and clinical decision support remain prohibited.

This distinction is deliberate:

- **Permitted:** classroom, simulation-center, tabletop, and approved in-situ simulation using synthetic, fictionalized, or locally approved deidentified data.
- **Not granted:** real-patient diagnosis, treatment selection, dosing, procedure authority, clinical prioritization, time-critical direction, autonomous action, or clinical decision support.
- **Separately governed:** high-stakes credentialing, educational-effectiveness claims, program accreditation, and real-world clinical timing transfer.

## Production designation

The only production designation this release may compute is:

`PRODUCTION_HEALTHCARE_SIMULATION_SOFTWARE_READY`

That designation means that the software build, deterministic scenario runtime, role boundaries, facilitator controls, learner interaction, hub access controls, evidence graph, reproducibility checks, and release artifacts passed their declared machine-verifiable gates.

It does **not** mean:

- clinically effective;
- approved for direct patient care;
- a clinical decision-support device;
- calibrated to every facility or population;
- accredited as a simulation program;
- valid for high-stakes credentialing without an externally validated assessment program.

The designation is evidence-computed, content-addressed, revocable, and fail-closed. A changed graph, source input, output, dependency, required report, or authenticated stage receipt invalidates the designation until the full gate is rerun.

## Timing model

Project Asklepios separates three clock domains.

### 1. Simulation logical clock

The engine uses monotonic, discrete logical seconds. Time-driven exercise events must:

- never fire early;
- fire exactly once;
- fire at the first transition at or after their due time;
- remain independent of any one learner action identity;
- produce the same result under multiple valid action orderings;
- remain replayable from the event-sourced record.

This clock may be validated for deterministic simulation behavior.

### 2. Software response time

The runtime measures decision-evaluation and hub round-trip latency with monotonic high-resolution clocks. These are engineering responsiveness budgets only. They have no clinical meaning and must never be interpreted as care deadlines.

### 3. Real-world clinical operational timing

Real-world clinical timing remains `NOT_CALIBRATED` and its transferability remains `NOT_ESTABLISHED`.

The pre-specified requirements for any future transfer claim are recorded in `config/release/OPERATIONAL_TIMING_CALIBRATION_PROTOCOL.json`. They require multisite data, independent and temporal holdouts, missingness analysis, uncertainty intervals, site and subgroup analysis, external reproduction, independent review, drift monitoring, and explicit rollback criteria. A simulation release cannot automatically promote a clinical timing parameter.

## Simulation-quality lifecycle

The release contract requires:

1. measurable and debriefable objectives;
2. a visible prebrief and fiction contract;
3. facilitator controls and an event trace;
4. bounded deterministic scenario logic;
5. multiple valid routes;
6. fail-closed unsafe branches;
7. no reachable active dead ends;
8. no learner answer leakage;
9. planned debriefing and guided reflection;
10. source-bound evaluation with uncertainty disclosure;
11. rollback, incident evidence, health checks, and access control.

Manual facilitator pilots, representative learner review, accessibility user validation, and educational-effectiveness studies remain required before making corresponding program-level claims.

## Multiplayer hub boundary

The provider lobby code is an identifier, not an authorization credential.

- WIT and command consoles require a cryptographically random controller capability.
- Controller capabilities are stored only as digests on the server.
- Secure links carry the capability in a URL fragment, not a query string, and the browser removes the fragment after import.
- Provider identities receive rotating capabilities bound to the newest socket.
- A device ID alone cannot take over another provider session.
- Stale sockets cannot update status, profile, handoff, or session state.
- Public device projections exclude socket IDs, capability digests, raw capabilities, and user-agent data.
- Production wildcard CORS is rejected.

## Evidence and technical debt

The early technical-debt gate validates the register and release policy without trusting runtime reports. The final debt gate runs only after all required evidence-producing stages and authenticates the current receipt chain, current graph, current inputs, and current outputs.

The permitted claim is limited to:

> No known release-blocking technical debt remains within the machine-checked scope and current authenticated evidence.

An absolute claim that no undiscovered defect exists is intentionally prohibited.
