import type { ReactNode } from 'react';

interface TrainingBannerProps {
  compact?: boolean;
}

export function TrainingBanner({ compact = false }: TrainingBannerProps) {
  return (
    <div
      role="note"
      aria-label="Training simulation notice"
      className={`relative z-20 shrink-0 border-b border-ask-caution/25 bg-ask-caution/8 text-center ${compact ? 'px-3 py-1.5' : 'px-4 py-2'}`}
    >
      <p className={`text-ask-caution ${compact ? 'text-xs' : 'text-sm'}`}>
        Training simulation only · Not for operational use · Follow instructor guidance
      </p>
    </div>
  );
}

interface PageShellProps {
  children: ReactNode;
  variant?: 'default' | 'fullscreen' | 'dashboard' | 'hero';
  showTrainingBanner?: boolean;
  showGrid?: boolean;
  className?: string;
}

const SHELL_CLASS: Record<NonNullable<PageShellProps['variant']>, string> = {
  default: 'relative flex min-h-[100dvh] flex-col bg-ask-bg',
  fullscreen: 'relative flex h-[100dvh] max-h-[100dvh] flex-col overflow-hidden bg-ask-bg',
  dashboard: 'relative flex h-[100dvh] max-h-[100dvh] flex-col overflow-hidden bg-ask-bg',
  hero: 'relative flex min-h-[100dvh] flex-col overflow-hidden bg-ask-bg',
};

const CONTENT_CLASS: Record<NonNullable<PageShellProps['variant']>, string> = {
  default: 'relative z-10 flex w-full flex-1 flex-col',
  fullscreen: 'relative z-10 flex min-h-0 w-full flex-1 flex-col overflow-hidden',
  dashboard: 'relative z-10 flex min-h-0 w-full flex-1 flex-col overflow-hidden',
  hero: 'relative z-10 flex min-h-0 w-full flex-1 flex-col',
};

export function PageShell({
  children,
  variant = 'default',
  showTrainingBanner = true,
  showGrid: _showGrid = false,
  className = '',
}: PageShellProps) {
  return (
    <div className={`${SHELL_CLASS[variant]} ${className}`}>
      <a href="#main-content" className="skip-link rounded-ask-sm">
        Skip to main content
      </a>
      {showTrainingBanner && <TrainingBanner compact={variant === 'fullscreen'} />}
      <div className={CONTENT_CLASS[variant]}>{children}</div>
    </div>
  );
}

interface AppFooterProps {
  children?: ReactNode;
  className?: string;
}

export function AppFooter({ children, className = '' }: AppFooterProps) {
  return (
    <footer
      className={`shrink-0 border-t border-ask-border/50 px-4 py-3 text-center text-xs text-ask-muted ${className}`}
    >
      {children ?? 'Controlled training environment · v0.2.0'}
    </footer>
  );
}

/** Sidebar + main region below a full-width header on dashboard screens. */
export function DashboardBody({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`dashboard-body ${className}`.trim()}>{children}</div>
  );
}
