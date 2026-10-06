import { createHash } from 'node:crypto';
import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, renameSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { facilityArrivalContext } from '../src/facility-arrival/context';
import {
  FACILITY_DECISION_ALTERNATE_SEQUENCE,
  FACILITY_DECISION_CANONICAL_SEQUENCE,
  applyFacilityDecisionSubmission,
  buildFacilityDecisionView,
  createFacilityDecisionSession,
  decisionSessionIntegrityErrors,
  facilityDecisionContext,
  facilityDecisionProfile,
  facilityDecisionSubmission,
} from '../src/facility-decision';
import { verifyFacilityDecisionSession } from '../src/facility-decision-checker/verify';
import { sha256Canonical } from '../src/scenario-core/hash';
import type { FacilityDecisionIntegritySession, FacilityDecisionUiMode } from '../src/facility-decision';

const repoIndex = process.argv.indexOf('--repo');
const repo = resolve(repoIndex >= 0 ? process.argv[repoIndex + 1] : '.');
const checkMode = process.argv.includes('--check');
const outputDir = resolve(repo, 'examples/facility-decision');
const reportPath = resolve(repo, checkMode
  ? 'reports/facility-decision-artifact-check.json'
  : 'reports/facility-decision-artifact-generation.json');
const context = facilityDecisionContext(facilityArrivalContext);
const profile = facilityDecisionProfile();

function fileSha256(content: string): string {
  return createHash('sha256').update(content, 'utf8').digest('hex');
}

function jsonText(value: unknown): string {
  return `${JSON.stringify(value, null, 2)}\n`;
}

function requireRegularTarget(path: string): void {
  if (!existsSync(path)) return;
  const status = lstatSync(path);
  if (status.isSymbolicLink() || !status.isFile()) {
    throw new Error(`Artifact target is not a regular file: ${path}`);
  }
}

function writeAtomic(path: string, content: string): void {
  requireRegularTarget(path);
  mkdirSync(dirname(path), { recursive: true });
  const temporary = `${path}.tmp-${process.pid}-${fileSha256(content).slice(0, 12)}`;
  rmSync(temporary, { force: true });
  try {
    writeFileSync(temporary, content, { encoding: 'utf8', flag: 'wx', mode: 0o644 });
    renameSync(temporary, path);
  } finally {
    rmSync(temporary, { force: true });
  }
}

function runSequence(sequence: readonly string[], mode: FacilityDecisionUiMode): FacilityDecisionIntegritySession {
  let session = createFacilityDecisionSession(facilityArrivalContext, mode, profile);
  sequence.forEach((decisionId, index) => {
    session = applyFacilityDecisionSubmission(
      session,
      facilityDecisionSubmission(decisionId, session.revision, index + 1),
      context,
    );
  });
  const localErrors = decisionSessionIntegrityErrors(session, context);
  const independentErrors = verifyFacilityDecisionSession(session, profile);
  if (localErrors.length > 0 || independentErrors.length > 0) {
    throw new Error(`Reference sequence failed verification: ${[...localErrors, ...independentErrors].join(',')}`);
  }
  return session;
}

const canonicalByMode = Object.fromEntries(
  (['learner_assessment', 'learner_teaching', 'instructor', 'stakeholder_demo'] as const)
    .map((mode) => [mode, runSequence(FACILITY_DECISION_CANONICAL_SEQUENCE, mode)]),
) as Record<FacilityDecisionUiMode, FacilityDecisionIntegritySession>;
const alternate = runSequence(FACILITY_DECISION_ALTERNATE_SEQUENCE, 'learner_assessment');
const canonical = canonicalByMode.learner_assessment;

if (canonical.facility_session.final_state.terminal_status !== 'completed') {
  throw new Error('Canonical reference session did not complete.');
}
if (alternate.facility_session.final_state.terminal_status !== 'completed') {
  throw new Error('Alternate reference session did not complete.');
}
if (canonical.facility_session.normalized_score_bps !== 10_000 || alternate.facility_session.normalized_score_bps !== 10_000) {
  throw new Error('Reference sessions did not preserve complete inherited source-action coverage.');
}

const artifacts: Record<string, string> = {
  'reference-session.json': jsonText(canonical),
  'alternate-session.json': jsonText(alternate),
  'learner-projection.json': jsonText(buildFacilityDecisionView(canonicalByMode.learner_assessment, context)),
  'teaching-projection.json': jsonText(buildFacilityDecisionView(canonicalByMode.learner_teaching, context)),
  'instructor-projection.json': jsonText(buildFacilityDecisionView(canonicalByMode.instructor, context)),
  'demo-projection.json': jsonText(buildFacilityDecisionView(canonicalByMode.stakeholder_demo, context)),
};

