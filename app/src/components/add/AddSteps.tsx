import { StyleSheet, Text, View } from 'react-native';

import { Card } from '@/components/ui';
import { colors, fontFamilies, spacing } from '@/theme';

const STEPS = [
  {
    title: 'Sube una foto',
    text: 'Una sola prenda, extendida sobre una superficie lisa. Con buena luz.',
  },
  { title: 'Recortamos la prenda', text: 'Quitamos el fondo automáticamente.' },
  { title: 'Detectamos categoría y colores', text: 'Tú solo confirmas o corriges.' },
];

/** The three real stages a photo goes through, so numbering is honest here. */
export function AddSteps() {
  return (
    <View style={styles.list} accessibilityRole="list">
      {STEPS.map((step, index) => (
        <Card key={step.title} style={styles.step}>
          <View style={styles.number}>
            <Text style={styles.numberText}>{index + 1}</Text>
          </View>
          <View style={styles.copy}>
            <Text style={styles.title}>{step.title}</Text>
            <Text style={styles.text}>{step.text}</Text>
          </View>
        </Card>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 10 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: spacing.lg },
  number: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.surface2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  numberText: { fontFamily: fontFamilies.displayRegular, fontSize: 17, color: colors.ink },
  copy: { flex: 1, gap: 2 },
  title: {
    fontFamily: fontFamilies.bodySemiBold,
    fontSize: 14.5,
    lineHeight: 20,
    color: colors.ink,
  },
  text: { fontFamily: fontFamilies.body, fontSize: 13, lineHeight: 18, color: colors.ink2 },
});
