import { focusRingCss } from '@/components/ui/WebFocusRing';
import { colors } from '@/theme';

describe('focusRingCss', () => {
  it('rings keyboard focus only, with the accent colour, on every interactive role', () => {
    expect(focusRingCss).toContain(`outline:3px solid ${colors.accent}`);
    expect(focusRingCss).not.toMatch(/(^|,)[^,]*:focus[,{]/);
    for (const role of ['button', 'tab', 'link', 'checkbox']) {
      expect(focusRingCss).toContain(`[role="${role}"]:focus-visible`);
    }
  });
});
