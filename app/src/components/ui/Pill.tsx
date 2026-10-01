import { StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies, radii } from '@/theme';

export type PillTone = 'ok' | 'info' | 'warn' | 'ghost';

type PillProps = { label: string; tone?: PillTone; dot?: boolean; testID?: string };

// Text uses the AA-safe variants; the soft fills match the mockup.
const TONES: Record<PillTone, { bg: string; fg: string }> = {
  ok: { bg: colors.okSoft, fg: colors.okText },
  info: { bg: colors.infoSoft, fg: colors.infoText },
  warn: { bg: colors.warnSoft, fg: colors.warnText },
  ghost: { bg: colors.surface2, fg: colors.ink2 },
};

/** Status label: ok (En el armario, Nueva), info (Lavando), warn (Revisar), ghost (Archivada). */
export function Pill({ label, tone = 'ghost', dot = false, testID }: PillProps) {
  const t = TONES[tone];
  return (
    <View style={[styles.pill, { backgroundColor: t.bg }]} testID={testID}>
      {dot ? <View style={[styles.dot, { backgroundColor: t.fg }]} /> : null}
      <Text style={[styles.label, { color: t.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 6,
    paddingVertical: 5,
    paddingHorizontal: 11,
    borderRadius: radii.pill,
  },
  dot: { width: 6, height: 6, borderRadius: 3 },
  label: { fontFamily: fontFamilies.bodyMedium, fontSize: 12.5, lineHeight: 16 },
});
