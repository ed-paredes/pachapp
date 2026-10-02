import { Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { colors, fontFamilies, radii } from '@/theme';

import { pressFeedback } from './feedback';
import type { IconName } from './icons';

type BannerProps = {
  icon: IconName;
  text: string;
  /** Label of the action button (e.g. "Revisar"). */
  actionLabel?: string;
  onAction?: () => void;
  testID?: string;
};

/** Warning strip on `warnSoft`: icon, message and an optional action. */
export function Banner({ icon, text, actionLabel, onAction, testID }: BannerProps) {
  return (
    <View style={styles.banner} testID={testID}>
      <IconSymbol name={icon} size={20} color={colors.warnText} />
      <Text style={styles.text}>{text}</Text>
      {actionLabel && onAction ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={actionLabel}
          onPress={onAction}
          style={(state) => [styles.action, pressFeedback(state)]}
        >
          <Text style={styles.actionLabel}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 10,
    paddingLeft: 16,
    paddingRight: 10,
    borderRadius: radii.md,
    backgroundColor: colors.warnSoft,
  },
  text: {
    flex: 1,
    fontFamily: fontFamilies.bodyMedium,
    fontSize: 14,
    lineHeight: 20,
    color: colors.warnText,
  },
  action: {
    minHeight: 44,
    justifyContent: 'center',
    paddingHorizontal: 16,
    borderRadius: radii.pill,
    backgroundColor: colors.ink,
  },
  actionLabel: { fontFamily: fontFamilies.bodySemiBold, fontSize: 13.5, color: colors.onInk },
});
