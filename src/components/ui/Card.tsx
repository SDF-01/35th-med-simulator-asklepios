import type { HTMLAttributes, ReactNode } from 'react';

type CardVariant = 'default' | 'accent' | 'caution' | 'critical' | 'muted' | 'immediate' | 'delayed';
type CardElevation = 'flat' | 'raised' | 'floating' | 'inset';

const VARIANT_CLASSES: Record<CardVariant, string> = {
  default: 'ask-card--default',
  accent: 'ask-card--accent',
  caution: 'ask-card--caution',
  critical: 'ask-card--critical',
  muted: 'ask-card--muted',
  immediate: 'ask-card--immediate',
  delayed: 'ask-card--delayed',
};

const ELEVATION_CLASSES: Record<CardElevation, string> = {
  flat: 'ask-card--flat',
  raised: '',
  floating: 'ask-card--floating',
  inset: 'ask-card--inset',
};

const PADDING_CLASSES = {
  none: '',
  sm: 'p-3',
  md: 'p-4',
  lg: 'p-5',
};

interface CardProps extends HTMLAttributes<HTMLElement> {
  variant?: CardVariant;
  elevation?: CardElevation;
  padding?: keyof typeof PADDING_CLASSES;
  as?: 'div' | 'section' | 'article';
  children: ReactNode;
}

/** Layered surface card — shadcn-style elevation with clinical token washes. */
export function Card({
  variant = 'default',
  elevation = 'raised',
  padding = 'md',
  as: Tag = 'div',
  className = '',
  children,
  ...props
}: CardProps) {
  return (
    <Tag
      className={[
        'ask-card',
        VARIANT_CLASSES[variant],
        ELEVATION_CLASSES[elevation],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      <div className={`ask-card__body ${PADDING_CLASSES[padding]}`}>{children}</div>
    </Tag>
  );
}
