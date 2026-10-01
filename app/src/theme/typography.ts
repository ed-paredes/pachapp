import type { TextStyle } from 'react-native';

/** Loaded font family names (see `fontAssets` in `fonts.ts`). */
export const fontFamilies = {
  display: 'Fraunces_600SemiBold',
  /** Light-weight Fraunces for page titles, hero text and numbers. */
  displayRegular: 'Fraunces_400Regular',
  displayItalic: 'Fraunces_400Regular_Italic',
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

type TextVariant =
  | 'caption'
  | 'small'
  | 'body'
  | 'title'
  | 'headline'
  | 'display'
  // Redesign scale. `pageTitle` is the redesign "title" (34 dp); `title` keeps its 20 dp meaning.
  | 'hero'
  | 'pageTitle'
  | 'section'
  | 'stat'
  | 'eyebrow'
  | 'label';

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
  hero: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 44,
    lineHeight: 46,
    letterSpacing: -0.9,
  },
  pageTitle: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 34,
    lineHeight: 37,
    letterSpacing: -0.6,
  },
  section: { fontFamily: fontFamilies.display, fontSize: 20, lineHeight: 26 },
  stat: { fontFamily: fontFamilies.displayRegular, fontSize: 28, lineHeight: 30 },
  eyebrow: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 13.5, lineHeight: 18 },
};
