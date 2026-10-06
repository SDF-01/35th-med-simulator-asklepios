import type { HTMLAttributes, ReactNode } from 'react';

type PanelVariant = 'default' | 'sidebar' | 'inset';

const VARIANT_CLASSES: Record<PanelVariant, string> = {
  default: '',
  sidebar: 'ask-panel--sidebar',
  inset: 'ask-panel--inset',
};

interface PanelProps extends HTMLAttributes<HTMLElement> {
  variant?: PanelVariant;
  header?: ReactNode;
  footer?: ReactNode;
  as?: 'div' | 'aside' | 'section';
  children: ReactNode;
}

/** Layout panel for sidebars and major screen regions. */
export function Panel({
  variant = 'default',
  header,
  footer,
  as: Tag = 'div',
  className = '',
  children,
  ...props
}: PanelProps) {
  return (
    <Tag className={['ask-panel', VARIANT_CLASSES[variant], className].filter(Boolean).join(' ')} {...props}>
      {header && <div className="ask-panel__header">{header}</div>}
      <div className="ask-panel__body">{children}</div>
      {footer && <div className="ask-panel__footer">{footer}</div>}
    </Tag>
  );
}

interface PanelHeaderProps {
  eyebrow?: string;
  title: string;
  description?: string;
}

export function PanelHeader({ eyebrow, title, description }: PanelHeaderProps) {
  return (
    <>
      {eyebrow && <p className="mb-1 text-xs font-semibold text-ask-accent">{eyebrow}</p>}
      <h2 className="text-base font-semibold text-ask-text">{title}</h2>
      {description && <p className="mt-1 text-xs leading-relaxed text-ask-muted">{description}</p>}
    </>
  );
}
