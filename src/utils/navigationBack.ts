import { getSavedLobbyCode, buildJoinPath } from '@/utils/lobbyCode';

export interface BackTarget {
  to: string;
  label: string;
}

function providerLobbyPath(): string {
  const saved = getSavedLobbyCode();
  return saved ? buildJoinPath(saved, 'provider') : '/join';
}

/** Predictable back navigation for training flows (not browser history). */
export function getBackTarget(pathname: string): BackTarget | null {
  if (pathname === '/' || pathname === '/home') {
    return null;
  }

  if (pathname === '/join' || pathname.startsWith('/join/')) {
    if (pathname.endsWith('/provider')) {
      return { to: '/join', label: 'Join' };
    }
    if (pathname.endsWith('/wit') || pathname.endsWith('/command')) {
      const code = pathname.split('/')[2];
      return code ? { to: `/host/${code}`, label: 'Host lobby' } : { to: '/host', label: 'Host' };
    }
    return { to: '/home', label: 'Home' };
  }

  if (pathname.startsWith('/host')) {
    return { to: '/home', label: 'Home' };
  }

  if (pathname.startsWith('/provider')) {
    if (pathname === '/provider/brief') {
      return { to: providerLobbyPath(), label: 'Lobby' };
    }
    if (pathname === '/provider/simulation') {
      return { to: '/provider/brief', label: 'Brief' };
    }
    if (pathname === '/provider/handoff') {
      return { to: '/provider/simulation', label: 'Simulation' };
    }
    if (pathname === '/provider/aar') {
      return { to: providerLobbyPath(), label: 'Lobby' };
    }
    return { to: providerLobbyPath(), label: 'Lobby' };
  }

  if (pathname.startsWith('/wit')) {
    return { to: '/host', label: 'Host' };
  }

  if (pathname.startsWith('/command')) {
    return { to: '/host', label: 'Host' };
  }

  return { to: '/home', label: 'Home' };
}
