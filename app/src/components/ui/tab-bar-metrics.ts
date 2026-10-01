import { useSafeAreaInsets } from 'react-native-safe-area-context';

/** Floating tab bar: 44 dp controls inside 6 dp of padding. */
export const TAB_BAR_HEIGHT = 56;
/** Gap between the floating tab bar and the bottom edge (plus the safe-area inset). */
export const TAB_BAR_BOTTOM_GAP = 18;
/** Extra air between the end of the content and the bar. */
const CONTENT_GAP = 24;

/** Distance from the bottom of the window to the top of the floating tab bar. */
export function useTabBarTop(): number {
  const { bottom } = useSafeAreaInsets();
  return TAB_BAR_BOTTOM_GAP + bottom + TAB_BAR_HEIGHT;
}

/** Bottom padding that keeps scrolling content clear of the floating tab bar. */
export function useTabBarSpace(): number {
  return useTabBarTop() + CONTENT_GAP;
}
