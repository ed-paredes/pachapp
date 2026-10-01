import { Link } from 'expo-router';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { IconSymbol } from '@/components/IconSymbol';
import { CONTENT_MAX_WIDTH, colors, fontFamilies, radii, spacing } from '@/theme';

import type { PressState } from './feedback';

/**
 * Header icon that opens Ajustes (UI-REQ-002: "Ajustes desde un icono de cabecera"). It sits in
 * the header of every tab for consistent access from anywhere in the bottom tabs.
 */
function SettingsButton() {
  return (
    <Link href="/settings" asChild>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Abrir ajustes"
        style={({ hovered, pressed }: PressState) => [
          styles.round,
          (hovered || pressed) && styles.roundActive,
        ]}
      >
        <IconSymbol
          name={{ ios: 'gearshape', android: 'settings', web: 'settings' }}
          size={22}
          color={colors.ink}
        />
      </Pressable>
    </Link>
  );
}

/** Tab header: the "Armario." wordmark (italic terracotta full stop) and the settings button. */
export function AppHeader() {
  const { top } = useSafeAreaInsets();
  return (
    <View style={[styles.bar, { paddingTop: top }]}>
      <View style={styles.inner}>
        <Text accessibilityLabel="Armario" style={styles.logo}>
          Armario<Text style={styles.dot}>.</Text>
        </Text>
        <SettingsButton />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { backgroundColor: colors.bg },
  inner: {
    width: '100%',
    maxWidth: CONTENT_MAX_WIDTH,
    alignSelf: 'center',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.screen,
    paddingVertical: 10,
  },
  logo: { fontFamily: fontFamilies.display, fontSize: 24, letterSpacing: -0.5, color: colors.ink },
  dot: { fontFamily: fontFamilies.displayItalic, color: colors.accent },
  round: {
    width: 44,
    height: 44,
    borderRadius: radii.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  roundActive: { backgroundColor: colors.surface2 },
});
