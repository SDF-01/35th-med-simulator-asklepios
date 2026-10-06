import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { DeviceProvider } from '@/context/DeviceContext';
import { AARPage } from '@/pages/AARPage';
import { CommandRoomPage } from '@/pages/CommandRoomPage';
import { HostExercisePage } from '@/pages/HostExercisePage';
import { JoinLobbyPage } from '@/pages/JoinLobbyPage';
import { LandingPage } from '@/pages/LandingPage';
import { ProviderBriefPage } from '@/pages/ProviderBriefPage';
import { ProviderHandoffPage } from '@/pages/ProviderHandoffPage';
import { ProviderLobbyPage } from '@/pages/ProviderLobbyPage';
import { ProviderSimulationPage } from '@/pages/ProviderSimulationPage';
import { WitDashboardPage } from '@/pages/WitDashboardPage';
import { ResearchScenarioLabPage } from '@/pages/ResearchScenarioLabPage';
import { FacilityDecisionIntegrityPage } from '@/pages/FacilityDecisionIntegrityPage';
import {
  FacilityDecisionDemoPage,
  FacilityDecisionInstructorPage,
  FacilityDecisionLearnerPage,
  FacilityDecisionTeachingPage,
} from '@/pages/FacilityDecisionSessionPage';
import { FacilityArrivalExamplePage } from '@/pages/FacilityArrivalExamplePage';
import { ScenarioLibraryPage } from '@/pages/ScenarioLibraryPage';
import { SoloPracticePage } from '@/pages/SoloPracticePage';
import { getSavedLobbyCode, buildJoinPath } from '@/utils/lobbyCode';

function HomeRoute() {
  const mode = import.meta.env.VITE_ENTRY_MODE;
  if (mode === 'provider') return <Navigate to="/join" replace />;
  if (mode === 'wit') return <Navigate to="/host" replace />;
  return <LandingPage />;
}

function LegacyProviderRoute() {
  const saved = getSavedLobbyCode();
  if (saved) return <Navigate to={buildJoinPath(saved, 'provider')} replace />;
  return <Navigate to="/join" replace />;
}

function LegacyWitRoute() {
  const saved = getSavedLobbyCode();
  if (saved) return <Navigate to={`/host/${encodeURIComponent(saved)}`} replace />;
  return <Navigate to="/host" replace />;
}

function LegacyCommandRoute() {
  const saved = getSavedLobbyCode();
  if (saved) return <Navigate to={buildJoinPath(saved, 'command')} replace />;
  return <Navigate to="/join" replace />;
}

export default function App() {
  return (
    <DeviceProvider>
      <BrowserRouter>
        <Routes>
        <Route path="/" element={<HomeRoute />} />
        <Route path="/home" element={<LandingPage />} />

        <Route path="/join" element={<JoinLobbyPage />} />
        <Route path="/join/:code" element={<JoinLobbyPage />} />
        <Route path="/join/:code/provider" element={<ProviderLobbyPage />} />
        <Route path="/join/:code/wit" element={<WitDashboardPage />} />
        <Route path="/join/:code/command" element={<CommandRoomPage />} />

        <Route path="/host" element={<HostExercisePage />} />
        <Route path="/host/:code" element={<HostExercisePage />} />
        <Route path="/solo" element={<SoloPracticePage />} />
        <Route path="/scenarios" element={<ScenarioLibraryPage />} />
        <Route path="/scenario-library" element={<ScenarioLibraryPage />} />
        <Route path="/scenario-science" element={<ScenarioLibraryPage />} />
        <Route path="/research-sandbox" element={<ResearchScenarioLabPage />} />
        <Route path="/examples/facility-decision" element={<FacilityDecisionIntegrityPage />} />
        <Route path="/examples/facility-decision/learner" element={<FacilityDecisionLearnerPage />} />
        <Route path="/examples/facility-decision/teaching" element={<FacilityDecisionTeachingPage />} />
        <Route path="/examples/facility-decision/instructor" element={<FacilityDecisionInstructorPage />} />
        <Route path="/examples/facility-decision/demo" element={<FacilityDecisionDemoPage />} />
        <Route path="/examples/facility-arrival" element={<FacilityArrivalExamplePage />} />

        <Route path="/provider" element={<LegacyProviderRoute />} />
        <Route path="/provider/brief" element={<ProviderBriefPage />} />
        <Route path="/provider/simulation" element={<ProviderSimulationPage />} />
        <Route path="/provider/handoff" element={<ProviderHandoffPage />} />
        <Route path="/provider/aar" element={<AARPage />} />

        <Route path="/wit" element={<LegacyWitRoute />} />
        <Route path="/command" element={<LegacyCommandRoute />} />

        <Route path="/role-selection" element={<Navigate to="/join" replace />} />
        <Route path="/wit-console" element={<Navigate to="/join" replace />} />
        <Route path="/training-mode" element={<Navigate to="/join" replace />} />
        <Route path="/brief" element={<Navigate to="/provider/brief" replace />} />
        <Route path="/simulation" element={<Navigate to="/provider/simulation" replace />} />
        <Route path="/aar" element={<Navigate to="/provider/aar" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </DeviceProvider>
  );
}
