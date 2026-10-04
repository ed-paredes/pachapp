import { useEffect, useMemo, type ReactNode } from 'react';
import { AccessibilityInfo, StyleSheet, Text, View } from 'react-native';
import { SafeAreaInsetsContext, useSafeAreaInsets } from 'react-native-safe-area-context';

import { IconSymbol } from '@/components/IconSymbol';
import { formatSavedAt } from '@/lib/format-date';
import { useIsOffline, useLastSync } from '@/offline/reachability';
import { colors, fontFamilies, spacing } from '@/theme';

const ICON = { ios: 'wifi.slash', android: 'cloud_off', web: 'cloud_off' } as const;

/** Why every control that changes something is off while the backend is unreachable. */
export const OFFLINE_NOTE = 'Podrás hacer cambios cuando vuelva la conexión.';

/** Banner copy: says what is happening and how old the data on screen is. */
export function offlineBannerText(lastSync: number, now: Date = new Date()): string {
  return `Sin conexión con tu armario. Mostrando lo guardado ${formatSavedAt(lastSync, now)}.`;
}

/**
 * Calm strip at the top of the app while the backend cannot be reached and there is saved data
 * to show. `topInset` keeps it clear of the status bar (the screens below then see no inset).
 * It is read aloud once, when it appears, not on every render.
 */
export function OfflineBanner({ text, topInset = 0 }: { text: string; topInset?: number }) {
  useEffect(() => {
    void AccessibilityInfo.announceForAccessibility(text);
    // Announce on appearing only: a later change of the date text must not interrupt again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <View style={[styles.banner, { paddingTop: topInset + spacing.sm }]} testID="offline-banner">
      <IconSymbol name={ICON} size={18} color={colors.infoText} />
      <Text style={styles.text}>{text}</Text>
    </View>
  );
}

/** Mounted once at the root: the banner shows only on native, offline, with something saved. */
export function OfflineBannerHost() {
  const offline = useIsOffline();
  const lastSync = useLastSync();
  const insets = useSafeAreaInsets();
  if (!offline || lastSync === undefined) return null;
  return <OfflineBanner text={offlineBannerText(lastSync)} topInset={insets.top} />;
}

/**
 * Root wrapper: the banner above the app. While it is up it covers the status bar area, so the
 * screens below are told the top inset is 0 (they pad themselves from `useSafeAreaInsets`).
 * The tree has the same shape either way, so showing the banner never remounts the screens.
 */
export function OfflineChrome({ children }: { children: ReactNode }) {
  const offline = useIsOffline();
  const lastSync = useLastSync();
  const shown = offline && lastSync !== undefined;
  const insets = useSafeAreaInsets();
  const below = useMemo(() => (shown ? { ...insets, top: 0 } : insets), [shown, insets]);
  return (
    <View style={styles.root}>
      <OfflineBannerHost />
      <SafeAreaInsetsContext.Provider value={below}>
        <View style={styles.root}>{children}</View>
      </SafeAreaInsetsContext.Provider>
    </View>
  );
}

/**
 * For screens with controls that change data: `blocked` is true offline, and `OfflineNote`
 * says why. Nothing is queued: changes are simply unavailable until the backend answers.
 */
export function useOfflineBlock(): boolean {
  return useIsOffline();
}

export function OfflineNote({
  testID = 'offline-note',
  centered = false,
}: {
  testID?: string;
  centered?: boolean;
}) {
  if (!useIsOffline()) return null;
  return (
    <Text style={[styles.note, centered && styles.centered]} testID={testID}>
      {OFFLINE_NOTE}
    </Text>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1 },
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingBottom: spacing.sm,
    paddingHorizontal: spacing.screen,
    backgroundColor: colors.infoSoft,
  },
  text: {
    flex: 1,
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 14,
    lineHeight: 20,
    color: colors.infoText,
  },
  centered: { textAlign: 'center' },
  note: {
    fontFamily: fontFamilies.body,
    fontSize: 14,
    lineHeight: 20,
    color: colors.ink2,
  },
});
