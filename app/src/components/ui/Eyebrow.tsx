import { Text, type StyleProp, type TextStyle } from 'react-native';

import { colors, textStyles } from '@/theme';

type EyebrowProps = { children: string; style?: StyleProp<TextStyle> };

/** Small uppercase line above a title or a card heading. */
export function Eyebrow({ children, style }: EyebrowProps) {
  return <Text style={[textStyles.eyebrow, { color: colors.ink2 }, style]}>{children}</Text>;
}
