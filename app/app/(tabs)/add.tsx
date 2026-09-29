import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { CaptureTipsPanel } from '@/components/CaptureTipsPanel';
import { IconSymbol } from '@/components/IconSymbol';
import { useCaptureTipsSeen } from '@/hooks/useCaptureTipsSeen';

/**
 * Añadir (Add): photo capture + upload/processing progress. The capture flow
 * itself needs `POST /garments` and `GET /jobs/{id}` (out of scope here, no
 * endpoints beyond `/health` are wired up yet); this screen implements the
 * capture-tips panel (UI-REQ-020 / UI-SCN-007) — shown automatically the
 * first time, dismissible, and re-openable via the help icon.
 */
export default function AddScreen() {
  const { seen, markSeen } = useCaptureTipsSeen();
  // `null` means "no manual override yet": visibility then follows whether
  // the panel has already been seen on this device. Deriving it this way
  // (instead of syncing it via a `useEffect`) avoids a setState-in-effect.
  const [manualVisible, setManualVisible] = useState<boolean | null>(null);
  const tipsVisible = manualVisible ?? seen === false;

  const openTips = () => setManualVisible(true);
  const closeTips = () => {
    setManualVisible(false);
    markSeen();
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Añadir</Text>
        <Pressable
          onPress={openTips}
          accessibilityRole="button"
          accessibilityLabel="Ver consejos de captura"
          hitSlop={8}
        >
          <IconSymbol
            name={{ ios: 'questionmark.circle.fill', android: 'help', web: 'help' }}
            size={24}
          />
        </Pressable>
      </View>
      <Text style={styles.description}>
        Próximamente: captura de fotos de tus prendas, con seguimiento de subida y procesado.
      </Text>
      <CaptureTipsPanel visible={tipsVisible} onDismiss={closeTips} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 24,
    gap: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
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
