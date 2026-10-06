import { useLocation, useNavigate } from 'react-router-dom';
import { HubOfflineBanner } from '@/components/ui/HubOfflineBanner';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { useHubConnection } from '@/hooks/useHubConnection';
import { getBackTarget, type BackTarget } from '@/utils/navigationBack';

export type AppRole = 'provider' | 'wit' | 'command';

interface AppChromeProps {
  role: AppRole;
  title?: string;
  backTo?: BackTarget;
  hideBack?: boolean;
  /** Full-width bar above a dashboard split (no sticky duplicate title row) */
  layout?: 'default' | 'dashboard';
}

const ROLE_LABELS: Record<AppRole, string> = {
  provider: 'Provider',
  wit: 'WIT Evaluator',
  command: 'Commander',
};

function HubIndicator({ state }: { state: ReturnType<typeof useHubConnection> }) {
  const variant =
    state === 'online' ? 'success' : state === 'offline' ? 'critical' : 'muted';
  const label =
    state === 'online' ? 'Hub online' : state === 'offline' ? 'Hub offline' : 'Connecting';

  return <Badge variant={variant}>{label}</Badge>;
}

export function AppChrome({
  role,
  title,
  backTo,
  hideBack = false,
  layout = 'default',
}: AppChromeProps) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const hubState = useHubConnection();
  const back = hideBack ? null : (backTo ?? getBackTarget(pathname));
  const isDashboard = layout === 'dashboard';

  return (
    <header
      className={`z-30 shrink-0 border-b border-ask-border/80 bg-ask-surface/95 backdrop-blur-md ${
        isDashboard ? '' : 'sticky top-0'
      }`}
    >
      <div className="app-chrome__bar">
        <div className="app-chrome__start">
          {back && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => navigate(back.to)}
              className="app-chrome__back"
              aria-label={`Back to ${back.label}`}
            >
              <span aria-hidden className="text-base leading-none">
                ←
              </span>
              <span className="hidden sm:inline">Back to {back.label}</span>
              <span className="sm:hidden">Back</span>
            </Button>
          )}
          <button
            type="button"
            onClick={() => navigate('/home')}
            className="app-chrome__brand"
          >
            Asklepios
          </button>
          <Badge variant="accent" className="shrink-0">
            {ROLE_LABELS[role]}
          </Badge>
        </div>

        <div className="app-chrome__end">
          {title && <span className="app-chrome__title">{title}</span>}
          <HubIndicator state={hubState} />
        </div>
      </div>

      {hubState !== 'online' && <HubOfflineBanner />}
    </header>
  );
}
