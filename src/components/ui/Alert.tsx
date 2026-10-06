import type { ReactNode } from 'react';

type AlertVariant = 'info' | 'caution' | 'critical' | 'success' | 'immediate' | 'delayed';

const VARIANT_MAP: Record<AlertVariant, { card: string; title: string }> = {
  info: { card: 'ask-card--default', title: 'text-ask-info' },
  caution: { card: 'ask-card--delayed', title: 'text-ask-delayed' },
  critical: { card: 'ask-card--immediate', title: 'text-ask-immediate' },
  success: { card: 'ask-card--accent', title: 'text-ask-accent' },
  immediate: { card: 'ask-card--immediate', title: 'text-ask-immediate' },
  delayed: { card: 'ask-card--delayed', title: 'text-ask-delayed' },
};

interface AlertProps {
  variant?: AlertVariant;
  title?: string;
  children: ReactNode;
  className?: string;
  role?: 'alert' | 'status';
}

export function Alert({
  variant = 'info',
  title,
  children,
  className = '',
  role = 'status',
}: AlertProps) {
  const styles = VARIANT_MAP[variant];

  return (
    <div role={role} className={`ask-card ${styles.card} ${className}`}>
      <div className="ask-card__body p-4">
        {title && <p className={`mb-2 text-sm font-semibold ${styles.title}`}>{title}</p>}
        <div className="text-sm leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
