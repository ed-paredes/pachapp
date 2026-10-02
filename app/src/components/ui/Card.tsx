import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { colors, radii, shadows } from '@/theme';

type CardProps = { children: ReactNode; style?: StyleProp<ViewStyle>; testID?: string };

/** White surface with a soft shadow. Padding is up to the caller. */
export function Card({ children, style, testID }: CardProps) {
  return (
    <View style={[styles.card, style]} testID={testID}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surface, borderRadius: radii.md, boxShadow: shadows.card },
});
