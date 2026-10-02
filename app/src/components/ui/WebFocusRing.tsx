import { useEffect } from 'react';
import { Platform } from 'react-native';

import { colors } from '@/theme';

const STYLE_ID = 'pachapp-focus-ring';

/**
 * Keyboard focus ring for the web build. The browser default is a thin dark outline that vanishes
 * on ink buttons and the dark tab bar; this one is a 3 px terracotta ring (4.4:1 on the linen
 * background, over the 3:1 WCAG 1.4.11 asks for) kept off the element with an offset. It only
 * shows for keyboard focus (`:focus-visible`), never after a mouse or touch press.
 */
export const focusRingCss = `a:focus-visible,button:focus-visible,input:focus-visible,textarea:focus-visible,[tabindex]:focus-visible,[role="button"]:focus-visible,[role="tab"]:focus-visible,[role="link"]:focus-visible,[role="checkbox"]:focus-visible{outline:3px solid ${colors.accent};outline-offset:2px;}`;

/** Mount once near the root. Renders nothing; native platforms ignore it. */
export function WebFocusRing() {
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = focusRingCss;
    document.head.appendChild(style);
  }, []);
  return null;
}
