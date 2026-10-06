import crypto from 'node:crypto';

/** Shared pure renderers for Node-side engine-evolution documentation checks.
 *
 * Python remains the independently implemented canonical writer. Node checkers
 * share these pure renderers so a second stale Node rendering cannot silently
 * disagree with another check inside the same verification boundary.
 */

export const EVOLUTION_START = '<!-- asklepios-offline-evolution:start -->';
export const EVOLUTION_END = '<!-- asklepios-offline-evolution:end -->';

function normalizeCanonical(value, location = '$') {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) throw new TypeError(`non-safe canonical integer:${location}`);
    return value;
  }
  if (Array.isArray(value)) return value.map((item, index) => normalizeCanonical(item, `${location}[${index}]`));
  if (typeof value === 'object') {
    return Object.fromEntries(Object.keys(value).sort().map((key) => [key, normalizeCanonical(value[key], `${location}.${key}`)]));
  }
  throw new TypeError(`unsupported canonical value:${location}`);
}

export function graphContractProjection(graph) {
  if (!graph || typeof graph !== 'object' || Array.isArray(graph)) throw new TypeError('release graph must be an object');
  const inputSets = {};
  for (const setId of Object.keys(graph.input_sets ?? {}).sort()) {
    const specification = graph.input_sets[setId];
    inputSets[setId] = {
      include: specification.include ?? [],
      exclude: specification.exclude ?? [],
      file_paths: Object.keys(specification.files ?? {}).sort(),
    };
  }
  return {
    schema_version: graph.schema_version,
    graph_id: graph.graph_id,
    classifications: graph.classifications,
    managed_package_scripts: graph.managed_package_scripts,
    production_designation: graph.production_designation,
    release_candidate: graph.release_candidate,
    truth_boundaries: graph.truth_boundaries,
    input_sets: inputSets,
    stages: graph.stages,
    targets: graph.targets,
    integrations: graph.integrations,
  };
}

export function graphContractSha256(graph) {
  const bytes = Buffer.from(JSON.stringify(normalizeCanonical(graphContractProjection(graph))), 'utf8');
  return crypto.createHash('sha256').update(bytes).digest('hex');
}

function validatedOptions({ graphBindingMode, graphContractSha256 } = {}) {
  if (typeof graphBindingMode !== 'string' || graphBindingMode.length === 0) {
    throw new TypeError('graphBindingMode is required');
  }
  if (!/^[0-9a-f]{64}$/.test(graphContractSha256 ?? '')) {
    throw new TypeError('graphContractSha256 must be a lowercase SHA-256 digest');
  }
  return { graphBindingMode, graphContractSha256 };
}

