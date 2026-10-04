import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { colors, fontFamilies, radii, shadows } from '@/theme';

type SectionErrorProps = {
  /** Name of the section that failed; it keeps the card's place and names the retry button. */
  title: string;
  onRetry: () => void;
  /** A retry is already in flight: the button is disabled so it cannot cancel it. */
  retrying?: boolean;
  testID?: string;
};

/**
 * Compact error for one section of a screen that otherwise loaded (`ErrorState` is the
 * full-screen version). It sits in the failed card's slot, so the rest of the screen stays put,
 * and the alert role makes screen readers announce it when it appears.
 */
export function SectionError({
  title,
  onRetry,
  retrying = false,
  testID = 'section-error',
}: SectionErrorProps) {
  return (
    <View style={styles.card} accessibilityRole="alert" testID={testID}>
      <Text accessibilityRole="header" style={styles.title}>
        {title}
      </Text>
      <Text style={styles.message}>No se pudo cargar esta lista.</Text>
      <View style={styles.action}>
        <Button
          label="Reintentar"
          accessibilityLabel={`Reintentar: ${title}`}
          onPress={onRetry}
          disabled={retrying}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    gap: 4,
    padding: 20,
    borderRadius: radii.md,
    backgroundColor: colors.surface,
    boxShadow: shadows.card,
  },
  title: { fontFamily: fontFamilies.display, fontSize: 17, lineHeight: 24, color: colors.ink },
  message: { fontFamily: fontFamilies.body, fontSize: 14.5, lineHeight: 21, color: colors.ink2 },
  // Keeps the pill at its natural width instead of stretching across the card.
  action: { alignSelf: 'flex-start', marginTop: 8 },
});
