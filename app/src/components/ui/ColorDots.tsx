import { StyleSheet, View } from 'react-native';

import { colors } from '@/theme';

type ColorDotsProps = {
  /** Hex colours, dominant first. */
  colors: string[];
  /** Colour of the ring that separates overlapping dots; match the surface behind them. */
  ringColor?: string;
};

/** Row of overlapping 14 dp colour dots. */
export function ColorDots({ colors: dots, ringColor = colors.surface }: ColorDotsProps) {
  return (
    <View style={styles.row}>
      {dots.map((color, index) => (
        <View
          key={`${color}-${index}`}
          style={[
            styles.dot,
            { backgroundColor: color, borderColor: ringColor },
            index > 0 && styles.overlap,
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 14, height: 14, borderRadius: 7, borderWidth: 2 },
  overlap: { marginLeft: -4 },
});
