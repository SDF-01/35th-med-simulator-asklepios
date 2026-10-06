import type { SupplyItem } from '@/types';
import { SUPPLY_OPTIONS } from '@/types/witConfig';
import type { SupplyLevel } from '@/types/witConfig';
import { Card } from '@/components/ui/Card';
import { SectionLabel } from '@/components/ui/PageHeader';

interface ProviderSupplyPanelProps {
  supplyLevel: SupplyLevel;
  inventory: SupplyItem[];
  statusNote: string;
  compact?: boolean;
}

export function ProviderSupplyPanel({
  supplyLevel,
  inventory,
  statusNote,
  compact = false,
}: ProviderSupplyPanelProps) {
  const levelLabel = SUPPLY_OPTIONS.find((o) => o.id === supplyLevel)?.label ?? supplyLevel;

  return (
    <Card as="section" padding={compact ? 'sm' : 'md'} aria-labelledby="supply-panel-title">
      <SectionLabel accent id="supply-panel-title" className="mb-1">
        Supply Limits
      </SectionLabel>
      <p className="mb-3 text-xs leading-relaxed text-ask-muted">
        {levelLabel}: {statusNote}
      </p>
      <ul
        className={`grid gap-1.5 ${compact ? 'grid-cols-2 text-xs' : 'grid-cols-1 text-sm'}`}
        aria-label="Supply inventory"
      >
        {inventory.map((item) => (
          <li
            key={item.id}
            className="flex items-center justify-between rounded-ask-sm border border-ask-border/60 bg-ask-bg/50 px-2.5 py-1.5"
          >
            <span>{item.label}</span>
            <span
              className={`font-mono tabular-nums ${
                item.quantity === 0
                  ? 'text-ask-critical'
                  : item.quantity <= 1
                    ? 'text-ask-caution'
                    : 'text-ask-accent'
              }`}
              aria-label={`${item.quantity} of ${item.maxQuantity} remaining`}
            >
              {item.quantity}/{item.maxQuantity}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

