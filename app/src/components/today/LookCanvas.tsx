import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useState } from 'react';
import { Platform, StyleSheet, Text, View, type ImageStyle, type ViewStyle } from 'react-native';

import { useImageTransition } from '@/hooks/useImageTransition';
import { GARMENT_IMAGE_CACHE_POLICY } from '@/lib/image-url';
import { useReducedMotion } from '@/hooks/useReducedMotion';
import { colors, fontFamilies, radii, shadows, tint } from '@/theme';

import { showsTryOn, TryOnError, TryOnImage, TryOnProgress, type TryOnCanvas } from './TryOnLayer';
import { matchLabel, type LookPiece } from './types';

type Slot = 'layer' | 'top' | 'bottom' | 'shoes';
type Place = { left: number; top: number; width: number; ratio: number; tilt: number };

/**
 * Mockup collage (left / top / width in % of the stage, `ratio` = width / height of the box each
 * garment is drawn in). Portrait fits phones, landscape the wide canvas and small previews.
 */
const LAYOUTS: Record<'portrait' | 'landscape', { stage: number; slots: Record<Slot, Place> }> = {
  portrait: {
    stage: 0.95,
    slots: {
      layer: { left: 6, top: 8, width: 46, ratio: 1, tilt: -3 },
      top: { left: 34, top: 14, width: 40, ratio: 1, tilt: 2 },
      bottom: { left: 36, top: 52, width: 40, ratio: 0.8, tilt: 0 },
      shoes: { left: 10, top: 64, width: 34, ratio: 1.15, tilt: 0 },
    },
  },
  landscape: {
    stage: 1.2,
    slots: {
      layer: { left: 10, top: 8, width: 34, ratio: 1, tilt: -3 },
      top: { left: 33, top: 14, width: 30, ratio: 1, tilt: 2 },
      bottom: { left: 58, top: 47, width: 27, ratio: 0.8, tilt: 0 },
      shoes: { left: 14, top: 62, width: 28, ratio: 1.15, tilt: 0 },
    },
  },
};
/** Painting order: the layer sits behind the top, the shoes in front. */
const ORDER: Slot[] = ['layer', 'top', 'bottom', 'shoes'];

/** Which slot a role draws in; accessories stay out of the collage (UI-REQ-010). */
function slotOf(role: LookPiece['role']): Slot | null {
  if (role === 'outerwear' || role === 'mid_layer') return 'layer';
  if (role === 'top' || role === 'one_piece') return 'top';
  if (role === 'bottom') return 'bottom';
  if (role === 'shoes') return 'shoes';
  return null;
}

/** First piece per slot; outerwear wins over mid-layer, top over a one-piece. */
export function pieceBySlot(pieces: LookPiece[]): Partial<Record<Slot, LookPiece>> {
  const result: Partial<Record<Slot, LookPiece>> = {};
  const rank = (piece: LookPiece) =>
    piece.role === 'mid_layer' || piece.role === 'one_piece' ? 1 : 0;
  for (const piece of [...pieces].sort((a, b) => rank(a) - rank(b))) {
    const slot = slotOf(piece.role);
    if (slot && !result[slot] && piece.imageUri) result[slot] = piece;
  }
  return result;
}

const NATIVE_SHADOW = {
  shadowColor: '#3C2819',
  shadowOffset: { width: 0, height: 10 },
  shadowOpacity: 0.2,
  shadowRadius: 12,
} as const;

type LookItemsProps = {
  pieces: LookPiece[];
  /** Tilt the first two pieces slightly (hover on web). */
  tilted?: boolean;
  /** Skip the shadows (small previews). */
  flat?: boolean;
};

/** The garments laid out on the collage positions, absolutely placed inside a sized parent. */
export function LookItems({ pieces, tilted = false, flat = false }: LookItemsProps) {
  const duration = useImageTransition();
  const bySlot = pieceBySlot(pieces);
  const [box, setBox] = useState<{ width: number; height: number } | null>(null);
  // Fit the stage inside the container so the composition keeps its proportions on any canvas.
  const layout = box && box.width / box.height >= 1.05 ? LAYOUTS.landscape : LAYOUTS.portrait;
  const stage = box
    ? {
        width: Math.min(box.width, box.height * layout.stage),
        height: Math.min(box.height, box.width / layout.stage),
      }
    : { width: '100%' as const, height: '100%' as const };
  return (
    <View
      style={[StyleSheet.absoluteFill, styles.stageHost]}
      onLayout={(event) => setBox(event.nativeEvent.layout)}
    >
      <View style={stage}>
        {ORDER.map((slot) => {
          const piece = bySlot[slot];
          if (!piece?.imageUri) return null;
          const at = layout.slots[slot];
          const rotate = tilted && at.tilt ? `${at.tilt}deg` : '0deg';
          return (
            <View
              key={slot}
              style={[
                {
                  position: 'absolute',
                  left: `${at.left}%`,
                  top: `${at.top}%`,
                  width: `${at.width}%`,
                  aspectRatio: at.ratio,
                  transform: [{ rotate }],
                },
                webTransition,
                flat || Platform.OS === 'web' ? null : NATIVE_SHADOW,
              ]}
            >
              <Image
                source={{ uri: piece.imageUri }}
                style={[styles.image, flat || Platform.OS !== 'web' ? null : webShadow]}
                contentFit="contain"
                cachePolicy={GARMENT_IMAGE_CACHE_POLICY}
                transition={{ duration, effect: 'cross-dissolve' }}
                accessibilityLabel={piece.name}
                testID={`look-piece-${piece.garmentId}`}
              />
            </View>
          );
        })}
      </View>
    </View>
  );
}

