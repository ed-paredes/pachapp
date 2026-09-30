import type { components } from '@/api-client/schema';

type Category = components['schemas']['GarmentCategory'];

/** Spanish UI names of the categories (glossary in docs/specs/00-index.md). */
export const CATEGORY_LABELS: Record<Category, string> = {
  top: 'Top',
  bottom: 'Pantalón',
  one_piece: 'Vestido / mono',
  mid_layer: 'Jersey',
  outerwear: 'Abrigo',
  shoes: 'Calzado',
  accessory: 'Complemento',
};

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS) as Category[];

export function categoryLabel(category: Category | null | undefined): string {
  return category ? CATEGORY_LABELS[category] : 'Sin categoría';
}
