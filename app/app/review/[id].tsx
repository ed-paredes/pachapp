import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

/**
 * Revisión (Review): cropped photo + editable attribute chips + the
 * "Revisión terminada" button (UI-REQ-021, D19). Reached after a garment's
 * upload job finishes (UI-REQ-019). The chip/photo UI needs real garment
 * data from `PATCH/GET /garments/{id}` (out of scope here, no endpoints
 * beyond `/health` are wired up yet), so this is a screen shell.
 */
export default function ReviewScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Revisión</Text>
      <Text style={styles.description}>
        Esta pantalla mostrará la foto recortada y los atributos editables de la prenda {id}
        cuando haya datos reales del servidor.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    gap: 12,
  },
  title: {
    fontSize: 24,
    fontWeight: '700',
  },
  description: {
    fontSize: 15,
    opacity: 0.7,
  },
});
