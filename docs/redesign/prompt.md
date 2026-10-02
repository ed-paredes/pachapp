Quiero rediseñar la UI de la app siguiendo el material de la carpeta `rediseno/`:

- `rediseno/maqueta.html`: maqueta navegable en HTML/CSS de todas las pantallas (Hoy, Armario, Añadir, Historial y Detalle). Es la **referencia visual**: léela entera, incluidos los estilos CSS y el JS (datos de ejemplo, layout del look).
- `rediseno/DISENO.md`: especificación del sistema de diseño, componentes, navegación, cada pantalla y cómo traducir cada técnica CSS a React Native.
- `rediseno/tokens.ts`: propuesta de tokens (colores, radios, espaciado, sombras, tipografía) y la función `tint()`.

## Contexto del proyecto
Expo SDK 57, React Native 0.86, React 19, react-native-web, TypeScript estricto, Expo Router (pestañas Hoy, Armario, Añadir, Historial, más Revisión, Detalle y Ajustes), TanStack Query, openapi-fetch, expo-image, StyleSheet con el tema propio "Probador" en `src/theme`, Fraunces y Manrope con @expo-google-fonts, Jest con React Native Testing Library, ESLint y Prettier.

## Reglas
1. **Antes de tocar nada**, explora `src/theme`, la carpeta de rutas, los componentes existentes y cómo se obtienen los datos. Luego dame un plan breve: qué archivos crearás o modificarás, qué dependencias faltan y qué datos de la maqueta **no** existen en el API.
2. **Solo cambia la presentación.** No modifiques la lógica de datos, los hooks de TanStack Query, el cliente del API ni los tipos generados. Si un elemento de la maqueta necesita datos que el API no da (tiempo, coste por uso, % de coincidencia, nombre de look…), no te los inventes: ocúltalo o déjalo preparado tras una prop opcional y apúntalo en una lista al final.
3. **Fusiona** `tokens.ts` con `src/theme`, respetando su estructura y sus nombres actuales. No crees un segundo tema paralelo. Mantén Manrope como fuente de texto (la maqueta usa Inter solo porque es web).
4. Componentes base reutilizables según DISENO.md §3, tipados y con `StyleSheet`. Sin librerías de UI ni Tailwind. Solo se permiten estas dependencias nuevas si faltan, instaladas con `npx expo install`: `expo-linear-gradient`, `expo-blur`, `react-native-reanimated`.
5. Las prendas se muestran con las **imágenes recortadas reales** (`expo-image`, `contentFit="contain"`) sobre `tint(colorDominante)`. Los SVG de la maqueta son solo de relleno.
6. Debe verse bien en **web y en móvil**: diseño a dos columnas a partir de 880px y cuadrícula del armario con columnas calculadas con `useWindowDimensions`.
7. Accesibilidad: `accessibilityRole` y `accessibilityLabel` en los botones de solo icono, zonas táctiles de al menos 44px y contraste legible.
8. Textos de la interfaz en español, como en la maqueta.

## Orden de trabajo (para y enséñame el resultado al terminar cada fase)
1. Tema + componentes base + `FloatingTabBar`.
2. Armario + Detalle.
3. Hoy.
4. Añadir (con el estado de procesamiento conectado al polling existente).
5. Historial, y después Revisión y Ajustes con el mismo sistema.

En cada fase: pasa `tsc`, ESLint y los tests, y actualiza los tests que se rompan por cambios de texto o estructura sin perder cobertura. Si puedes, arranca la versión web y compara con la maqueta.
