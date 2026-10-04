import { render, screen } from '@testing-library/react-native';
import { Image } from 'expo-image';
import { Platform } from 'react-native';

import { GarmentImage, HeroImage } from '@/components/GarmentImage';
import { RankCard } from '@/components/history/RankCard';
import { garmentImageUrls, prefetchGarmentImages } from '../src/offline/images';

const realOS = Platform.OS;
const setPlatform = (os: string) =>
  Object.defineProperty(Platform, 'OS', { configurable: true, get: () => os });

let prefetch: jest.SpyInstance;
let cachePath: jest.SpyInstance;

beforeEach(() => {
  prefetch = jest.spyOn(Image, 'prefetch').mockResolvedValue(true);
  cachePath = jest.spyOn(Image, 'getCachePathAsync').mockResolvedValue(null);
});

afterEach(() => {
  setPlatform(realOS);
  jest.restoreAllMocks();
});

const prefetched = () => prefetch.mock.calls.flatMap(([urls]) => urls as string[]);

describe('garmentImageUrls', () => {
  it('lists each thumbnail and cutout once as a full URL and skips missing paths', () => {
    const urls = garmentImageUrls([
      { img_thumb: 'thumb/a.webp', img_cutout: 'cutout/a.png' },
      { img_thumb: 'thumb/a.webp', img_cutout: null },
      { img_thumb: null, img_cutout: null },
    ]);
    expect(urls).toEqual([
      'http://localhost:8000/images/thumb/a.webp',
      'http://localhost:8000/images/cutout/a.png',
    ]);
  });
});

describe('prefetchGarmentImages', () => {
  const urls = Array.from({ length: 45 }, (_, index) => `http://api/images/${index}.png`);

  it('on native downloads every URL to the disk cache', async () => {
    setPlatform('android');
    const failed = await prefetchGarmentImages(urls);

    expect(failed).toBe(0);
    expect(prefetched().sort()).toEqual([...urls].sort());
    expect(prefetch.mock.calls.every(([, policy]) => policy === 'disk')).toBe(true);
    // Batches, so one bad image does not lose the whole wardrobe.
    expect(prefetch.mock.calls.length).toBeGreaterThan(1);
  });

  it('on native skips the images that are already on disk', async () => {
    setPlatform('android');
    cachePath.mockImplementation(async (url: string) =>
      url.endsWith('/3.png') ? '/cache/3' : null,
    );

    await prefetchGarmentImages(urls);

    expect(prefetched()).toHaveLength(44);
    expect(prefetched()).not.toContain('http://api/images/3.png');
  });

  it('counts the images it could not fetch instead of throwing', async () => {
    setPlatform('android');
    prefetch.mockResolvedValueOnce(false).mockRejectedValueOnce(new Error('disk full'));

    await expect(prefetchGarmentImages(urls)).resolves.toBe(40);
  });

  it('on web never touches the image cache', async () => {
    setPlatform('web');
    await expect(prefetchGarmentImages(urls)).resolves.toBe(0);
    expect(prefetch).not.toHaveBeenCalled();
    expect(cachePath).not.toHaveBeenCalled();
  });
});

describe('garment image cache policy', () => {
  beforeEach(() => setPlatform('android'));

  it('keeps the garment card image on disk', async () => {
    await render(<GarmentImage uri="http://img/a.png" testID="garment" />);
    expect(screen.getByTestId('garment').props.cachePolicy).toBe('memory-disk');
  });

  it('keeps the hero image on disk', async () => {
    await render(<HeroImage uri="http://img/b.png" testID="hero" />);
    expect(screen.getByTestId('hero').props.cachePolicy).toBe('memory-disk');
  });

  it('keeps the Historial thumbnails on disk', async () => {
    await render(
      <RankCard
        title="Las que más usas"
        items={[
          {
            id: 'g1',
            name: 'Camisa',
            detail: '3 usos',
            color: '#888',
            thumbUri: 'http://img/t.webp',
          },
        ]}
        onOpen={jest.fn()}
      />,
    );

    expect(screen.getByTestId('rank-thumb-g1', { hidden: true }).props.cachePolicy).toBe(
      'memory-disk',
    );
  });
});
