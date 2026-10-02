/** Largest page the garments API serves (`page_size` <= 200). */
export const USAGE_PAGE_SIZE = 200;

type WearItem = { wear_count: number };

/**
 * Share of the active wardrobe worn at least once, from ONE page of active garments sorted by
 * `wear_count` descending (the API cannot filter on wear count). The result is exact when the page
 * holds every garment, or when it already reaches an unworn one; a page made only of worn garments
 * says nothing about the rest, so it returns `null` and the caller hides the figure.
 */
export function wardrobeUsage(
  items: WearItem[],
  total: number,
): { worn: number; total: number; percent: number } | null {
  if (total <= 0) return null;
  const complete = items.length >= total;
  const reachedUnworn = items.length > 0 && items[items.length - 1].wear_count === 0;
  if (!complete && !reachedUnworn) return null;
  const worn = items.filter((item) => item.wear_count > 0).length;
  return { worn, total, percent: Math.round((worn / total) * 100) };
}
