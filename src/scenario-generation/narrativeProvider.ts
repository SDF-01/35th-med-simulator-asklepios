import type {
  ScenarioNarrativeDraft,
  ScenarioNarrativeProvider,
  ScenarioNarrativeRequest,
} from './types';

const ALLOWED_KEYS = new Set([
  'title',
  'operational_narrative',
  'initial_presentation',
  'cue_labels',
  'complication_labels',
]);

function cleanText(value: unknown, maximum: number): string | undefined {
  if (typeof value !== 'string') return undefined;
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (!cleaned) return undefined;
  return cleaned.slice(0, maximum);
}

function cleanList(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value
    .map((item) => cleanText(item, 140))
    .filter((item): item is string => Boolean(item));
  return items.length > 0 ? [...new Set(items)].slice(0, 8) : undefined;
}

/**
 * Accepts model output only after strict field filtering. Clinical rules, actions,
 * doses, scores, and state-transition instructions are not part of this contract.
 */
export function validateNarrativeDraft(value: unknown): ScenarioNarrativeDraft {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Narrative draft must be an object.');
  }
  const record = value as Record<string, unknown>;
  const unknown = Object.keys(record).filter((key) => !ALLOWED_KEYS.has(key));
  if (unknown.length > 0) {
    throw new Error(`Narrative draft contains unsupported fields: ${unknown.join(', ')}`);
  }
  return {
    title: cleanText(record.title, 120),
    operational_narrative: cleanText(record.operational_narrative, 900),
    initial_presentation: cleanText(record.initial_presentation, 700),
    cue_labels: cleanList(record.cue_labels),
    complication_labels: cleanList(record.complication_labels),
  };
}

/**
 * Provider-neutral adapter. The caller owns the server-side model connection and
 * returns a JSON-compatible draft. No secret or licensed source text belongs here.
 */
export function createNarrativeProvider(
  providerId: string,
  invoke: (request: ScenarioNarrativeRequest) => Promise<unknown>,
): ScenarioNarrativeProvider {
  return {
    provider_id: providerId,
    async draft(request) {
      return validateNarrativeDraft(await invoke(request));
    },
  };
}
