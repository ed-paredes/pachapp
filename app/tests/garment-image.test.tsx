import { render, screen } from '@testing-library/react-native';
import { StyleSheet, type ViewStyle } from 'react-native';

import { GarmentImage, HeroImage } from '@/components/GarmentImage';
import { tint } from '@/theme';

const backgroundOf = (element: { props: { style?: unknown } }) =>
  (StyleSheet.flatten(element.props.style as ViewStyle) as ViewStyle | undefined)?.backgroundColor;

describe('GarmentImage', () => {
  it('floats the cutout on a tint of the garment colour', async () => {
    await render(<GarmentImage uri="http://img/a.png" tintColor="#8B5E3C" testID="garment" />);

    const image = screen.getByTestId('garment');
    expect(backgroundOf(image)).toBe('transparent');
    // image -> shadow wrapper -> tinted panel
    const panel = image.parent?.parent;
    expect(panel && backgroundOf(panel)).toBe(tint('#8B5E3C'));
  });

  it('shows the plain image on the plinth colour without a tint', async () => {
    await render(<GarmentImage uri="http://img/a.png" testID="garment" />);

    const image = screen.getByTestId('garment');
    expect(backgroundOf(image)).not.toBe('transparent');
    expect(backgroundOf(image)).toBeTruthy();
    expect(image.parent && backgroundOf(image.parent)).not.toBe(tint('#8B5E3C'));
  });
});

describe('HeroImage', () => {
  it('tints the panel behind the garment when a colour is given', async () => {
    await render(<HeroImage uri="http://img/a.png" tintColor="#8B5E3C" testID="hero" />);

    expect(backgroundOf(screen.getByTestId('hero-panel'))).toBe(tint('#8B5E3C'));
    expect(backgroundOf(screen.getByTestId('hero'))).toBe('transparent');
  });

  it('leaves the panel untinted without a colour', async () => {
    await render(<HeroImage uri="http://img/a.png" testID="hero" />);

    expect(backgroundOf(screen.getByTestId('hero-panel'))).not.toBe(tint('#8B5E3C'));
    expect(backgroundOf(screen.getByTestId('hero'))).not.toBe('transparent');
  });
});
