import type { ReactNode } from 'react';

type BadgeVariant =
  | 'default'
  | 'accent'
  | 'caution'
  | 'critical'
  | 'success'
  | 'muted'
  | 'immediate'
  | 'delayed'
  | 'minimal'
  | 'expectant';

const VARIANT_CLASSES: Record<BadgeVariant, string> = {
  default: 'border-ask-border bg-ask-surface-raised text-ask-text',
  accent: 'border-ask-accent/30 bg-ask-accent/12 text-ask-accent',
  caution: 'border-ask-delayed/35 bg-ask-delayed/10 text-ask-delayed',
  critical: 'border-ask-immediate/35 bg-ask-immediate/10 text-ask-immediate',
  success: 'border-ask-minimal/30 bg-ask-minimal/12 text-ask-minimal',
  muted: 'border-ask-border bg-ask-surface text-ask-muted',
  immediate: 'border-ask-immediate/35 bg-ask-immediate/10 text-ask-immediate',
  delayed: 'border-ask-delayed/35 bg-ask-delayed/10 text-ask-delayed',
  minimal: 'border-ask-minimal/30 bg-ask-minimal/12 text-ask-minimal',
  expectant: 'border-ask-expectant/35 bg-ask-surface-raised text-ask-expectant',
};

interface BadgeProps {
  variant?: BadgeVariant;
  children: ReactNode;
  className?: string;
}

export function Badge({ variant = 'default', children, className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

interface StatusDotProps {
  status: 'online' | 'offline' | 'active' | 'warning' | 'critical';
  label?: string;
  className?: string;
}

const DOT_CLASSES: Record<StatusDotProps['status'], string> = {
  online: 'bg-ask-accent',
  offline: 'bg-ask-muted',
  active: 'bg-ask-accent animate-status-pulse',
  warning: 'bg-ask-delayed',
  critical: 'bg-ask-immediate',
};

export function StatusDot({ status, label, className = '' }: StatusDotProps) {
  return (
    <span
      className={`inline-flex items-center gap-2 text-sm text-ask-muted ${className}`}
    >
      <span className={`h-2 w-2 shrink-0 rounded-full ${DOT_CLASSES[status]}`} aria-hidden="true" />
      {label && <span>{label}</span>}
    </span>
  );
}
