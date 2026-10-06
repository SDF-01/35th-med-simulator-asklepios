import type { ScenarioOperationalBehaviorProfileId } from './behaviorProfiles';
import type { ScenarioRouteEdge, ScenarioRouteGraph, ScenarioRouteNode } from './types';

export interface RouteValidationResult {
  valid: boolean;
  reachable_terminal: boolean;
  no_dead_end: boolean;
  all_nodes_reachable: boolean;
  deterministic_triggers: boolean;
  all_paths_terminate: boolean;
  acyclic: boolean;
  single_terminal: boolean;
  terminal_has_no_outgoing: boolean;
  human_readable_labels: boolean;
  meaningful_branch: boolean;
  successful_route_count: number;
  profile_requirements_preserved: boolean;
  issues: string[];
}

export interface ScenarioRouteWitness {
  node_ids: string[];
  edge_ids: string[];
  triggers: ScenarioRouteEdge['trigger'][];
  terminal_node_id: string;
}

const OPERATIONAL_PROFILE_IDS: readonly ScenarioOperationalBehaviorProfileId[] = [
  'DIRECT_HANDOFF_BASELINE',
  'COMMUNICATION_RELAY_REQUIRED',
  'RESOURCE_COORDINATION_REQUIRED',
  'DUAL_CONSTRAINT_RELAY_AND_COORDINATION',
];

function operationalProfileFromRouteId(routeId: string): ScenarioOperationalBehaviorProfileId | null {
  const parts = routeId.split(':');
  const candidate = parts[parts.length - 1] ?? '';
  return OPERATIONAL_PROFILE_IDS.includes(candidate as ScenarioOperationalBehaviorProfileId)
    ? candidate as ScenarioOperationalBehaviorProfileId
    : null;
}

function requiredOperationalSemantics(
  profileId: ScenarioOperationalBehaviorProfileId,
): Array<NonNullable<ScenarioRouteNode['operational_semantic']>> {
  switch (profileId) {
    case 'DIRECT_HANDOFF_BASELINE':
      return [];
    case 'COMMUNICATION_RELAY_REQUIRED':
      return ['communications_relay'];
    case 'RESOURCE_COORDINATION_REQUIRED':
      return ['resource_coordination'];
    case 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION':
      return ['communications_relay', 'resource_coordination'];
  }
}

export function buildFieldRoute(
  routeId: string,
  profileId: ScenarioOperationalBehaviorProfileId = 'DIRECT_HANDOFF_BASELINE',
): ScenarioRouteGraph {
  const nodes: ScenarioRouteNode[] = [
    { node_id: 'briefing', node_kind: 'briefing', operational_semantic: 'orientation', label: 'Receive the operational brief', terminal: false },
    { node_id: 'approach', node_kind: 'movement', operational_semantic: 'movement', label: 'Move to the casualty location', terminal: false },
    { node_id: 'contact', node_kind: 'observation', operational_semantic: 'scene_observation', label: 'Establish contact and observe the scene', terminal: false },
    { node_id: 'pressure', node_kind: 'pressure', operational_semantic: 'operational_pressure', label: 'Respond to an operational constraint', terminal: false },
  ];

  const requiredChain: ScenarioRouteNode[] = [];
  if (profileId === 'COMMUNICATION_RELAY_REQUIRED' || profileId === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') {
    requiredChain.push({
      node_id: 'communications-relay',
      node_kind: 'handoff',
      operational_semantic: 'communications_relay',
      label: 'Establish a verified communications relay',
      terminal: false,
    });
  }
  if (profileId === 'RESOURCE_COORDINATION_REQUIRED' || profileId === 'DUAL_CONSTRAINT_RELAY_AND_COORDINATION') {
    requiredChain.push({
      node_id: 'resource-coordination',
      node_kind: 'pressure',
      operational_semantic: 'resource_coordination',
      label: 'Coordinate constrained response resources',
      terminal: false,
    });
  }
  requiredChain.push({
    node_id: 'handoff',
    node_kind: 'handoff',
    operational_semantic: 'closed_loop_handoff',
    label: 'Prepare a traceable closed loop handoff',
    terminal: false,
  });
  nodes.push(...requiredChain, {
    node_id: 'complete',
    node_kind: 'complete',
    operational_semantic: 'completion',
    label: 'Close the training evolution',
    terminal: true,
  });

  const firstRequiredNode = requiredChain[0]!.node_id;
  const edges: ScenarioRouteEdge[] = [
    { edge_id: 'e1', from: 'briefing', to: 'approach', trigger: 'start', priority: 100 },
    { edge_id: 'e2', from: 'approach', to: 'contact', trigger: 'arrive', priority: 100 },
    { edge_id: 'e3', from: 'contact', to: 'pressure', trigger: 'facilitator_event', priority: 100 },
    // The alternate route may bypass the optional operational-pressure event,
    // but it may never bypass a teamwork obligation required by the selected
    // profile. Both admitted routes therefore converge at the first required
    // profile node rather than jumping directly to completion or handoff.
    { edge_id: 'e4', from: 'contact', to: firstRequiredNode, trigger: 'handoff_ready', priority: 90 },
    { edge_id: 'e5', from: 'pressure', to: firstRequiredNode, trigger: 'handoff_ready', priority: 100 },
  ];

  let edgeNumber = 6;
  for (let index = 0; index < requiredChain.length - 1; index += 1) {
    edges.push({
      edge_id: `e${edgeNumber++}`,
      from: requiredChain[index]!.node_id,
      to: requiredChain[index + 1]!.node_id,
      trigger: 'handoff_ready',
      priority: 100,
    });
  }
  edges.push({
    edge_id: `e${edgeNumber}`,
    from: 'handoff',
    to: 'complete',
    trigger: 'close',
    priority: 100,
  });

  return { route_id: `${routeId}:${profileId}`, start_node_id: 'briefing', nodes, edges };
}

