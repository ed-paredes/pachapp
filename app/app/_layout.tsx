import { QueryClientProvider } from '@tanstack/react-query';
import { useFonts } from 'expo-font';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';

import { queryClient } from '@/api-client/query-client';
import { ToastProvider } from '@/components/ui';
import { colors, fontAssets, fontFamilies, fontSizes } from '@/theme';

// Keep the splash up until the fonts are ready. Failing to do so only means a
// brief flash of the system font, so a rejection is ignored.
SplashScreen.preventAutoHideAsync().catch(() => undefined);

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts(fontAssets);
  const ready = fontsLoaded || fontError !== null;

  useEffect(() => {
    if (ready) SplashScreen.hideAsync().catch(() => undefined);
  }, [ready]);

  // A font error falls through to the system font rather than blocking the app.
  if (!ready) return null;

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
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
          <Stack.Screen name="review/[id]" options={{ title: 'Revisión' }} />
          {/* Detalle draws its own back button over the hero. */}
          <Stack.Screen name="garments/[id]" options={{ headerShown: false }} />
          <Stack.Screen name="favorites" options={{ title: 'Favoritos' }} />
          <Stack.Screen name="settings" options={{ title: 'Ajustes' }} />
        </Stack>
      </ToastProvider>
    </QueryClientProvider>
  );
}
