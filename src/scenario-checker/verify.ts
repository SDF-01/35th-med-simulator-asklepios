import type { ResearchRuntimeBridge } from '../research/types';
import type { Scenario } from '../types';
import type {
  ScenarioBuildStage,
  ScenarioPackageCheckIssue,
  ScenarioPackageCheckReport,
  ScenarioRouteGraph,
  ScenarioStageId,
  VerifiedScenarioPackage,
} from '../scenario-core/types';

const HASH_PATTERN = /^[a-f0-9]{64}$/;

function canonicalNumber(value: number): string {
  if (!Number.isFinite(value)) throw new Error('Non-finite number.');
  if (Object.is(value, -0)) return '0';
  return JSON.stringify(value);
}

function encodeCanonical(value: unknown): string {
  if (value === null) return 'null';
  if (typeof value === 'number') return canonicalNumber(value);
  if (typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(encodeCanonical).join(',')}]`;
  if (typeof value !== 'object') throw new Error(`Unsupported value ${typeof value}.`);
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record).sort().map((key) => {
    if (record[key] === undefined) throw new Error(`Undefined value at ${key}.`);
    return `${JSON.stringify(key)}:${encodeCanonical(record[key])}`;
  }).join(',')}}`;
}

async function digestText(value: string): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

async function digestCanonical(value: unknown): Promise<string> {
  return digestText(encodeCanonical(value));
}

async function merkleRootIndependent(hashes: string[]): Promise<string> {
  if (hashes.length === 0) return digestText('');
  let level = [...hashes].sort();
  while (level.length > 1) {
    const next: string[] = [];
    for (let index = 0; index < level.length; index += 2) {
      const left = level[index]!;
      const right = level[index + 1] ?? left;
      next.push(await digestText(`${left}:${right}`));
    }
    level = next;
  }
  return level[0]!;
}

function protectedProjection(scenario: Scenario): object {
  return {
    training_objectives: scenario.training_objectives,
    target_section: scenario.target_section,
    target_role: scenario.target_role,
    skill_level: scenario.skill_level,
    difficulty: scenario.difficulty,
    threat_type: scenario.threat_type,
    casualty_count: scenario.casualty_count,
    patients: scenario.patients,
    expected_actions: scenario.expected_actions,
    end_conditions: scenario.end_conditions,
    aar_teaching_points: scenario.aar_teaching_points,
  };
}

