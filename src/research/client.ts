import type {
  ResearchEvidenceRefRecord,
  ResearchRuntimeBridge,
  ResearchSourceRecord,
} from './types';
import { validatePublicResearchBridge } from './validation';

let cachedBridge: ResearchRuntimeBridge | null = null;

export async function loadResearchRuntimeBridge(): Promise<ResearchRuntimeBridge> {
  if (cachedBridge) return cachedBridge;
  const base = import.meta.env.BASE_URL || '/';
  const response = await fetch(`${base}data/research_sandbox/runtime_bridge.json`);
  if (!response.ok) {
    throw new Error(`Unable to load research runtime bridge: HTTP ${response.status}`);
  }
  const payload = validatePublicResearchBridge((await response.json()) as ResearchRuntimeBridge);
  cachedBridge = payload;
  return payload;
}

export function clearResearchRuntimeBridgeCache(): void {
  cachedBridge = null;
}

export function evidenceReferencesForPrototype(
  bridge: ResearchRuntimeBridge,
  evidenceIds: string,
): Array<{ evidence: ResearchEvidenceRefRecord; source: ResearchSourceRecord }> {
  const orderedIds = evidenceIds.split('|').map((item) => item.trim()).filter(Boolean);
  const evidenceById = new Map(bridge.evidence_refs.map((evidence) => [evidence.evidence_id, evidence] as const));
  const sourceByIndex = new Map(bridge.sources.map((source) => [source.source_index, source] as const));

  return orderedIds.map((evidenceId) => {
    const evidence = evidenceById.get(evidenceId);
    if (!evidence) throw new Error(`Missing evidence ${evidenceId}`);
    const source = sourceByIndex.get(evidence.source_index);
    if (!source) throw new Error(`Missing source ${evidence.source_index}`);
    return { evidence, source };
  });
}
