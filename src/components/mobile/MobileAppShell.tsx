import type { ReactNode } from 'react';
import { MobileTabBar } from '@/components/mobile/MobileTabBar';

interface MobileAppShellProps {
  children: ReactNode;
  header: ReactNode;
  showTabBar?: boolean;
  footer?: ReactNode;
  className?: string;
}

export function MobileAppShell({
  children,
  header,
  showTabBar = true,
  footer,
  className = '',
}: MobileAppShellProps) {
  return (
    <div className={`mobile-app-shell ${className}`.trim()}>
      {header}
      <main id="main-content" className="mobile-app-shell__main">
        {children}
      </main>
      {footer}
      {showTabBar && <MobileTabBar />}
    </div>
  );
}
