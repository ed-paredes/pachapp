import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

const FADE_MS = 160;

/** Short cross-fade for loading images; no animation when the OS asks for reduced motion. */
export function useImageTransition(): number {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled?.()
      .then((value) => {
        if (active) setReduced(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);
  return reduced ? 0 : FADE_MS;
}
