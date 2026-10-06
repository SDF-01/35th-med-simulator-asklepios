import type { SupplyItem } from '@/types';
import type { SupplyLevel } from '@/types/witConfig';
import { SUPPLY_OPTIONS } from '@/types/witConfig';

const BASE_CATALOG: Omit<SupplyItem, 'quantity' | 'maxQuantity'>[] = [
  { id: 'tourniquet', label: 'Tourniquet (CAT)', category: 'hemorrhage' },
  { id: 'pressure_dressing', label: 'Pressure dressing', category: 'hemorrhage' },
  { id: 'hemostatic_gauze', label: 'Hemostatic gauze', category: 'hemorrhage' },
  { id: 'np_airway', label: 'Nasopharyngeal airway', category: 'airway' },
  { id: 'opa', label: 'Oropharyngeal airway set', category: 'airway' },
  { id: 'chest_seal', label: 'Chest seal', category: 'breathing' },
  { id: 'needle_decomp', label: 'Needle decompression kit', category: 'breathing' },
  { id: 'iv_start', label: 'IV start kit', category: 'circulation' },
  { id: 'fluid_bolus', label: 'Fluid bolus (500mL)', category: 'circulation' },
  { id: 'blanket', label: 'Hypothermia prevention blanket', category: 'general' },
  { id: 'splint', label: 'SAM splint', category: 'general' },
  { id: 'analgesia', label: 'Analgesia (field dose)', category: 'medication' },
  { id: 'ifak', label: 'IFAK refill', category: 'general' },
];

const SUPPLY_MULTIPLIERS: Record<SupplyLevel, number> = {
  full: 1,
  limited: 0.55,
  critical_shortage: 0.25,
};

const SUPPLY_DEFAULT_MAX: Record<string, number> = {
  tourniquet: 4,
  pressure_dressing: 6,
  hemostatic_gauze: 4,
  np_airway: 3,
  opa: 2,
  chest_seal: 3,
  needle_decomp: 2,
  iv_start: 4,
  fluid_bolus: 3,
  blanket: 6,
  splint: 4,
  analgesia: 2,
  ifak: 3,
};

export function getSupplyStatusNote(level: SupplyLevel): string {
  return SUPPLY_OPTIONS.find((o) => o.id === level)?.description ?? level;
}

export function buildSupplyInventory(level: SupplyLevel, casualtyCount: number): SupplyItem[] {
  const multiplier = SUPPLY_MULTIPLIERS[level];
  const scale = Math.max(1, Math.ceil(casualtyCount * 0.5));

  return BASE_CATALOG.map((item) => {
    const baseMax = SUPPLY_DEFAULT_MAX[item.id] ?? 2;
    const maxQuantity = Math.max(1, Math.floor(baseMax * multiplier * scale));
    return {
      ...item,
      maxQuantity,
      quantity: maxQuantity,
    };
  });
}

export function getSupplyLimitsSummary(level: SupplyLevel, inventory: SupplyItem[]): string {
  const status = getSupplyStatusNote(level);
  const constrained = inventory.filter((i) => i.quantity < i.maxQuantity * 0.5);
  const lowItems =
    constrained.length > 0
      ? ` Low stock: ${constrained.map((i) => i.label).join(', ')}.`
      : '';
  return `${status}.${lowItems}`;
}

export function consumeSupplyItem(
  inventory: SupplyItem[],
  itemId: string,
  amount = 1,
): { inventory: SupplyItem[]; consumed: boolean } {
  const index = inventory.findIndex((i) => i.id === itemId);
  if (index < 0 || inventory[index].quantity < amount) {
    return { inventory, consumed: false };
  }
  const next = [...inventory];
  next[index] = { ...next[index], quantity: next[index].quantity - amount };
  return { inventory: next, consumed: true };
}

export function mapActionToSupplyItem(actionId: string): string | null {
  switch (actionId) {
    case 'hemorrhage_control':
      return 'tourniquet';
    case 'airway_assessment':
      return 'np_airway';
    case 'breathing_assessment':
      return 'chest_seal';
    case 'circulation_check':
      return 'iv_start';
    case 'hypothermia_prevention':
      return 'blanket';
    case 'pain_management':
      return 'analgesia';
    default:
      return null;
  }
}
