import { Pressable, StyleSheet, Text, View } from 'react-native';

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
      <Pressable
        onPress={onRetry}
        accessibilityRole="button"
        accessibilityLabel="Reintentar"
        style={styles.button}
      >
        <Text style={styles.buttonText}>Reintentar</Text>
      </Pressable>
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
    fontSize: 16,
    textAlign: 'center',
  },
  button: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#208AEF',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '600',
  },
});
