# Content registry and evidence boundary

This release introduces an additive, source-bound registry for existing Project Asklepios content.

## Boundaries

- Existing scenario, exercise, taxonomy, injury-profile, and research identifiers are preserved.
- Research evidence remains citation-only and supporting-only.
- Evidence identity does not imply claim entailment.
- Importing future content stages it; import never activates it.
- Clinical rules, scoring truth, medication doses, provider scope, and physiology cannot be created by a research or operational import.
- Licensed article text, private indexes, credentials, embeddings, and institutional-access artifacts remain outside the application repository.

## Future-content flow

```
source-specific adapter
  -> data-only import bundle
  -> deterministic sealing
  -> independent validation
  -> staging registry
  -> separate compatibility review
  -> separate activation release
```

The authoritative baseline registry is `public/data/content_registry/content_registry.json`.
The extension commit point is `public/data/content_registry/import_index.json`.


## Closed-world authority policy representation

RC3.1.2 represents formal capabilities as exhaustive Boolean decision functions,
not proposition-level list membership. This makes protected denials definitional,
forces review when the capability vocabulary grows, and keeps the formal authority
boundary executable. Independent Python and Node audits still validate the public
registry records; no component may use the Lean model as a self-issued runtime
certificate.
