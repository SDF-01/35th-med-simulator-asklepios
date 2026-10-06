import type { HTMLAttributes, ReactNode } from 'react';

interface SectionLabelProps extends HTMLAttributes<HTMLParagraphElement> {
  children: ReactNode;
  accent?: boolean;
  className?: string;
}

export function SectionLabel({
  children,
  accent = false,
  className = '',
  ...props
}: SectionLabelProps) {
  return (
    <p
      className={`text-xs font-semibold tracking-wide ${accent ? 'text-ask-accent' : 'text-ask-muted'} ${className}`}
      {...props}
    >
      {children}
    </p>
  );
}

interface PageHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  align?: 'left' | 'center';
  className?: string;
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  align = 'left',
  className = '',
}: PageHeaderProps) {
  const alignClass = align === 'center' ? 'text-center items-center' : 'text-left items-start';

  return (
    <header className={`mb-6 flex flex-wrap justify-between gap-4 ${alignClass} ${className}`}>
      <div className={align === 'center' ? 'mx-auto max-w-2xl' : 'min-w-0 flex-1'}>
        {eyebrow && <SectionLabel className="mb-2">{eyebrow}</SectionLabel>}
        <h1 className="font-display text-xl font-semibold text-ask-text md:text-2xl">{title}</h1>
        {description && (
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ask-text-dim">{description}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}