export function renderEvolutionBlock(
  ctx,
  {
    heading = '## Engine evolution binding',
    ...rawOptions
  } = {},
) {
  const { graphBindingMode, graphContractSha256 } = validatedOptions(rawOptions);
  return [
    EVOLUTION_START,
    heading,
    '',
    `This artifact is bound to **${ctx.policy.display_version}** (\`${ctx.policy.release_id}\`), the evidence-calibrated evolution that adds a deterministic Scenario Genome, true behavioral-policy diversity, a balanced operational scenario pack, stakeholder scorecards, a fail-closed treatment-admission pipeline, dual monotonic ratchets, differential documentation verification, and graph-receipt-bound scenario-evolution evidence.`,
    '',
    `- Engine evolution profile: \`${ctx.policy.engine_evolution}\``,
    `- Scenario Genome: \`${ctx.genome.genome_id}\` (\`${ctx.genome.genome_sha256}\`)`,
    `- Capability ratchet: \`${ctx.capability.ratchet_id}\`, epoch \`${ctx.capability.ratchet_epoch}\` (\`${ctx.capability.ratchet_anchor_sha256}\`)`,
    `- Technical-debt ratchet: \`${ctx.debt.ratchet_id}\`, epoch \`${ctx.debt.ratchet_epoch}\` (\`${ctx.debt.ratchet_anchor_sha256}\`)`,
    `- Canonical release graph: \`${ctx.graph.graph_id}\` with \`${ctx.graph.stages.length}\` stages and \`${Object.keys(ctx.graph.targets).length}\` targets`,
    '- Behavioral quality-diversity: the ratcheted archive preserves 107 unique structural behavior signatures across all 30 observed behavior cells; its integer quality vector selects scenario representatives only and never scores learners.',
    '- Behavioral policy diversity: 107 operational contexts are quotient-checked into four genuinely different decision-policy classes; wording, names, provenance, and seeds cannot claim novelty by themselves.',
    '- Operational scenario pack: 12 reviewed scenarios are balanced three-per-profile across direct handoff, communication relay, resource coordination, and dual-constraint coordination.',
    '- Four playable offline role-model teamwork challenges: the standalone file lets the user select and play direct handoff, communications relay, resource coordination, or the combined relay-and-resource route; added teamwork actions carry zero clinical points.',
    '- Source-conformance scorecard: four reference scorecards expose evidence by competency dimension, preserve a hard safety gate, and return INSUFFICIENT_EVIDENCE rather than fabricated precision; they are not psychometrically validated proficiency scores.',
    '- Treatment-admission pipeline: two treatment concepts remain DISCOVERED, zero are SIMULATION_ADMITTED, and zero active learner treatment choices are allowed until exact source spans, applicability, scope, and SME review are complete.',
    '- Plain-language release translation: every release must state what changed for learners, instructors, reviewers, and maintainers, plus what remains uncalibrated or prohibited.',
    '- Scenario-science telemetry: event traces are privacy-bounded, append-only, and hash-chained; they create calibration evidence without silently promoting exercise timing or learner scoring.',
    `- Release-identity DAG: \`${graphBindingMode}\` contract \`${graphContractSha256}\``,
    '- Truth boundary: clinical authority `NOT_GRANTED`; operational calibration `NOT_CALIBRATED`; patient-care use `PROHIBITED`; human-team behavior `STRUCTURAL_ONLY_NOT_CALIBRATED`; patient dynamics `SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY`; quality-vector use `SCENARIO_SELECTION_ONLY_NOT_LEARNER_SCORING`.',
    '',
    '- Canonical-writer rule: each governed artifact has one writer and at least one independently implemented read-only verifier.',
    '- Receipt rule: a committed `PASS` report is insufficient; final evidence must bind current graph, stage configuration, inputs, and output hashes.',
    '- Release-identity rule: the offline descriptor binds an acyclic semantic graph projection rather than the graph\'s raw file hash, while the graph independently locks the descriptor.',
    '- Route topology: the Scenario Genome admits only reachable, terminating, cycle-free routes with zero nonterminal dead ends.',
    '- Technical-debt rule: reviewed blocker classifications, evidence floors, and final receipt requirements cannot be silently weakened.',
    '- Regression rule: future epochs may raise demonstrated floors but cannot lower them without an explicit reviewed epoch change and renewed evidence.',
    '',
    'The Scenario Genome is a structural identity and provenance artifact. It does not establish clinical certification, empirical timing, human-behavior calibration, treatment effect, dynamic physiology, psychometric validity, or suitability for direct patient care.',
    EVOLUTION_END,
  ].join('\n');
}

