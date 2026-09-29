import { StyleSheet, View } from 'react-native';

import { EmptyState } from '@/components/EmptyState';

/**
 * Historial (History): calendar + simple stats. Empty-state copy is exact
 * per UI-REQ-007 (no `wear_log` rows for the queried month — and there's no
 * `/wear-log` endpoint wired up yet, only `/health`, so this is always the
 * real current state).
 */
export default function HistoryScreen() {
  return (
    <View style={styles.container}>
      <EmptyState title="Todavía no has registrado ningún outfit" />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
