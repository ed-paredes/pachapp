import { StyleSheet, Text, View } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';
import { Button } from '@/components/ui';
import { colors, fontFamilies, radii, spacing } from '@/theme';

type CaptureTipsPanelProps = {
  /** Expanded with every tip and a dismiss button; otherwise the compact "Consejo" card. */
  visible: boolean;
  onDismiss: () => void;
};

const TIPS = [
  'Fotografía una sola prenda por foto.',
  'Extiéndela sobre un fondo liso o cuélgala en una percha.',
  'Usa luz natural siempre que puedas.',
];

const BULB = { ios: 'lightbulb', android: 'lightbulb', web: 'lightbulb' } as const;

/**
 * "Consejo" card of Añadir (UI-REQ-020 / UI-SCN-007). It opens expanded the first time the
 * screen is shown and stays dismissible; afterwards it rests as a one-line tip and the help
 * button in the header expands it again. "Seen" persistence lives in the caller via
 * `useCaptureTipsSeen`.
 */
export function CaptureTipsPanel({ visible, onDismiss }: CaptureTipsPanelProps) {
  if (!visible) {
    return (
      <View style={styles.card} testID="capture-tip-card">
        <View style={styles.mark}>
          <IconSymbol name={BULB} size={18} color={colors.accentText} />
        </View>
        <View style={styles.copy}>
          <Text style={styles.heading}>Consejo</Text>
          <Text style={styles.text}>
            Con fondo liso y la prenda extendida, el recorte sale mejor.
          </Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.card, styles.expanded]} testID="capture-tips-panel">
      <View style={styles.row}>
        <View style={styles.mark}>
          <IconSymbol name={BULB} size={18} color={colors.accentText} />
        </View>
        <View style={styles.copy}>
          <Text style={styles.heading} accessibilityRole="header">
            Consejos para fotografiar tus prendas
          </Text>
          {TIPS.map((tip) => (
            <Text key={tip} style={styles.tip}>
              {`•  ${tip}`}
            </Text>
          ))}
        </View>
      </View>
      <View style={styles.footer}>
        <Button
          label="Entendido"
          accessibilityLabel="Entendido, cerrar consejos"
          onPress={onDismiss}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: spacing.lg,
    borderRadius: radii.md,
    backgroundColor: colors.accentSoft,
  },
  expanded: { flexDirection: 'column', alignItems: 'stretch', gap: spacing.md },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 14 },
  mark: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  heading: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 14.5,
    lineHeight: 20,
    color: colors.ink,
  },
  text: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
  tip: { fontFamily: fontFamilies.body, fontSize: 14, lineHeight: 20, color: colors.ink },
  footer: { alignItems: 'flex-end' },
});
