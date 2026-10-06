import type {
  ResearchPrototypeRecord,
  ResearchSandboxEvent,
  ResearchSandboxState,
} from './types';

function hash32(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function eventId(prototypeId: string, sequence: number, type: string): string {
  return `rse-${hash32(`${prototypeId}|${sequence}|${type}`).toString(16).padStart(8, '0')}`;
}

function makeEvent(
  state: ResearchSandboxState,
  eventType: ResearchSandboxEvent['event_type'],
  payload: ResearchSandboxEvent['payload'],
  elapsedSeconds = state.elapsed_seconds,
): ResearchSandboxEvent {
  const sequence = state.events.length + 1;
  return {
    event_id: eventId(state.prototype_id, sequence, eventType),
    event_type: eventType,
    sequence,
    elapsed_seconds: elapsedSeconds,
    payload,
  };
}

export function startResearchSandbox(prototype: ResearchPrototypeRecord): ResearchSandboxState {
  const initial: ResearchSandboxState = {
    prototype_id: prototype.prototype_id,
    deterministic_seed: prototype.seed,
    retriever_track: prototype.retriever_track,
    elapsed_seconds: 0,
    revealed_cues: [],
    triggered_resource_events: [],
    learner_notes: [],
    events: [],
    mode: 'research_sandbox',
    scoring_enabled: false,
    clinical_authority: 'NOT_GRANTED',
  };
  return reduceResearchEvent(initial, makeEvent(initial, 'sandbox_started', {
    topic_id: prototype.topic_id,
    retriever_track: prototype.retriever_track,
  }));
}

export function reduceResearchEvent(
  state: ResearchSandboxState,
  event: ResearchSandboxEvent,
): ResearchSandboxState {
  if (event.sequence !== state.events.length + 1) {
    throw new Error('Research event sequence is not contiguous.');
  }
  const next: ResearchSandboxState = {
    ...state,
    elapsed_seconds: Math.max(state.elapsed_seconds, event.elapsed_seconds),
    events: [...state.events, event],
  };
  if (event.event_type === 'cue_revealed') {
    const cue = String(event.payload.cue ?? '');
    next.revealed_cues = cue && !state.revealed_cues.includes(cue)
      ? [...state.revealed_cues, cue]
      : state.revealed_cues;
  }
  if (event.event_type === 'resource_event_triggered') {
    const value = String(event.payload.resource_event ?? '');
    next.triggered_resource_events = value && !state.triggered_resource_events.includes(value)
      ? [...state.triggered_resource_events, value]
      : state.triggered_resource_events;
  }
  if (event.event_type === 'learner_note_recorded') {
    const note = String(event.payload.note ?? '').trim();
    next.learner_notes = note ? [...state.learner_notes, note] : state.learner_notes;
  }
  if (event.event_type === 'sandbox_reset') {
    return {
      ...state,
      elapsed_seconds: 0,
      revealed_cues: [],
      triggered_resource_events: [],
      learner_notes: [],
      events: [event],
    };
  }
  return next;
}

export function advanceResearchSandbox(state: ResearchSandboxState, seconds: number): ResearchSandboxState {
  const safeSeconds = Math.max(1, Math.floor(seconds));
  return reduceResearchEvent(
    state,
    makeEvent(state, 'time_advanced', { seconds: safeSeconds }, state.elapsed_seconds + safeSeconds),
  );
}

export function revealResearchCue(state: ResearchSandboxState, cue: string): ResearchSandboxState {
  return reduceResearchEvent(state, makeEvent(state, 'cue_revealed', { cue }));
}

export function triggerResearchResourceEvent(
  state: ResearchSandboxState,
  resourceEvent: string,
): ResearchSandboxState {
  return reduceResearchEvent(
    state,
    makeEvent(state, 'resource_event_triggered', { resource_event: resourceEvent }),
  );
}

export function recordResearchLearnerNote(state: ResearchSandboxState, note: string): ResearchSandboxState {
  return reduceResearchEvent(state, makeEvent(state, 'learner_note_recorded', { note }));
}

export function replayResearchSandbox(
  prototype: ResearchPrototypeRecord,
  events: ResearchSandboxEvent[],
): ResearchSandboxState {
  let state: ResearchSandboxState = {
    prototype_id: prototype.prototype_id,
    deterministic_seed: prototype.seed,
    retriever_track: prototype.retriever_track,
    elapsed_seconds: 0,
    revealed_cues: [],
    triggered_resource_events: [],
    learner_notes: [],
    events: [],
    mode: 'research_sandbox',
    scoring_enabled: false,
    clinical_authority: 'NOT_GRANTED',
  };
  for (const event of events) state = reduceResearchEvent(state, event);
  return state;
}
