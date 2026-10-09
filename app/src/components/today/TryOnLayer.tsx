import { Image } from 'expo-image';
import { StyleSheet, Text, View } from 'react-native';

import { ProgressBar } from '@/components/add/ProgressBar';
import { Button } from '@/components/ui';
import { GARMENT_IMAGE_CACHE_POLICY } from '@/lib/image-url';
import { colors, fontFamilies, radii } from '@/theme';

import { TRYON_HELPER, type TryOnStatus } from './tryon-status';
import type { LookPiece } from './types';

/** What the canvas needs to show the try-on instead of (or over) the collage. */
export type TryOnCanvas = {
  /** `tryon` is the "Puesto" view; the canvas ignores it while the look has no render. */
  mode: 'collage' | 'tryon';
  status: TryOnStatus;
  /** Absolute URL of the finished render; null until it is done. */
  imageUri: string | null;
  /** Screen reader text of the finished render. */
  description: string;
  onRetry: () => void;
  onShowCollage: () => void;
};

/** Everything Hoy shows about the try-on of the look on screen (built by `useTodayTryOn`). */
export type TodayTryOn = {
  /** "Verlo puesto" is offered (try-on is on and the look has a piece the model can wear). */
  canTry: boolean;
  /** The button is shown but off. */
  tryOnDisabled: boolean;
  onTryOn: () => void;
  /** The Collage | Puesto control is shown (the look has been tried). */
  showToggle: boolean;
  mode: 'collage' | 'tryon';
  onModeChange: (mode: 'collage' | 'tryon') => void;
  canvas: TryOnCanvas;
  /** Pieces the finished image does not show. */
  notIncluded: LookPiece[];
};

/** True when the canvas is on the "Puesto" view of a look that has something to show there. */
export const showsTryOn = (tryOn: TryOnCanvas | undefined): tryOn is TryOnCanvas =>
  !!tryOn && tryOn.mode === 'tryon' && tryOn.status.phase !== 'idle';

/** The generated image, contained over the linen so the person is never cropped. */
export function TryOnImage({ uri, description }: { uri: string; description: string }) {
  return (
    <>
      {/* The render is 3:4 and the canvas is not: a blurred copy fills the sides so the frame looks intended. */}
      <Image
        source={{ uri }}
        style={StyleSheet.absoluteFill}
        contentFit="cover"
        blurRadius={30}
        cachePolicy={GARMENT_IMAGE_CACHE_POLICY}
        accessible={false}
        importantForAccessibility="no-hide-descendants"
        testID="tryon-backdrop"
      />
      <View style={styles.wash} />
      <Image
        source={{ uri }}
        style={StyleSheet.absoluteFill}
        contentFit="contain"
        cachePolicy={GARMENT_IMAGE_CACHE_POLICY}
        accessibilityLabel={description}
        testID="tryon-image"
      />
      <View style={styles.generated}>
        <Text style={styles.generatedText}>Imagen generada · aproximación</Text>
      </View>
    </>
  );
}

/** Progress, step line and helper over the dimmed collage while the render is being made. */
export function TryOnProgress({ status }: { status: TryOnStatus }) {
  const label = status.label ?? '';
  // Queued (0) says nothing about how far along it is: sweep instead of showing an empty bar.
  const value = status.progress && status.progress > 0 ? status.progress : null;
  return (
    <View style={styles.panel} testID="tryon-working">
      <ProgressBar value={value} label={label} testID="tryon-progress" />
      <Text accessibilityLiveRegion="polite" style={styles.step}>
        {label}
      </Text>
      <Text style={styles.helper}>{TRYON_HELPER}</Text>
    </View>
  );
}

/** The error of the try-on, with the action its kind allows. */
export function TryOnError({
  status,
  onRetry,
  onShowCollage,
}: Pick<TryOnCanvas, 'status' | 'onRetry' | 'onShowCollage'>) {
  const retry = status.errorKind === 'retry';
  return (
    <View style={styles.panel} accessibilityLiveRegion="polite" testID="tryon-error">
      <Text style={styles.message}>{status.message}</Text>
      <View style={styles.actions}>
        {retry ? <Button label="Reintentar" onPress={onRetry} /> : null}
        <Button
          variant="secondary"
          label="Ver collage"
          onPress={onShowCollage}
          testID="tryon-show-collage"
        />
      </View>
    </View>
  );
}

/** Small thumbnails of the pieces the image does not show; renders nothing when there are none. */
export function NotIncludedRow({ pieces }: { pieces: LookPiece[] }) {
  if (pieces.length === 0) return null;
  return (
    <View style={styles.notIncluded} testID="tryon-not-included">
      <Text style={styles.notIncludedTitle}>No incluidos en la imagen</Text>
      <View style={styles.thumbs}>
        {pieces.map((piece) => (
          <View key={piece.garmentId} style={styles.thumb}>
            {piece.imageUri ? (
              <Image
                source={{ uri: piece.imageUri }}
                style={styles.thumbImage}
                contentFit="contain"
                cachePolicy={GARMENT_IMAGE_CACHE_POLICY}
                accessibilityLabel={piece.name}
              />
            ) : null}
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wash: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: 'rgba(239,230,218,0.3)',
  },
  generated: {
    position: 'absolute',
    left: 18,
    bottom: 18,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(255,255,255,0.85)',
  },
  generatedText: { fontFamily: fontFamilies.bodyMedium, fontSize: 12.5, color: colors.ink2 },
  panel: {
    position: 'absolute',
    left: 18,
    right: 18,
    bottom: 18,
    gap: 10,
    padding: 16,
    borderRadius: radii.md,
    backgroundColor: 'rgba(255,255,255,0.92)',
  },
  step: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, lineHeight: 20, color: colors.ink },
  helper: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  message: { fontFamily: fontFamilies.body, fontSize: 15, lineHeight: 22, color: colors.ink },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  notIncluded: { gap: 8 },
  notIncludedTitle: { fontFamily: fontFamilies.bodyMedium, fontSize: 13, color: colors.ink2 },
  thumbs: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  thumb: {
    width: 48,
    height: 48,
    padding: 4,
    borderRadius: radii.tile,
    backgroundColor: colors.surface2,
  },
  thumbImage: { width: '100%', height: '100%', backgroundColor: 'transparent' },
});
