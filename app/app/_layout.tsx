import { useIsRestoring } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';

import { queryClient } from '@/api-client/query-client';
import { ToastProvider, WebFocusRing } from '@/components/ui';
import { OfflineProvider } from '@/offline/OfflineProvider';
import { colors, fontAssets, fontFamilies, fontSizes } from '@/theme';

// Keep the splash up until the fonts are ready. Failing to do so only means a
// brief flash of the system font, so a rejection is ignored.
SplashScreen.preventAutoHideAsync().catch(() => undefined);

export default function RootLayout() {
  return (
    <OfflineProvider client={queryClient}>
      <AppShell />
    </OfflineProvider>
  );
}

function AppShell() {
  const [fontsLoaded, fontError] = useFonts(fontAssets);
  // On native the saved cache is read before the first screen, so screens never flash an empty state.
  const restoring = useIsRestoring();
  const ready = (fontsLoaded || fontError !== null) && !restoring;

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => undefined);
  }, [ready]);

  // A font error falls through to the system font rather than blocking the app.
  if (!ready) return null;

  return (
    <ToastProvider>
      <WebFocusRing />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.plinth },
          headerShadowVisible: false,
          headerTintColor: colors.olive,
          headerTitleStyle: {
            fontFamily: fontFamilies.display,
            fontSize: fontSizes.title,
            color: colors.charcoal,
          },
          contentStyle: { backgroundColor: colors.stone },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        {/* Revisión draws its own back button, like Detalle. */}
        <Stack.Screen name="review/[id]" options={{ headerShown: false }} />
        {/* Detalle draws its own back button over the hero. */}
        <Stack.Screen name="garments/[id]" options={{ headerShown: false }} />
        <Stack.Screen name="favorites" options={{ title: 'Favoritos' }} />
        {/* Ajustes draws its own back button and title, like Revisión. */}
        <Stack.Screen name="settings" options={{ headerShown: false }} />
      </Stack>
    </ToastProvider>
  );
}
