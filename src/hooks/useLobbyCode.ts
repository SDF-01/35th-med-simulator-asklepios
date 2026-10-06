import { useEffect, useMemo } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { setActiveLobbyCode } from '@/services/networkHub';
import { importControllerCapabilityFromFragment } from '@/utils/lobbyCapability';
import {
  getSavedLobbyCode,
  isValidLobbyCode,
  normalizeLobbyCode,
  saveLobbyCode,
} from '@/utils/lobbyCode';

export function resolveLobbyCodeFromRoute(
  paramCode?: string,
  searchCode?: string | null,
): string | null {
  const fromParam = paramCode ? normalizeLobbyCode(paramCode) : '';
  if (isValidLobbyCode(fromParam)) return fromParam;

  const fromSearch = searchCode ? normalizeLobbyCode(searchCode) : '';
  if (isValidLobbyCode(fromSearch)) return fromSearch;

  const saved = getSavedLobbyCode();
  if (saved && isValidLobbyCode(saved)) return saved;

  return null;
}

/** Binds lobby code from URL or storage and syncs it to the network hub client. */
export function useLobbyCode(options?: { redirectIfMissing?: boolean }): string | null {
  const navigate = useNavigate();
  const { code: paramCode } = useParams<{ code?: string }>();
  const [searchParams] = useSearchParams();

  const code = useMemo(
    () => resolveLobbyCodeFromRoute(paramCode, searchParams.get('code')),
    [paramCode, searchParams],
  );

  useEffect(() => {
    if (code) {
      importControllerCapabilityFromFragment(code);
      saveLobbyCode(code);
      setActiveLobbyCode(code);
      return;
    }
    setActiveLobbyCode(null);
    if (options?.redirectIfMissing) {
      navigate('/join', { replace: true });
    }
  }, [code, navigate, options?.redirectIfMissing]);

  return code;
}