export function validateRouteGraph(route: ScenarioRouteGraph): RouteValidationResult {
  const issues: string[] = [];
  const nodeIds = route.nodes.map((node) => node.node_id);
  const nodeSet = new Set(nodeIds);
  if (nodeSet.size !== nodeIds.length) issues.push('Route node IDs must be unique.');
  if (!nodeSet.has(route.start_node_id)) issues.push('Route start node is missing.');

  const edgeIds = route.edges.map((edge) => edge.edge_id);
  if (new Set(edgeIds).size !== edgeIds.length) issues.push('Route edge IDs must be unique.');

  for (const edge of route.edges) {
    if (!nodeSet.has(edge.from)) issues.push(`Unknown edge source ${edge.from}.`);
    if (!nodeSet.has(edge.to)) issues.push(`Unknown edge destination ${edge.to}.`);
    if (edge.from === edge.to) issues.push(`Route self-loop is not admitted at ${edge.from}.`);
    if (!Number.isInteger(edge.priority)) issues.push(`Route priority must be an integer for ${edge.edge_id}.`);
  }

  const outgoing = new Map<string, ScenarioRouteEdge[]>();
  const incoming = new Map<string, ScenarioRouteEdge[]>();
  for (const edge of route.edges) {
    const sourceGroup = outgoing.get(edge.from) ?? [];
    sourceGroup.push(edge);
    outgoing.set(edge.from, sourceGroup);
    const destinationGroup = incoming.get(edge.to) ?? [];
    destinationGroup.push(edge);
    incoming.set(edge.to, destinationGroup);
  }

  const terminals = route.nodes.filter((node) => node.terminal);
  const singleTerminal = terminals.length === 1;
  if (!singleTerminal) issues.push('Route must have exactly one terminal node.');
  const terminalHasNoOutgoing = terminals.every((node) => (outgoing.get(node.node_id)?.length ?? 0) === 0);
  if (!terminalHasNoOutgoing) issues.push('Terminal route nodes must not have outgoing edges.');

  let noDeadEnd = true;
  for (const node of route.nodes) {
    if (!node.terminal && (outgoing.get(node.node_id)?.length ?? 0) === 0) {
      noDeadEnd = false;
      issues.push(`Nonterminal node ${node.node_id} has no outgoing edge.`);
    }
  }

  let deterministic = true;
  for (const [source, edges] of outgoing.entries()) {
    const seen = new Set<string>();
    for (const edge of edges) {
      if (seen.has(edge.trigger)) {
        deterministic = false;
        issues.push(`Node ${source} has more than one destination for trigger ${edge.trigger}.`);
      }
      seen.add(edge.trigger);
    }
  }

  const reached = new Set<string>();
  const queue = nodeSet.has(route.start_node_id) ? [route.start_node_id] : [];
  while (queue.length > 0) {
    const current = queue.shift()!;
    if (reached.has(current)) continue;
    reached.add(current);
    for (const edge of outgoing.get(current) ?? []) {
      if (!reached.has(edge.to)) queue.push(edge.to);
    }
  }

  const terminalReached = terminals.some((node) => reached.has(node.node_id));
  if (!terminalReached) issues.push('No terminal node is reachable from the route start.');
  const allReachable = route.nodes.every((node) => reached.has(node.node_id));
  if (!allReachable) issues.push('One or more route nodes are unreachable.');

  const canReachTerminal = new Set<string>();
  const reverseQueue = terminals.map((node) => node.node_id);
  while (reverseQueue.length > 0) {
    const current = reverseQueue.shift()!;
    if (canReachTerminal.has(current)) continue;
    canReachTerminal.add(current);
    for (const edge of incoming.get(current) ?? []) {
      if (!canReachTerminal.has(edge.from)) reverseQueue.push(edge.from);
    }
  }
  const allPathsTerminate = route.nodes.every((node) => canReachTerminal.has(node.node_id));
  if (!allPathsTerminate) issues.push('One or more route nodes cannot reach the terminal node.');

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
    for (const edge of outgoing.get(nodeId) ?? []) visit(edge.to);
    visiting.delete(nodeId);
    visited.add(nodeId);
  };
  for (const node of route.nodes) visit(node.node_id);
  if (!acyclic) issues.push('Route cycles are not admitted.');

  const labels = route.nodes.map((node) => node.label.trim().replace(/\s+/g, ' ').toLowerCase());
  const humanReadableLabels = labels.every((label) => label.length > 0 && !label.includes('_') && label.split(' ').length >= 3)
    && new Set(labels).size === labels.length;
  if (!humanReadableLabels) issues.push('Route labels must be unique plain-language phrases.');

  const meaningfulBranch = [...outgoing.entries()].some(([nodeId, edges]) => (
    reached.has(nodeId)
      && edges.length >= 2
      && new Set(edges.map((edge) => edge.to)).size >= 2
      && new Set(edges.map((edge) => edge.trigger)).size >= 2
  ));

  let successfulRouteCount = 0;
  if (acyclic && singleTerminal && terminalReached) {
    const pathMemo = new Map<string, number>();
    const countSuccessfulRoutes = (nodeId: string): number => {
      const cached = pathMemo.get(nodeId);
      if (cached !== undefined) return cached;
      const node = route.nodes.find((candidate) => candidate.node_id === nodeId);
      if (node?.terminal) return 1;
      const count = (outgoing.get(nodeId) ?? []).reduce(
        (total, edge) => total + countSuccessfulRoutes(edge.to),
        0,
      );
      pathMemo.set(nodeId, count);
      return count;
    };
    successfulRouteCount = countSuccessfulRoutes(route.start_node_id);
    if (!Number.isSafeInteger(successfulRouteCount)) {
      successfulRouteCount = 0;
      issues.push('Successful route count exceeds the safe integer boundary.');
    }
  }

  const profileId = operationalProfileFromRouteId(route.route_id);
  let profileRequirementsPreserved = true;
  if (profileId) {
    if (!meaningfulBranch || successfulRouteCount < 2) {
      profileRequirementsPreserved = false;
      issues.push(`Operational profile ${profileId} must expose at least two meaningful successful routes.`);
    }

    const requiredSemantics = requiredOperationalSemantics(profileId);
    const governedSemantics = new Set(['communications_relay', 'resource_coordination']);
    const semanticNodes = new Map<string, string[]>();
    for (const node of route.nodes) {
      if (!node.operational_semantic) continue;
      const values = semanticNodes.get(node.operational_semantic) ?? [];
      values.push(node.node_id);
      semanticNodes.set(node.operational_semantic, values);
    }
    for (const semantic of governedSemantics) {
      const expected = requiredSemantics.includes(semantic as NonNullable<ScenarioRouteNode['operational_semantic']>) ? 1 : 0;
      const observed = semanticNodes.get(semantic)?.length ?? 0;
      if (observed !== expected) {
        profileRequirementsPreserved = false;
        issues.push(`Operational profile ${profileId} requires exactly ${expected} ${semantic} node(s); observed ${observed}.`);
      }
    }

    const reachableAvoiding = (targetId: string, blockedId: string): boolean => {
      if (route.start_node_id === blockedId) return false;
      const seen = new Set<string>();
      const pending = [route.start_node_id];
      while (pending.length > 0) {
        const current = pending.shift()!;
        if (current === blockedId || seen.has(current)) continue;
        if (current === targetId) return true;
        seen.add(current);
        for (const edge of outgoing.get(current) ?? []) {
          if (edge.to !== blockedId && !seen.has(edge.to)) pending.push(edge.to);
        }
      }
      return false;
    };

    const terminalId = terminals[0]?.node_id;
    const requiredNodeIds = requiredSemantics.map((semantic) => semanticNodes.get(semantic)?.[0]).filter((value): value is string => Boolean(value));
    if (terminalId) {
      for (const requiredNodeId of requiredNodeIds) {
        if (reachableAvoiding(terminalId, requiredNodeId)) {
          profileRequirementsPreserved = false;
          issues.push(`Operational profile ${profileId} permits a successful route that bypasses ${requiredNodeId}.`);
        }
      }
    }
    for (let index = 0; index < requiredNodeIds.length - 1; index += 1) {
      if (reachableAvoiding(requiredNodeIds[index + 1]!, requiredNodeIds[index]!)) {
        profileRequirementsPreserved = false;
        issues.push(`Operational profile ${profileId} permits required teamwork steps out of order.`);
      }
    }
  }

  return {
    valid: issues.length === 0,
    reachable_terminal: terminalReached,
    no_dead_end: noDeadEnd,
    all_nodes_reachable: allReachable,
    deterministic_triggers: deterministic,
    all_paths_terminate: allPathsTerminate,
    acyclic,
    single_terminal: singleTerminal,
    terminal_has_no_outgoing: terminalHasNoOutgoing,
    human_readable_labels: humanReadableLabels,
    meaningful_branch: meaningfulBranch,
    successful_route_count: successfulRouteCount,
    profile_requirements_preserved: profileRequirementsPreserved,
    issues,
  };
}

