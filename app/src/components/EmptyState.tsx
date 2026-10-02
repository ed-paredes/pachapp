import { StyleSheet, Text, View } from 'react-native';

import { colors, fontFamilies } from '@/theme';

type EmptyStateProps = {
  title: string;
  description?: string;
};

/**
 * Generic empty-state block: a short title plus optional supporting copy.
 * Used by screens that have no data yet (UI-REQ-004/UI-REQ-005/UI-REQ-007).
 */
export function EmptyState({ title, description }: EmptyStateProps) {
  return (
    <View style={styles.container} testID="empty-state">
      <Text style={styles.title}>{title}</Text>
      {description ? <Text style={styles.description}>{description}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: 24,
  },
  title: {
    fontFamily: fontFamilies.displayRegular,
    fontSize: 24,
    lineHeight: 30,
    color: colors.ink,
    textAlign: 'center',
  },
  description: {
    fontFamily: fontFamilies.body,
    fontSize: 14,
    lineHeight: 20,
    color: colors.ink2,
    textAlign: 'center',
  },
});
