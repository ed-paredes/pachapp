import type { ReactNode } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';

import { CONTENT_MAX_WIDTH } from '@/theme';

type ContentContainerProps = {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
};

/** Style that centres a block and caps its width; for scroll content containers. */
export const centeredContentStyle: ViewStyle = {
  width: '100%',
  maxWidth: CONTENT_MAX_WIDTH,
  alignSelf: 'center',
};

/** Centres content and caps its width on large screens; full width on phones. */
export function ContentContainer({ children, style }: ContentContainerProps) {
  return <View style={[styles.container, style]}>{children}</View>;
}

const styles = StyleSheet.create({ container: centeredContentStyle });