// CSS-only props are valid on react-native-web but missing from the RN types.
const webTransition = (
  Platform.OS === 'web' ? { transition: 'transform 0.5s cubic-bezier(.2,.8,.2,1)' } : null
) as ViewStyle | null;
const webShadow = (
  Platform.OS === 'web' ? { filter: 'drop-shadow(0px 14px 16px rgba(60, 40, 25, 0.22))' } : null
) as ImageStyle | null;

type LookCanvasProps = {
  pieces: LookPiece[];
  /** Tag at the top left, e.g. "Casual · Formalidad 2/5". Hidden when absent. */
  formalityLabel?: string;
  /** Match badge at the top right. Hidden when absent. */
  matchPercent?: number;
  /** Canvas width / height; Hoy uses a landscape canvas on wide screens. Defaults to portrait. */
  aspectRatio?: number;
  /** Try-on of this look; without it (or on `collage`) the canvas is the plain collage. */
  tryOn?: TryOnCanvas;
  testID?: string;
};

/**
 * Hoy's large canvas: linen gradient, the look's garments overlapped like a flat-lay (layer,
 * top, trousers, shoes) as real cutouts with a garment-shaped shadow, and a slight tilt on hover.
 */
export function LookCanvas({
  pieces,
  formalityLabel,
  matchPercent,
  aspectRatio = 0.8,
  tryOn,
  testID,
}: LookCanvasProps) {
  const [hovered, setHovered] = useState(false);
  const reduced = useReducedMotion();
  const accessories = pieces.filter((piece) => piece.role === 'accessory' && piece.imageUri);
  const puesto = showsTryOn(tryOn) ? tryOn : undefined;
  const generated = puesto?.status.phase === 'done' ? puesto.imageUri : null;
  // The collage stays behind the progress and the error, dimmed; the finished image replaces it.
  const dimmed = !!puesto && !generated;

  return (
    <View
      style={[styles.canvas, { aspectRatio }]}
      onPointerEnter={() => setHovered(true)}
      onPointerLeave={() => setHovered(false)}
      testID={testID}
    >
      {Platform.OS === 'web' ? (
        <View
          style={[
            StyleSheet.absoluteFill,
            {
              backgroundImage: 'radial-gradient(120% 100% at 30% 10%, #EFE6DA, #D9CBB9)',
            } as unknown as ViewStyle,
          ]}
        />
      ) : (
        <LinearGradient
          colors={['#EFE6DA', '#D9CBB9']}
          start={{ x: 0.3, y: 0 }}
          end={{ x: 0.7, y: 1 }}
          style={StyleSheet.absoluteFill}
        />
      )}
      {generated ? (
        <TryOnImage uri={generated} description={puesto?.description ?? ''} />
      ) : (
        <View style={[StyleSheet.absoluteFill, dimmed && styles.dimmed]} testID="look-collage">
          <LookItems pieces={pieces} tilted={hovered && !reduced} />
        </View>
      )}
      {formalityLabel ? (
        <View style={styles.tag}>
          <Text style={styles.tagText}>{formalityLabel}</Text>
        </View>
      ) : null}
      {matchPercent !== undefined ? (
        <View style={styles.score} testID="look-match">
          <View style={styles.scoreDot} />
          <Text style={styles.scoreText}>{matchLabel(matchPercent)}</Text>
        </View>
      ) : null}
      {puesto?.status.phase === 'working' ? <TryOnProgress status={puesto.status} /> : null}
      {puesto?.status.phase === 'error' ? (
        <TryOnError
          status={puesto.status}
          onRetry={puesto.onRetry}
          onShowCollage={puesto.onShowCollage}
        />
      ) : null}
      {accessories.length && !puesto ? (
        <View style={styles.accessories}>
          {accessories.map((piece) => (
            <View
              key={piece.garmentId}
              style={[styles.accessory, { backgroundColor: tint(piece.color ?? colors.ink3, 0.2) }]}
            >
              <Image
                source={{ uri: piece.imageUri as string }}
                style={styles.accessoryImage}
                contentFit="contain"
                cachePolicy={GARMENT_IMAGE_CACHE_POLICY}
                accessibilityLabel={piece.name}
              />
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  canvas: {
    width: '100%',
    minHeight: 340,
    borderRadius: radii.lg,
    overflow: 'hidden',
    boxShadow: shadows.card,
    backgroundColor: '#E5D8C8',
  },
  dimmed: { opacity: 0.4 },
  stageHost: { alignItems: 'center', justifyContent: 'center', pointerEvents: 'none' },
  image: { width: '100%', height: '100%', backgroundColor: 'transparent' },
  tag: {
    position: 'absolute',
    left: 18,
    top: 18,
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(255,255,255,0.8)',
  },
  tagText: { fontFamily: fontFamilies.bodyMedium, fontSize: 12.5, color: colors.ink2 },
  score: {
    position: 'absolute',
    right: 18,
    top: 18,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingVertical: 7,
    paddingHorizontal: 12,
    borderRadius: radii.pill,
    backgroundColor: 'rgba(255,255,255,0.8)',
  },
  scoreDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.ok },
  scoreText: { fontFamily: fontFamilies.bodySemiBold, fontSize: 12.5, color: colors.ink },
  accessories: { position: 'absolute', right: 18, bottom: 18, flexDirection: 'row', gap: 8 },
  accessory: { width: 44, height: 44, borderRadius: radii.tile, padding: 6 },
  accessoryImage: { width: '100%', height: '100%', backgroundColor: 'transparent' },
});
