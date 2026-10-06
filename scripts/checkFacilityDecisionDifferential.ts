import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { facilityArrivalContext } from '../src/facility-arrival/context';
import {
  applyFacilityDecisionSubmission,
  buildFacilityDecisionView,
  createFacilityDecisionSession,
  decisionSessionIntegrityErrors,
  facilityDecisionContext,
  facilityDecisionSubmission,
} from '../src/facility-decision';
import type { FacilityDecisionIntegritySession } from '../src/facility-decision';

interface DifferentialProjection {
  completed_decision_ids: string[];
  elapsed_seconds: number;
  terminal_status: string;
  visible_world_event_ids: string[];
  fired_facility_event_ids: string[];
  orders: Array<{
    order_code: string;
    resource_id: string;
    age_region_seconds: number;
    status: string;
  }>;
  result_ids: string[];
  wait_count: number;
  reassessment_due: boolean;
  staleness_region_seconds: number;
  available_decision_ids: string[];
  timeout_seconds: number;
}

interface DifferentialCase {
  case_id: string;
  sequence_before: string[];
  state_before: DifferentialProjection;
  decision_id: string;
  expected_after: DifferentialProjection;
}

interface FixtureFile {
  schema_version: string;
  profile_id: string;
  abstraction: string;
  sample_count: number;
  cases: DifferentialCase[];
}

const repoArg = process.argv.indexOf('--repo');
const repo = resolve(repoArg >= 0 ? process.argv[repoArg + 1] : '.');
const outputArg = process.argv.indexOf('--json-output');
const output = resolve(repo, outputArg >= 0 ? process.argv[outputArg + 1] : 'reports/facility-decision-differential.json');
const fixtures = JSON.parse(
  readFileSync(resolve(repo, 'reports/facility-decision-differential-fixtures.json'), 'utf8'),
) as FixtureFile;
const context = facilityDecisionContext(facilityArrivalContext);

function regionProjection(session: FacilityDecisionIntegritySession): DifferentialProjection {
  const elapsed = session.facility_session.final_state.elapsed_seconds;
  const view = buildFacilityDecisionView(session, context);
  return {
    completed_decision_ids: [...session.completed_decision_ids].sort(),
    elapsed_seconds: elapsed,
    terminal_status: session.facility_session.final_state.terminal_status,
    visible_world_event_ids: session.visible_world_events.map((event) => event.event_id).sort(),
    fired_facility_event_ids: [...session.facility_session.final_state.fired_system_events].sort(),
    orders: session.orders
      .map((order) => ({
        order_code: order.order_code,
        resource_id: order.resource_id,
        age_region_seconds: Math.min(180, Math.max(0, elapsed - order.placed_at_seconds)),
        status: order.status,
      }))
      .sort((left, right) => left.order_code.localeCompare(right.order_code)),
    result_ids: session.results.map((result) => result.result_id).sort(),
    wait_count: session.submissions.filter((submission) => submission.decision_id === 'wait_60').length,
    reassessment_due: session.information_state.reassessment_due,
    staleness_region_seconds: Math.min(180, session.information_state.staleness_seconds),
    available_decision_ids: view.actions.filter((action) => action.enabled).map((action) => action.decision_id).sort(),
    timeout_seconds: context.facility.spec.parameters.timeout_seconds.value,
  };
}

function replay(sequence: readonly string[]): FacilityDecisionIntegritySession {
  let session = createFacilityDecisionSession(facilityArrivalContext, 'learner_assessment');
  sequence.forEach((decisionId, index) => {
    session = applyFacilityDecisionSubmission(
      session,
      facilityDecisionSubmission(decisionId, session.revision, index + 1),
      context,
    );
  });
  return session;
}

const errors: string[] = [];
let beforeChecks = 0;
let afterChecks = 0;
let integrityChecks = 0;
for (const candidate of fixtures.cases) {
  try {
    const before = replay(candidate.sequence_before);
    assert.deepStrictEqual(regionProjection(before), candidate.state_before);
    beforeChecks += 1;
    const after = applyFacilityDecisionSubmission(
      before,
      facilityDecisionSubmission(candidate.decision_id, before.revision, candidate.sequence_before.length + 1),
      context,
    );
    assert.deepStrictEqual(regionProjection(after), candidate.expected_after);
    afterChecks += 1;
    const integrity = decisionSessionIntegrityErrors(after, context);
    assert.deepStrictEqual(integrity, []);
    integrityChecks += 1;
  } catch (error) {
    errors.push(`${candidate.case_id}:${error instanceof Error ? error.message : String(error)}`);
  }
}

const report = {
  schema_version: '1.0.0',
  status: errors.length === 0 ? 'PASS' : 'FAIL',
  abstraction: fixtures.abstraction,
  fixture_profile_id: fixtures.profile_id,
  fixtures_declared: fixtures.sample_count,
  fixtures_observed: fixtures.cases.length,
  before_projection_checks: beforeChecks,
  after_transition_checks: afterChecks,
  integrity_checks: integrityChecks,
  independent_model: 'Python timed-automata region quotient',
  executable_model: 'TypeScript facility decision runtime',
  errors,
};
writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, 'utf8');
console.log(JSON.stringify(report, null, 2));
if (errors.length > 0) process.exit(1);