function selectNextEdge(
  route: ScenarioRouteGraph,
  currentNodeId: string,
  trigger: ScenarioRouteEdge['trigger'],
): ScenarioRouteEdge | null {
  const candidates = route.edges
    .filter((edge) => edge.from === currentNodeId && edge.trigger === trigger)
    .sort((left, right) => right.priority - left.priority || left.edge_id.localeCompare(right.edge_id));
  return candidates[0] ?? null;
}

export function enumerateSuccessfulRouteWitnesses(
  route: ScenarioRouteGraph,
  maxWitnesses = 1_024,
): ScenarioRouteWitness[] {
  if (!Number.isSafeInteger(maxWitnesses) || maxWitnesses < 1) {
    throw new Error('Route witness limit must be a positive safe integer.');
  }

  const nodeById = new Map(route.nodes.map((node) => [node.node_id, node] as const));
  if (!nodeById.has(route.start_node_id)) throw new Error('Route witness start node is missing.');

  const outgoing = new Map<string, ScenarioRouteEdge[]>();
  for (const edge of route.edges) {
    if (!nodeById.has(edge.from)) throw new Error(`Route witness edge source is missing: ${edge.from}.`);
    if (!nodeById.has(edge.to)) throw new Error(`Route witness edge destination is missing: ${edge.to}.`);
    const group = outgoing.get(edge.from) ?? [];
    group.push(edge);
    outgoing.set(edge.from, group);
  }
  for (const group of outgoing.values()) {
    group.sort((left, right) => (
      left.trigger.localeCompare(right.trigger)
      || right.priority - left.priority
      || left.edge_id.localeCompare(right.edge_id)
    ));
  }

  const witnesses: ScenarioRouteWitness[] = [];
  const walk = (
    nodeId: string,
    nodeIds: string[],
    edgeIds: string[],
    triggers: ScenarioRouteEdge['trigger'][],
    visiting: Set<string>,
  ): void => {
    if (visiting.has(nodeId)) throw new Error(`Route witness encountered a cycle at ${nodeId}.`);
    const node = nodeById.get(nodeId);
    if (!node) throw new Error(`Route witness node is missing: ${nodeId}.`);
    if (node.terminal) {
      witnesses.push({
        node_ids: nodeIds,
        edge_ids: edgeIds,
        triggers,
        terminal_node_id: nodeId,
      });
      if (witnesses.length > maxWitnesses) throw new Error('Route witness inventory exceeds the configured limit.');
      return;
    }

    const edges = outgoing.get(nodeId) ?? [];
    if (edges.length === 0) throw new Error(`Route witness reached a nonterminal dead end at ${nodeId}.`);
    const nextVisiting = new Set(visiting).add(nodeId);
    for (const edge of edges) {
      walk(
        edge.to,
        [...nodeIds, edge.to],
        [...edgeIds, edge.edge_id],
        [...triggers, edge.trigger],
        nextVisiting,
      );
    }
  };

  walk(route.start_node_id, [route.start_node_id], [], [], new Set());
  return witnesses.sort((left, right) => (
    left.edge_ids.join('>').localeCompare(right.edge_ids.join('>'))
    || left.node_ids.join('>').localeCompare(right.node_ids.join('>'))
  ));
}

export function replayRouteWitness(
  route: ScenarioRouteGraph,
  witness: ScenarioRouteWitness,
): boolean {
  if (
    witness.node_ids.length !== witness.triggers.length + 1
    || witness.edge_ids.length !== witness.triggers.length
    || witness.node_ids[0] !== route.start_node_id
  ) return false;

  let current = route.start_node_id;
  for (let index = 0; index < witness.triggers.length; index += 1) {
    const edge = selectNextEdge(route, current, witness.triggers[index]!);
    if (!edge || edge.edge_id !== witness.edge_ids[index] || edge.to !== witness.node_ids[index + 1]) return false;
    current = edge.to;
  }
  const terminal = route.nodes.find((node) => node.node_id === current);
  return Boolean(terminal?.terminal && current === witness.terminal_node_id);
}

export function selectNextNode(
  route: ScenarioRouteGraph,
  currentNodeId: string,
  trigger: ScenarioRouteEdge['trigger'],
): string | null {
  return selectNextEdge(route, currentNodeId, trigger)?.to ?? null;
}
