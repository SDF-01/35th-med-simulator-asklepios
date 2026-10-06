import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';
import { SectionLabel } from '@/components/ui/PageHeader';
import type { CommsStatus, ResourceStatus } from '@/types';
import {
  SCENARIO_CATEGORIES,
  getEventTypesForCategory,
  getSpecificsForEvent,
  normalizeScenarioSelection,
  type ScenarioSelection,
} from '@/content/scenarioTaxonomy';
import { scenariosById } from '@/content/scenarios';
import { Button } from '@/components/ui/Button';
import {
  DYNAMIC_TRIAGE_OPTIONS,
  TRIAGE_LABELS,
  adjustCasualtyTotal,
  adjustTriageCategory,
  isCasualtyConfigValid,
  triageSum,
} from '@/engines/casualtyTriageEngine';
import {
  getResolvedScenarioLabel,
  isScenarioPlayable,
  resolveBaseScenarioId,
} from '@/engines/scenarioResolver';
import type { HospitalDepartmentId } from '@/types/providerProfile';
import {
  AI_FEATURE_OPTIONS,
  SUPPLY_OPTIONS,
  type AiFeatureId,
  type CasualtyConfiguration,
  type ScenarioConfiguration,
  type TriageCategory,
  type WitSimulatorEvent,
} from '@/types/witConfig';

const COMMS_OPTIONS: CommsStatus[] = ['normal', 'degraded', 'intermittent', 'unavailable'];
const RESOURCE_OPTIONS: ResourceStatus[] = ['normal', 'constrained', 'overwhelmed'];

const TRIAGE_CARD_CLASSES: Record<TriageCategory, string> = {
  immediate: 'border-ask-critical/50 bg-ask-critical/5',
  delayed: 'border-ask-caution/50 bg-ask-caution/5',
  minimal: 'border-ask-accent/30 bg-ask-accent/5',
};

const TRIAGE_HINTS: Record<TriageCategory, string> = {
  immediate: 'Life-threatening. Treat first.',
  delayed: 'Urgent but can wait briefly',
  minimal: 'Walking wounded / minor injuries',
};

function ConfigSection({
  title,
  number,
  children,
}: {
  title: string;
  number: number;
  children: ReactNode;
}) {
  return (
    <Card as="section" padding="lg">
      <SectionLabel accent className="mb-1">
        Element {number}
      </SectionLabel>
      <h2 className="mb-4 text-lg font-semibold uppercase tracking-wide">{title}</h2>
      {children}
    </Card>
  );
}

function applySelectionUpdate(
  config: ScenarioConfiguration,
  selection: ScenarioSelection,
  department: HospitalDepartmentId,
): ScenarioConfiguration {
  const normalized = normalizeScenarioSelection(selection);
  return {
    ...config,
    scenarioSelection: normalized,
    baseScenarioId: resolveBaseScenarioId(normalized, department),
  };
}

interface WitScenarioConfigPanelProps {
  config: ScenarioConfiguration;
  onChange: (config: ScenarioConfiguration) => void;
  targetDeviceLabel?: string;
  providerDepartment?: HospitalDepartmentId;
  onDeploy?: () => void;
  deployDisabled?: boolean;
  hideDeployButton?: boolean;
}

