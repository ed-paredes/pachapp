import { HERO_MAX_HEIGHT_RATIO, HERO_MAX_WIDTH, heroImageBox } from '../src/lib/hero-size';

const base = { uri: 'a', panelWidth: 1000, padding: 16, windowHeight: 1000 };

describe('heroImageBox', () => {
  it('caps the height at 45 % of the window', () => {
    expect(HERO_MAX_HEIGHT_RATIO).toBe(0.45);
    const loaded = { uri: 'a', size: { width: 1000, height: 4000 } };
    expect(heroImageBox({ ...base, loaded })).toEqual({ width: 113, height: 450 });
  });

  it('caps the width at 520 dp on a wide panel', () => {
    expect(HERO_MAX_WIDTH).toBe(520);
    const loaded = { uri: 'a', size: { width: 4000, height: 1000 } };
    expect(heroImageBox({ ...base, windowHeight: 2000, loaded })).toEqual({
      width: 520,
      height: 130,
    });
  });

  it('fits a narrow panel minus its padding', () => {
    const loaded = { uri: 'a', size: { width: 2000, height: 2000 } };
    expect(heroImageBox({ ...base, panelWidth: 358, windowHeight: 2000, loaded })).toEqual({
      width: 326,
      height: 326,
    });
  });

  it('never renders above the intrinsic size', () => {
    const loaded = { uri: 'a', size: { width: 200, height: 300 } };
    expect(heroImageBox({ ...base, loaded })).toEqual({ width: 200, height: 300 });
  });

  it('honours a custom height ratio', () => {
    const loaded = { uri: 'a', size: { width: 1000, height: 4000 } };
    expect(heroImageBox({ ...base, loaded, maxHeightRatio: 0.3 })).toEqual({
      width: 75,
      height: 300,
    });
  });

  it('reserves the largest box until the size is known', () => {
    expect(heroImageBox({ ...base, loaded: null })).toEqual({ width: 520, height: 450 });
  });

  it('ignores a size loaded for a different uri (stale-uri guard)', () => {
    const loaded = { uri: 'old', size: { width: 100, height: 100 } };
    expect(heroImageBox({ ...base, uri: 'new', loaded })).toEqual({ width: 520, height: 450 });
  });

  it('is empty before the panel is measured', () => {
    expect(heroImageBox({ ...base, panelWidth: 0, loaded: null })).toEqual({
      width: 0,
      height: 450,
    });
    const loaded = { uri: 'a', size: { width: 100, height: 100 } };
    expect(heroImageBox({ ...base, panelWidth: 0, loaded })).toEqual({ width: 0, height: 0 });
  });
});