export function renderRootSection(ctx, rawOptions = {}) {
  const { graphBindingMode, graphContractSha256 } = validatedOptions(rawOptions);
  const docs = ctx.policy.documentation_contract;
  const experience = ctx.capability.hard_floors.scenario_experience;
  const contract = ctx.capability.hard_floors.scenario_contract;
  return [
    docs.root_start_marker,
    `## Current canonical offline scenario and engine evolution (${ctx.policy.display_version})`,
    '',
    '[Open the complete Facility Arrival walkthrough](examples/facility-arrival/README.md), or download [`playable.html`](examples/facility-arrival/playable.html?raw=1) and double-click it.',
    '',
    '[Open the browser-based Facility Arrival experience](/examples/facility-arrival).',
    '',
    'The standalone file embeds the learner interface, WIT process view, deterministic state machine, hidden-information schedule, clock-driven world events, timeout and unsafe-action branches, provenance view, replay, and after-action review. It requires no server, package installation, API, WebSocket, Vercel deployment, or network request.',
    '',
    '### Four playable offline role-model teamwork challenges',
    '',
    '- **Direct handoff baseline** — complete the normal closed-loop receiving workflow.',
    '- **Communications relay** — establish an intermediate relay and confirm receipt before the final handoff.',
    '- **Resource coordination** — coordinate a constrained resource and confirm ownership before the final handoff.',
    '- **Relay and resource coordination** — establish the relay first, coordinate the constrained resource second, and then close the handoff.',
    '',
    'Open `examples/facility-arrival/playable.html`, choose a role-model challenge at the top, and play it manually, with **Watch autoplay**, or with **Complete canonical replay**. These profiles keep the same source-bound clinical template; their added teamwork actions award zero clinical points and their timing remains uncalibrated exercise timing.',
    '',
    '[Open the canonical verified example](examples/verified-scenario/README.md) for the source package, Scenario Genome, evidence identity ledger, route topology, and open validity gates.',
    '',
    '### Scenario Genome, dual ratchets, and authenticated evidence',
    '',
    `This documentation is generated from **${ctx.policy.display_version}** (\`${ctx.policy.release_id}\`) and \`${ctx.graph.graph_id}\`.`,
    '',
    `- Engine evolution profile: \`${ctx.policy.engine_evolution}\``,
    `- Scenario Genome: \`${ctx.genome.genome_id}\` (\`${ctx.genome.genome_sha256}\`)`,
    `- Capability ratchet: \`${ctx.capability.ratchet_id}\`, epoch \`${ctx.capability.ratchet_epoch}\` (\`${ctx.capability.ratchet_anchor_sha256}\`)`,
    `- Technical-debt ratchet: \`${ctx.debt.ratchet_id}\`, epoch \`${ctx.debt.ratchet_epoch}\` (\`${ctx.debt.ratchet_anchor_sha256}\`)`,
    `- Canonical release graph: \`${ctx.graph.graph_id}\` with \`${ctx.graph.stages.length}\` stages and \`${Object.keys(ctx.graph.targets).length}\` targets`,
    `- Structural floor: \`${experience.generated_cases}\` generated scenarios, \`${experience.unique_operational_contexts}\` distinct contexts, strength-\`${experience.covering_array_strength}\` coverage, \`${experience.covered_interactions}/${experience.required_interactions}\` feasible interactions, and zero uncovered interactions`,
    `- Contract floor: \`${contract.generated_cases}\` cases across \`${contract.unique_operational_contexts}\` distinct contract contexts`,
    '- Behavioral quality-diversity: 107 unique structural behavior signatures occupy all 30 observed behavior cells; narrative-only and provenance-only variants do not create new behavior, and the integer quality vector is limited to scenario selection rather than learner scoring.',
    '- Behavioral policy diversity: four verified policy-equivalence classes require materially different learner coordination rather than cosmetic context changes.',
    '- Operational scenario pack: 12 reviewed scenarios are balanced three-per-profile across the four operational behavior classes.',
    '- Four playable offline role-model teamwork challenges: the no-server file exposes direct handoff, communications relay, resource coordination, and the combined route as selectable, replayable examples.',
    '- Source-conformance scorecard: four reference scorecards show evidence by dimension, preserve hard safety failure, and explicitly distinguish insufficient evidence from proficiency.',
    '- Treatment-admission pipeline: two concepts are tracked, zero are simulation-admitted, and no treatment choice is activated before source, applicability, scope, and SME gates pass.',
    '- Plain-language release translation: each release must explain stakeholder-visible changes and remaining scientific limitations without implementation jargon.',
    '- Checker boundary: all Node scenario-release checkers share one strict cross-platform CLI, repository-relative path guard, and atomic report writer.',
    '- Artifact authority: every governed artifact class has one canonical writer and at least one independently implemented read-only verifier.',
    '- Evidence freshness: final joins authenticate the current graph, stage configuration, input hashes, output hashes, and receipt chain; a copied `PASS` report is insufficient.',
    `- Release-identity DAG: the offline descriptor binds \`${graphBindingMode}\` contract \`${graphContractSha256}\` rather than the graph's raw file hash, while the graph independently locks the descriptor. This prevents self-referential hash cycles.`,
    '- Route topology: only reachable, terminating, cycle-free routes with zero reachable nonterminal dead ends are admitted.',
    '- Technical-debt ratchet: reviewed debt records, blocker classifications, evidence floors, and final receipt obligations cannot be silently removed or weakened.',
    '- Diagnostic model: independent read-only branches may continue after a failure so one run can report the complete safe failure inventory; publication still fails closed.',
    '',
    'Clinical authority remains NOT_GRANTED. Operational timing remains NOT_CALIBRATED. Patient dynamics remain SOURCE_BOUND_STATIC_OBSERVATIONS_ONLY. Direct patient care and clinical decision support remain prohibited.',
    '',
    'Rebuild and verify the offline boundary:',
    '',
    '```bash',
    'npm run generate:facility-arrival',
    'npm run generate:verified-scenario',
    'npm run generate:facility-arrival-standalone',
    'npm run generate:offline-scenario-release',
    'npm run verify:offline-scenario-release',
    'npm run verify:engine-evolution-docs',
    'npm run verify:facility-arrival-standalone',
    '```',
    docs.root_end_marker,
  ].join('\n');
}

