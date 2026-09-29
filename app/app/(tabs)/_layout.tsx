import { Link, Tabs } from 'expo-router';
import { Pressable } from 'react-native';

import { IconSymbol } from '@/components/IconSymbol';

/**
 * Header icon that opens Ajustes (UI-REQ-002: "Ajustes desde un icono de
 * cabecera"). 07 doesn't say which tab carries it, so it's placed on every
 * tab's header for consistent access from anywhere in the bottom tabs.
 */
function SettingsHeaderButton() {
  return (
    <Link href="/settings" asChild>
      <Pressable accessibilityRole="button" accessibilityLabel="Abrir ajustes" hitSlop={8}>
        <IconSymbol
          name={{ ios: 'gearshape.fill', android: 'settings', web: 'settings' }}
          size={22}
        />
      </Pressable>
    </Link>
  );
}

/**
 * Bottom tabs (UI-REQ-002): exactly Hoy, Armario, Añadir, Historial, reused
 * as-is on web per UI-REQ-003. Revisión, Detalle de prenda, Favoritos and
 * Ajustes are stack screens reached from here or from within a tab.
 */
export default function TabsLayout() {
  return (
    <Tabs screenOptions={{ headerRight: () => <SettingsHeaderButton /> }}>
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
              name={{ ios: 'plus.circle.fill', android: 'add_circle', web: 'add_circle' }}
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