export function WitScenarioConfigPanel({
  config,
  onChange,
  targetDeviceLabel,
  providerDepartment = 'clinical_immediate',
  onDeploy,
  deployDisabled = false,
  hideDeployButton = false,
}: WitScenarioConfigPanelProps) {
  const selection = config.scenarioSelection;
  const category = SCENARIO_CATEGORIES.find((item) => item.id === selection.categoryId);
  const eventTypes = getEventTypesForCategory(selection.categoryId);
  const specifics = getSpecificsForEvent(selection.eventTypeId);
  const resolvedLabel = getResolvedScenarioLabel(selection, config.baseScenarioId);
  const playable = isScenarioPlayable(config.baseScenarioId);
  const triageValid = isCasualtyConfigValid(config.casualties);
  const triageAllocated = triageSum(config.casualties.triage);
  const selectedSpecific = specifics.find((item) => item.id === selection.specificId);
  const engineScenario = scenariosById[config.baseScenarioId];

  function updateSelection(partial: Partial<ScenarioSelection>) {
    onChange(applySelectionUpdate(config, { ...selection, ...partial }, providerDepartment));
  }

  function updateField<K extends keyof ScenarioConfiguration>(key: K, value: ScenarioConfiguration[K]) {
    onChange({ ...config, [key]: value });
  }

  function toggleAiFeature(featureId: AiFeatureId) {
    onChange({
      ...config,
      aiFeatures: config.aiFeatures.includes(featureId)
        ? config.aiFeatures.filter((id) => id !== featureId)
        : [...config.aiFeatures, featureId],
    });
  }

  function updateCasualties(next: CasualtyConfiguration) {
    onChange({ ...config, casualties: next });
  }

  function adjustTotal(delta: number) {
    updateCasualties(adjustCasualtyTotal(config.casualties, config.casualties.total + delta));
  }

  function adjustCategory(categoryId: TriageCategory, delta: number) {
    updateCasualties(adjustTriageCategory(config.casualties, categoryId, delta));
  }

  function updateEvent(index: number, partial: Partial<WitSimulatorEvent>) {
    onChange({
      ...config,
      witEvents: config.witEvents.map((event, eventIndex) =>
        eventIndex === index ? { ...event, ...partial } : event,
      ),
    });
  }

  function addEvent() {
    onChange({
      ...config,
      witEvents: [
        ...config.witEvents,
        {
          id: `evt-${Date.now()}`,
          trigger_turn: config.witEvents.length + 3,
          type: 'inject_narrative',
          label: 'Custom event',
          description: 'Describe simulator event for this turn',
        },
      ],
    });
  }

  function removeEvent(index: number) {
    onChange({
      ...config,
      witEvents: config.witEvents.filter((_, eventIndex) => eventIndex !== index),
    });
  }

  return (
    <div>
      {targetDeviceLabel && (
        <p className="mb-4 text-sm text-ask-accent">
          Deploying to: <span className="font-semibold">{targetDeviceLabel}</span>
        </p>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <ConfigSection title="Scenario Setting" number={1}>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">Category</label>
              <select
                value={selection.categoryId}
                onChange={(e) =>
                  updateSelection({ categoryId: e.target.value as ScenarioSelection['categoryId'] })
                }
                className="w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm"
              >
                {SCENARIO_CATEGORIES.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
              {category && <p className="mt-1 text-xs text-ask-muted">{category.description}</p>}
            </div>

            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">Event Type</label>
              <select
                value={selection.eventTypeId}
                onChange={(e) =>
                  updateSelection({ eventTypeId: e.target.value as ScenarioSelection['eventTypeId'] })
                }
                className="w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm"
              >
                {eventTypes.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">Specifics</label>
              <select
                value={selection.specificId}
                onChange={(e) => updateSelection({ specificId: e.target.value })}
                className="w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm"
              >
                {specifics.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
              {selectedSpecific && (
                <p className="mt-1 text-xs text-ask-muted">{selectedSpecific.description}</p>
              )}
            </div>
          </div>

          <div className="mt-4 border-t border-ask-border pt-4">
            <p className="mb-1 text-xs uppercase text-ask-muted">Resolved Template</p>
            <p className="text-sm font-medium">{resolvedLabel}</p>
            {!playable && (
              <p className="mt-1 text-xs text-ask-caution">
                Template {config.baseScenarioId} is not fully playable yet. Deployment uses closest
                available scenario engine.
              </p>
            )}
            {engineScenario && (
              <p className="mt-1 text-xs text-ask-muted">Engine: {engineScenario.title}</p>
            )}
          </div>

          <label className="mb-3 mt-4 flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={config.aiEnhanced}
              onChange={(e) => updateField('aiEnhanced', e.target.checked)}
              className="accent-ask-accent"
            />
            AI-enhanced scenario generation
          </label>

          {config.aiEnhanced && (
            <div className="space-y-2 border-t border-ask-border pt-3">
              {AI_FEATURE_OPTIONS.map((feature) => (
                <label key={feature.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={config.aiFeatures.includes(feature.id)}
                    onChange={() => toggleAiFeature(feature.id)}
                    className="accent-ask-accent"
                  />
                  {feature.label}
                </label>
              ))}
            </div>
          )}
        </ConfigSection>

        <ConfigSection title="Casualties" number={2}>
          <p className="mb-4 text-xs text-ask-muted">
            Set total casualties, then distribute across triage categories. Allocations must equal the
            total before deploy.
          </p>

          <div className="mb-5 flex items-center gap-4">
            <span className="text-xs uppercase text-ask-muted">Total casualties</span>
            <Button variant="secondary" className="px-4 py-2" onClick={() => adjustTotal(-1)}>
              -
            </Button>
            <span className="min-w-[4rem] text-center font-mono text-3xl">
              {config.casualties.total}
            </span>
            <Button variant="secondary" className="px-4 py-2" onClick={() => adjustTotal(1)}>
              +
            </Button>
          </div>

          <div className="mb-4 space-y-2">
            {(['immediate', 'delayed', 'minimal'] as TriageCategory[]).map((categoryId) => (
              <div
                key={categoryId}
                className={`flex items-center justify-between border p-3 ${TRIAGE_CARD_CLASSES[categoryId]}`}
              >
                <div>
                  <p className="text-sm font-semibold uppercase tracking-wide">
                    {TRIAGE_LABELS[categoryId]}
                  </p>
                  <p className="text-xs text-ask-muted">{TRIAGE_HINTS[categoryId]}</p>
                </div>
                <div className="flex items-center gap-3">
                  <Button
                    variant="secondary"
                    className="px-3 py-1"
                    onClick={() => adjustCategory(categoryId, -1)}
                  >
                    -
                  </Button>
                  <span className="min-w-[2rem] text-center font-mono text-xl">
                    {config.casualties.triage[categoryId]}
                  </span>
                  <Button
                    variant="secondary"
                    className="px-3 py-1"
                    onClick={() => adjustCategory(categoryId, 1)}
                  >
                    +
                  </Button>
                </div>
              </div>
            ))}
          </div>

          <p className={`mb-5 text-xs ${triageValid ? 'text-ask-accent' : 'text-ask-critical'}`}>
            Allocated: {triageAllocated} / {config.casualties.total}
            {!triageValid && '. Triage must equal total casualties.'}
          </p>

          <div>
            <p className="mb-2 text-xs uppercase text-ask-muted">Dynamic triage (Provider)</p>
            <div className="space-y-2">
              {DYNAMIC_TRIAGE_OPTIONS.map((option) => (
                <label
                  key={option.id}
                  className={`flex cursor-pointer items-start gap-3 border p-3 ${
                    config.casualties.dynamicTriage === option.id
                      ? 'border-ask-accent bg-ask-accent/10'
                      : 'border-ask-border'
                  }`}
                >
                  <input
                    type="radio"
                    name="dynamic-triage"
                    checked={config.casualties.dynamicTriage === option.id}
                    onChange={() =>
                      updateCasualties({ ...config.casualties, dynamicTriage: option.id })
                    }
                    className="mt-1 accent-ask-accent"
                  />
                  <div>
                    <p className="font-medium">{option.label}</p>
                    <p className="text-xs text-ask-muted">{option.description}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </ConfigSection>

        <ConfigSection title="Constraints" number={3}>
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">Comms</label>
              <select
                value={config.constraints.comms_status}
                onChange={(e) =>
                  onChange({
                    ...config,
                    constraints: {
                      ...config.constraints,
                      comms_status: e.target.value as CommsStatus,
                    },
                  })
                }
                className="w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm capitalize"
              >
                {COMMS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">Resources</label>
              <select
                value={config.constraints.resource_status}
                onChange={(e) =>
                  onChange({
                    ...config,
                    constraints: {
                      ...config.constraints,
                      resource_status: e.target.value as ResourceStatus,
                    },
                  })
                }
                className="w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm capitalize"
              >
                {RESOURCE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">
                Treatment time (minutes)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={5}
                  max={45}
                  step={5}
                  value={config.constraints.treatment_time_minutes}
                  onChange={(e) =>
                    onChange({
                      ...config,
                      constraints: {
                        ...config.constraints,
                        treatment_time_minutes: Number(e.target.value),
                      },
                    })
                  }
                  className="flex-1 accent-ask-accent"
                />
                <span className="font-mono text-lg">
                  {config.constraints.treatment_time_minutes}
                </span>
              </div>
              <p className="mt-1 text-xs text-ask-muted">
                Time pressure before ambient deterioration escalates.
              </p>
            </div>
            <div>
              <label className="mb-1 block text-xs uppercase text-ask-muted">
                Deterioration interval (turns)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={2}
                  max={8}
                  step={1}
                  value={config.constraints.deterioration_interval_turns}
                  onChange={(e) =>
                    onChange({
                      ...config,
                      constraints: {
                        ...config.constraints,
                        deterioration_interval_turns: Number(e.target.value),
                      },
                    })
                  }
                  className="flex-1 accent-ask-accent"
                />
                <span className="font-mono text-lg">
                  {config.constraints.deterioration_interval_turns}
                </span>
              </div>
              <p className="mt-1 text-xs text-ask-muted">
                How often complications may occur during treatment.
              </p>
            </div>
          </div>
          <textarea
            value={config.constraints.environmental_notes}
            onChange={(e) =>
              onChange({
                ...config,
                constraints: { ...config.constraints, environmental_notes: e.target.value },
              })
            }
            rows={3}
            placeholder="Environmental / operational constraints..."
            className="w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm"
          />
        </ConfigSection>

        <ConfigSection title="Supply" number={4}>
          <div className="space-y-2">
            {SUPPLY_OPTIONS.map((option) => (
              <label
                key={option.id}
                className={`flex cursor-pointer items-start gap-3 border p-3 ${
                  config.supply === option.id
                    ? 'border-ask-accent bg-ask-accent/10'
                    : 'border-ask-border'
                }`}
              >
                <input
                  type="radio"
                  name="supply"
                  checked={config.supply === option.id}
                  onChange={() => updateField('supply', option.id)}
                  className="mt-1 accent-ask-accent"
                />
                <div>
                  <p className="font-medium">{option.label}</p>
                  <p className="text-xs text-ask-muted">{option.description}</p>
                </div>
              </label>
            ))}
          </div>
        </ConfigSection>

        <ConfigSection title="Time for Medical Care" number={5}>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min={5}
              max={60}
              step={5}
              value={config.timeLimitMinutes}
              onChange={(e) => updateField('timeLimitMinutes', Number(e.target.value))}
              className="flex-1 accent-ask-accent"
            />
            <span className="font-mono text-2xl">{config.timeLimitMinutes}</span>
            <span className="text-sm text-ask-muted">min</span>
          </div>
        </ConfigSection>

        <section className="border border-ask-border bg-ask-surface p-5 lg:col-span-2">
          <h2 className="mb-4 text-lg font-semibold uppercase tracking-wide">
            Disposition & Turn Events
          </h2>
          <textarea
            value={config.dispositionRequirements}
            onChange={(e) => updateField('dispositionRequirements', e.target.value)}
            rows={2}
            placeholder="Disposition / requirements for Provider..."
            className="mb-6 w-full border border-ask-border bg-ask-bg px-3 py-2 text-sm"
          />

          <div className="space-y-3">
            {config.witEvents.map((event, index) => (
              <div
                key={event.id}
                className="grid gap-3 border border-ask-border bg-ask-bg p-3 md:grid-cols-[100px_140px_1fr_auto]"
              >
                <input
                  type="number"
                  min={0}
                  value={event.trigger_turn}
                  onChange={(e) => updateEvent(index, { trigger_turn: Number(e.target.value) })}
                  className="border border-ask-border bg-ask-surface px-2 py-1 text-sm"
                />
                <select
                  value={event.type}
                  onChange={(e) =>
                    updateEvent(index, { type: e.target.value as WitSimulatorEvent['type'] })
                  }
                  className="border border-ask-border bg-ask-surface px-2 py-1 text-sm"
                >
                  <option value="block_patient_death">Block patient death</option>
                  <option value="block_scenario_end">Block scenario end</option>
                  <option value="inject_narrative">Inject narrative</option>
                  <option value="inject_complication">Inject complication</option>
                  <option value="unlock_deterioration">Unlock deterioration</option>
                </select>
                <input
                  type="text"
                  value={event.description}
                  onChange={(e) => updateEvent(index, { description: e.target.value })}
                  className="border border-ask-border bg-ask-surface px-2 py-1 text-sm"
                />
                <Button variant="ghost" className="px-2 py-1 text-xs" onClick={() => removeEvent(index)}>
                  Remove
                </Button>
              </div>
            ))}
          </div>

          <Button variant="secondary" className="mt-3" onClick={addEvent}>
            Add Simulator Event
          </Button>
        </section>
      </div>

      {!hideDeployButton && onDeploy && (
        <div className="mt-6">
          <Button onClick={onDeploy} disabled={deployDisabled || !triageValid}>
            Deploy Scenario to Device
          </Button>
        </div>
      )}
    </div>
  );
}
