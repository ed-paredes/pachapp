const MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Short, relative "last worn" text for a stat cell: "Nunca" without a date, "Hoy", "Ayer",
 * "Hace 12 d" up to two months, then "12 mar" (this year) or "mar 2025". Unparseable input is
 * returned as is.
 */
export function formatLastWorn(iso: string | null, now: Date = new Date()): string {
  if (!iso) return 'Nunca';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOfDay(now) - startOfDay(date)) / DAY_MS);
  if (days <= 0) return 'Hoy';
  if (days === 1) return 'Ayer';
  if (days < 60) return `Hace ${days} d`;
  const month = MONTHS[date.getMonth()];
  return date.getFullYear() === now.getFullYear()
    ? `${date.getDate()} ${month}`
    : `${month} ${date.getFullYear()}`;
}
