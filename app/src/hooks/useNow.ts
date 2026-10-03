import { useEffect, useState } from 'react';
import { AppState } from 'react-native';

/** Local hours at which the date or the greeting changes (see `greeting` in `format-date`). */
const TICK_HOURS = [0, 6, 12, 20];

/** The next local tick strictly after `now`: midnight or a greeting boundary. */
export function nextTick(now: Date): Date {
  for (const hour of TICK_HOURS.slice(1)) {
    const at = new Date(now.getFullYear(), now.getMonth(), now.getDate(), hour);
    if (at.getTime() > now.getTime()) return at;
  }
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
}

/**
 * The current date, kept fresh: it updates at the next local midnight or greeting boundary
 * (06:00, 12:00, 20:00) and whenever the app returns to the foreground, so a screen left open
 * overnight does not keep yesterday's date, greeting or relative labels. `AppState` also covers
 * the web (react-native-web maps it to `visibilitychange`).
 */
export function useNow(): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') setNow(new Date());
    });
    return () => subscription.remove();
  }, []);

  // Re-armed after every update, so it also follows a foreground refresh.
  useEffect(() => {
    const timer = setTimeout(
      () => setNow(new Date()),
      Math.max(nextTick(now).getTime() - Date.now(), 0) + 50,
    );
    return () => clearTimeout(timer);
  }, [now]);

  return now;
}
