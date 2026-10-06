import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildConstraintAwareCoveringArray,
  buildDeterministicAssignmentCycle,
  canonicalJson,
  countUncoveredFeasibleInteractions,
  selectDeterministicFeasibleAssignment,
} from '../scenario-core/index';
import type { FactorConstraint, FactorValues } from '../scenario-core/index';

const factors: FactorValues = {
  location: ['inside', 'outside'],
  communications: ['normal', 'unavailable'],
  resources: ['normal', 'constrained'],
  visibility: ['good', 'reduced'],
};

const constraints: readonly FactorConstraint[] = [
  {
    constraint_id: 'no-unavailable-inside',
    kind: 'forbid',
    when: { location: 'inside', communications: 'unavailable' },
    reason: 'Synthetic feasibility fixture.',
  },
  {
    constraint_id: 'reduced-needs-constrained',
    kind: 'require',
    when: { visibility: 'reduced' },
    then: { resources: 'constrained' },
    reason: 'Synthetic implication fixture.',
  },
];

test('constraint-aware three-way schedule covers every feasible interaction', () => {
  const result = buildConstraintAwareCoveringArray(factors, {
    strength: 3,
    constraints,
  });
  assert.equal(result.certificate.status, 'PASS');
  assert.equal(result.certificate.strength, 3);
  assert.ok(result.certificate.infeasible_assignments > 0);
  assert.ok(result.certificate.infeasible_interactions > 0);
  assert.equal(result.certificate.covered_interactions, result.certificate.required_feasible_interactions);
  assert.equal(countUncoveredFeasibleInteractions(result.rows, factors, { strength: 3, constraints }), 0);
  for (const row of result.rows) {
    assert.notEqual(row.location === 'inside' && row.communications === 'unavailable', true);
    if (row.visibility === 'reduced') assert.equal(row.resources, 'constrained');
  }
});

test('covering schedule is independent of factor, value, and constraint ordering', () => {
  const first = buildConstraintAwareCoveringArray(factors, { strength: 3, constraints });
  const reordered: FactorValues = {
    visibility: [...factors.visibility].reverse(),
    resources: [...factors.resources].reverse(),
    communications: [...factors.communications].reverse(),
    location: [...factors.location].reverse(),
  };
  const second = buildConstraintAwareCoveringArray(reordered, {
    strength: 3,
    constraints: [...constraints].reverse(),
  });
  assert.equal(canonicalJson(first), canonicalJson(second));
});

test('deterministic assignment cycle is bijective and seed selection is periodic', () => {
  const cycle = buildDeterministicAssignmentCycle(factors, 'fixture-cycle', { constraints });
  assert.equal(cycle.certificate.status, 'PASS');
  assert.equal(new Set(cycle.assignments.map(canonicalJson)).size, cycle.assignments.length);
  const first = selectDeterministicFeasibleAssignment(factors, 0, 'fixture-cycle', { constraints });
  const repeated = selectDeterministicFeasibleAssignment(factors, cycle.assignments.length, 'fixture-cycle', { constraints });
  assert.equal(canonicalJson(first.assignment), canonicalJson(repeated.assignment));
  assert.equal(first.cycle_length, cycle.assignments.length);
  assert.equal(first.assignment_space_sha256, cycle.certificate.assignment_space_sha256);
});

test('contradictory constraints fail closed', () => {
  assert.throws(() => buildConstraintAwareCoveringArray(
    { one: ['a'], two: ['b'] },
    {
      constraints: [{
        constraint_id: 'reject-only-row',
        kind: 'forbid',
        when: { one: 'a', two: 'b' },
        reason: 'Synthetic contradiction.',
      }],
    },
  ), /contradictory/i);
});

test('constraint references outside the finite pool fail closed', () => {
  assert.throws(() => buildConstraintAwareCoveringArray(factors, {
    constraints: [{
      constraint_id: 'unknown-value',
      kind: 'forbid',
      when: { location: 'orbit' },
      reason: 'Synthetic invalid rule.',
    }],
  }), /unknown value location=orbit/i);
});

test('Cartesian and constraint-evaluation budgets fail closed', () => {
  assert.throws(() => buildConstraintAwareCoveringArray(factors, {
    max_cartesian_assignments: 2,
  }), /coverage budget exceeded: cartesian/i);
  assert.throws(() => buildConstraintAwareCoveringArray(factors, {
    constraints,
    max_constraint_evaluations: 1,
  }), /coverage budget exceeded: constraint evaluations/i);
});

test('schedule row budget fails closed rather than returning partial coverage', () => {
  assert.throws(() => buildConstraintAwareCoveringArray(factors, {
    strength: 3,
    constraints,
    max_schedule_rows: 1,
  }), /coverage budget exceeded: schedule rows/i);
});

test('invalid scenario seeds fail closed', () => {
  assert.throws(() => selectDeterministicFeasibleAssignment(factors, -1, 'fixture-cycle', { constraints }), /nonnegative safe integer/i);
  assert.throws(() => selectDeterministicFeasibleAssignment(factors, Number.MAX_SAFE_INTEGER + 1, 'fixture-cycle', { constraints }), /nonnegative safe integer/i);
});
