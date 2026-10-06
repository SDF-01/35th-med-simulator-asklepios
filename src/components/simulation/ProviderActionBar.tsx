import { useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Input';

interface ProviderActionBarProps {
  onSubmit: (text: string) => void;
  disabled?: boolean;
}

/** Sticky thumb-zone action input for provider simulation. */
export function ProviderActionBar({ onSubmit, disabled = false }: ProviderActionBarProps) {
  const [text, setText] = useState('');

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText('');
  }

  return (
    <form className="provider-action-bar" onSubmit={handleSubmit} aria-label="Submit assessment or action">
      <div className="provider-action-bar__row">
        <Textarea
          id="provider-action-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          disabled={disabled}
          placeholder="Assessment or action…"
          rows={2}
          className="provider-action-bar__input resize-none"
          aria-label="Enter assessment or action"
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e);
            }
          }}
        />
        <Button
          type="submit"
          disabled={disabled || !text.trim()}
          size="lg"
          className="provider-action-bar__submit"
        >
          Submit
        </Button>
      </div>
      <p className="mt-1.5 text-xs text-ask-muted">Enter to submit · Shift+Enter for new line</p>
    </form>
  );
}
