import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { Platform, Pressable, StyleSheet, Text, View, type ViewStyle } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { pressFeedback } from '@/components/ui/feedback';
import { useImageTransition } from '@/hooks/useImageTransition';
import { GARMENT_IMAGE_CACHE_POLICY } from '@/lib/image-url';
import { colors, fontFamilies, radii, shadows, tint } from '@/theme';

const BACK_ICON = { ios: 'chevron.left', android: 'chevron_left', web: 'chevron_left' } as const;
const SHADE = '#DCCFC0';

type BackButtonProps = {
  onPress: () => void;
  /** `glass` floats translucent over the hero; `plain` sits on the page background. */
  variant?: 'glass' | 'plain';
};

/** Round 44 dp "Volver" button. */
export function BackButton({ onPress, variant = 'plain' }: BackButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Volver"
      onPress={onPress}
      style={(state) => [
        styles.round,
        variant === 'glass' ? styles.glass : styles.plain,
        pressFeedback(state),
      ]}
    >
      <IconSymbol name={BACK_ICON} size={22} color={colors.ink} />
    </Pressable>
  );
}

type GarmentHeroProps = {
  /** Cutout (or thumbnail) to show; without it the tinted panel stays empty. */
  uri: string | null;
  /** Dominant colour (hex) the panel is tinted from. */
  color: string;
  onBack: () => void;
  /** Shows "Recortada y analizada automáticamente" (only when the garment has a real cutout). */
  analyzed: boolean;
  /** Keeps the hero in view while the attributes scroll (web, two-column layout). */
  sticky?: boolean;
  testID?: string;
};

/**
 * Detalle hero: 4:5 panel with a radial gradient built from the garment's own colour (real
 * `radial-gradient` on web, a vertical linear approximation on native), the cutout large with
 * a soft shadow, and translucent round controls.
 */
export function GarmentHero({ uri, color, onBack, analyzed, sticky, testID }: GarmentHeroProps) {
  const duration = useImageTransition();
  const light = tint(color);
  const deep = tint(color, 0.3, SHADE);

  return (
    <View
      style={[styles.hero, sticky && Platform.OS === 'web' ? (stickyStyle as ViewStyle) : null]}
    >
      {Platform.OS === 'web' ? (
        <View
          style={[
            StyleSheet.absoluteFill,
            {
              backgroundImage: `radial-gradient(120% 90% at 50% 20%, ${light}, ${deep})`,
            } as unknown as ViewStyle,
          ]}
        />
      ) : (
        <LinearGradient
          colors={[light, deep]}
          start={{ x: 0.5, y: 0 }}
          end={{ x: 0.5, y: 1 }}
          style={StyleSheet.absoluteFill}
        />
      )}
      {uri ? (
        <View style={[styles.imageWrap, Platform.OS === 'web' ? null : styles.nativeShadow]}>
          <Image
            source={{ uri }}
            style={[styles.image, Platform.OS === 'web' ? (webShadow as object) : null]}
            contentFit="contain"
            cachePolicy={GARMENT_IMAGE_CACHE_POLICY}
            transition={{ duration, effect: 'cross-dissolve' }}
            testID={testID}
            accessibilityLabel="Foto de la prenda"
          />
        </View>
      ) : null}
      <View style={styles.top}>
        <BackButton onPress={onBack} variant="glass" />
      </View>
      {analyzed ? (
        <View style={styles.badge}>
          <View style={styles.badgeDot} />
          <Text style={styles.badgeText}>Recortada y analizada automáticamente</Text>
        </View>
      ) : null}
    </View>
  );
}

// CSS-only style props are valid on react-native-web but missing from the RN style types.
const stickyStyle = { position: 'sticky', top: 24 };
const webShadow = { filter: 'drop-shadow(0px 24px 30px rgba(60, 40, 25, 0.25))' };

const styles = StyleSheet.create({
  hero: {
    width: '100%',
    aspectRatio: 4 / 5,
    borderRadius: radii.lg,
    overflow: 'hidden',
    boxShadow: shadows.card,
  },
  imageWrap: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0, padding: '12%' },
  nativeShadow: {
    shadowColor: '#3C2819',
    shadowOffset: { width: 0, height: 20 },
    shadowOpacity: 0.25,
    shadowRadius: 24,
  },
  image: { width: '100%', height: '100%' },
  top: { position: 'absolute', top: 16, left: 16, right: 16, flexDirection: 'row' },
  round: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  glass: { backgroundColor: 'rgba(255,255,255,0.78)' },
  plain: { backgroundColor: colors.surface, boxShadow: shadows.card },
  badge: {
    position: 'absolute',
    left: 16,
    bottom: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(255,255,255,0.85)',
    maxWidth: '85%',
  },
  badgeDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.accent },
  badgeText: { fontFamily: fontFamilies.bodyMedium, fontSize: 12, color: colors.ink2 },
});
