import type { components } from '@/api-client/schema';

type Category = components['schemas']['GarmentCategory'];

/** Spanish UI names of the categories (glossary in docs/specs/00-index.md). */
export const CATEGORY_LABELS: Record<Category, string> = {
  top: 'Top',
  bottom: 'Pantalón',
  one_piece: 'Vestido / mono',
  mid_layer: 'Capa intermedia',
  outerwear: 'Abrigo',
  shoes: 'Calzado',
  accessory: 'Complemento',
};

export const CATEGORY_ORDER = Object.keys(CATEGORY_LABELS) as Category[];

export function categoryLabel(category: Category | null | undefined): string {
  return category ? CATEGORY_LABELS[category] : 'Sin categoría';
}

type Pattern = components['schemas']['GarmentPattern'];
type Season = components['schemas']['Season'];
type StyleTag = components['schemas']['StyleTag'];
type GarmentStatus = components['schemas']['GarmentStatus'];

export const PATTERN_LABELS: Record<Pattern, string> = {
  solid: 'Liso',
  striped: 'Rayas',
  plaid: 'Cuadros',
  printed: 'Estampado',
  textured: 'Textura',
};
export const PATTERN_ORDER = Object.keys(PATTERN_LABELS) as Pattern[];

export const SEASON_LABELS: Record<Season, string> = {
  spring: 'Primavera',
  summer: 'Verano',
  autumn: 'Otoño',
  winter: 'Invierno',
};
export const SEASON_ORDER = Object.keys(SEASON_LABELS) as Season[];

export const STYLE_LABELS: Record<StyleTag, string> = {
  casual: 'Casual',
  classic: 'Clásico',
  street: 'Street',
  minimal: 'Minimal',
  sport: 'Deportivo',
  elegant: 'Elegante',
  bohemian: 'Bohemio',
  preppy: 'Preppy',
};
export const STYLE_ORDER = Object.keys(STYLE_LABELS) as StyleTag[];

export const STATUS_LABELS: Record<GarmentStatus, string> = {
  active: 'Activa',
  laundry: 'Lavando',
  archived: 'Archivada',
};

/** Suggested materials (docs/specs/08 taxonomy); the field stays free text. */
export const MATERIAL_SUGGESTIONS = ['algodón', 'denim', 'lana', 'cuero', 'lino', 'sintético'];