export function renderStandaloneSection(ctx, rawOptions = {}) {
  const { graphBindingMode, graphContractSha256 } = validatedOptions(rawOptions);
  const docs = ctx.policy.documentation_contract;
  return [
    docs.standalone_start_marker,
    '## Engine evolution and reproducibility boundary',
    '',
    `The canonical offline artifact is bound to **${ctx.policy.display_version}** (\`${ctx.policy.release_id}\`) and \`${ctx.policy.engine_evolution}\`.`,
    '',
    `- Scenario Genome: \`${ctx.genome.genome_id}\` (\`${ctx.genome.genome_sha256}\`)`,
    `- Capability ratchet: \`${ctx.capability.ratchet_id}\`, epoch \`${ctx.capability.ratchet_epoch}\` (\`${ctx.capability.ratchet_anchor_sha256}\`)`,
    `- Technical-debt ratchet: \`${ctx.debt.ratchet_id}\`, epoch \`${ctx.debt.ratchet_epoch}\` (\`${ctx.debt.ratchet_anchor_sha256}\`)`,
    `- Release graph: \`${ctx.graph.graph_id}\` with \`${ctx.graph.stages.length}\` stages and \`${Object.keys(ctx.graph.targets).length}\` targets`,
    `- Release-identity DAG: \`${graphBindingMode}\` contract \`${graphContractSha256}\``,
    '- Canonical writer: `scripts/build_facility_arrival_standalone.py`',
    '- Independent verifier: `scripts/check_facility_arrival_standalone.py`',
    '- Offline release writer: `scripts/build_offline_scenario_release.py`',
    '- Independent offline verifier: `scripts/check_offline_scenario_release.mjs`',
    '',
    "The single-file artifact has no external runtime asset, server, API, WebSocket, or network request. Its content-security policy includes `connect-src 'none'`. The embedded simulation clock is deterministic and reproducible; it is not an empirically calibrated real-clinical workflow clock.",
    '',
    'Behavioral quality-diversity is structural and deterministic: 107 unique behavior signatures occupy all 30 observed cells. Narrative-only and provenance-only changes do not create new behavior, and the integer quality vector is restricted to scenario selection rather than learner scoring.',
    '',
    'Behavioral policy diversity distinguishes four genuinely different coordination policies. The operational scenario pack contains 12 reviewed scenarios, balanced three per policy profile.',
    '',
    '### Four playable offline role-model teamwork challenges',
    '',
    'The standalone page itself exposes **Direct handoff baseline**, **Communications relay**, **Resource coordination**, and **Relay and resource coordination**. The user can select any challenge and complete it manually, replay the canonical route immediately, or watch the deterministic autoplay. Added relay and resource actions are operational only, carry zero clinical points, and do not claim calibrated human timing.',
    '',
    'The source-conformance scorecard preserves hard safety failure and reports insufficient evidence rather than fabricated proficiency. The treatment-admission pipeline tracks two discovered concepts, but zero are simulation-admitted and zero active learner treatment choices exist. Plain-language release translation is required for every release.',
    '',
    'A release report is not accepted merely because it says `PASS`. Evidence consumers authenticate the current release graph, stage configuration, source inputs, output inventory, output hashes, and receipt chain. The offline descriptor uses an acyclic semantic graph projection instead of a raw graph-file digest, and capability and technical-debt floors are monotonic across ratchet epochs.',
    '',
    'This boundary demonstrates software integrity and simulation behavior only. It does not establish clinical certification, treatment authority, dynamic physiology, causal effect, human-team calibration, psychometric validity, or suitability for direct patient care.',
    docs.standalone_end_marker,
  ].join('\n');
}
