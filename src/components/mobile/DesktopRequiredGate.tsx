import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { MobileAppShell } from '@/components/mobile/MobileAppShell';
import { MobileHeader } from '@/components/mobile/MobileHeader';
import { buildSecureControllerUrl, getControllerCapability } from '@/utils/lobbyCapability';

interface DesktopRequiredGateProps {
  role: 'wit' | 'command';
  lobbyCode?: string | null;
}

export function DesktopRequiredGate({ role, lobbyCode }: DesktopRequiredGateProps) {
  const navigate = useNavigate();
  const [copied, setCopied] = useState(false);
  const title = role === 'wit' ? 'WIT console' : 'Command room';
  const secureUrl = useMemo(() => {
    if (!lobbyCode) return null;
    const capability = getControllerCapability(lobbyCode);
    return capability ? buildSecureControllerUrl(lobbyCode, role, capability) : null;
  }, [lobbyCode, role]);

  async function copySecureLink() {
    if (!secureUrl) return;
    try {
      await navigator.clipboard.writeText(secureUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt(`Copy the secure ${title} link:`, secureUrl);
    }
  }

  return (
    <MobileAppShell showTabBar={false} header={<MobileHeader title={title} backTo="/home" showHub />}>
      <div className="mobile-page-pad">
        <Alert variant="info" title="Use a computer for this role">
          <p className="text-sm leading-relaxed">
            {title} is designed for laptop screens: scenario facilitation, device monitoring, and
            multi-panel layouts need a wider display.
          </p>
          {lobbyCode && (
            <p className="mt-3 font-mono text-lg tracking-widest text-ask-accent">
              Lobby {lobbyCode.split('').join(' ')}
            </p>
          )}
          <p className="mt-3 text-sm text-ask-muted">
            The controller credential is intentionally not recoverable from the lobby code.
          </p>
        </Alert>
        {secureUrl ? (
          <Button type="button" className="mt-6 w-full" onClick={copySecureLink}>
            {copied ? 'Secure link copied' : `Copy secure ${title} link`}
          </Button>
        ) : (
          <Alert variant="critical" className="mt-6" title="Secure link unavailable">
            Return to the browser session that created the lobby and copy the controller link from the host page.
          </Alert>
        )}
        <Button type="button" variant="secondary" className="mt-3 w-full" onClick={() => navigate('/host')}>
          Back to host lobby
        </Button>
        <Button type="button" variant="ghost" className="mt-3 w-full" onClick={() => navigate('/join')}>
          Join as provider
        </Button>
      </div>
    </MobileAppShell>
  );
}
