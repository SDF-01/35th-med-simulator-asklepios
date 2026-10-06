interface ToggleOption<T extends string> {
  value: T;
  label: string;
}

interface ToggleGroupProps<T extends string> {
  options: ToggleOption<T>[];
  value: T;
  onChange: (value: T) => void;
  label?: string;
  size?: 'sm' | 'md';
  className?: string;
}

export function ToggleGroup<T extends string>({
  options,
  value,
  onChange,
  label,
  size = 'sm',
  className = '',
}: ToggleGroupProps<T>) {
  const sizeClasses = size === 'sm' ? 'min-h-9 px-2.5 text-[9px]' : 'min-h-11 px-3 text-[10px]';

  return (
    <div className={className} role="group" aria-label={label}>
      <div className="inline-flex border border-ask-border bg-ask-bg/80 p-0.5 backdrop-blur-sm">
        {options.map((option) => {
          const selected = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(option.value)}
              className={[
                'font-mono font-medium uppercase tracking-[0.12em] transition-all',
                'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ask-accent/50',
                sizeClasses,
                selected
                  ? 'bg-ask-accent/15 text-ask-accent border border-ask-accent/30'
                  : 'border border-transparent text-ask-muted hover:text-ask-text',
              ].join(' ')}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
