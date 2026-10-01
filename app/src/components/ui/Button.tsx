import { Pressable, StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { colors, fontFamilies, radii, shadows } from '@/theme';

import { pressFeedback } from './feedback';
import type { IconName } from './icons';

type ButtonVariant = 'primary' | 'secondary' | 'accent';

type CommonProps = {
  variant?: ButtonVariant;
  onPress: () => void;
  disabled?: boolean;
  testID?: string;
};

type ButtonProps = CommonProps &
  (
    | { label: string; icon?: IconName; accessibilityLabel?: string }
    // Icon-only: there is no visible text, so the accessible name is mandatory.
    | { label?: undefined; icon: IconName; accessibilityLabel: string }
  );

const VARIANTS: Record<ButtonVariant, { bg: string; fg: string; shadow?: string }> = {
  primary: { bg: colors.ink, fg: colors.onInk },
  secondary: { bg: colors.surface, fg: colors.ink, shadow: shadows.card },
  accent: { bg: colors.accent, fg: colors.onInk },
};

/**
 * Pill button. One `primary` per screen; `secondary` is white with a soft shadow; `accent` is
 * terracotta. Without `label` it renders as a 44 dp round icon button.
 */
export function Button({
  label,
  icon,
  variant = 'primary',
  onPress,
  disabled,
  accessibilityLabel,
  testID,
}: ButtonProps) {
  const v = VARIANTS[variant];
  const iconOnly = label === undefined;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      accessibilityState={{ disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      testID={testID}
      style={(state) => [
        styles.base,
        iconOnly ? styles.iconOnly : styles.withLabel,
        { backgroundColor: v.bg, boxShadow: v.shadow },
        disabled && styles.disabled,
        pressFeedback(state),
      ]}
    >
      <View style={styles.row}>
        {icon ? <IconSymbol name={icon} size={20} color={v.fg} /> : null}
        {label ? <Text style={[styles.label, { color: v.fg }]}>{label}</Text> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: { minHeight: 44, borderRadius: radii.pill, alignItems: 'center', justifyContent: 'center' },
  withLabel: { paddingVertical: 12, paddingHorizontal: 22 },
  iconOnly: { width: 44 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  label: { fontFamily: fontFamilies.bodySemiBold, fontSize: 15, lineHeight: 20 },
  disabled: { opacity: 0.5 },
});
