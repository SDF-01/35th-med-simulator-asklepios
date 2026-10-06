import { Alert } from '@/components/ui/Alert';
import { getHubSetupIssue, getHubSetupSteps, getHubOfflineMessage } from '@/utils/hubMessages';
import { hasExternalHubUrl } from '@/utils/hubUrl';
import type { HubConnectionState } from '@/services/networkHub';

interface HubSetupAlertProps {
  connection: HubConnectionState;
  className?: string;
}

export function HubSetupAlert({ connection, className = '' }: HubSetupAlertProps) {
  const issue = getHubSetupIssue(connection);

  if (issue === 'ok' || issue === 'dev') {
    return null;
  }

  return (
    <Alert variant="caution" className={className} title="Hub offline">
      <p className="mb-3 text-sm leading-relaxed">{getHubOfflineMessage()}</p>
      <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-ask-muted">
        {getHubSetupSteps().map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      {hasExternalHubUrl() && (
        <p className="mt-3 text-xs text-ask-muted">
          Hub URL: <span className="font-mono">{import.meta.env.VITE_HUB_URL}</span>
        </p>
      )}
      <p className="mt-3 text-xs text-ask-muted">
        Docs:{' '}
        <a
          href="https://github.com/swolem12/ProjectAsklepios#deployment"
          className="text-ask-accent underline-offset-2 hover:underline"
          target="_blank"
          rel="noreferrer"
        >
          GitHub deployment guide
        </a>
      </p>
    </Alert>
  );
}
