import { StyleSheet, Text, View } from 'react-native';

import { Button } from '@/components/ui';
import { colors, fontFamilies } from '@/theme';

type ErrorStateProps = {
  message?: string;
  onRetry: () => void;
};

const DEFAULT_MESSAGE = 'Algo salió mal. Inténtalo de nuevo.';

/**
 * Explicit error state with a retry action (UI-REQ-008): any screen that
 * depends on a network request must show this instead of an infinite
 * spinner or a blank screen when the request fails.
 */
export function ErrorState({ message = DEFAULT_MESSAGE, onRetry }: ErrorStateProps) {
  return (
    <View style={styles.container} testID="error-state">
      <Text style={styles.message}>{message}</Text>
      <Button label="Reintentar" onPress={onRetry} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
    padding: 24,
  },
  message: {
    fontFamily: fontFamilies.body,
    fontSize: 16,
    lineHeight: 24,
    color: colors.ink,
    textAlign: 'center',
  },
});
