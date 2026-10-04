/** The local calendar day as `YYYY-MM-DD` (what the wear log and Hoy's daily batch are keyed by). */
export function localDateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** Milliseconds from `now` to the next local midnight (at least 1, so a stale time is never 0). */
export function msUntilEndOfDay(now: Date): number {
  const midnight = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
  return Math.max(midnight.getTime() - now.getTime(), 1);
}
