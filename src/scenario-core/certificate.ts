import { canonicalJson, sha256Canonical, sha256Text } from './hash';
import { protectedScenarioProjection } from './projection';
import { validateRouteGraph } from './route';
import { stageOutputDigest, stagePayload, type PackageWithoutCertificate } from './stages';
import type {
  ScenarioAtom,
  ScenarioCertificate,
  ScenarioCertificateChecks,
  ScenarioFieldOrigin,
  ScenarioRouteGraph,
  VerifiedScenarioPackage,
} from './types';
import type { Scenario } from '../types';
import type { ScenarioEvidenceCitation } from '../scenario-generation/types';

export function merkleRoot(hashes: readonly string[]): string {
  if (hashes.length === 0) return sha256Text('');
  let level = [...hashes].sort();
  while (level.length > 1) {
    const next: string[] = [];
    for (let index = 0; index < level.length; index += 2) {
      const left = level[index]!;
      const right = level[index + 1] ?? left;
      next.push(sha256Text(`${left}:${right}`));
    }
    level = next;
  }
  return level[0]!;
}

export function createScenarioAtom(
  atom: Omit<ScenarioAtom, 'atom_sha256'>,
): ScenarioAtom {
  return { ...atom, atom_sha256: sha256Canonical(atom) };
}

function verifyStagePayloads(
  baseScenario: Scenario,
  generated: PackageWithoutCertificate,
): boolean {
  return generated.stages.every((stage) => {
    const expectedPayloadHash = sha256Canonical(stagePayload(stage.stage_id, generated, baseScenario));
    const { output_sha256: _ignored, ...withoutOutput } = stage;
    void _ignored;
    return stage.formula_version === '1.0.0'
      && stage.payload_sha256 === expectedPayloadHash
      && stage.output_sha256 === stageOutputDigest(withoutOutput);
  });
}

export function buildCertificate(
  baseScenario: Scenario,
  packageWithoutCertificate: PackageWithoutCertificate,
): ScenarioCertificate {
  const routeValidation = validateRouteGraph(packageWithoutCertificate.route);
  const baseProtected = protectedScenarioProjection(baseScenario);
  const outputProtected = protectedScenarioProjection(packageWithoutCertificate.scenario);
  const originPaths = new Set(packageWithoutCertificate.field_origins.map((origin) => origin.field_path));
  const changedPaths = packageWithoutCertificate.stages
    .flatMap((stage) => stage.touched_paths)
    .filter((path) => path !== 'scenario.protected_projection');
  const stageContiguous = packageWithoutCertificate.stages.every((stage, index, stages) => (
    index === 0 || stage.input_sha256 === stages[index - 1]!.output_sha256
  ));
  const evidenceIds = new Set(packageWithoutCertificate.evidence.map((item) => item.evidence_id));
  const evidenceScope = packageWithoutCertificate.atoms.every((atom) => {
    const referencesKnown = atom.evidence_ids.every((id) => evidenceIds.has(id));
    if (!referencesKnown) return false;
    if (atom.authority === 'supporting_only') return atom.evidence_ids.length > 0;
    if (atom.authority === 'template_inherited') return atom.evidence_ids.length === 0;
    return atom.evidence_ids.length === 0;
  });

  const checks: ScenarioCertificateChecks = {
    protected_fields_unchanged: canonicalJson(baseProtected) === canonicalJson(outputProtected),
    route_has_reachable_terminal: routeValidation.reachable_terminal,
    route_has_no_dead_end: routeValidation.no_dead_end,
    field_origins_complete: changedPaths.every((path) => originPaths.has(path)),
    evidence_scope_preserved: evidenceScope,
    stage_chain_contiguous: stageContiguous,
    stage_payloads_verified: verifyStagePayloads(baseScenario, packageWithoutCertificate),
  };

  const certificateWithoutPackageHash: Omit<ScenarioCertificate, 'package_sha256'> = {
    certificate_version: '1.1.0',
    checker_profile: 'scenario-contract-v1',
    base_scenario_sha256: sha256Canonical(baseScenario),
    base_protected_sha256: sha256Canonical(baseProtected),
    output_protected_sha256: sha256Canonical(outputProtected),
    source_bridge_sha256: packageWithoutCertificate.build.source_bridge_sha256,
    source_prototype_sha256: packageWithoutCertificate.build.source_prototype_sha256,
    source_prototype_record_sha256: packageWithoutCertificate.build.source_prototype_record_sha256,
    blueprint_sha256: sha256Canonical(packageWithoutCertificate.blueprint),
    atom_root_sha256: merkleRoot(packageWithoutCertificate.atoms.map((atom) => atom.atom_sha256)),
    stage_chain_sha256: sha256Canonical(packageWithoutCertificate.stages),
    route_sha256: sha256Canonical(packageWithoutCertificate.route),
    field_origin_sha256: sha256Canonical(packageWithoutCertificate.field_origins),
    evidence_sha256: sha256Canonical(packageWithoutCertificate.evidence),
    checks,
  };
  const packageSha256 = sha256Canonical({
    ...packageWithoutCertificate,
    certificate: certificateWithoutPackageHash,
  });
  return { ...certificateWithoutPackageHash, package_sha256: packageSha256 };
}

export function validateLocalCertificate(
  baseScenario: Scenario,
  generated: VerifiedScenarioPackage,
): string[] {
  const { certificate: _certificate, ...withoutCertificate } = generated;
  const expected = buildCertificate(baseScenario, withoutCertificate);
  const issues: string[] = [];
  if (canonicalJson(expected) !== canonicalJson(generated.certificate)) {
    issues.push('Certificate does not match the generated package.');
  }
  if (!Object.values(generated.certificate.checks).every(Boolean)) {
    issues.push('One or more certificate checks failed.');
  }
  return issues;
}

export function routeHash(route: ScenarioRouteGraph): string {
  return sha256Canonical(route);
}

export function originHash(origins: ScenarioFieldOrigin[]): string {
  return sha256Canonical(origins);
}

export function evidenceHash(evidence: ScenarioEvidenceCitation[]): string {
  return sha256Canonical(evidence);
}
