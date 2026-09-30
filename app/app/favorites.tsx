import { StyleSheet, View } from 'react-native';

import { EmptyState } from '@/components/EmptyState';
import { centeredContentStyle } from '@/components/ContentContainer';

/**
 * Favoritos (Favorites): saved outfits, reusable with one tap. Needs
 * `GET /outfits?favorite=true` or similar (out of scope here, no endpoints
 * beyond `/health` are wired up yet). 07 doesn't specify this screen's empty
 * copy, so this uses a neutral placeholder consistent with Historial's tone.
 */
export default function FavoritesScreen() {
  return (
    <View style={[styles.container, centeredContentStyle]}>
      <EmptyState
        title="Aún no tienes outfits favoritos"
        description="Marca un outfit como favorito desde Hoy para verlo aquí."
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
});
