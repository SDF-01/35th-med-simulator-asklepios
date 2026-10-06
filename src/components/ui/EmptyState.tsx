import type { ReactNode } from 'react';
import { Card } from '@/components/ui/Card';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, className = '' }: EmptyStateProps) {
  return (
    <Card variant="muted" elevation="inset" padding="lg" className={`text-center ${className}`}>
      <p className="text-sm font-semibold text-ask-text">{title}</p>
      {description && (
        <p className="mx-auto mt-2 max-w-md text-sm leading-relaxed text-ask-muted">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </Card>
  );
}