function inspectRoute(route: ScenarioRouteGraph): { terminal: boolean; noDeadEnd: boolean; valid: boolean } {
  const nodes = new Set(route.nodes.map((node) => node.node_id));
  const edgeIds = route.edges.map((edge) => edge.edge_id);
  const labels = route.nodes.map((node) => node.label.trim().replace(/\s+/g, ' ').toLowerCase());
  if (
    nodes.size !== route.nodes.length
    || !nodes.has(route.start_node_id)
    || new Set(edgeIds).size !== edgeIds.length
    || labels.some((label) => !label || label.includes('_') || label.split(' ').length < 3)
    || new Set(labels).size !== labels.length
  ) {
    return { terminal: false, noDeadEnd: false, valid: false };
  }
  const outgoing = new Map<string, string[]>();
  const incoming = new Map<string, string[]>();
  const triggerKeys = new Set<string>();
  for (const edge of route.edges) {
    if (!nodes.has(edge.from) || !nodes.has(edge.to) || edge.from === edge.to || !Number.isInteger(edge.priority)) {
      return { terminal: false, noDeadEnd: false, valid: false };
    }
    const triggerKey = `${edge.from}:${edge.trigger}`;
    if (triggerKeys.has(triggerKey)) return { terminal: false, noDeadEnd: false, valid: false };
    triggerKeys.add(triggerKey);
    const destinations = outgoing.get(edge.from) ?? [];
    destinations.push(edge.to);
    outgoing.set(edge.from, destinations);
    const sources = incoming.get(edge.to) ?? [];
    sources.push(edge.from);
    incoming.set(edge.to, sources);
  }
  const terminals = route.nodes.filter((node) => node.terminal);
  if (terminals.length !== 1 || terminals.some((node) => (outgoing.get(node.node_id)?.length ?? 0) > 0)) {
    return { terminal: false, noDeadEnd: false, valid: false };
  }
  const noDeadEnd = route.nodes.every((node) => node.terminal || (outgoing.get(node.node_id)?.length ?? 0) > 0);
  const reached = new Set<string>();
  const queue = [route.start_node_id];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (reached.has(current)) continue;
    reached.add(current);
    for (const destination of outgoing.get(current) ?? []) queue.push(destination);
  }
  const terminal = reached.has(terminals[0]!.node_id);
  const allReachable = route.nodes.every((node) => reached.has(node.node_id));

  const canReachTerminal = new Set<string>();
  const reverseQueue = [terminals[0]!.node_id];
  while (reverseQueue.length > 0) {
    const current = reverseQueue.shift()!;
    if (canReachTerminal.has(current)) continue;
    canReachTerminal.add(current);
    for (const source of incoming.get(current) ?? []) reverseQueue.push(source);
  }
  const allTerminate = route.nodes.every((node) => canReachTerminal.has(node.node_id));

  const visiting = new Set<string>();
  const visited = new Set<string>();
  let acyclic = true;
  const visit = (nodeId: string): void => {
    if (!acyclic || visited.has(nodeId)) return;
    if (visiting.has(nodeId)) {
      acyclic = false;
      return;
    }
    visiting.add(nodeId);
    for (const destination of outgoing.get(nodeId) ?? []) visit(destination);
    visiting.delete(nodeId);
    visited.add(nodeId);
  };
  for (const node of route.nodes) visit(node.node_id);
  return { terminal, noDeadEnd, valid: terminal && noDeadEnd && allReachable && allTerminate && acyclic };
}

function differencePaths(left: unknown, right: unknown, prefix = ''): string[] {
  if (encodeCanonical(left) === encodeCanonical(right)) return [];
  if (
    left === null || right === null
    || typeof left !== 'object' || typeof right !== 'object'
    || Array.isArray(left) || Array.isArray(right)
  ) {
    return [prefix];
  }
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const keys = new Set([...Object.keys(leftRecord), ...Object.keys(rightRecord)]);
  return [...keys].sort().flatMap((key) => differencePaths(
    leftRecord[key],
    rightRecord[key],
    prefix ? `${prefix}.${key}` : key,
  ));
}

function pathAllowed(path: string, allowed: string[]): boolean {
  return allowed.some((candidate) => path === candidate || path.startsWith(`${candidate}.`));
}

function stagePayloadIndependent(
  stageId: ScenarioStageId,
  generated: VerifiedScenarioPackage,
  baseScenarioSha256: string,
): unknown {
  switch (stageId) {
    case 'source':
      return {
        build: generated.build,
        base_scenario_sha256: baseScenarioSha256,
        blueprint_sha256: generated.certificate.blueprint_sha256,
        evidence_ids: generated.evidence.map((item) => item.evidence_id),
      };
    case 'setting':
      return {
        scenario_id: generated.scenario.scenario_id,
        title: generated.scenario.title,
        version: generated.scenario.version,
        fictionalization_notice: generated.scenario.fictionalization_notice,
        location_type: generated.scenario.operational_context.location_type,
        weather: generated.scenario.operational_context.weather,
        visibility: generated.scenario.operational_context.visibility,
        comms_status: generated.scenario.operational_context.comms_status,
        resource_status: generated.scenario.operational_context.resource_status,
      };
    case 'pressure':
      return {
        narrative: generated.scenario.operational_context.narrative,
        resource_event_atom_sha256: generated.atoms.find((atom) => atom.atom_id === 'atom-resource-event')?.atom_sha256 ?? '',
      };
    case 'route':
      return generated.route;
    case 'final':
      return {
        scenario: generated.scenario,
        route_sha256: generated.certificate.route_sha256,
        evidence_sha256: generated.certificate.evidence_sha256,
      };
  }
}

