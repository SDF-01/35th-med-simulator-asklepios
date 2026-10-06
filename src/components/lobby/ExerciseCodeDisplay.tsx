import { useState } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

interface ExerciseCodeDisplayProps {
  code: string;
  label?: string;
  className?: string;
}

export function ExerciseCodeDisplay({
  code,
  label = 'Exercise code',
  className = '',
}: ExerciseCodeDisplayProps) {
  const [copied, setCopied] = useState(false);

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      window.prompt('Copy this exercise code:', code);
    }
  }

  return (
    <Card padding="lg" variant="accent" className={`exercise-code-card text-center ${className}`.trim()}>
      <p className="text-xs font-medium uppercase tracking-widest text-ask-muted">{label}</p>
      <p className="exercise-code mt-3" aria-label={`Exercise code ${code}`}>
        {code.split('').join(' ')}
      </p>
      <Button type="button" variant="secondary" className="mt-5 w-full sm:w-auto" onClick={copyCode}>
        {copied ? 'Code copied' : 'Copy exercise code'}
      </Button>
      <p className="mt-3 text-xs leading-relaxed text-ask-muted">
        Share this code with providers. They enter it on Join Exercise, like a game lobby.
      </p>
    </Card>
  );
}
