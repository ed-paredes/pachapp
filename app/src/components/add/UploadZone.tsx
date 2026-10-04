import { StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { OfflineNote, useOfflineBlock } from '@/components/OfflineBanner';
import { Button } from '@/components/ui';
import { colors, fontFamilies, radii } from '@/theme';

type UploadZoneProps = {
  onCamera: () => void;
  onGallery: () => void;
  /** Permission or picker problem to show under the buttons. */
  error?: string | null;
};

const CAMERA = { ios: 'camera', android: 'photo_camera', web: 'photo_camera' } as const;
const GALLERY = {
  ios: 'photo.on.rectangle',
  android: 'photo_library',
  web: 'photo_library',
} as const;

/**
 * Dashed upload area of Añadir: a camera mark, one primary action and a secondary one. There is
 * no drag-and-drop affordance because the upload path only takes what the pickers return.
 */
export function UploadZone({ onCamera, onGallery, error }: UploadZoneProps) {
  const offline = useOfflineBlock();
  return (
    <View style={styles.zone} testID="upload-zone">
      <View style={styles.mark}>
        <IconSymbol name={CAMERA} size={32} color={colors.accent} />
      </View>
      <Text style={styles.title}>Añade tus fotos</Text>
      <Text style={styles.hint}>
        Haz una foto o elige varias de la galería. Puedes seguir añadiendo mientras se procesan.
      </Text>
      <View style={styles.actions}>
        <Button label="Hacer foto" icon={CAMERA} disabled={offline} onPress={onCamera} />
        <Button
          label="Galería"
          accessibilityLabel="Elegir de la galería"
          icon={GALLERY}
          variant="secondary"
          disabled={offline}
          onPress={onGallery}
        />
      </View>
      <OfflineNote centered />
      {error ? (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  zone: {
    alignItems: 'center',
    paddingVertical: 36,
    paddingHorizontal: 20,
    borderRadius: radii.lg,
    borderWidth: 2,
    borderStyle: 'dashed',
    // AA boundary variant (WCAG 1.4.11); the mockup's `line` is only 1.2:1.
    borderColor: colors.lineStrong,
    backgroundColor: colors.surface,
  },
  mark: {
    width: 72,
    height: 72,
    borderRadius: 24,
    backgroundColor: colors.accentSoft,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 18,
  },
  title: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 26,
    lineHeight: 31,
    color: colors.ink,
  },
  hint: {
    fontFamily: fontFamilies.body,
    fontSize: 14.5,
    lineHeight: 21,
    color: colors.ink2,
    textAlign: 'center',
    marginTop: 6,
    marginBottom: 22,
    maxWidth: 360,
  },
  actions: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center', gap: 10 },
  error: {
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 14,
    lineHeight: 20,
    color: colors.danger,
    textAlign: 'center',
    marginTop: 16,
  },
});
