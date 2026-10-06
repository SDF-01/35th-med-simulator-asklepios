import { useState } from 'react';
import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { SectionLabel } from '@/components/ui/PageHeader';

interface LobbySharePanelProps {
  code: string;
  className?: string;
}

export function LobbySharePanel({ code, className = '' }: LobbySharePanelProps) {
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
    <Card padding="md" variant="accent" className={className}>
      <SectionLabel accent className="mb-1">
        Share with players
      </SectionLabel>
      <p className="exercise-code text-xl">{code.split('').join(' ')}</p>
      <Button type="button" variant="secondary" className="mt-4 w-full" onClick={copyCode}>
        {copied ? 'Code copied' : 'Copy exercise code'}
      </Button>
      <p className="mt-3 text-xs leading-relaxed text-ask-muted">
        Providers tap Join exercise on the home page and enter this code.
      </p>
    </Card>
  );
}
