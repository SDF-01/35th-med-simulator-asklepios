# Scenario template contracts

Project Asklepios separates scenario generation into two authority zones.

## Reviewed template zone

A reviewed repository scenario owns every field that can affect patient care or scoring:

- patient identity and injury data;
- vital signs and deterioration timelines;
- expected, optional, and unsafe actions;
- point values and end conditions;
- teaching points and clinical objectives.

The current generator does not synthesize or edit those fields. It imports them from a named source scenario and records a SHA-256 digest of both the complete source and its protected projection.

## Operational-variation zone

A scenario blueprint may vary only explicitly listed nonclinical fields, such as:

- fictional location;
- weather and visibility;
- communications status;
- resource pressure;
- a facilitator-controlled operational event;
- a deterministic execution route.

Every allowed variation is selected from a finite reviewed pool. Research records select the topic and citations, but licensed article prose is not copied into runtime scenario fields.

## Staged assembly

A package is assembled through versioned stages:

1. source binding;
2. setting selection;
3. operational pressure;
4. route construction;
5. final package binding.

Each stage records its input hash, normalized payload hash, output hash, selected atoms, and touched fields. A contiguous stage chain makes the build reproducible and auditable.

## Acceptance

A generated package is admitted only when all of the following hold:

- the protected projection matches the source template exactly;
- all changes are inside the blueprint allowlist;
- the route has a reachable terminal and no nonterminal dead end;
- every changed field has a valid origin record;
- every evidence reference resolves to the public citation bridge;
- source, prototype, atom, stage, route, origin, and package hashes match;
- both the local validator and the independently implemented checker accept it.

The formal declarations under `formal/` prove abstract preservation properties of the template-overlay architecture. They do not prove clinical correctness, nor do they replace review of the source scenario.
