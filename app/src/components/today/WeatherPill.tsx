import { StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { colors, fontFamilies, radii, shadows } from '@/theme';

export type Weather = {
  /** Current temperature in °C. */
  temperature: number;
  /** Short description, e.g. "Nublado". */
  summary: string;
  /** Maximum of the day in °C. */
  max?: number;
};

const ICON = { ios: 'cloud', android: 'cloud', web: 'cloud' } as const;

/** Weather chip under the greeting. Renders nothing without data (the API has none yet). */
export function WeatherPill({ weather }: { weather?: Weather }) {
  if (!weather) return null;
  const detail =
    weather.max === undefined ? weather.summary : `${weather.summary}, máx. ${weather.max}°`;
  return (
    <View style={styles.pill} testID="weather-pill">
      <IconSymbol name={ICON} size={18} color={colors.ink2} />
      <Text style={styles.text}>
        <Text style={styles.temp}>{weather.temperature}°</Text> · {detail}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    alignSelf: 'flex-start',
    gap: 8,
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: radii.pill,
    backgroundColor: colors.surface,
    boxShadow: shadows.card,
  },
  text: { fontFamily: fontFamilies.body, fontSize: 14, color: colors.ink2 },
  temp: { fontFamily: fontFamilies.bodySemiBold, color: colors.ink },
});
