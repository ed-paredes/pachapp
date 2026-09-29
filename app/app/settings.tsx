import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import { useHealth } from '@/hooks/useHealth';

/**
 * Ajustes (Settings): engine weights, no-repeat days, N complements — no
 * export (see 07's "Conflictos resueltos"). Those settings need
 * `GET/PATCH /settings` (out of scope here, no endpoints beyond `/health`
 * are wired up yet), so they're listed as static, non-editable placeholders.
 * The one real query wired up in this iteration, `/health`, is shown here
 * as a discreet connection status line (UI-REQ-014).
 */
export default function SettingsScreen() {
  const health = useHealth();

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Motor de recomendación</Text>
        <Text style={styles.placeholder}>Pesos del motor (próximamente editable)</Text>
        <Text style={styles.placeholder}>Días de no repetir (próximamente editable)</Text>
        <Text style={styles.placeholder}>Número de complementos (próximamente editable)</Text>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Conexión</Text>
        {health.isPending ? <LoadingState /> : null}
        {health.isError ? (
          <ErrorState
            message="No se pudo conectar con el servidor."
            onRetry={() => health.refetch()}
          />
        ) : null}
        {health.isSuccess ? <Text style={styles.connectionOk}>Conectado al servidor</Text> : null}
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  content: {
    padding: 24,
    gap: 24,
  },
  section: {
    gap: 8,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  placeholder: {
    fontSize: 14,
    opacity: 0.6,
  },
  connectionOk: {
    fontSize: 14,
    color: '#1a7f37',
  },
});
