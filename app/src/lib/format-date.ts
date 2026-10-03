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

const WEEKDAYS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];
const MONTH_NAMES = [
  'enero',
  'febrero',
  'marzo',
  'abril',
  'mayo',
  'junio',
  'julio',
  'agosto',
  'septiembre',
  'octubre',
  'noviembre',
  'diciembre',
];

/** "Jueves, 1 de octubre" (es-ES, capitalised; hand-built so it does not depend on `Intl`). */
export function formatToday(now: Date = new Date()): string {
  const weekday = WEEKDAYS[now.getDay()];
  return `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)}, ${now.getDate()} de ${MONTH_NAMES[now.getMonth()]}`;
}

/** Local hours at which the greeting changes (shared with `nextTick` in `useNow`). */
export const GREETING_HOURS = { morning: 6, afternoon: 12, evening: 20 } as const;

/** "Buenos días" until noon, "Buenas tardes" until 8 pm, "Buenas noches" otherwise. */
export function greeting(now: Date = new Date()): string {
  const hour = now.getHours();
  if (hour >= GREETING_HOURS.morning && hour < GREETING_HOURS.afternoon) return 'Buenos días';
  if (hour >= GREETING_HOURS.afternoon && hour < GREETING_HOURS.evening) return 'Buenas tardes';
  return 'Buenas noches';
}
