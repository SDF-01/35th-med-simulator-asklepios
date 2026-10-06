import type {
  InputHTMLAttributes,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';

const INPUT_CLASSES =
  'w-full min-h-11 rounded-ask-md border border-ask-border bg-ask-bg px-3 py-2.5 text-sm text-ask-text placeholder:text-ask-muted/60 transition-colors focus:border-ask-accent/50 focus:bg-ask-surface focus:outline-none focus:ring-2 focus:ring-ask-accent/20 disabled:cursor-not-allowed disabled:opacity-45';

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export function Input({ invalid = false, className = '', ...props }: InputProps) {
  return (
    <input
      aria-invalid={invalid || undefined}
      className={`${INPUT_CLASSES} ${invalid ? 'border-ask-critical focus:border-ask-critical focus:ring-ask-critical/20' : ''} ${className}`}
      {...props}
    />
  );
}

export function Select({
  className = '',
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`${INPUT_CLASSES} ${className}`} {...props}>
      {children}
    </select>
  );
}

export function Textarea({
  className = '',
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea className={`${INPUT_CLASSES} min-h-[5.5rem] resize-y ${className}`} {...props} />
  );
}
