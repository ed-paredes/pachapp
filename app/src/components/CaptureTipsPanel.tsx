import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

type CaptureTipsPanelProps = {
  visible: boolean;
  onDismiss: () => void;
};

const TIPS = [
  'Fotografía una sola prenda por foto.',
  'Extiéndela sobre un fondo liso o cuélgala en una percha.',
  'Usa luz natural siempre que puedas.',
];

/**
 * Capture-tips panel for Añadir (UI-REQ-020 / UI-SCN-007): shown the first
 * time the screen opens, dismissible, and re-openable afterwards from the
 * help icon on the screen. "Seen" persistence lives in the caller via
 * `useCaptureTipsSeen`.
 */
export function CaptureTipsPanel({ visible, onDismiss }: CaptureTipsPanelProps) {
  if (!visible) {
    return null;
  }

  return (
    <View style={styles.overlay} testID="capture-tips-panel">
      <View style={styles.panel}>
        <Text style={styles.title}>Consejos para fotografiar tus prendas</Text>
        <ScrollView>
          {TIPS.map((tip) => (
            <Text key={tip} style={styles.tip}>
              • {tip}
            </Text>
          ))}
        </ScrollView>
        <Pressable
          onPress={onDismiss}
          accessibilityRole="button"
          accessibilityLabel="Entendido, cerrar consejos"
          style={styles.dismissButton}
        >
          <Text style={styles.dismissText}>Entendido</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.4)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 24,
  },
  panel: {
    width: '100%',
    maxWidth: 420,
    maxHeight: '80%',
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    gap: 12,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  tip: {
    fontSize: 15,
    marginBottom: 8,
  },
  dismissButton: {
    alignSelf: 'flex-end',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: '#208AEF',
  },
  dismissText: {
    color: '#fff',
    fontWeight: '600',
  },
});
