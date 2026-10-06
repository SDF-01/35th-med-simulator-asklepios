import type { BodyInjuryHighlight, BodyZone, InjuryHighlightSeverity } from '@/types/bodyInjury';
import type { TcccTqEntry } from '@/engines/tcccCardMapper';
import {
  TCCC_BACK_ORIGIN,
  TCCC_FRONT_ORIGIN,
  TCCC_TQ_PANELS,
  TCCC_ZONE_VIEW,
  tcccGlobalAnchor,
} from '@/content/tcccFormDiagram';

interface TcccInjuryDiagramProps {
  highlights: BodyInjuryHighlight[];
  tqEntries: Partial<Record<'r_arm' | 'l_arm' | 'r_leg' | 'l_leg', TcccTqEntry>>;
  selectedZone: BodyZone | null;
  onSelectZone: (zone: BodyZone | null) => void;
}

function severityClass(severity: InjuryHighlightSeverity): string {
  return `tccc-form__mark--${severity}`;
}

function FrontFigure() {
  return (
    <g className="tccc-form-fig" transform={`translate(${TCCC_FRONT_ORIGIN.x}, ${TCCC_FRONT_ORIGIN.y})`}>
      <ellipse cx="50" cy="14" rx="11" ry="12" />
      <path d="M 39 26 L 39 28 L 61 28 L 61 26 Z" />
      <rect x="38" y="28" width="24" height="38" />
      <rect x="8" y="31" width="30" height="7" />
      <rect x="62" y="31" width="30" height="7" />
      <rect x="2" y="31" width="6" height="7" />
      <rect x="92" y="31" width="6" height="7" />
      <rect x="40" y="66" width="9" height="10" />
      <rect x="51" y="66" width="9" height="10" />
      <rect x="40" y="76" width="9" height="44" />
      <rect x="51" y="76" width="9" height="44" />
      <rect x="38" y="120" width="12" height="6" />
      <rect x="50" y="120" width="12" height="6" />
      <text x="50" y="17" className="tccc-form-fig__pct">4.5</text>
      <text x="50" y="49" className="tccc-form-fig__pct">18</text>
      <text x="23" y="36" className="tccc-form-fig__pct">4.5</text>
      <text x="77" y="36" className="tccc-form-fig__pct">4.5</text>
      <text x="50" y="73" className="tccc-form-fig__pct">1</text>
      <text x="44" y="102" className="tccc-form-fig__pct">9</text>
      <text x="56" y="102" className="tccc-form-fig__pct">9</text>
    </g>
  );
}

function BackFigure() {
  return (
    <g className="tccc-form-fig" transform={`translate(${TCCC_BACK_ORIGIN.x}, ${TCCC_BACK_ORIGIN.y})`}>
      <ellipse cx="50" cy="14" rx="11" ry="12" />
      <path d="M 39 26 L 39 28 L 61 28 L 61 26 Z" />
      <rect x="38" y="28" width="24" height="38" />
      <rect x="8" y="31" width="30" height="7" />
      <rect x="62" y="31" width="30" height="7" />
      <rect x="2" y="31" width="6" height="7" />
      <rect x="92" y="31" width="6" height="7" />
      <path d="M 40 66 L 60 66 L 58 76 L 42 76 Z" />
      <rect x="40" y="76" width="9" height="44" />
      <rect x="51" y="76" width="9" height="44" />
      <rect x="38" y="120" width="12" height="6" />
      <rect x="50" y="120" width="12" height="6" />
      <line x1="50" y1="30" x2="50" y2="66" className="tccc-form-fig__spine" />
      <text x="50" y="17" className="tccc-form-fig__pct">4.5</text>
      <text x="50" y="49" className="tccc-form-fig__pct">18</text>
      <text x="23" y="36" className="tccc-form-fig__pct">4.5</text>
      <text x="77" y="36" className="tccc-form-fig__pct">4.5</text>
      <text x="50" y="73" className="tccc-form-fig__pct">1</text>
      <text x="44" y="102" className="tccc-form-fig__pct">9</text>
      <text x="56" y="102" className="tccc-form-fig__pct">9</text>
    </g>
  );
}

function InjuryMarks({
  view,
  highlights,
  selectedZone,
  onSelectZone,
}: {
  view: 'front' | 'back';
  highlights: BodyInjuryHighlight[];
  selectedZone: BodyZone | null;
  onSelectZone: (zone: BodyZone | null) => void;
}) {
  return (
    <>
      {highlights
        .filter((highlight) => TCCC_ZONE_VIEW[highlight.zone] === view)
        .map((highlight) => {
        const anchor = tcccGlobalAnchor(view, highlight.zone);
        const isSelected = selectedZone === highlight.zone;
        return (
          <g
            key={`${view}-${highlight.zone}`}
            className={`tccc-form__mark ${severityClass(highlight.severity)} ${isSelected ? 'tccc-form__mark--selected' : ''}`}
            transform={`translate(${anchor.cx}, ${anchor.cy})`}
            onClick={() => onSelectZone(isSelected ? null : highlight.zone)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                onSelectZone(isSelected ? null : highlight.zone);
              }
            }}
            role="button"
            tabIndex={0}
            aria-label={`${highlight.label}. ${highlight.severity} injury.`}
          >
            <text y="4" className="tccc-form__mark-x">
              X
            </text>
          </g>
        );
      })}
    </>
  );
}

export function TcccInjuryDiagram({
  highlights,
  tqEntries,
  selectedZone,
  onSelectZone,
}: TcccInjuryDiagramProps) {
  return (
    <svg
      viewBox="0 0 560 188"
      className="tccc-form__injury-svg"
      role="img"
      aria-label="DD Form 1380 injury diagram with anterior and posterior views"
    >
      <FrontFigure />
      <BackFigure />

      {TCCC_TQ_PANELS.map((panel) => {
        const entry = tqEntries[panel.id];
        return (
          <g key={panel.id} className="tccc-form__tq">
            <rect x={panel.x} y={panel.y} width={panel.w} height={panel.h} />
            <text x={panel.x + panel.w / 2} y={panel.y + 9} className="tccc-form__tq-title">
              {panel.label}
            </text>
            <text x={panel.x + 3} y={panel.y + 20} className="tccc-form__tq-field">
              TYPE {entry?.type ?? '________'}
            </text>
            <text x={panel.x + 3} y={panel.y + 30} className="tccc-form__tq-field">
              TIME {entry?.time ?? '________'}
            </text>
          </g>
        );
      })}

      <InjuryMarks
        view="front"
        highlights={highlights}
        selectedZone={selectedZone}
        onSelectZone={onSelectZone}
      />
      <InjuryMarks
        view="back"
        highlights={highlights}
        selectedZone={selectedZone}
        onSelectZone={onSelectZone}
      />
    </svg>
  );
}
