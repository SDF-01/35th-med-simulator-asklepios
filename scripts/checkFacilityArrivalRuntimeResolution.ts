import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { facilityArrivalContext } from '../src/facility-arrival/context';
import {
  buildFacilityClaimLedger,
  runCanonicalFacilitySession,
  validateFacilitySession,
} from '../src/facility-arrival/engine';
import { verifyFacilitySessionIndependent } from '../src/facility-arrival-checker/verify';

const repo = resolve(process.cwd());
const errors: string[] = [];
const context = facilityArrivalContext;
const session = runCanonicalFacilitySession(context);
const ledger = buildFacilityClaimLedger(context);
const localErrors = validateFacilitySession(session, context, ledger);
const independentErrors = verifyFacilitySessionIndependent(session, context, ledger);

if (context.scenario.scenario_id !== 'ASK-D-001') errors.push('runtime source scenario mismatch');
if (session.final_state.terminal_status !== 'completed') errors.push('canonical runtime did not complete');
if (session.normalized_score_bps !== 10_000) errors.push('canonical runtime score differs');
errors.push(...localErrors.map((value) => `local:${value}`));
errors.push(...independentErrors.map((value) => `independent:${value}`));

try {
  const reference = JSON.parse(
    readFileSync(resolve(repo, 'examples/facility-arrival/interaction.json'), 'utf8'),
  ) as { certificate?: { session_sha256?: string } };
  if (reference.certificate?.session_sha256 !== session.certificate.session_sha256) {
    errors.push('runtime session differs from committed reference');
  }
} catch (error) {
  errors.push(`reference session unavailable:${error instanceof Error ? error.message : String(error)}`);
}

const report = {
  schema_version: '1.0.0',
  status: errors.length === 0 ? 'PASS' : 'FAIL',
  runtime: 'tsx',
  tsconfig: 'tsconfig.app.json',
  source_scenario_id: context.scenario.scenario_id,
  session_sha256: session.certificate.session_sha256,
  transitions: session.transitions.length,
  local_checks: localErrors.length === 0 ? 'PASS' : 'FAIL',
  independent_checks: independentErrors.length === 0 ? 'PASS' : 'FAIL',
  errors: [...new Set(errors)].sort(),
};

mkdirSync(resolve(repo, 'reports'), { recursive: true });
writeFileSync(
  resolve(repo, 'reports/facility-arrival-runtime-resolution.json'),
  `${JSON.stringify(report, null, 2)}\n`,
  'utf8',
);
console.log(JSON.stringify(report, null, 2));
if (report.status !== 'PASS') process.exitCode = 3;