async function expectedStageOutput(stage: ScenarioBuildStage): Promise<string> {
  const { output_sha256: _ignored, ...withoutOutput } = stage;
  void _ignored;
  return digestCanonical(withoutOutput);
}


function normalizedBridgeView(bridge: ResearchRuntimeBridge): ResearchRuntimeBridge {
  return {
    ...bridge,
    sources: [...bridge.sources].sort((left, right) => left.source_index - right.source_index),
    evidence_refs: [...bridge.evidence_refs].sort((left, right) => left.evidence_id.localeCompare(right.evidence_id)),
    prototypes: [...bridge.prototypes].sort((left, right) => left.prototype_id.localeCompare(right.prototype_id)),
  };
}

function pushIssue(
  issues: ScenarioPackageCheckIssue[],
  code: string,
  path: string,
  message: string,
): void {
  issues.push({ code, path, message });
}

export async function verifyScenarioPackage(
  baseScenario: Scenario,
  generated: VerifiedScenarioPackage,
  bridge?: ResearchRuntimeBridge,
): Promise<ScenarioPackageCheckReport> {
  const issues: ScenarioPackageCheckIssue[] = [];
  let checksRun = 0;
  const check = (condition: boolean, code: string, path: string, message: string): void => {
    checksRun += 1;
    if (!condition) pushIssue(issues, code, path, message);
  };

  check(generated.schema_version === '2.1.0', 'schema', 'schema_version', 'Unsupported package schema.');
  check(generated.build.build_version === '2.1.0', 'schema', 'build.build_version', 'Unsupported build version.');
  check(generated.build.mode === 'template_locked', 'mode', 'build.mode', 'Only template-locked packages are admitted.');
  check(generated.authority.clinical_authority === 'NOT_GRANTED', 'authority', 'authority.clinical_authority', 'Clinical authority must remain blocked.');
  check(generated.authority.deployment_scope === 'research_sandbox_only', 'authority', 'authority.deployment_scope', 'Package may run only in the research sandbox.');
  check(generated.authority.source_template_status === 'repository_template_not_clinically_certified', 'authority', 'authority.source_template_status', 'Source template status was overstated.');
  check(generated.authority.clinical_rule_source === 'inherited_template', 'authority', 'authority.clinical_rule_source', 'Clinical rules must be inherited.');
  check(generated.authority.evidence_authority === 'supporting_only', 'authority', 'authority.evidence_authority', 'Research evidence must remain supporting-only.');
  check(generated.authority.evidence_effect_scope === 'citation_support_only', 'authority', 'authority.evidence_effect_scope', 'Research evidence may affect citation support only.');
  check(generated.authority.scoring_behavior === 'inherited_unchanged', 'authority', 'authority.scoring_behavior', 'Scoring must remain inherited and unchanged.');
  check(HASH_PATTERN.test(generated.build.source_database_sha256), 'hash', 'build.source_database_sha256', 'Database hash is malformed.');
  check(HASH_PATTERN.test(generated.build.source_bridge_sha256), 'hash', 'build.source_bridge_sha256', 'Bridge hash is malformed.');
  check(HASH_PATTERN.test(generated.build.source_prototype_sha256), 'hash', 'build.source_prototype_sha256', 'Prototype hash is malformed.');
  check(HASH_PATTERN.test(generated.build.source_prototype_record_sha256), 'hash', 'build.source_prototype_record_sha256', 'Prototype record hash is malformed.');

  const baseHash = await digestCanonical(baseScenario);
  const baseProtectedHash = await digestCanonical(protectedProjection(baseScenario));
  const outputProtectedHash = await digestCanonical(protectedProjection(generated.scenario));
  check(generated.certificate.base_scenario_sha256 === baseHash, 'hash', 'certificate.base_scenario_sha256', 'Base scenario hash mismatch.');
  check(generated.certificate.base_protected_sha256 === baseProtectedHash, 'hash', 'certificate.base_protected_sha256', 'Base protected-field hash mismatch.');
  check(generated.certificate.output_protected_sha256 === outputProtectedHash, 'hash', 'certificate.output_protected_sha256', 'Output protected-field hash mismatch.');
  check(baseProtectedHash === outputProtectedHash, 'protected', 'scenario', 'Protected scenario fields changed.');
  check(generated.certificate.source_bridge_sha256 === generated.build.source_bridge_sha256, 'hash', 'certificate.source_bridge_sha256', 'Bridge binding mismatch.');
  check(generated.certificate.source_prototype_sha256 === generated.build.source_prototype_sha256, 'hash', 'certificate.source_prototype_sha256', 'Prototype binding mismatch.');
  check(generated.certificate.source_prototype_record_sha256 === generated.build.source_prototype_record_sha256, 'hash', 'certificate.source_prototype_record_sha256', 'Prototype record binding mismatch.');

  const differences = differencePaths(baseScenario, generated.scenario).filter(Boolean);
  check(
    differences.every((path) => pathAllowed(`scenario.${path}`, generated.blueprint.mutable_paths)),
    'path_scope',
    'scenario',
    `Scenario changed outside the blueprint allowlist: ${differences.join(', ')}`,
  );

  check(
    generated.certificate.blueprint_sha256 === await digestCanonical(generated.blueprint),
    'hash',
    'certificate.blueprint_sha256',
    'Blueprint hash mismatch.',
  );

  const evidenceIds = new Set(generated.evidence.map((citation) => citation.evidence_id));
  for (const [index, citation] of generated.evidence.entries()) {
    check(HASH_PATTERN.test(citation.chunk_sha256), 'hash', `evidence[${index}].chunk_sha256`, 'Malformed chunk hash.');
    check(HASH_PATTERN.test(citation.source_file_sha256), 'hash', `evidence[${index}].source_file_sha256`, 'Malformed source hash.');
  }
  check(generated.evidence.length > 0 && generated.evidence.length <= 6, 'evidence', 'evidence', 'One to six evidence references are required.');
  check(evidenceIds.size === generated.evidence.length, 'evidence', 'evidence', 'Evidence IDs must be unique.');
  check(
    generated.certificate.evidence_sha256 === await digestCanonical(generated.evidence),
    'hash',
    'certificate.evidence_sha256',
    'Evidence hash mismatch.',
  );

  for (const [index, atom] of generated.atoms.entries()) {
    const { atom_sha256: _hash, ...withoutHash } = atom;
    void _hash;
    check(
      atom.atom_sha256 === await digestCanonical(withoutHash),
      'hash',
      `atoms[${index}].atom_sha256`,
      'Atom hash mismatch.',
    );
    check(
      atom.evidence_ids.every((id) => evidenceIds.has(id)),
      'evidence',
      `atoms[${index}].evidence_ids`,
      'Atom references unknown evidence.',
    );
    check(
      atom.authority !== 'supporting_only' || atom.evidence_ids.length > 0,
      'authority',
      `atoms[${index}].authority`,
      'Supporting atom lacks an evidence reference.',
    );
    check(
      atom.authority !== 'nonclinical' || atom.evidence_ids.length === 0,
      'authority',
      `atoms[${index}].authority`,
      'Nonclinical atom must not claim research derivation.',
    );
  }
  check(
    generated.certificate.atom_root_sha256 === await merkleRootIndependent(generated.atoms.map((atom) => atom.atom_sha256)),
    'hash',
    'certificate.atom_root_sha256',
    'Atom root mismatch.',
  );

  const stageContiguous = generated.stages.every((stage, index, stages) => (
    index === 0 || stage.input_sha256 === stages[index - 1]!.output_sha256
  ));
  check(stageContiguous, 'stage_chain', 'stages', 'Stage chain is not contiguous.');
  for (const [index, stage] of generated.stages.entries()) {
    const expectedPayloadHash = await digestCanonical(stagePayloadIndependent(stage.stage_id, generated, baseHash));
    check(stage.formula_version === '1.0.0', 'stage', `stages[${index}].formula_version`, 'Stage formula version is invalid.');
    check(stage.payload_sha256 === expectedPayloadHash, 'stage', `stages[${index}].payload_sha256`, 'Stage payload hash mismatch.');
    check(stage.output_sha256 === await expectedStageOutput(stage), 'stage', `stages[${index}].output_sha256`, 'Stage output hash mismatch.');
  }
  check(
    generated.certificate.stage_chain_sha256 === await digestCanonical(generated.stages),
    'hash',
    'certificate.stage_chain_sha256',
    'Stage-chain hash mismatch.',
  );

  const routeState = inspectRoute(generated.route);
  check(routeState.valid, 'route', 'route', 'Route graph is invalid or incomplete.');
  check(
    generated.certificate.route_sha256 === await digestCanonical(generated.route),
    'hash',
    'certificate.route_sha256',
    'Route hash mismatch.',
  );

  const atomsById = new Set(generated.atoms.map((atom) => atom.atom_id));
  const originsByPath = new Map(generated.field_origins.map((origin) => [origin.field_path, origin] as const));
  const actualChangedPaths = differences.map((path) => `scenario.${path}`);
  for (const path of [...actualChangedPaths, 'route']) {
    const origin = originsByPath.get(path);
    check(Boolean(origin), 'origin', path, 'Changed field has no origin record.');
    if (origin) {
      check(origin.atom_ids.every((id) => atomsById.has(id)), 'origin', path, 'Origin references an unknown atom.');
      check(origin.evidence_ids.every((id) => evidenceIds.has(id)), 'origin', path, 'Origin references unknown evidence.');
    }
  }
  check(
    generated.certificate.field_origin_sha256 === await digestCanonical(generated.field_origins),
    'hash',
    'certificate.field_origin_sha256',
    'Field-origin hash mismatch.',
  );

  if (bridge) {
    check(await digestCanonical(normalizedBridgeView(bridge)) === generated.build.source_bridge_sha256, 'bridge', 'build.source_bridge_sha256', 'Source bridge content does not match the package binding.');
    check(bridge.retrieval_release.database_sha256 === generated.build.source_database_sha256, 'bridge', 'build.source_database_sha256', 'Source database binding mismatch.');
    const prototype = bridge.prototypes.find((item) => item.prototype_id === generated.build.source_prototype_id);
    check(Boolean(prototype), 'bridge', 'build.source_prototype_id', 'Source prototype is missing from the bridge.');
    if (prototype) {
      check(prototype.prototype_sha256 === generated.build.source_prototype_sha256, 'bridge', 'build.source_prototype_sha256', 'Source prototype declared hash mismatch.');
      check(await digestCanonical(prototype) === generated.build.source_prototype_record_sha256, 'bridge', 'build.source_prototype_record_sha256', 'Source prototype record mismatch.');
    }
  }

  const { certificate, ...withoutCertificate } = generated;
  const { package_sha256: _packageHash, ...certificateWithoutPackageHash } = certificate;
  void _packageHash;
  const expectedPackageHash = await digestCanonical({
    ...withoutCertificate,
    certificate: certificateWithoutPackageHash,
  });
  check(certificate.package_sha256 === expectedPackageHash, 'hash', 'certificate.package_sha256', 'Package hash mismatch.');
  check(Object.values(certificate.checks).every(Boolean), 'certificate', 'certificate.checks', 'Certificate contains a failed check.');

  return { status: issues.length === 0 ? 'PASS' : 'FAIL', issues, checks_run: checksRun };
}
