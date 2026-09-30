import type { components } from '@/api-client/schema';

export type EngineSettings = components['schemas']['SettingsRead'];

const WEIGHT_KEYS = [
  'weight_color',
  'weight_style',
  'weight_novelty',
  'weight_preference',
] as const;
const COUNT_KEYS = ['no_repeat_days', 'max_accessories'] as const;

export type EngineFields = Record<
  (typeof WEIGHT_KEYS)[number] | (typeof COUNT_KEYS)[number],
  string
>;

/** Same tolerance as the server (DAT-REQ-011). */
export const WEIGHT_SUM_TOLERANCE = 0.01;

export function fieldsFromSettings(settings: EngineSettings): EngineFields {
  return {
    weight_color: String(settings.weight_color),
    weight_style: String(settings.weight_style),
    weight_novelty: String(settings.weight_novelty),
    weight_preference: String(settings.weight_preference),
    no_repeat_days: String(settings.no_repeat_days),
    max_accessories: String(settings.max_accessories),
  };
}

/** Accepts `0.25` and `0,25`; returns `null` for anything that is not a plain number. */
export function parseDecimal(text: string): number | null {
  const normalized = text.trim().replace(',', '.');
  if (!/^\d*\.?\d+$|^\d+\.$/.test(normalized)) return null;
  return Number(normalized);
}

/** Sum of the four weights, or `null` while any of them is not a number. */
export function weightSum(fields: EngineFields): number | null {
  let sum = 0;
  for (const key of WEIGHT_KEYS) {
    const value = parseDecimal(fields[key]);
    if (value === null) return null;
    sum += value;
  }
  return sum;
}

export type EngineValidation = {
  errors: Partial<Record<keyof EngineFields | 'form', string>>;
  values: Record<keyof EngineFields, number> | null;
};

/** Cheap client-side checks (the API remains the authority). */
export function validateEngineFields(fields: EngineFields): EngineValidation {
  const errors: EngineValidation['errors'] = {};
  const values: Partial<Record<keyof EngineFields, number>> = {};

  for (const key of WEIGHT_KEYS) {
    const value = parseDecimal(fields[key]);
    if (value === null || value > 1) {
      errors[key] = 'Introduce un número entre 0 y 1.';
    } else {
      values[key] = value;
    }
  }
  for (const key of COUNT_KEYS) {
    const text = fields[key].trim();
    if (!/^\d+$/.test(text)) {
      errors[key] = 'Introduce un número entero igual o mayor que 0.';
    } else {
      values[key] = Number(text);
    }
  }

  if (WEIGHT_KEYS.every((key) => errors[key] === undefined)) {
    const sum = weightSum(fields) as number;
    if (Math.abs(sum - 1) > WEIGHT_SUM_TOLERANCE) {
      errors.form = `Los pesos deben sumar 1,00 (ahora suman ${sum.toFixed(2)}).`;
    }
  }

  return Object.keys(errors).length > 0
    ? { errors, values: null }
    : { errors, values: values as Record<keyof EngineFields, number> };
}
