import { useLocalSearchParams } from 'expo-router';
import { StyleSheet, Text, View } from 'react-native';

/**
 * Detalle de prenda (Garment detail): attributes, usage, outfits it appears
 * in, and archive/status toggle. Needs `GET /garments/{id}` (out of scope
 * here, no endpoints beyond `/health` are wired up yet), so this is a
 * screen shell.
 */
export default function GarmentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Detalle de prenda</Text>
      <Text style={styles.description}>
        Esta pantalla mostrará los atributos y el uso de la prenda {id} cuando haya datos reales del
        servidor.
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