const fileManifest = Object.fromEntries(
  Object.entries(artifacts).sort(([left], [right]) => left.localeCompare(right)).map(([path, content]) => [path, {
    bytes: Buffer.byteLength(content, 'utf8'),
    sha256: fileSha256(content),
  }]),
);
const manifestWithoutBinding = {
  schema_version: '1.0.0',
  release_id: 'ASK-FACILITY-DECISION-RC3-6A',
  profile_id: profile.profile_id,
  source_scenario_id: profile.source_scenario_id,
  source_scenario_sha256: canonical.facility_session.source_binding.source_scenario_sha256,
  template_record_sha256: canonical.facility_session.source_binding.template_record_sha256,
  content_registry_merkle_root: canonical.facility_session.source_binding.content_registry_merkle_root,
  canonical_decision_root_sha256: canonical.decision_root_sha256,
  alternate_decision_root_sha256: alternate.decision_root_sha256,
  canonical_facility_session_sha256: canonical.facility_session.certificate.session_sha256,
  alternate_facility_session_sha256: alternate.facility_session.certificate.session_sha256,
  canonical_sequence: [...FACILITY_DECISION_CANONICAL_SEQUENCE],
  alternate_sequence: [...FACILITY_DECISION_ALTERNATE_SEQUENCE],
  role_routes: {
    learner_assessment: '/examples/facility-decision/learner',
    learner_teaching: '/examples/facility-decision/teaching',
    instructor: '/examples/facility-decision/instructor',
    stakeholder_demo: '/examples/facility-decision/demo',
  },
  authority: profile.authority,
  open_limits: [
    'Concrete treatments remain blocked pending exact governing-rule and eligibility admission.',
    'Operational durations and event timing are deterministic exercise assumptions and remain NOT_CALIBRATED.',
    'Continuous dynamic physiology has not been validated.',
    'The static client routes are presentation boundaries, not a replacement for authenticated server-side authorization.',
    'The formal model is not yet an end-to-end refinement proof of every TypeScript execution.',
  ],
  files: fileManifest,
};
const manifest = {
  ...manifestWithoutBinding,
  manifest_binding_sha256: sha256Canonical(manifestWithoutBinding),
};
artifacts['manifest.json'] = jsonText(manifest);

const readme = `# Facility decision integrity RC3.6A

This example begins after CUF/TFC when the field-stabilized casualty reaches a constrained receiving clinic. It demonstrates structured assessment, explicit diagnostic orders, source-limited results, resource queues, time-driven operational events, closed-loop handoff, and role-specific information projections.

## Role-bound routes

- Learner assessment: \`/examples/facility-decision/learner\`
- Learner teaching: \`/examples/facility-decision/teaching\`
- Instructor review: \`/examples/facility-decision/instructor\`
- Stakeholder demonstration: \`/examples/facility-decision/demo\`

The learner routes do not expose live score, source points, source-origin labels, WIT observations, provenance hashes, autoplay, completed replay, or correctness labels. Instructor and demonstration routes are separate entry points.

## Reference outcomes

- Canonical sequence: completed with 100% inherited source-action coverage.
- Alternate sequence: completed with the same inherited source-action coverage through a materially different admissible ordering.
- Concrete medication, dose, route, procedure, tourniquet-change, and treatment-effect content: blocked.

## Rebuild and verify

\`\`\`bash
npm run generate:facility-decision-contracts
npm run generate:facility-decision-artifacts
npm run verify:facility-decision
\`\`\`

## Validity boundary

This is a production-training reference, not patient-care decision support. Clinical actions and scoring remain inherited from ASK-D-001. Operational timings remain \`NOT_CALIBRATED\`, continuous physiology remains unvalidated, and a future authenticated server boundary is required before route roles can be treated as a security boundary.
`;
artifacts['README.md'] = readme;

const expectedNames = Object.keys(artifacts).sort((left, right) => left.localeCompare(right));
const mismatches: string[] = [];
if (existsSync(outputDir)) {
  const observedNames = readdirSync(outputDir).sort((left, right) => left.localeCompare(right));
  for (const name of observedNames) if (!expectedNames.includes(name)) mismatches.push(`unexpected:${name}`);
}
for (const [name, content] of Object.entries(artifacts).sort(([left], [right]) => left.localeCompare(right))) {
  const target = resolve(outputDir, name);
  if (checkMode) {
    if (!existsSync(target)) mismatches.push(`missing:${name}`);
    else {
      requireRegularTarget(target);
      if (readFileSync(target, 'utf8') !== content) mismatches.push(`content:${name}`);
    }
  } else {
    writeAtomic(target, content);
  }
}

const report = {
  schema_version: '1.0.0',
  status: mismatches.length === 0 ? 'PASS' : 'FAIL',
  mode: checkMode ? 'check' : 'write',
  release_id: manifest.release_id,
  profile_id: profile.profile_id,
  artifacts: Object.keys(artifacts).length,
  canonical_records: canonical.decision_records.length,
  alternate_records: alternate.decision_records.length,
  canonical_terminal_status: canonical.facility_session.final_state.terminal_status,
  alternate_terminal_status: alternate.facility_session.final_state.terminal_status,
  canonical_score_bps: canonical.facility_session.normalized_score_bps,
  alternate_score_bps: alternate.facility_session.normalized_score_bps,
  manifest_binding_sha256: manifest.manifest_binding_sha256,
  artifact_inventory_policy: 'CLOSED_REGULAR_FILE_INVENTORY_V1',
  write_policy: 'ATOMIC_RENAME_NO_SYMLINK_V1',
  expected_artifacts: expectedNames,
  mismatches,
};
mkdirSync(dirname(reportPath), { recursive: true });
writeFileSync(reportPath, jsonText(report), 'utf8');
console.log(JSON.stringify(report, null, 2));
if (mismatches.length > 0) process.exit(1);
