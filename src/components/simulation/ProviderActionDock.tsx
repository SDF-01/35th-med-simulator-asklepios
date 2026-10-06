import type { ReactNode } from 'react';

export type ProviderDockTab = 'treat' | 'monitor' | 'supply';

const TABS: { id: ProviderDockTab; label: string }[] = [
  { id: 'treat', label: 'Treat' },
  { id: 'monitor', label: 'Monitor' },
  { id: 'supply', label: 'Supply' },
];

interface ProviderActionDockProps {
  activeTab: ProviderDockTab;
  onTabChange: (tab: ProviderDockTab) => void;
  panelContent: ReactNode;
}

/** Bottom dock replacing stacked mobile bottom sheets. */
export function ProviderActionDock({ activeTab, onTabChange, panelContent }: ProviderActionDockProps) {
  const showPanel = activeTab !== 'treat';

  return (
    <div className="provider-action-dock">
      {showPanel && <div className="provider-action-dock__panel">{panelContent}</div>}
      <div className="provider-action-dock__tabs" role="tablist" aria-label="Simulation tools">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            className={`provider-action-dock__tab ${activeTab === tab.id ? 'provider-action-dock__tab--active' : ''}`}
            onClick={() => onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
    </div>
  );
}
