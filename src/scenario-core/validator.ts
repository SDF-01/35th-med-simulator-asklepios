import { scenariosById } from '../content/scenarios';
import type { ResearchRuntimeBridge } from '../research/types';
import { canonicalJson, sha256Canonical } from './hash';
import { protectedScenarioProjection } from './projection';
import { validateRouteGraph } from './route';
import { validateLocalCertificate } from './certificate';
import type {
  ScenarioPackageCheckIssue,
  ScenarioPackageCheckReport,
  VerifiedScenarioPackage,
} from './types';

const HASH_PATTERN = /^[a-f0-9]{64}$/;

function issue(code: string, path: string, message: string): ScenarioPackageCheckIssue {
  return { code, path, message };
}

function differences(left: unknown, right: unknown, prefix = ''): string[] {
  if (canonicalJson(left) === canonicalJson(right)) return [];
  if (
    left === null || right === null
    || typeof left !== 'object' || typeof right !== 'object'
    || Array.isArray(left) || Array.isArray(right)
  ) return [prefix];
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const keys = new Set([...Object.keys(leftRecord), ...Object.keys(rightRecord)]);
  return [...keys].sort().flatMap((key) => differences(
    leftRecord[key],
    rightRecord[key],
    prefix ? `${prefix}.${key}` : key,
  ));
}


function normalizedBridgeView(bridge: ResearchRuntimeBridge): ResearchRuntimeBridge {
  return {
    ...bridge,
    sources: [...bridge.sources].sort((left, right) => left.source_index - right.source_index),
    evidence_refs: [...bridge.evidence_refs].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id)),
    prototypes: [...bridge.prototypes].sort((left, right) => left.prototype_id.localeCompare(right.prototype_id)),
  };
}

