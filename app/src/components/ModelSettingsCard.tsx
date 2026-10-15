import { Image } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { useEffect, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import type { ViewStyle } from 'react-native';

import { OfflineNote, useOfflineBlock } from '@/components/OfflineBanner';
import { Card, Segmented } from '@/components/ui';
import { usePatchSettings, type SettingsRead } from '@/hooks/useSettings';
import { useTryOnCapabilities } from '@/hooks/useTryOnCapabilities';
import { tryOnPreview, type ModelGender } from '@/lib/tryon-preview';
import { colors, fontFamilies, radii, spacing } from '@/theme';

/** How long the "Guardado" confirmation stays on screen. */
export const SAVED_NOTE_MS = 3000;

const GENDER_LABELS: Record<ModelGender, string> = { woman: 'Mujer', man: 'Hombre' };

/** Preview linen, as the prototype's radial gradient (web) and a vertical approximation (native). */
const LINEN = ['#F1E9DE', '#E3D6C5', '#D8C8B4'] as const;
const WEB_LINEN = `radial-gradient(110% 80% at 50% 18%, ${LINEN[0]} 0%, ${LINEN[1]} 70%, ${LINEN[2]} 100%)`;

// CSS-only style props are valid on react-native-web but missing from the RN style types.
const webBackdrop = { backgroundImage: WEB_LINEN } as unknown as ViewStyle;
const webShadow = { filter: 'drop-shadow(0px 14px 18px rgba(70, 45, 25, 0.16))' } as object;

/** Ink on the light tones, white on the dark ones, so the check keeps >= 3:1 on every swatch. */
function checkColor(hex: string): string {
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  return 0.299 * r + 0.587 * g + 0.114 * b > 150 ? colors.ink : '#FFFFFF';
}

type Draft = { gender?: ModelGender; tone?: number };

/**
 * "Tu modelo" (Ajustes): the model the try-on dresses, shown as a 3:4 preview on the linen
 * backdrop with its gender and skin tone. Every change is saved at once (`PATCH /settings`) and
 * shown right away; a failed save puts the previous value back and says so, and "Guardado"
 * fades after a few seconds. The card is hidden
 * while the try-on is off or the capabilities are unknown.
 */
export function ModelSettingsCard({ settings }: { settings: SettingsRead }) {
  const capabilities = useTryOnCapabilities();
  const patch = usePatchSettings();
  const offline = useOfflineBlock();
  // What the user picked and the server has not confirmed yet.
  const [draft, setDraft] = useState<Draft>({});
  // Counts the confirmed saves; 0 hides the note. A new count restarts its timer.
  const [saved, setSaved] = useState(0);

  useEffect(() => {
    if (!saved) return undefined;
    const timer = setTimeout(() => setSaved(0), SAVED_NOTE_MS);
    return () => clearTimeout(timer);
  }, [saved]);

  const offered = capabilities.data;
  if (!offered?.enabled) return null;

  const genders = offered.genders.filter((g): g is ModelGender => g in GENDER_LABELS);
  const tones = offered.skin_tones;
  const gender: ModelGender = draft.gender ?? settings.tryon_gender;
  const tone = draft.tone ?? settings.tryon_skin_tone;

  const save = (next: Draft, body: { tryon_gender?: ModelGender; tryon_skin_tone?: number }) => {
    setDraft((current) => ({ ...current, ...next }));
    setSaved(0);
    patch.mutate(body, {
      onSuccess: () => setSaved((count) => count + 1),
      onSettled: () => setDraft({}),
    });
  };

  return (
    <Card style={styles.card} testID="settings-model">
      <View style={styles.head}>
        <Text accessibilityRole="header" style={styles.title}>
          Tu modelo
        </Text>
        <Text style={styles.text}>
          El modelo sobre el que verás tus looks con «Verlo puesto». Se guarda automáticamente.
        </Text>
      </View>

      <View style={styles.body}>
        <View style={styles.preview} testID="model-preview">
          {Platform.OS === 'web' ? (
            <View style={[StyleSheet.absoluteFill, webBackdrop]} />
          ) : (
            <LinearGradient
              colors={LINEN}
              start={{ x: 0.5, y: 0 }}
              end={{ x: 0.5, y: 1 }}
              style={StyleSheet.absoluteFill}
            />
          )}
          <Image
            source={tryOnPreview(gender, tone)}
            style={[styles.figure, Platform.OS === 'web' ? webShadow : null]}
            contentFit="contain"
            accessibilityLabel={`Modelo ${GENDER_LABELS[gender].toLowerCase()}, tono ${tone} de ${tones.length}`}
          />
        </View>

        <View style={styles.controls}>
          {genders.length > 1 ? (
            <View style={styles.field}>
              <Text style={styles.label}>Modelo</Text>
              <Segmented
                accessibilityLabel="Modelo"
                options={genders.map((value) => ({ value, label: GENDER_LABELS[value] }))}
                value={gender}
                onChange={(value) => {
                  if (!offline && value !== gender)
                    save({ gender: value }, { tryon_gender: value });
                }}
              />
            </View>
          ) : null}

          <View style={styles.field}>
            <Text style={styles.label} nativeID="model-tone-label">
              Tono de piel
            </Text>
            <View
              accessibilityRole="radiogroup"
              accessibilityLabel="Tono de piel"
              aria-labelledby="model-tone-label"
              style={styles.tones}
            >
              {tones.map((option) => {
                const checked = option.id === tone;
                return (
                  <Pressable
                    key={option.id}
                    accessibilityRole="radio"
                    accessibilityLabel={`Tono ${option.id} de ${tones.length}`}
                    accessibilityState={{ checked, disabled: offline }}
                    // react-native-web only emits aria-checked from the aria prop.
                    aria-checked={checked}
                    disabled={offline}
                    onPress={() => {
                      if (!checked) save({ tone: option.id }, { tryon_skin_tone: option.id });
                    }}
                    style={styles.toneHit}
                  >
                    <View
                      style={[
                        styles.tone,
                        { backgroundColor: option.hex },
                        checked && styles.toneOn,
                      ]}
                    >
                      {checked ? (
                        <View style={[styles.check, { borderColor: checkColor(option.hex) }]} />
                      ) : null}
                    </View>
                  </Pressable>
                );
              })}
            </View>
          </View>

          <Text style={styles.note}>
            Usamos modelos generados, nunca tu foto. La imagen se encuadra de la barbilla a los
            tobillos para centrarse en la ropa.
          </Text>

          {patch.isError ? (
            <Text style={styles.error} accessibilityRole="alert">
              No se pudo guardar el cambio. {patch.error.message}
            </Text>
          ) : null}
          {saved > 0 && !patch.isPending ? (
            <Text style={styles.ok} accessibilityRole="alert" testID="model-saved">
              Guardado
            </Text>
          ) : null}
          <OfflineNote />
        </View>
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.lg, padding: 20 },
  head: { gap: 4 },
  title: { fontFamily: fontFamilies.display, fontSize: 20, lineHeight: 26, color: colors.ink },
  text: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.ink2 },
  body: { flexDirection: 'row', flexWrap: 'wrap', gap: 22, alignItems: 'center' },
  preview: {
    width: 220,
    maxWidth: '100%',
    aspectRatio: 3 / 4,
    borderRadius: radii.panel,
    overflow: 'hidden',
    alignSelf: 'center',
  },
  figure: { width: '100%', height: '100%' },
  controls: { flexGrow: 1, flexBasis: 240, gap: spacing.lg },
  field: { gap: 8 },
  label: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, color: colors.ink },
  tones: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  // The hit area is 44 x 44; the visible swatch is a little smaller so the selected ring fits.
  toneHit: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  tone: {
    width: 34,
    height: 34,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: `inset 0px 0px 0px 1px ${colors.lineStrong}`,
  },
  toneOn: { boxShadow: `0px 0px 0px 2px ${colors.surface}, 0px 0px 0px 4px ${colors.ink}` },
  check: {
    width: 12,
    height: 7,
    marginTop: -2,
    borderLeftWidth: 2.5,
    borderBottomWidth: 2.5,
    transform: [{ rotate: '-45deg' }],
  },
  note: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  error: { fontFamily: fontFamilies.body, fontSize: 13.5, lineHeight: 19, color: colors.danger },
  ok: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, color: colors.okText },
});
