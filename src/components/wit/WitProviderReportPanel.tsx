import type { WitProviderReport } from '@/engines/witProviderReportEngine';
import { reportToPlainText } from '@/engines/witProviderReportEngine';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { SectionLabel } from '@/components/ui/PageHeader';

interface WitProviderReportPanelProps {
  report: WitProviderReport;
  onClose: () => void;
}

export function WitProviderReportPanel({ report, onClose }: WitProviderReportPanelProps) {
  const { aar } = report;

  function handlePrint() {
    window.print();
  }

  function handleCopy() {
    void navigator.clipboard.writeText(reportToPlainText(report));
  }

  function handleDownload() {
    const blob = new Blob([reportToPlainText(report)], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `asklepios-report-${report.device_id}-${Date.now()}.txt`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="wit-provider-report">
      <div className="wit-provider-report__toolbar mb-4 flex flex-wrap gap-3 print:hidden">
        <Button onClick={handlePrint}>Print Report</Button>
        <Button variant="secondary" onClick={handleDownload}>
          Download .txt
        </Button>
        <Button variant="secondary" onClick={handleCopy}>
          Copy to Clipboard
        </Button>
        <Button variant="ghost" onClick={onClose}>
          Close Report
        </Button>
      </div>

      <header className="mb-6">
        <Card padding="lg">
          <SectionLabel className="mb-1">WIT Evaluator: Provider Learning Report</SectionLabel>
          <h2 className="mb-2 text-2xl font-bold uppercase tracking-wide">{report.provider_name}</h2>
          <p className="text-sm text-ask-muted">
            {report.scenario_title} | {report.device_id} |{' '}
            {new Date(report.generated_at).toLocaleString()}
          </p>
        </Card>
      </header>

      <Card as="section" padding="lg" className="mb-6">
        <SectionLabel className="mb-3">Executive Summary</SectionLabel>
        <p className="mb-4 text-sm leading-relaxed">{report.learning_summary}</p>
        <dl className="flex flex-wrap gap-6 text-sm">
          <div>
            <dt className="text-xs uppercase text-ask-muted">Score</dt>
            <dd className="font-mono text-2xl">{aar.score}/100</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ask-muted">Result</dt>
            <dd>
              <Badge variant={aar.passed ? 'success' : 'critical'}>
                {aar.passed ? 'PASS' : 'NEEDS IMPROVEMENT'}
              </Badge>
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ask-muted">Turns</dt>
            <dd className="font-mono">{report.total_turns}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-ask-muted">Patient Outcome</dt>
            <dd>{aar.patient_outcome}</dd>
          </div>
        </dl>
      </Card>

      <Card as="section" padding="lg" className="mb-6">
        <SectionLabel accent className="mb-3">
          Full Provider Input Log
        </SectionLabel>
        {report.provider_inputs.length === 0 ? (
          <p className="text-sm italic text-ask-muted">No provider inputs recorded.</p>
        ) : (
          <div className="space-y-3">
            {report.provider_inputs.map((input) => (
              <div key={`${input.turn}-${input.time}`} className="border-l-2 border-ask-accent pl-3">
                <p className="text-xs text-ask-muted">
                  Turn {input.turn} | {input.time}
                  {input.score_delta !== 0 && (
                    <span className="ml-2 font-mono text-ask-accent">
                      {input.score_delta > 0 ? '+' : ''}
                      {input.score_delta}
                    </span>
                  )}
                </p>
                <p className="text-sm text-ask-text">&quot;{input.raw_text}&quot;</p>
                {input.recognized.length > 0 ? (
                  <p className="text-xs text-ask-accent">
                    Recognized: {input.recognized.join('; ')}
                  </p>
                ) : (
                  <p className="text-xs text-ask-caution">Not mapped to doctrine action</p>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>

      <div className="mb-6 grid gap-4 md:grid-cols-2">
        <section className="border border-ask-border bg-ask-surface p-5">
          <h3 className="mb-3 text-xs uppercase tracking-wider text-ask-accent">Sustain</h3>
          <ul className="list-inside list-disc space-y-1 text-sm">
            {aar.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
        <section className="border border-ask-border bg-ask-surface p-5">
          <h3 className="mb-3 text-xs uppercase tracking-wider text-ask-caution">Improve</h3>
          <ul className="list-inside list-disc space-y-1 text-sm">
            {aar.improvements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      </div>

      {aar.missed_critical.length > 0 && (
        <section className="mb-6 border border-ask-critical/40 bg-ask-surface p-5">
          <h3 className="mb-3 text-xs uppercase tracking-wider text-ask-critical">
            Missed Critical Actions
          </h3>
          <ul className="list-inside list-disc space-y-1 text-sm">
            {aar.missed_critical.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}

      {report.assessments_confirmed.length > 0 && (
        <section className="mb-6 border border-ask-border bg-ask-surface p-5">
          <h3 className="mb-3 text-xs uppercase tracking-wider text-ask-muted">
            Assessments Provider Confirmed
          </h3>
          <p className="text-sm">{report.assessments_confirmed.join(', ')}</p>
        </section>
      )}

      <section className="mb-6 border border-ask-border bg-ask-surface p-5">
        <h3 className="mb-3 text-xs uppercase tracking-wider text-ask-muted">Remediation Plan</h3>
        <ul className="list-inside list-disc space-y-1 text-sm">
          {report.remediation_plan.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>

      <section className="border border-ask-border bg-ask-surface p-5">
        <h3 className="mb-3 text-xs uppercase tracking-wider text-ask-muted">Teaching Points</h3>
        <ul className="list-inside list-disc space-y-1 text-sm">
          {aar.teaching_points.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </div>
  );
}
