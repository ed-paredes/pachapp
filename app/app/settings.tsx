import { StyleSheet, Text, View } from 'react-native';

import { EngineSettingsForm } from '@/components/EngineSettingsForm';
import { ErrorState } from '@/components/ErrorState';
import { BackButton } from '@/components/GarmentHero';
import { LoadingState } from '@/components/LoadingState';
import { useGoBack } from '@/components/StateShell';
import { Card, Eyebrow, Pill, Screen, Title } from '@/components/ui';
import { useHealth } from '@/hooks/useHealth';
import { useSettings } from '@/hooks/useSettings';
import { colors, fontFamilies, spacing } from '@/theme';

/**
 * Ajustes (Settings): engine weights, no-repeat days, N complements — no
 * export (see 07's "Conflictos resueltos"). Loaded from `GET /settings` and
 * saved with `PATCH /settings`; below it, `/health` is shown as a discreet
 * connection status line (UI-REQ-014).
 */
export default function SettingsScreen() {
  const health = useHealth();
  const settings = useSettings();
  const goBack = useGoBack();

  return (
    <Screen standalone testID="settings-screen">
      <View style={styles.page}>
        <View style={styles.back}>
          <BackButton onPress={goBack} />
        </View>
        <View style={styles.header}>
          <Eyebrow>Preferencias</Eyebrow>
          <Title>Ajustes</Title>
        </View>

        <Card style={styles.section} testID="settings-engine">
          <View style={styles.sectionHead}>
            <Text accessibilityRole="header" style={styles.sectionTitle}>
              Motor de recomendación
            </Text>
            <Text style={styles.sectionText}>
              Cómo se eligen las prendas de cada outfit. Los cuatro pesos deben sumar 1,00.
            </Text>
          </View>
          {settings.isPending ? <LoadingState /> : null}
          {settings.isError ? (
            <ErrorState
              message="No se pudieron cargar los ajustes."
              onRetry={() => void settings.refetch()}
            />
          ) : null}
          {settings.isSuccess ? <EngineSettingsForm settings={settings.data} /> : null}
        </Card>

        <Card style={styles.section} testID="settings-connection">
          <Text accessibilityRole="header" style={styles.sectionTitle}>
            Conexión
          </Text>
          {health.isPending ? <LoadingState /> : null}
          {health.isError ? (
            <ErrorState
              message="No se pudo conectar con el servidor."
              onRetry={() => health.refetch()}
            />
          ) : null}
          {health.isSuccess ? <Pill label="Conectado al servidor" tone="ok" dot /> : null}
        </Card>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  page: { gap: spacing.lg, maxWidth: 720, width: '100%', alignSelf: 'center' },
  back: { alignItems: 'flex-start' },
  header: { gap: 10, marginBottom: spacing.xs },
  section: { gap: spacing.lg, padding: 20 },
  sectionHead: { gap: 4 },
  sectionTitle: {
    fontFamily: fontFamilies.display,
    fontSize: 17,
    lineHeight: 24,
    color: colors.ink,
  },
  sectionText: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.ink2 },
});
