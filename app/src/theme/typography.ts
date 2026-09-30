import type { TextStyle } from 'react-native';

/** Loaded font family names (see `fontAssets` in `fonts.ts`). */
export const fontFamilies = {
  display: 'Fraunces_600SemiBold',
  body: 'Manrope_400Regular',
  bodyMedium: 'Manrope_500Medium',
  bodySemiBold: 'Manrope_600SemiBold',
  bodyBold: 'Manrope_700Bold',
} as const;

/** Type scale: 12 / 14 / 16 / 20 / 28 / 36. */
export const fontSizes = {
  caption: 12,
  small: 14,
  body: 16,
  title: 20,
  headline: 28,
  display: 36,
} as const;

export const lineHeights = {
  caption: 16,
  small: 20,
  body: 24,
  title: 26,
  headline: 34,
  display: 42,
} as const;

type TextVariant = 'caption' | 'small' | 'body' | 'title' | 'headline' | 'display';

/** Ready-made text styles. Titles use Fraunces, everything else Manrope. */
export const textStyles: Record<TextVariant, TextStyle> = {
  caption: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: fontSizes.caption,
    lineHeight: lineHeights.caption,
  },
  small: {
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.small,
    lineHeight: lineHeights.small,
  },
  body: {
    fontFamily: fontFamilies.body,
    fontSize: fontSizes.body,
    lineHeight: lineHeights.body,
  },
  title: {
    fontFamily: fontFamilies.display,
    fontSize: fontSizes.title,
    lineHeight: lineHeights.title,
  },
  headline: {
    fontFamily: fontFamilies.display,
    fontSize: fontSizes.headline,
    lineHeight: lineHeights.headline,
  },
  display: {
    fontFamily: fontFamilies.display,
    fontSize: fontSizes.display,
    lineHeight: lineHeights.display,
  },
};
