import { useMemo, useState } from 'react';
import { Alert } from '@/components/ui/Alert';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { SectionLabel } from '@/components/ui/PageHeader';
import { buildSecureControllerUrl, getControllerCapability } from '@/utils/lobbyCapability';

interface ControllerSharePanelProps {
  code: string;
  className?: string;
}

async function copyValue(value: string, promptLabel: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    window.prompt(promptLabel, value);
  }
}

export function ControllerSharePanel({ code, className = '' }: ControllerSharePanelProps) {
  const [copied, setCopied] = useState<'wit' | 'command' | null>(null);
  const capability = getControllerCapability(code);
  const urls = useMemo(() => {
    if (!capability) return null;
    return {
      wit: buildSecureControllerUrl(code, 'wit', capability),
      command: buildSecureControllerUrl(code, 'command', capability),
    };
  }, [capability, code]);

  async function copy(role: 'wit' | 'command') {
    if (!urls) return;
    await copyValue(urls[role], `Copy the secure ${role} link:`);
    setCopied(role);
    window.setTimeout(() => setCopied(null), 2000);
  }

  return (
    <Card padding="md" className={className}>
      <SectionLabel accent className="mb-1">
        Secure exercise-control links
      </SectionLabel>
      <p className="text-sm leading-relaxed text-ask-muted">
        These links grant facilitator or command access. Share them only with authorized exercise staff.
        The provider lobby code alone cannot open either console.
      </p>
      {!urls ? (
        <Alert variant="critical" className="mt-4" title="Controller credential unavailable">
          Return to the browser session that created this lobby. For safety, a lobby code cannot recreate a
          controller credential.
        </Alert>
      ) : (
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <Button type="button" variant="secondary" onClick={() => copy('wit')}>
            {copied === 'wit' ? 'WIT link copied' : 'Copy secure WIT link'}
          </Button>
          <Button type="button" variant="secondary" onClick={() => copy('command')}>
            {copied === 'command' ? 'Command link copied' : 'Copy secure command link'}
          </Button>
        </div>
      )}
    </Card>
  );
}
