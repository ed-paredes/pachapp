import type { ReactNode } from 'react';
import {
  ScrollView,
  StyleSheet,
  View,
  type RefreshControlProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';

import { CONTENT_MAX_WIDTH, colors, spacing } from '@/theme';

import { useTabBarSpace } from './tab-bar-metrics';

type ScreenProps = {
  children: ReactNode;
  /** Scrolls the content (default). Pass `false` for screens that manage their own list. */
  scroll?: boolean;
  /** Pull-to-refresh control, forwarded to the scroll view. */
  refreshControl?: React.ReactElement<RefreshControlProps>;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/**
 * Page shell: linen background, 16 dp side margin, content centred up to 1120 dp, and enough
 * bottom padding that the floating tab bar never covers the last element.
 */
export function Screen({ children, scroll = true, refreshControl, style, testID }: ScreenProps) {
  const bottom = useTabBarSpace();
  const content = [styles.content, { paddingBottom: bottom }, style];

  if (!scroll) {
    return (
      <View style={styles.root} testID={testID}>
        <View style={content}>{children}</View>
      </View>
    );
  }
  return (
    <ScrollView
      style={styles.root}
      contentContainerStyle={content}
      refreshControl={refreshControl}
      keyboardShouldPersistTaps="handled"
      testID={testID}
    >
      {children}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: {
    width: '100%',
    maxWidth: CONTENT_MAX_WIDTH,
    alignSelf: 'center',
    paddingHorizontal: spacing.screen,
    paddingTop: spacing.sm,
  },
});
