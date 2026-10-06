import { useNavigate } from 'react-router-dom';
import { Badge } from '@/components/ui/Badge';
import { useHubConnection } from '@/hooks/useHubConnection';

interface MobileHeaderProps {
  title: string;
  subtitle?: string;
  backTo?: string;
  backLabel?: string;
  showHub?: boolean;
}

export function MobileHeader({
  title,
  subtitle,
  backTo,
  backLabel = 'Back',
  showHub = true,
}: MobileHeaderProps) {
  const navigate = useNavigate();
  const hubState = useHubConnection();
  const hubVariant =
    hubState === 'online' ? 'success' : hubState === 'offline' ? 'critical' : 'muted';

  return (
    <header className="mobile-header">
      <div className="mobile-header__row">
        {backTo ? (
          <button
            type="button"
            className="mobile-header__back"
            onClick={() => navigate(backTo)}
            aria-label={backLabel}
          >
            ←
          </button>
        ) : (
          <span className="mobile-header__spacer" aria-hidden />
        )}
        <div className="mobile-header__titles">
          <h1 className="mobile-header__title">{title}</h1>
          {subtitle && <p className="mobile-header__subtitle">{subtitle}</p>}
        </div>
        {showHub ? (
          <Badge variant={hubVariant} className="mobile-header__hub">
            {hubState === 'online' ? 'Live' : hubState === 'offline' ? 'Off' : '…'}
          </Badge>
        ) : (
          <span className="mobile-header__spacer" aria-hidden />
        )}
      </div>
    </header>
  );
}
