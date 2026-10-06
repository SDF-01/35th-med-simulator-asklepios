import type { ResearchRuntimeBridge } from './types';

const HASH_PATTERN = /^[a-f0-9]{64}$/;
const DOI_PATTERN = /^10\.\d{4,9}\/.+/i;

export function validatePublicResearchBridge(payload: ResearchRuntimeBridge): ResearchRuntimeBridge {
  if (payload.contains_licensed_source_text !== false) {
    throw new Error('Research bridge violated the public-text boundary.');
  }
  if (
    payload.authority.clinical_authority !== 'NOT_GRANTED'
    || payload.authority.scoring_enabled !== false
    || payload.authority.unscored_research_sandbox_only !== true
  ) {
    throw new Error('Research bridge incorrectly grants clinical authority or scoring.');
  }
  if (!HASH_PATTERN.test(payload.retrieval_release.database_sha256)) {
    throw new Error('Research bridge database hash is invalid.');
  }
  if (!Array.isArray(payload.sources) || !Array.isArray(payload.evidence_refs) || !Array.isArray(payload.prototypes)) {
    throw new Error('Research bridge is missing required record arrays.');
  }

  const sourceIndexes = new Set<number>();
  for (const source of payload.sources) {
    if (sourceIndexes.has(source.source_index)) throw new Error(`Duplicate source index ${source.source_index}.`);
    sourceIndexes.add(source.source_index);
    if (!HASH_PATTERN.test(source.source_file_sha256)) throw new Error(`Source ${source.source_id} has an invalid hash.`);
    if (!DOI_PATTERN.test(source.doi)) throw new Error(`Source ${source.source_id} has an invalid DOI.`);
  }

  const evidenceIds = new Set<string>();
  for (const evidence of payload.evidence_refs) {
    if (evidenceIds.has(evidence.evidence_id)) throw new Error(`Duplicate evidence ID ${evidence.evidence_id}.`);
    evidenceIds.add(evidence.evidence_id);
    if (!sourceIndexes.has(evidence.source_index)) throw new Error(`Evidence ${evidence.evidence_id} references an unknown source.`);
    if (!HASH_PATTERN.test(evidence.chunk_sha256)) throw new Error(`Evidence ${evidence.evidence_id} has an invalid hash.`);
  }

  const prototypeIds = new Set<string>();
  for (const prototype of payload.prototypes) {
    if (prototypeIds.has(prototype.prototype_id)) throw new Error(`Duplicate prototype ID ${prototype.prototype_id}.`);
    prototypeIds.add(prototype.prototype_id);
    if (!HASH_PATTERN.test(prototype.prototype_sha256)) throw new Error(`Prototype ${prototype.prototype_id} has an invalid hash.`);
    const references = prototype.evidence_ids.split('|').map((item) => item.trim()).filter(Boolean);
    if (references.length === 0 || references.some((id) => !evidenceIds.has(id))) {
      throw new Error(`Prototype ${prototype.prototype_id} has invalid evidence references.`);
    }
  }
  return payload;
}
