import { useEffect, useState } from 'react';
import {
  MOBILE_MEDIA_QUERY,
  STANDALONE_MEDIA_QUERY,
  TOUCH_PRIMARY_MEDIA_QUERY,
} from '@/utils/deviceBreakpoints';

export type DeviceFormFactor = 'mobile' | 'desktop';

export interface DeviceProfile {
  formFactor: DeviceFormFactor;
  isTouchPrimary: boolean;
  isStandalone: boolean;
  viewportWidth: number;
  prefersReducedMotion: boolean;
}

function readProfile(): DeviceProfile {
  const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1024;
  const isMobileViewport = window.matchMedia(MOBILE_MEDIA_QUERY).matches;
  const isTouchPrimary = window.matchMedia(TOUCH_PRIMARY_MEDIA_QUERY).matches;
  const isStandalone = window.matchMedia(STANDALONE_MEDIA_QUERY).matches;
  const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const forced = localStorage.getItem('asklepios_device_override');
  let formFactor: DeviceFormFactor = isMobileViewport ? 'mobile' : 'desktop';
  if (forced === 'mobile') formFactor = 'mobile';
  if (forced === 'desktop') formFactor = 'desktop';

  return {
    formFactor,
    isTouchPrimary,
    isStandalone,
    viewportWidth,
    prefersReducedMotion,
  };
}

export function useDeviceProfile(): DeviceProfile {
  const [profile, setProfile] = useState<DeviceProfile>(() =>
    typeof window !== 'undefined' ? readProfile() : {
      formFactor: 'desktop',
      isTouchPrimary: false,
      isStandalone: false,
      viewportWidth: 1024,
      prefersReducedMotion: false,
    },
  );

  useEffect(() => {
    function sync() {
      const next = readProfile();
      setProfile(next);
      document.documentElement.dataset.device = next.formFactor;
      document.documentElement.dataset.standalone = next.isStandalone ? 'true' : 'false';
    }

    sync();
    const mobileMq = window.matchMedia(MOBILE_MEDIA_QUERY);
    const onChange = () => sync();
    mobileMq.addEventListener('change', onChange);
    window.addEventListener('resize', onChange);
    window.addEventListener('orientationchange', onChange);

    return () => {
      mobileMq.removeEventListener('change', onChange);
      window.removeEventListener('resize', onChange);
      window.removeEventListener('orientationchange', onChange);
    };
  }, []);

  return profile;
}

export function useIsMobile(): boolean {
  return useDeviceProfile().formFactor === 'mobile';
}
