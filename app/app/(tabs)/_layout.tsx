import { Tabs } from 'expo-router';

import { IconSymbol } from '@/components/IconSymbol';
import { AppHeader, FloatingTabBar, useTabBarSpace } from '@/components/ui';
import { colors } from '@/theme';

/**
 * Bottom tabs (UI-REQ-002): exactly Hoy, Armario, Añadir, Historial, reused
 * as-is on web per UI-REQ-003. Revisión, Detalle de prenda, Favoritos and
 * Ajustes are stack screens reached from here or from within a tab.
 */
export default function TabsLayout() {
  const legacyInset = useTabBarSpace();
  return (
    <Tabs
      tabBar={(props) => <FloatingTabBar {...props} />}
      screenOptions={{
        header: () => <AppHeader />,
        // The bar floats over the scenes, so they need room below their content. Screens built on
        // `Screen` pad themselves; this inset covers the ones that are not migrated yet (P2-P5
        // remove it as they move to `Screen`).
        sceneStyle: { backgroundColor: colors.bg, paddingBottom: legacyInset },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Hoy',
          // Hoy is built on `Screen`, which pads itself for the floating bar.
          sceneStyle: { backgroundColor: colors.bg },
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
          // Armario is built on `Screen`, which pads itself for the floating bar.
          sceneStyle: { backgroundColor: colors.bg },
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
