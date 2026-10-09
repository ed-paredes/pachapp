import type { ReactNode, Ref } from 'react';
import {
  ScrollView,
  StyleSheet,
  View,
  type RefreshControlProps,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CONTENT_MAX_WIDTH, colors, spacing } from '@/theme';

import { useTabBarSpace } from './tab-bar-metrics';

type ScreenProps = {
  children: ReactNode;
  /** Scrolls the content (default). Pass `false` for screens that manage their own list. */
  scroll?: boolean;
  /** Pull-to-refresh control, forwarded to the scroll view. */
  refreshControl?: React.ReactElement<RefreshControlProps>;
  /**
   * For stack screens with no native header and no floating tab bar (Ajustes): pads the top and
   * bottom by the safe-area insets instead of reserving room for the bar.
   */
  standalone?: boolean;
  /** Ref of the scroll view, for screens that scroll to a section themselves. */
  scrollRef?: Ref<ScrollView>;
  style?: StyleProp<ViewStyle>;
  testID?: string;
};

/**
 * Page shell: linen background, 16 dp side margin, content centred up to 1120 dp, and enough
 * bottom padding that the floating tab bar never covers the last element.
 */
export function Screen({
  children,
  scroll = true,
  refreshControl,
  standalone = false,
  scrollRef,
  style,
  testID,
}: ScreenProps) {
  const tabBarSpace = useTabBarSpace();
  const insets = useSafeAreaInsets();
  const content = [
    styles.content,
    standalone
      ? { paddingTop: insets.top + spacing.md, paddingBottom: insets.bottom + spacing.xxl }
      : { paddingBottom: tabBarSpace },
    style,
  ];

  if (!scroll) {
    return (
      <View style={styles.root} testID={testID}>
        <View style={content}>{children}</View>
      </View>
    );
  }
  return (
    <ScrollView
      ref={scrollRef}
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
