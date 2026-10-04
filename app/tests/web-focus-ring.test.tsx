import { render } from '@testing-library/react-native';
import { Platform } from 'react-native';

import { WebFocusRing, focusRingCss } from '@/components/ui/WebFocusRing';
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

/** The Jest environment has no DOM: a tiny `document` that records the <style> tags appended. */
type FakeStyle = { id: string; textContent: string };

function installFakeDocument() {
  const styles: FakeStyle[] = [];
  Object.defineProperty(globalThis, 'document', {
    configurable: true,
    value: {
      getElementById: (id: string) => styles.find((style) => style.id === id) ?? null,
      createElement: () => ({ id: '', textContent: '' }),
      head: { appendChild: (style: FakeStyle) => styles.push(style) },
    },
  });
  return styles;
}

describe('WebFocusRing', () => {
  const originalOS = Platform.OS;

  afterEach(() => {
    Object.defineProperty(Platform, 'OS', { value: originalOS, configurable: true });
    Reflect.deleteProperty(globalThis, 'document');
  });

  it('injects the focus-ring stylesheet once on web, however many times it mounts', async () => {
    Object.defineProperty(Platform, 'OS', { value: 'web', configurable: true });
    const styles = installFakeDocument();

    await render(<WebFocusRing />);
    expect(styles).toHaveLength(1);
    expect(styles[0].id).toBe('pachapp-focus-ring');
    expect(styles[0].textContent).toBe(focusRingCss);

    await render(<WebFocusRing />);
    expect(styles).toHaveLength(1);
  });

  it('renders nothing and leaves the document alone on native platforms', async () => {
    Object.defineProperty(Platform, 'OS', { value: 'ios', configurable: true });
    const styles = installFakeDocument();

    const view = await render(<WebFocusRing />);
    expect(view.toJSON()).toBeNull();
    expect(styles).toHaveLength(0);
  });
});
