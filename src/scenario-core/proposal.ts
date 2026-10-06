export interface ScenarioBuildProposal {
  proposal_version: '1.0.0';
  source_scenario_id: string;
  proposed_title_suffix?: string;
  location_options?: string[];
  weather_options?: string[];
  visibility_options?: string[];
  resource_event_options?: string[];
  review: {
    status: 'pending' | 'accepted' | 'rejected';
    reviewer: string;
    reviewed_at_utc: string;
    source_scenario_sha256: string;
  };
}

const ALLOWED_KEYS = new Set([
  'proposal_version',
  'source_scenario_id',
  'proposed_title_suffix',
  'location_options',
  'weather_options',
  'visibility_options',
  'resource_event_options',
  'review',
]);

const FORBIDDEN_CONTENT_PATTERNS: ReadonlyArray<{ code: string; pattern: RegExp }> = [
  { code: 'dose', pattern: /\b\d+(?:\.\d+)?\s*(?:mg|mcg|ug|µg|g|ml|units?|mL\/kg)\b/i },
  { code: 'clinical_directive', pattern: /\b(?:administer|give|inject|dose|medication|drug|tourniquet|needle decompression|cricothyrotom|intubat|transfus|airway adjunct)\b/i },
  { code: 'scoring', pattern: /\b(?:expected action|unsafe action|score|scoring|points?)\b/i },
  { code: 'scope', pattern: /\b(?:provider scope|scope of practice|authorized provider)\b/i },
  { code: 'physiology', pattern: /\b(?:vital signs?|heart rate|blood pressure|oxygen saturation|gcs|physiology transition)\b/i },
  { code: 'executable_markup', pattern: /(?:<script\b|javascript:|onerror\s*=|onload\s*=)/i },
];

function cleanProposalText(value: unknown, maximum: number, field: string): string | undefined {
  if (value === undefined) return undefined;
  if (typeof value !== 'string') throw new Error(`${field} must be a string.`);
  const cleaned = value.replace(/\s+/g, ' ').trim();
  if (!cleaned || cleaned.length > maximum) throw new Error(`${field} is invalid.`);
  for (const rule of FORBIDDEN_CONTENT_PATTERNS) {
    if (rule.pattern.test(cleaned)) throw new Error(`${field} contains prohibited ${rule.code} content.`);
  }
  return cleaned;
}

function cleanList(value: unknown, field: string): string[] | undefined {
  if (value === undefined) return undefined;
  if (!Array.isArray(value)) throw new Error(`${field} must be an array.`);
  const items = value.map((item, index) => {
    const cleaned = cleanProposalText(item, 160, `${field}[${index}]`);
    if (!cleaned) throw new Error(`${field}[${index}] is invalid.`);
    return cleaned;
  });
  return [...new Set(items)].slice(0, 16);
}

export function validateScenarioBuildProposal(value: unknown): ScenarioBuildProposal {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Scenario build proposal must be an object.');
  }
  const record = value as Record<string, unknown>;
  const unexpected = Object.keys(record).filter((key) => !ALLOWED_KEYS.has(key));
  if (unexpected.length > 0) throw new Error(`Unsupported proposal fields: ${unexpected.join(', ')}`);
  if (record.proposal_version !== '1.0.0') throw new Error('Unsupported proposal version.');
  if (typeof record.source_scenario_id !== 'string' || !record.source_scenario_id.trim()) {
    throw new Error('Proposal source scenario ID is required.');
  }
  const review = record.review;
  if (!review || typeof review !== 'object' || Array.isArray(review)) {
    throw new Error('Proposal review record is required.');
  }
  const reviewRecord = review as Record<string, unknown>;
  if (!['pending', 'accepted', 'rejected'].includes(String(reviewRecord.status))) {
    throw new Error('Proposal review status is invalid.');
  }
  if (typeof reviewRecord.reviewer !== 'string' || !reviewRecord.reviewer.trim()) {
    throw new Error('Proposal reviewer is required.');
  }
  if (
    typeof reviewRecord.reviewed_at_utc !== 'string'
    || Number.isNaN(Date.parse(reviewRecord.reviewed_at_utc))
  ) {
    throw new Error('Proposal review timestamp must be a valid date-time.');
  }
  if (
    typeof reviewRecord.source_scenario_sha256 !== 'string'
    || !/^[a-f0-9]{64}$/.test(reviewRecord.source_scenario_sha256)
  ) {
    throw new Error('Proposal source scenario hash is invalid.');
  }
  return {
    proposal_version: '1.0.0',
    source_scenario_id: record.source_scenario_id.trim(),
    proposed_title_suffix: cleanProposalText(record.proposed_title_suffix, 80, 'proposed_title_suffix'),
    location_options: cleanList(record.location_options, 'location_options'),
    weather_options: cleanList(record.weather_options, 'weather_options'),
    visibility_options: cleanList(record.visibility_options, 'visibility_options'),
    resource_event_options: cleanList(record.resource_event_options, 'resource_event_options'),
    review: {
      status: reviewRecord.status as 'pending' | 'accepted' | 'rejected',
      reviewer: reviewRecord.reviewer.trim(),
      reviewed_at_utc: reviewRecord.reviewed_at_utc,
      source_scenario_sha256: reviewRecord.source_scenario_sha256,
    },
  };
}

export function assertAcceptedScenarioBuildProposal(
  value: unknown,
  expectedSourceScenarioId: string,
  expectedSourceScenarioSha256: string,
): ScenarioBuildProposal {
  const proposal = validateScenarioBuildProposal(value);
  if (proposal.review.status !== 'accepted') {
    throw new Error('Scenario build proposal has not been accepted.');
  }
  if (proposal.source_scenario_id !== expectedSourceScenarioId) {
    throw new Error('Scenario build proposal references the wrong source scenario.');
  }
  if (proposal.review.source_scenario_sha256 !== expectedSourceScenarioSha256) {
    throw new Error('Scenario build proposal was reviewed against a different source scenario revision.');
  }
  return proposal;
}
