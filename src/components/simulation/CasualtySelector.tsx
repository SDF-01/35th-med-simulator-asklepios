import type { PatientState } from '@/types';
import type { CasualtyViewMode } from '@/store/simulationStore';
import { SectionLabel } from '@/components/ui/PageHeader';
import { ToggleGroup } from '@/components/ui/ToggleGroup';

interface CasualtySelectorProps {
  patients: PatientState[];
  activePatientId: string;
  viewMode: CasualtyViewMode;
  onSelectPatient: (patientId: string) => void;
  onViewModeChange: (mode: CasualtyViewMode) => void;
}

export function CasualtySelector({
  patients,
  activePatientId,
  viewMode,
  onSelectPatient,
  onViewModeChange,
}: CasualtySelectorProps) {
  if (patients.length <= 1) return null;

  return (
    <div
      className="border-b border-ask-border bg-ask-surface px-3 py-2.5"
      role="region"
      aria-label="Casualty selection"
    >
      <div className="mb-2 flex items-center justify-between gap-2">
        <SectionLabel>Casualties</SectionLabel>
        <ToggleGroup
          label="Casualty view mode"
          options={[
            { value: 'focused', label: 'Single' },
            { value: 'all', label: 'All' },
          ]}
          value={viewMode}
          onChange={onViewModeChange}
        />
      </div>
      {viewMode === 'focused' && (
        <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="Select casualty">
          {patients.map((patient) => {
            const selected = patient.patient_id === activePatientId;
            return (
              <button
                key={patient.patient_id}
                type="button"
                role="tab"
                aria-selected={selected}
                onClick={() => onSelectPatient(patient.patient_id)}
                className={`casualty-tab ${selected ? 'casualty-tab--selected' : ''} focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ask-accent/50`}
              >
                {patient.display_label}
              </button>
            );
          })}
        </div>
      )}
      {viewMode === 'all' && (
        <p className="text-xs italic text-ask-muted">
          Actions apply to all {patients.length} casualties simultaneously.
        </p>
      )}
    </div>
  );
}
