import type { ButtonHTMLAttributes, ReactNode } from 'react';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    'border-ask-accent/40 bg-ask-accent text-ask-bg hover:bg-ask-accent-bright hover:border-ask-accent-bright focus-visible:ring-ask-accent/35',
  secondary:
    'border-ask-border bg-ask-surface-raised text-ask-text hover:border-ask-accent/35 hover:bg-ask-surface',
  ghost:
    'border-transparent bg-transparent text-ask-text-dim hover:bg-ask-surface hover:text-ask-text',
  danger:
    'border-ask-immediate/35 bg-ask-immediate/15 text-ask-immediate hover:bg-ask-immediate/25 hover:border-ask-immediate/50',
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: 'min-h-9 rounded-ask-sm px-3.5 py-2 text-sm',
  md: 'min-h-11 rounded-ask-md px-5 py-2.5 text-sm',
  lg: 'min-h-12 rounded-ask-md px-6 py-3 text-base',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  pulse?: boolean;
  children: ReactNode;
}

export function Button({
  variant = 'primary',
  size = 'md',
  pulse = false,
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={[
        'inline-flex items-center justify-center gap-2 border font-medium transition-colors duration-200',
        'disabled:pointer-events-none disabled:opacity-45 aria-disabled:cursor-not-allowed aria-disabled:opacity-55',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-ask-bg',
        VARIANT_CLASSES[variant],
        SIZE_CLASSES[size],
        pulse ? 'animate-pulse-subtle' : '',
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...props}
    >
      {children}
    </button>
  );
}
