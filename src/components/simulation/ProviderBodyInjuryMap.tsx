import type { ScenarioPatient, PatientState } from '@/types';
import { TcccCard } from '@/components/simulation/TcccCard';

interface ProviderBodyInjuryMapProps {
  scenarioPatient: ScenarioPatient;
  patientState: PatientState;
  sessionStartTime?: number;
  unitLabel?: string;
}

/** Provider-facing DD Form 1380 TCCC card (training simulation). */
export function ProviderBodyInjuryMap({
  scenarioPatient,
  patientState,
  sessionStartTime,
  unitLabel,
}: ProviderBodyInjuryMapProps) {
  return (
    <TcccCard
      scenarioPatient={scenarioPatient}
      patientState={patientState}
      sessionStartTime={sessionStartTime}
      unitLabel={unitLabel}
    />
  );
}
