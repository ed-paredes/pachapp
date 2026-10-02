import { Link } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

import { EmptyState } from '@/components/EmptyState';
import { centeredContentStyle } from '@/components/ContentContainer';

/**
 * Hoy (Today): shows the current outfit proposal, or the empty state from
 * UI-REQ-005 when there aren't enough garments yet to generate one. There's
 * no `/outfits/generate` call wired up yet (only `/health` is), so this
 * screen honestly shows that empty state rather than faking a proposal.
 */
export default function TodayScreen() {
  return (
    <View style={[styles.container, centeredContentStyle]}>
      <EmptyState
        title="Aún no tienes suficientes prendas para generar un outfit"
        description="Añade algunas prendas a tu armario para ver tu primera propuesta."
      />
      <Link href="/(tabs)/add" style={styles.link}>
        <Text style={styles.linkText}>Ir a Añadir</Text>
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
