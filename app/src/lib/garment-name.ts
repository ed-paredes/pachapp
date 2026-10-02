import type { components } from '@/api-client/schema';

import { categoryLabel } from './labels';

type NameSource = {
  category: components['schemas']['GarmentCategory'] | null;
  subcategory?: string | null;
  colors?: { name: string }[] | null;
  material?: string | null;
};

/**
 * Colour names that never change with the noun's gender or number. "gris", "azul", "verde"
 * and "marrón" are not here: they have no gender but do take a plural ("grises").
 */
const INVARIABLE = new Set([
  'rosa',
  'naranja',
  'caqui',
  'camel',
  'beige',
  'marino',
  'denim',
  'oliva',
  'burdeos',
  'turquesa',
]);

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Makes a palette colour name agree with the head noun of the garment: feminine nouns ending in
 * "a" turn "negro" into "negra", plural nouns ending in "s" add "s" / "es". Heuristic by design
 * (the API has no gender data); invariable colours stay as they are.
 */
function agree(color: string, noun: string): string {
  if (INVARIABLE.has(color)) return color;
  const word = noun.split(' ')[0].toLowerCase();
  const plural = word.endsWith('s');
  const feminine = plural ? word.endsWith('as') : word.endsWith('a');
  let result = feminine && color.endsWith('o') ? `${color.slice(0, -1)}a` : color;
  if (plural) result += /[aeiou]$/.test(result) ? 's' : 'es';
  return result.replace(/ónes$/, 'ones');
}

/**
 * Display name of a garment. The API has no name field, so it is composed from what it does
 * have: "<subcategory or category> <dominant colour> [de <material>]", e.g. "Camiseta azul de
 * algodón". Missing parts are skipped.
 */
export function garmentName(garment: NameSource): string {
  const noun =
    garment.subcategory?.trim() || (garment.category ? categoryLabel(garment.category) : 'Prenda');
  const color = garment.colors?.[0]?.name;
  const material = garment.material?.trim();
  const parts = [capitalise(noun)];
  if (color) parts.push(agree(color, noun));
  if (material) parts.push(`de ${material}`);
  return parts.join(' ');
}
