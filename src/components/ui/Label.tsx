import type { LabelHTMLAttributes, ReactNode } from 'react';

interface LabelProps extends LabelHTMLAttributes<HTMLLabelElement> {
  children: ReactNode;
  hint?: string;
}

export function Label({ children, hint, className = '', ...props }: LabelProps) {
  return (
    <label
      className={`mb-1.5 block text-sm font-medium text-ask-text-dim ${className}`}
      {...props}
    >
      {children}
      {hint && <span className="mt-0.5 block font-normal normal-case tracking-normal text-ask-muted/80">{hint}</span>}
    </label>
  );
}
