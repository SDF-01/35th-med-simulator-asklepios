import { createContext, useContext, type ReactNode } from 'react';
import { useDeviceProfile, type DeviceProfile } from '@/hooks/useDeviceProfile';

const DeviceContext = createContext<DeviceProfile | null>(null);

export function DeviceProvider({ children }: { children: ReactNode }) {
  const profile = useDeviceProfile();
  return <DeviceContext.Provider value={profile}>{children}</DeviceContext.Provider>;
}

export function useDevice(): DeviceProfile {
  const ctx = useContext(DeviceContext);
  if (!ctx) {
    throw new Error('useDevice must be used within DeviceProvider');
  }
  return ctx;
}