export function validateScenarioPackage(
  generated: VerifiedScenarioPackage,
  bridge?: ResearchRuntimeBridge,
): ScenarioPackageCheckReport {
  const issues: ScenarioPackageCheckIssue[] = [];
  let checksRun = 0;
  const check = (condition: boolean, next: ScenarioPackageCheckIssue): void => {
    checksRun += 1;
    if (!condition) issues.push(next);
  };

  const base = scenariosById[generated.build.source_scenario_id];
  check(Boolean(base), issue('source', 'build.source_scenario_id', 'Source scenario is missing.'));
  if (!base) return { status: 'FAIL', issues, checks_run: checksRun };

  check(generated.schema_version === '2.1.0', issue('schema', 'schema_version', 'Unsupported schema version.'));
  check(generated.build.build_version === '2.1.0', issue('schema', 'build.build_version', 'Unsupported build version.'));
  check(generated.build.mode === 'template_locked', issue('mode', 'build.mode', 'Build must be template-locked.'));
  check(generated.authority.clinical_authority === 'NOT_GRANTED', issue('authority', 'authority.clinical_authority', 'Clinical authority must remain blocked.'));
  check(generated.authority.deployment_scope === 'research_sandbox_only', issue('authority', 'authority.deployment_scope', 'Package may run only in the research sandbox.'));
  check(generated.authority.source_template_status === 'repository_template_not_clinically_certified', issue('authority', 'authority.source_template_status', 'Source template status was overstated.'));
  check(generated.authority.clinical_rule_source === 'inherited_template', issue('authority', 'authority.clinical_rule_source', 'Clinical rules must be inherited.'));
  check(generated.authority.evidence_authority === 'supporting_only', issue('authority', 'authority.evidence_authority', 'Research evidence must remain supporting-only.'));
  check(generated.authority.evidence_effect_scope === 'citation_support_only', issue('authority', 'authority.evidence_effect_scope', 'Evidence may affect citation support only.'));
  check(generated.authority.scoring_behavior === 'inherited_unchanged', issue('authority', 'authority.scoring_behavior', 'Scoring must be inherited unchanged.'));
  check(HASH_PATTERN.test(generated.build.source_database_sha256), issue('hash', 'build.source_database_sha256', 'Malformed database hash.'));
  check(HASH_PATTERN.test(generated.build.source_bridge_sha256), issue('hash', 'build.source_bridge_sha256', 'Malformed bridge hash.'));
  check(HASH_PATTERN.test(generated.build.source_prototype_sha256), issue('hash', 'build.source_prototype_sha256', 'Malformed prototype hash.'));
  check(HASH_PATTERN.test(generated.build.source_prototype_record_sha256), issue('hash', 'build.source_prototype_record_sha256', 'Malformed prototype record hash.'));
  check(
    canonicalJson(protectedScenarioProjection(base)) === canonicalJson(protectedScenarioProjection(generated.scenario)),
    issue('protected', 'scenario', 'Protected scenario fields changed.'),
  );

  const changedPaths = differences(base, generated.scenario).filter(Boolean).map((path) => `scenario.${path}`);
  check(
    changedPaths.every((path) => generated.blueprint.mutable_paths.some((allowed) => path === allowed || path.startsWith(`${allowed}.`))),
    issue('path_scope', 'scenario', 'Scenario changed outside the blueprint allowlist.'),
  );

  const routeResult = validateRouteGraph(generated.route);
  check(routeResult.valid, issue('route', 'route', routeResult.issues.join(' ')));

  const evidenceIds = generated.evidence.map((item) => item.evidence_id);
  check(evidenceIds.length > 0 && evidenceIds.length <= 6, issue('evidence', 'evidence', 'One to six citations are required.'));
  check(new Set(evidenceIds).size === evidenceIds.length, issue('evidence', 'evidence', 'Evidence IDs must be unique.'));
  for (const [index, citation] of generated.evidence.entries()) {
    check(HASH_PATTERN.test(citation.chunk_sha256), issue('hash', `evidence[${index}].chunk_sha256`, 'Malformed chunk hash.'));
    check(HASH_PATTERN.test(citation.source_file_sha256), issue('hash', `evidence[${index}].source_file_sha256`, 'Malformed source hash.'));
  }

  const atomIds = generated.atoms.map((atom) => atom.atom_id);
  check(new Set(atomIds).size === atomIds.length, issue('atom', 'atoms', 'Atom IDs must be unique.'));
  check(generated.atoms.every((atom) => HASH_PATTERN.test(atom.atom_sha256)), issue('atom', 'atoms', 'Atom hashes must be SHA-256 values.'));
  check(
    generated.atoms.every((atom) => atom.authority !== 'nonclinical' || atom.evidence_ids.length === 0),
    issue('authority', 'atoms', 'Nonclinical atoms must not claim evidence derivation.'),
  );

  const originPaths = new Set(generated.field_origins.map((origin) => origin.field_path));
  check(
    [...changedPaths, 'route'].every((path) => originPaths.has(path)),
    issue('origin', 'field_origins', 'Every changed field requires an origin record.'),
  );

  if (bridge) {
    check(sha256Canonical(normalizedBridgeView(bridge)) === generated.build.source_bridge_sha256, issue('bridge', 'build.source_bridge_sha256', 'Bridge hash mismatch.'));
    check(bridge.retrieval_release.database_sha256 === generated.build.source_database_sha256, issue('bridge', 'build.source_database_sha256', 'Database hash mismatch.'));
    const prototype = bridge.prototypes.find((item) => item.prototype_id === generated.build.source_prototype_id);
    check(Boolean(prototype), issue('bridge', 'build.source_prototype_id', 'Bound prototype is missing.'));
    if (prototype) {
      check(prototype.prototype_sha256 === generated.build.source_prototype_sha256, issue('bridge', 'build.source_prototype_sha256', 'Prototype declared hash mismatch.'));
      check(sha256Canonical(prototype) === generated.build.source_prototype_record_sha256, issue('bridge', 'build.source_prototype_record_sha256', 'Prototype record hash mismatch.'));
    }
  }

  for (const message of validateLocalCertificate(base, generated)) {
    check(false, issue('certificate', 'certificate', message));
  }

  return { status: issues.length === 0 ? 'PASS' : 'FAIL', issues, checks_run: checksRun };
}

export function assertScenarioPackage(
  generated: VerifiedScenarioPackage,
  bridge?: ResearchRuntimeBridge,
): void {
  const report = validateScenarioPackage(generated, bridge);
  if (report.status === 'FAIL') {
    throw new Error(report.issues.map((item) => `${item.path}: ${item.message}`).join('\n'));
  }
}
