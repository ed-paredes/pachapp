import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { CaptureTipsPanel } from '@/components/CaptureTipsPanel';
import { IconSymbol } from '@/components/IconSymbol';
import { UploadItem } from '@/components/UploadItem';
import { useCaptureTipsSeen } from '@/hooks/useCaptureTipsSeen';
import { useUploadQueue } from '@/hooks/useUploadQueue';
import { pickFromCamera, pickFromGallery, type PickResult } from '@/lib/photos';

/**
 * Añadir (Add): photo capture + upload/processing progress. Each photo gets
 * its own polled progress item (UI-REQ-006/017/018); when a job is done the
 * item invites to "Revisar" (UI-REQ-019) without navigating on its own, so
 * several photos can be chained. Also hosts the capture-tips panel
 * (UI-REQ-020 / UI-SCN-007) — shown automatically the first time,
 * dismissible, and re-openable via the help icon.
 */
export default function AddScreen() {
  const { seen, markSeen } = useCaptureTipsSeen();
  // `null` means "no manual override yet": visibility then follows whether
  // the panel has already been seen on this device. Deriving it this way
  // (instead of syncing it via a `useEffect`) avoids a setState-in-effect.
  const [manualVisible, setManualVisible] = useState<boolean | null>(null);
  const tipsVisible = manualVisible ?? seen === false;

  const { items, addAssets, retryUpload, dismiss } = useUploadQueue();
  const [pickError, setPickError] = useState<string | null>(null);

  const pick = async (picker: () => Promise<PickResult>) => {
    setPickError(null);
    try {
      const result = await picker();
      if (result.kind === 'assets') {
        addAssets(result.assets);
      } else if (result.kind === 'denied') {
        setPickError(result.message);
      }
    } catch {
      setPickError('No se pudo abrir la selección de fotos.');
    }
  };

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
      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Hacer foto"
          onPress={() => pick(pickFromCamera)}
          style={styles.button}
        >
          <Text style={styles.buttonText}>Hacer foto</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Elegir de la galería"
          onPress={() => pick(pickFromGallery)}
          style={styles.button}
        >
          <Text style={styles.buttonText}>Elegir de la galería</Text>
        </Pressable>
      </View>
      {pickError ? <Text style={styles.error}>{pickError}</Text> : null}
      {items.length === 0 ? (
        <Text style={styles.description}>
          Añade fotos de tus prendas. Puedes seguir añadiendo mientras se procesan las anteriores.
        </Text>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          {items.map((item) => (
            <UploadItem
              key={item.key}
              item={item}
              onRetryUpload={retryUpload}
              onDismiss={dismiss}
            />
          ))}
        </ScrollView>
      )}
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
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  button: {
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 10,
    backgroundColor: '#208AEF',
  },
  buttonText: { color: '#fff', fontWeight: '600' },
  error: { fontSize: 14, color: '#b42318' },
  list: { gap: 12 },
  description: {
    fontSize: 15,
    opacity: 0.7,
  },
});
