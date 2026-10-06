import { useLocation, useNavigate } from 'react-router-dom';
import { getSavedLobbyCode, buildJoinPath } from '@/utils/lobbyCode';

type TabId = 'join' | 'lobby' | 'home';

interface TabItem {
  id: TabId;
  label: string;
  path: string;
}

export function MobileTabBar() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const lobbyCode = getSavedLobbyCode();

  const tabs: TabItem[] = [
    { id: 'join', label: 'Join', path: '/join' },
    {
      id: 'lobby',
      label: 'Lobby',
      path: lobbyCode ? buildJoinPath(lobbyCode, 'provider') : '/join',
    },
    { id: 'home', label: 'Home', path: '/home' },
  ];

  function isActive(tab: TabItem): boolean {
    if (tab.id === 'join') return pathname === '/join' || pathname.startsWith('/join/') && !pathname.includes('/provider');
    if (tab.id === 'lobby') return pathname.includes('/provider');
    return pathname === '/' || pathname === '/home';
  }

  return (
    <nav className="mobile-tabbar" aria-label="Provider navigation">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          className={`mobile-tabbar__item ${isActive(tab) ? 'mobile-tabbar__item--active' : ''}`}
          onClick={() => navigate(tab.path)}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
