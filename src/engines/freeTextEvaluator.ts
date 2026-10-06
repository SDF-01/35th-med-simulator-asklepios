import type { ExpectedAction, RecognizedAction, Scenario } from '@/types';

function normalize(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function matchAction(text: string, action: ExpectedAction): RecognizedAction | null {
  const normalized = normalize(text);
  const terms = [action.label, ...action.synonyms].map(normalize);

  for (const term of terms) {
    if (term.length < 3) continue;
    if (normalized.includes(term)) {
      const confidence = Math.min(1, term.length / Math.max(normalized.length, 1) + 0.5);
      return {
        actionId: action.id,
        label: action.label,
        priority: action.priority,
        confidence: Math.round(confidence * 100) / 100,
        matchedText: term,
      };
    }
  }

  const words = normalized.split(' ');
  for (const term of terms) {
    const termWords = term.split(' ').filter((w) => w.length > 2);
    if (termWords.length === 0) continue;
    const matches = termWords.filter((w) => words.some((tw) => tw.includes(w) || w.includes(tw)));
    if (matches.length >= Math.ceil(termWords.length * 0.6)) {
      return {
        actionId: action.id,
        label: action.label,
        priority: action.priority,
        confidence: 0.6,
        matchedText: matches.join(' '),
      };
    }
  }

  return null;
}

export function evaluateFreeText(
  rawText: string,
  scenario: Scenario,
): { recognized: RecognizedAction[]; ambiguous: boolean } {
  if (!rawText.trim()) {
    return { recognized: [], ambiguous: false };
  }

  const allActions: ExpectedAction[] = [
    ...scenario.expected_actions.critical,
    ...scenario.expected_actions.important,
    ...scenario.expected_actions.optional,
    ...scenario.expected_actions.unsafe,
  ];

  const recognized: RecognizedAction[] = [];
  const seen = new Set<string>();

  for (const action of allActions) {
    const match = matchAction(rawText, action);
    if (match && !seen.has(match.actionId)) {
      seen.add(match.actionId);
      recognized.push(match);
    }
  }

  const ambiguous =
    recognized.length === 0 &&
    rawText.trim().split(/\s+/).length >= 2 &&
    !/^(help|status|what|how)/i.test(rawText.trim());

  return { recognized, ambiguous };
}

export function getClarificationPrompt(rawText: string): string {
  return `Action not fully recognized: "${rawText}". Clarify your intent. Specify treatment, assessment, order, handoff, or command action.`;
}
