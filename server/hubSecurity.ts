import { createHash, randomBytes, randomInt, timingSafeEqual } from 'node:crypto';

export const LOBBY_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
export const DEFAULT_CAPABILITY_BYTES = 32;

export function generateLobbyCode(length = 6): string {
  if (!Number.isInteger(length) || length < 4 || length > 12) {
    throw new Error('Lobby code length must be an integer between 4 and 12.');
  }
  return Array.from({ length }, () => LOBBY_ALPHABET[randomInt(0, LOBBY_ALPHABET.length)]).join('');
}

export function generateCapability(bytes = DEFAULT_CAPABILITY_BYTES): string {
  if (!Number.isInteger(bytes) || bytes < 16 || bytes > 128) {
    throw new Error('Capability size must be an integer between 16 and 128 bytes.');
  }
  return randomBytes(bytes).toString('base64url');
}

export function capabilityDigest(capability: string): string {
  return createHash('sha256').update(capability, 'utf8').digest('hex');
}

export function verifyCapability(candidate: unknown, expectedDigest: string): boolean {
  if (typeof candidate !== 'string' || candidate.length < 20 || candidate.length > 512) return false;
  if (!/^[A-Za-z0-9_-]+$/.test(candidate)) return false;
  if (!/^[0-9a-f]{64}$/.test(expectedDigest)) return false;
  const observed = Buffer.from(capabilityDigest(candidate), 'hex');
  const expected = Buffer.from(expectedDigest, 'hex');
  return observed.length === expected.length && timingSafeEqual(observed, expected);
}

export function cryptographicDeviceId(): string {
  return `DEV-${randomBytes(6).toString('base64url').replace(/[^A-Za-z0-9]/g, '').slice(0, 8).toUpperCase()}`;
}
