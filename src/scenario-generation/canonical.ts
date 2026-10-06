export function stableStringify(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const object = value as Record<string, unknown>;
  return `{${Object.keys(object)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(object[key])}`)
    .join(',')}}`;
}

/** Compact deterministic fingerprint; not presented as a cryptographic signature. */
export function contentFingerprint(value: unknown): string {
  const text = stableStringify(value);
  let high = 0xcbf29ce4;
  let low = 0x84222325;
  for (let index = 0; index < text.length; index += 1) {
    low ^= text.charCodeAt(index);
    const lowProduct = Math.imul(low, 0x1b3);
    const carry = ((low >>> 16) * 0x1b3) >>> 16;
    high = (Math.imul(high, 0x1b3) + carry) >>> 0;
    low = lowProduct >>> 0;
  }
  return `${high.toString(16).padStart(8, '0')}${low.toString(16).padStart(8, '0')}`;
}
