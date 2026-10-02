import { Pressable, StyleSheet, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { SEASON_LABELS } from '@/lib/labels';
import { colors, radii } from '@/theme';

import type { IconName } from './icons';

type Season = keyof typeof SEASON_LABELS;

const SEASONS: { value: Season; icon: IconName }[] = [
  {
    value: 'spring',
    icon: { ios: 'camera.macro', android: 'local_florist', web: 'local_florist' },
  },
  { value: 'summer', icon: { ios: 'sun.max', android: 'wb_sunny', web: 'wb_sunny' } },
  { value: 'autumn', icon: { ios: 'leaf', android: 'eco', web: 'eco' } },
  { value: 'winter', icon: { ios: 'snowflake', android: 'ac_unit', web: 'ac_unit' } },
];

type SeasonPickerProps = {
  value: Season[];
  /** Makes the squares toggles; without it the picker is read-only. */
  onChange?: (value: Season[]) => void;
};

/** Four 38 dp squares, one per season; active ones are filled with `accentSoft`. */
export function SeasonPicker({ value, onChange }: SeasonPickerProps) {
  const toggle = (season: Season) =>
    onChange?.(value.includes(season) ? value.filter((s) => s !== season) : [...value, season]);

  return (
    <View style={styles.row}>
      {SEASONS.map(({ value: season, icon }) => {
        const on = value.includes(season);
        const square = (
          <View style={[styles.square, on && styles.squareOn]}>
            <IconSymbol name={icon} size={18} color={on ? colors.accentText : colors.ink2} />
          </View>
        );
        if (!onChange) {
          return (
            <View
              key={season}
              accessible
              accessibilityLabel={`${SEASON_LABELS[season]}${on ? ', activa' : ''}`}
            >
              {square}
            </View>
          );
        }
        return (
          <Pressable
            key={season}
            accessibilityRole="checkbox"
            accessibilityLabel={SEASON_LABELS[season]}
            accessibilityState={{ checked: on }}
            hitSlop={3}
            onPress={() => toggle(season)}
          >
            {square}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 6 },
  square: {
    width: 38,
    height: 38,
    borderRadius: radii.sm,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface2,
    opacity: 0.6,
  },
  squareOn: { backgroundColor: colors.accentSoft, opacity: 1 },
});
