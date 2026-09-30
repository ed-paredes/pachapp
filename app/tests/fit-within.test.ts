import { fitWithin } from '../src/lib/fit-within';
import { isLowResolution } from '../src/lib/photos';

describe('fitWithin', () => {
  it('shrinks a large image to the height cap keeping the aspect ratio', () => {
    expect(fitWithin({ width: 2000, height: 1000 }, { width: 520, height: 300 })).toEqual({
      width: 520,
      height: 260,
    });
    expect(fitWithin({ width: 1000, height: 2000 }, { width: 520, height: 300 })).toEqual({
      width: 150,
      height: 300,
    });
  });

  it('never upscales a small image', () => {
    expect(fitWithin({ width: 200, height: 100 }, { width: 520, height: 400 })).toEqual({
      width: 200,
      height: 100,
    });
  });

  it('returns an empty size for degenerate input', () => {
    expect(fitWithin({ width: 0, height: 100 }, { width: 520, height: 400 })).toEqual({
      width: 0,
      height: 0,
    });
    expect(fitWithin({ width: 100, height: 100 }, { width: 0, height: 400 })).toEqual({
      width: 0,
      height: 0,
    });
  });
});

describe('isLowResolution', () => {
  it('flags photos whose long side is under 800 px', () => {
    expect(isLowResolution({ width: 417, height: 300 })).toBe(true);
    expect(isLowResolution({ width: 799, height: 100 })).toBe(true);
    expect(isLowResolution({ width: 800, height: 600 })).toBe(false);
    expect(isLowResolution({ width: 300, height: 1200 })).toBe(false);
  });
});
