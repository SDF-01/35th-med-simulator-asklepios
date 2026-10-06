/** Deterministic 32-bit generator used for reproducible training scenarios. */
export interface SeededRandom {
  next(): number;
  integer(min: number, max: number): number;
  pick<T>(values: readonly T[]): T;
}

function mixSeed(seed: number): number {
  let value = seed >>> 0;
  value += 0x9e3779b9;
  value = Math.imul(value ^ (value >>> 16), 0x21f0aaad);
  value = Math.imul(value ^ (value >>> 15), 0x735a2d97);
  return (value ^ (value >>> 15)) >>> 0;
}

export function createSeededRandom(seed: number): SeededRandom {
  let state = mixSeed(seed);
  const next = (): number => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = state;
    value = Math.imul(value ^ (value >>> 15), value | 1);
    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
  return {
    next,
    integer(min: number, max: number): number {
      if (!Number.isInteger(min) || !Number.isInteger(max) || max < min) {
        throw new Error('Invalid integer range.');
      }
      return min + Math.floor(next() * (max - min + 1));
    },
    pick<T>(values: readonly T[]): T {
      if (values.length === 0) throw new Error('Cannot pick from an empty collection.');
      return values[Math.floor(next() * values.length)]!;
    },
  };
}
