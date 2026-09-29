import { ActivityIndicator, StyleSheet, View } from 'react-native';

type LoadingStateProps = {
  /**
   * `spinner` (default) is a centered activity indicator, used for
   * one-off requests (e.g. the health check in Ajustes). `grid` renders a
   * placeholder grid of skeleton cells, used by Armario (UI-REQ-004).
   */
  variant?: 'spinner' | 'grid';
  gridItems?: number;
};

export function LoadingState({ variant = 'spinner', gridItems = 6 }: LoadingStateProps) {
  if (variant === 'grid') {
    return (
      <View style={styles.grid} testID="loading-state-grid">
        {Array.from({ length: gridItems }).map((_, index) => (
          <View key={index} style={styles.gridCell} testID="loading-state-grid-cell" />
        ))}
      </View>
    );
  }

  return (
    <View style={styles.spinnerContainer} testID="loading-state-spinner">
      <ActivityIndicator size="large" />
    </View>
  );
}

const styles = StyleSheet.create({
  spinnerContainer: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    padding: 16,
  },
  gridCell: {
    width: '30%',
    aspectRatio: 1,
    borderRadius: 8,
    backgroundColor: '#E2E8F0',
  },
});
