import { fireEvent, render, screen } from '@testing-library/react-native';
import type { BottomTabBarProps } from 'expo-router/js-tabs';
import { Text } from 'react-native';

import { FloatingTabBar } from '@/components/ui/FloatingTabBar';

const ROUTES = [
  { key: 'index-1', name: 'index', title: 'Hoy' },
  { key: 'wardrobe-1', name: 'wardrobe', title: 'Armario' },
  { key: 'add-1', name: 'add', title: 'Añadir' },
  { key: 'history-1', name: 'history', title: 'Historial' },
];

function makeProps(index: number, preventDefault = false) {
  const emit = jest.fn(() => ({ defaultPrevented: preventDefault }));
  const navigate = jest.fn();
  const props = {
    state: { index, routes: ROUTES.map(({ key, name }) => ({ key, name })) },
    descriptors: Object.fromEntries(
      ROUTES.map(({ key, title }) => [
        key,
        { options: { title, tabBarIcon: () => <Text>{`icon-${title}`}</Text> } },
      ]),
    ),
    navigation: { emit, navigate },
    insets: { top: 0, bottom: 20, left: 0, right: 0 },
  } as unknown as BottomTabBarProps;
  return { props, emit, navigate };
}

describe('FloatingTabBar', () => {
  it('renders the four tabs in order with the default tab labels', async () => {
    await render(<FloatingTabBar {...makeProps(0).props} />);

    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.props.accessibilityLabel)).toEqual([
      'Hoy, tab, 1 of 4',
      'Armario, tab, 2 of 4',
      'Añadir, tab, 3 of 4',
      'Historial, tab, 4 of 4',
    ]);
  });

  it('marks only the focused tab as selected', async () => {
    await render(<FloatingTabBar {...makeProps(1).props} />);

    const selected = screen.getAllByRole('tab', { selected: true });
    expect(selected).toHaveLength(1);
    expect(selected[0].props.accessibilityLabel).toBe('Armario, tab, 2 of 4');
  });

  it('renders Añadir as an icon-only button: no visible label, still named for screen readers', async () => {
    await render(<FloatingTabBar {...makeProps(0).props} />);

    expect(screen.queryByText('Añadir')).toBeNull();
    expect(screen.getByRole('tab', { name: 'Añadir, tab, 3 of 4' })).toBeTruthy();
    expect(screen.getByText('icon-Añadir')).toBeTruthy();
  });

  it('navigates to a tab that is not focused after emitting tabPress', async () => {
    const { props, emit, navigate } = makeProps(0);
    await render(<FloatingTabBar {...props} />);

    await fireEvent.press(screen.getByRole('tab', { name: 'Historial, tab, 4 of 4' }));

    expect(emit).toHaveBeenCalledWith({
      type: 'tabPress',
      target: 'history-1',
      canPreventDefault: true,
    });
    expect(navigate).toHaveBeenCalledWith('history', undefined);
  });

  it('does not navigate when the tab is already focused', async () => {
    const { props, navigate } = makeProps(0);
    await render(<FloatingTabBar {...props} />);

    await fireEvent.press(screen.getByRole('tab', { name: 'Hoy, tab, 1 of 4' }));
    expect(navigate).not.toHaveBeenCalled();
  });

  it('does not navigate when a tabPress listener prevents the default', async () => {
    const { props, navigate } = makeProps(0, true);
    await render(<FloatingTabBar {...props} />);

    await fireEvent.press(screen.getByRole('tab', { name: 'Armario, tab, 2 of 4' }));
    expect(navigate).not.toHaveBeenCalled();
  });

  it('navigates from the Añadir button', async () => {
    const { props, navigate } = makeProps(0);
    await render(<FloatingTabBar {...props} />);

    await fireEvent.press(screen.getByRole('tab', { name: 'Añadir, tab, 3 of 4' }));
    expect(navigate).toHaveBeenCalledWith('add', undefined);
  });
});
