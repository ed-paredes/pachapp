import { useRouter } from 'expo-router';
import type { ReactNode } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { BackButton } from '@/components/GarmentHero';
import { colors, spacing } from '@/theme';

/** Back to where the user came from; Armario when the page was opened directly. */
export function useGoBack() {
  const router = useRouter();
  return () => (router.canGoBack() ? router.back() : router.replace('/(tabs)/wardrobe'));
}

/**
 * Loading / error / not-found for the stack screens that hide the native header (Detalle,
 * Revisión): keeps a round "Volver" button so there is always a way out.
 */
export function StateShell({ state }: { state: ReactNode }) {
  const goBack = useGoBack();
  const insets = useSafeAreaInsets();
  return (
    <View style={[styles.shell, { paddingTop: insets.top + spacing.md }]}>
      <View style={styles.back}>
        <BackButton onPress={goBack} />
      </View>
      {state}
    </View>
  );
}

const styles = StyleSheet.create({
  shell: { flex: 1, backgroundColor: colors.bg, paddingHorizontal: spacing.screen },
  back: { alignItems: 'flex-start' },
});
