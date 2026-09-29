import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '@/components/EmptyState';

/**
 * Armario (Wardrobe): grid of garments with a "needs review" badge and
 * filters. There's no `/garments` endpoint wired up yet (only `/health`
 * is), so this shows the real current empty state (UI-REQ-004) rather than
 * placeholder garments. `LoadingState`'s grid-skeleton variant and
 * `ErrorState` are ready in `src/components/` for when the real query is
 * added.
 */
export default function WardrobeScreen() {
  return (
    <View style={styles.container}>
      <EmptyState
        title="Tu armario está vacío"
        description="Añade tu primera prenda para empezar a construir tu armario."
      />
      <Link href="/(tabs)/add" style={styles.link}>
        <Text style={styles.linkText}>Añadir prenda</Text>
      </Link>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  link: {
    alignSelf: 'center',
    marginBottom: 32,
  },
  linkText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#208AEF',
  },
});
