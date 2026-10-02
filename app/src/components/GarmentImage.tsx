import { Image } from 'expo-image';
import { useState } from 'react';
import { StyleSheet, useWindowDimensions, View } from 'react-native';

import { useImageTransition } from '@/hooks/useImageTransition';
import { fitWithin, type Size } from '@/lib/fit-within';
import { colors, radii, spacing } from '@/theme';

/** Hero image is at most this share of the window height. */
export const HERO_MAX_HEIGHT_RATIO = 0.45;
/** Hero image is at most this wide (dp). */
export const HERO_MAX_WIDTH = 520;

type GarmentImageProps = {
  uri: string;
  testID?: string;
  accessibilityLabel?: string;
};

type HeroImageProps = GarmentImageProps & {
  /** Share of the window height the image may use; defaults to `HERO_MAX_HEIGHT_RATIO`. */
  maxHeightRatio?: number;
  /** Tighter padding around the image, for screens where the fields below matter more. */
  compact?: boolean;
};

/** Quiet, cached, cross-fading image that always keeps its aspect ratio (`contain`). */
export function GarmentImage({ uri, testID, accessibilityLabel }: GarmentImageProps) {
  const duration = useImageTransition();
  return (
    <Image
      source={{ uri }}
      style={styles.fill}
      contentFit="contain"
      cachePolicy="memory-disk"
      transition={{ duration, effect: 'cross-dissolve' }}
      accessibilityLabel={accessibilityLabel}
      testID={testID}
    />
  );
}

/**
 * Detalle/Revisión hero: the garment on a centred plinth panel. The image is capped at
 * ~45 % of the window height and 520 dp wide, and never rendered beyond its intrinsic size.
 */
export function HeroImage({
  uri,
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
      style={[styles.panel, { padding }]}
      onLayout={(event) => setPanelWidth(event.nativeEvent.layout.width)}
      testID={testID ? `${testID}-panel` : undefined}
    >
      <Image
        source={{ uri }}
        style={{ width: box.width, height: box.height, backgroundColor: colors.plinth }}
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
