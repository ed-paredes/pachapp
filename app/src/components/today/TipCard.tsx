import { Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { Card } from '@/components/ui';
import { pressFeedback } from '@/components/ui/feedback';
import type { IconName } from '@/components/ui/icons';
import { colors, fontFamilies, radii, shadows } from '@/theme';

type TipCardProps = {
  icon: IconName;
  tone: 'info' | 'accent';
  title: string;
  text?: string;
  /** Makes the whole card a button that goes somewhere; a chevron shows it. */
  onPress?: () => void;
  accessibilityLabel?: string;
  testID?: string;
};

const CHEVRON = { ios: 'chevron.right', android: 'chevron_right', web: 'chevron_right' } as const;

const TONES = {
  info: { bg: colors.infoSoft, fg: colors.infoText },
  accent: { bg: colors.accentSoft, fg: colors.accentText },
};

/** Notice card: tinted icon square, bold title, one supporting line, optional chevron. */
export function TipCard({
  icon,
  tone,
  title,
  text,
  onPress,
  accessibilityLabel,
  testID,
}: TipCardProps) {
  const t = TONES[tone];
  const body = (
    <>
      <View style={[styles.icon, { backgroundColor: t.bg }]}>
        <IconSymbol name={icon} size={22} color={t.fg} />
      </View>
      <View style={styles.text}>
        <Text style={styles.title}>{title}</Text>
        {text ? <Text style={styles.detail}>{text}</Text> : null}
      </View>
      {onPress ? <IconSymbol name={CHEVRON} size={18} color={colors.ink2} /> : null}
    </>
  );
  if (!onPress) {
    return (
      <Card style={styles.card} testID={testID}>
        {body}
      </Card>
    );
  }
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? [title, text].filter(Boolean).join('. ')}
      onPress={onPress}
      style={(state) => [styles.card, styles.surface, pressFeedback(state)]}
      testID={testID}
    >
      {body}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingVertical: 16,
    paddingHorizontal: 18,
  },
  surface: {
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    boxShadow: shadows.card,
  },
  icon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  text: { flex: 1, gap: 2 },
  title: { fontFamily: fontFamilies.bodySemiBold, fontSize: 14, lineHeight: 20, color: colors.ink },
  detail: { fontFamily: fontFamilies.body, fontSize: 13.5, lineHeight: 19, color: colors.ink2 },
});
