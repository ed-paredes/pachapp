import { SymbolView, type SymbolViewProps } from 'expo-symbols';
import type { ColorValue } from 'react-native';

type IconSymbolProps = {
  name: SymbolViewProps['name'];
  size?: number;
  color?: ColorValue;
};

/**
 * Thin wrapper around `expo-symbols`, already an Expo-managed dependency of
 * this project, chosen over adding a separate icon package: `SymbolView`
 * renders native SF Symbols on iOS and falls back to the equivalent Material
 * Symbols font on Android and web from the same `name` prop (`{ ios, android,
 * web }`), so one component covers every platform this app targets.
 */
export function IconSymbol({ name, size = 24, color }: IconSymbolProps) {
  return (
    <SymbolView name={name} size={size} tintColor={color} style={{ width: size, height: size }} />
  );
}
