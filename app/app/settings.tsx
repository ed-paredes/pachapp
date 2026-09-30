import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { centeredContentStyle } from '@/components/ContentContainer';
import { ErrorState } from '@/components/ErrorState';
import { LoadingState } from '@/components/LoadingState';
import { EngineSettingsForm } from '@/components/EngineSettingsForm';
import { useHealth } from '@/hooks/useHealth';
import { useSettings } from '@/hooks/useSettings';

/**
 * Ajustes (Settings): engine weights, no-repeat days, N complements — no
 * export (see 07's "Conflictos resueltos"). Loaded from `GET /settings` and
 * saved with `PATCH /settings`; below it, `/health` is shown as a discreet
 * connection status line (UI-REQ-014).
 */
export default function SettingsScreen() {
  const health = useHealth();
  const settings = useSettings();

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={[styles.content, centeredContentStyle]}
    >
      <View style={styles.section} testID="settings-engine">
        <Text style={styles.sectionTitle}>Motor de recomendación</Text>
        {settings.isPending ? <LoadingState /> : null}
        {settings.isError ? (
          <ErrorState
            message="No se pudieron cargar los ajustes."
            onRetry={() => void settings.refetch()}
          />
        ) : null}
        {settings.isSuccess ? <EngineSettingsForm settings={settings.data} /> : null}
      </View>

      <View style={styles.section} testID="settings-connection">
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
  connectionOk: {
    fontSize: 14,
    color: '#1a7f37',
  },
});
