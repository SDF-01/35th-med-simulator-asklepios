import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';
import type { ScenarioSourceConformanceScorecard } from '../../scenario-core';

const STATUS_VARIANT = {
  SATISFIED: 'success',
  NOT_SATISFIED: 'caution',
  INSUFFICIENT_EVIDENCE: 'muted',
  NOT_APPLICABLE: 'muted',
  CRITICAL_FAILURE: 'critical',
} as const;

function plain(value: string): string {
  return value.replaceAll('_', ' ').toLowerCase().replace(/^\w/, (letter) => letter.toUpperCase());
}

export function ScenarioScorecard({ scorecard }: { scorecard: ScenarioSourceConformanceScorecard }) {
  return (
    <Card as="section" aria-labelledby="scenario-scorecard-heading" variant={scorecard.safety_gate === 'FAIL' ? 'critical' : 'accent'}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="scenario-scorecard-heading" className="font-display text-lg font-semibold text-ask-text">Source-conformance scorecard</h3>
          <p className="mt-2 max-w-3xl text-sm leading-relaxed text-ask-text-dim">
            This report explains which reviewed training steps were observed. It is not a validated measure of clinical proficiency.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={scorecard.safety_gate === 'FAIL' ? 'critical' : scorecard.safety_gate === 'PASS' ? 'success' : 'muted'}>
            Safety: {plain(scorecard.safety_gate)}
          </Badge>
          <Badge variant={scorecard.overall_status === 'PASS' ? 'success' : scorecard.overall_status === 'FAIL' ? 'critical' : 'muted'}>
            Evidence: {plain(scorecard.overall_status)}
          </Badge>
        </div>
      </div>

      {scorecard.source_conformance_score_bps === null ? (
        <p className="mt-4 rounded-ask-sm border border-ask-border bg-ask-bg/50 p-3 text-sm text-ask-text-dim">
          Composite result: <strong>Insufficient evidence</strong>. The engine refuses to invent a percentage from an incomplete trace.
        </p>
      ) : (
        <p className="mt-4 rounded-ask-sm border border-ask-border bg-ask-bg/50 p-3 text-sm text-ask-text-dim">
          Source-conformance result: <strong>{(scorecard.source_conformance_score_bps / 100).toFixed(0)}%</strong>. A critical safety failure always forces this result to zero.
        </p>
      )}

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {scorecard.dimensions.map((dimension) => (
          <article key={dimension.dimension_id} className="rounded-ask-sm border border-ask-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h4 className="font-semibold text-ask-text">{plain(dimension.dimension_id)}</h4>
              <Badge variant={STATUS_VARIANT[dimension.status]}>{plain(dimension.status)}</Badge>
            </div>
            <p className="mt-2 text-sm leading-relaxed text-ask-text-dim">{dimension.plain_language_finding}</p>
          </article>
        ))}
      </div>

      <p className="mt-4 text-xs leading-relaxed text-ask-muted">
        Scoring state: source conformance only · Timing has no score effect until calibrated for a declared scope · Psychometric validity not established.
      </p>
    </Card>
  );
}
