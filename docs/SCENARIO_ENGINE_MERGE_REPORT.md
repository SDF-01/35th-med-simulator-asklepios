# Scenario Engine Merge Report

## Retained from the evidence toolchain

- Citation-only runtime bridge contract
- Evidence and source identifiers
- DOI and section locators
- Source and chunk hashes
- Baseline/candidate retriever labels and rollback boundary
- Deterministic research-sandbox event log

## Deliberately not merged

- Raw Elsevier XML or licensed article text
- Private SQLite databases or embeddings
- Acquisition credentials and institutional tokens
- Scraper implementation and model caches
- Clinical scoring rules derived from journal evidence

## Compatibility

The generated object contains a normal Project Asklepios `Scenario`, so existing
body-injury, vitals, casualty, and handoff components can inspect it. It remains in
an envelope that disables scoring and clinical authority, so it is not automatically
deployed through the current scored exercise path.

The legacy four-source JEM registry was removed because the current evidence
pipeline supersedes it with a closed, provenance-validated corpus and a compact
citation bridge.
