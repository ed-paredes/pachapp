import { Image } from 'expo-image';
import { useState } from 'react';
import { Platform, StyleSheet, type ImageStyle, useWindowDimensions, View } from 'react-native';

import { useImageTransition } from '@/hooks/useImageTransition';
import { fitWithin, type Size } from '@/lib/fit-within';
import { colors, radii, spacing, tint } from '@/theme';

/** Hero image is at most this share of the window height. */
export const HERO_MAX_HEIGHT_RATIO = 0.45;
/** Hero image is at most this wide (dp). */
export const HERO_MAX_WIDTH = 520;

type GarmentImageProps = {
  uri: string;
  /**
   * Dominant colour of the garment (hex). When set, the cutout sits on a tint of it with a soft
   * garment-shaped shadow; without it the image keeps the plain plinth background.
   */
  tintColor?: string;
  testID?: string;
  accessibilityLabel?: string;
};

type HeroImageProps = Omit<GarmentImageProps, 'tintColor'> & {
  /** Dominant colour (hex): tints the panel behind the garment. */
  tintColor?: string;
  /** Share of the window height the image may use; defaults to `HERO_MAX_HEIGHT_RATIO`. */
  maxHeightRatio?: number;
  /** Tighter padding around the image, for screens where the fields below matter more. */
  compact?: boolean;
};

/** iOS draws the shadow from the alpha of a background-less wrapper around the image. */
const NATIVE_SHADOW = {
  shadowColor: '#3C2819',
  shadowOffset: { width: 0, height: 10 },
  shadowOpacity: 0.18,
  shadowRadius: 12,
} as const;
/** Web: garment-shaped shadow that follows the cutout's alpha. */
const WEB_SHADOW = 'drop-shadow(0px 12px 14px rgba(60, 40, 25, 0.18))';

/**
 * Quiet, cached, cross-fading image that always keeps its aspect ratio (`contain`). With
 * `tintColor` the cutout floats on a tint of the garment's own colour.
 */
export function GarmentImage({ uri, tintColor, testID, accessibilityLabel }: GarmentImageProps) {
  const duration = useImageTransition();
  const image = (
    <Image
      source={{ uri }}
      style={[styles.fill, tintColor ? styles.transparent : null, tintColor ? webShadow : null]}
      contentFit="contain"
      cachePolicy="memory-disk"
      transition={{ duration, effect: 'cross-dissolve' }}
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    />
  );
  if (!tintColor) return image;
  return (
    <View style={[styles.tinted, { backgroundColor: tint(tintColor) }]}>
      <View style={styles.shadowWrap}>{image}</View>
    </View>
  );
}

// `filter` strings are valid on react-native-web but missing from the ImageStyle type.
const webShadow = Platform.OS === 'web' ? ({ filter: WEB_SHADOW } as unknown as ImageStyle) : null;

/**
 * Detalle/Revisión hero: the garment on a centred plinth panel. The image is capped at
 * ~45 % of the window height and 520 dp wide, and never rendered beyond its intrinsic size.
 */
export function HeroImage({
  uri,
  tintColor,
  testID,
  accessibilityLabel,
  maxHeightRatio = HERO_MAX_HEIGHT_RATIO,
  compact = false,
}: HeroImageProps) {
  const padding = compact ? spacing.md : spacing.xl;
  const { height } = useWindowDimensions();
  const duration = useImageTransition();
  const [loaded, setLoaded] = useState<{ uri: string; size: Size } | null>(null);
  const intrinsic = loaded?.uri === uri ? loaded.size : null;
  const [panelWidth, setPanelWidth] = useState(0);

  const max: Size = {
    width: Math.min(HERO_MAX_WIDTH, Math.max(0, panelWidth - padding * 2)),
    height: Math.round(height * maxHeightRatio),
  };
  // Before the source size is known, reserve the largest box so the page does not jump much.
  const box = intrinsic ? fitWithin(intrinsic, max) : max;

  return (
    <View
      style={[styles.panel, { padding }, tintColor ? { backgroundColor: tint(tintColor) } : null]}
      onLayout={(event) => setPanelWidth(event.nativeEvent.layout.width)}
      testID={testID ? `${testID}-panel` : undefined}
    >
      <Image
        source={{ uri }}
        style={[
          { width: box.width, height: box.height },
          tintColor ? [styles.transparent, webShadow] : { backgroundColor: colors.plinth },
        ]}
        contentFit="contain"
        cachePolicy="memory-disk"
        transition={{ duration, effect: 'cross-dissolve' }}
        onLoad={(event) =>
          setLoaded({ uri, size: { width: event.source.width, height: event.source.height } })
        }
        accessibilityLabel={accessibilityLabel}
        testID={testID}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { width: '100%', height: '100%', backgroundColor: colors.plinth },
  transparent: { backgroundColor: 'transparent' },
  tinted: { width: '100%', height: '100%', padding: '6%' },
  shadowWrap: { flex: 1, ...(Platform.OS === 'web' ? null : NATIVE_SHADOW) },
  panel: {
    alignItems: 'center',
    justifyContent: 'center',
    alignSelf: 'stretch',
    backgroundColor: colors.plinth,
    borderRadius: radii.panel,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.hairline,
  },
});
