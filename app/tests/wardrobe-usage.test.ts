import { wardrobeUsage } from '@/lib/wardrobe-usage';

const worn = (n: number) => Array.from({ length: n }, () => ({ wear_count: 2 }));
const unworn = (n: number) => Array.from({ length: n }, () => ({ wear_count: 0 }));

describe('wardrobeUsage', () => {
  it('has nothing to say about an empty wardrobe', () => {
    expect(wardrobeUsage([], 0)).toBeNull();
  });

  it('is exact when the page holds every garment', () => {
    expect(wardrobeUsage([...worn(2), ...unworn(1)], 3)).toEqual({
      worn: 2,
      total: 3,
      percent: 67,
    });
    expect(wardrobeUsage(worn(3), 3)).toEqual({ worn: 3, total: 3, percent: 100 });
  });

  it('is exact on a partial page that already reaches an unworn garment', () => {
    expect(wardrobeUsage([...worn(1), ...unworn(1)], 300)).toEqual({
      worn: 1,
      total: 300,
      percent: 0,
    });
  });

  it('gives up when a partial page is all worn garments', () => {
    expect(wardrobeUsage(worn(200), 250)).toBeNull();
  });
});
