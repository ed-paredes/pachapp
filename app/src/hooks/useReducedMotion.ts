import { useEffect, useState } from 'react';
import { AccessibilityInfo } from 'react-native';

/** Whether the OS asks for reduced motion; follows later changes. Defaults to `false`. */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    let active = true;
    AccessibilityInfo.isReduceMotionEnabled?.()
      .then((value) => {
        if (active) setReduced(value);
      })
      .catch(() => undefined);
    const subscription = AccessibilityInfo.addEventListener?.('reduceMotionChanged', (value) =>
      setReduced(value),
    );
    return () => {
      active = false;
      subscription?.remove();
    };
  }, []);
  return reduced;
}
