import { Tabs } from 'expo-router';

import { IconSymbol } from '@/components/IconSymbol';
import { AppHeader, FloatingTabBar } from '@/components/ui';
import { colors } from '@/theme';

/**
 * Bottom tabs (UI-REQ-002): exactly Hoy, Armario, Añadir, Historial, reused
 * as-is on web per UI-REQ-003. Revisión, Detalle de prenda, Favoritos and
 * Ajustes are stack screens reached from here or from within a tab.
 */
export default function TabsLayout() {
  return (
    <Tabs
      // To hide a tab, give its screen `href: null`; FloatingTabBar ignores `tabBarButton`.
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{
        header: () => <AppHeader />,
        // Every scene is built on `Screen`, which pads itself for the floating bar.
        sceneStyle: { backgroundColor: colors.bg },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Hoy',
          tabBarIcon: ({ color, size }) => (
            <IconSymbol
              name={{ ios: 'house.fill', android: 'home', web: 'home' }}
              size={size}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="wardrobe"
        options={{
          title: 'Armario',
          tabBarIcon: ({ color, size }) => (
            <IconSymbol
              name={{ ios: 'tshirt.fill', android: 'checkroom', web: 'checkroom' }}
              size={size}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="add"
        options={{
          title: 'Añadir',
          tabBarIcon: ({ color, size }) => (
            <IconSymbol
              name={{ ios: 'plus', android: 'add', web: 'add' }}
              size={size}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: 'Historial',
          tabBarIcon: ({ color, size }) => (
            <IconSymbol
              name={{ ios: 'clock.arrow.circlepath', android: 'history', web: 'history' }}
              size={size}
              color={color}
            />
          ),
        }}
      />
    </Tabs>
  );
}
