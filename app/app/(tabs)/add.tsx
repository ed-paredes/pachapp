import { useState } from 'react';
import { StyleSheet, Text, View, useWindowDimensions } from 'react-native';

import { AddSteps } from '@/components/add/AddSteps';
import { CaptureTipsPanel } from '@/components/add/CaptureTipsPanel';
import { UploadZone } from '@/components/add/UploadZone';
import { UploadItem } from '@/components/UploadItem';
import { Button, Eyebrow, Screen, Title } from '@/components/ui';
import { useCaptureTipsSeen } from '@/hooks/useCaptureTipsSeen';
import { useUploadQueue } from '@/hooks/useUploadQueue';
import { pickFromCamera, pickFromGallery, type PickResult } from '@/lib/photos';
import { TWO_COLUMNS, colors, fontFamilies, spacing } from '@/theme';

const HELP = {
  ios: 'questionmark.circle',
  android: 'help',
  web: 'help',
} as const;

/**
 * Añadir (Add): photo capture + upload/processing progress. Each photo gets
 * its own polled progress item (UI-REQ-006/017/018); when a job is done the
 * item invites to "Revisar" (UI-REQ-019) without navigating on its own, so
 * several photos can be chained. Also hosts the capture-tips card
 * (UI-REQ-020 / UI-SCN-007) — expanded automatically the first time,
 * dismissible, and re-openable via the help icon.
 */
export default function AddScreen() {
  const { width } = useWindowDimensions();
  const wide = width >= TWO_COLUMNS;
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

  const tips = <CaptureTipsPanel visible={tipsVisible} onDismiss={closeTips} />;
  const zone = (
    <UploadZone
      onCamera={() => pick(pickFromCamera)}
      onGallery={() => pick(pickFromGallery)}
      error={pickError}
    />
  );
  const list = items.length ? (
    <View style={styles.list} testID="upload-list">
      {items.map((item) => (
        <UploadItem key={item.key} item={item} onRetryUpload={retryUpload} onDismiss={dismiss} />
      ))}
    </View>
  ) : null;

  return (
    <Screen>
      <View style={styles.header}>
        <View style={styles.headerText}>
          <Eyebrow>Nueva prenda</Eyebrow>
          <Title accent="armario">Añade a tu armario</Title>
          <Text style={styles.subtitle}>
            Una prenda por foto: la recortamos y detectamos su categoría y sus colores.
          </Text>
        </View>
        <Button
          icon={HELP}
          variant="secondary"
          accessibilityLabel="Ver consejos de captura"
          onPress={openTips}
        />
      </View>
      {wide ? (
        <View style={styles.columns}>
          <View style={styles.main}>
            {zone}
            {list}
          </View>
          <View style={styles.side}>
            <AddSteps />
            {tips}
          </View>
        </View>
      ) : (
        <View style={styles.stack}>
          {tipsVisible ? tips : null}
          {zone}
          {list}
          <AddSteps />
          {tipsVisible ? null : tips}
        </View>
      )}
    </Screen>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  headerText: { flex: 1, gap: 6 },
  subtitle: {
    fontFamily: fontFamilies.body,
    fontSize: 15,
    lineHeight: 22,
    color: colors.ink2,
    maxWidth: 520,
  },
  stack: { gap: spacing.xl, marginTop: spacing.xl },
  columns: {
    flexDirection: 'row',
    gap: spacing.xl,
    marginTop: spacing.xl,
    alignItems: 'flex-start',
  },
  main: { flex: 1.2, gap: spacing.xl },
  side: { flex: 1, gap: spacing.md },
  list: { gap: spacing.md },
});
