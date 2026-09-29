import { useCallback, useEffect, useState } from 'react';

import { getItem, setItem } from '@/lib/device-storage';

const STORAGE_KEY = 'pachapp.captureTips.seen';

/**
 * Tracks whether the Añadir capture-tips panel (UI-REQ-020) has already been
 * dismissed on this device. `seen` is `null` while the stored value is still
 * loading, so callers can avoid flashing the panel before it resolves.
 */
export function useCaptureTipsSeen() {
  const [seen, setSeen] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;
    getItem(STORAGE_KEY).then((value) => {
      if (!cancelled) {
        setSeen(value === 'true');
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const markSeen = useCallback(() => {
    setSeen(true);
    void setItem(STORAGE_KEY, 'true');
  }, []);

  return { seen, markSeen };
}
