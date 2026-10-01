# Especificación de diseño — Armario

Referencia visual: `maqueta.html` (abrir en el navegador; es navegable). Tokens: `tokens.ts`.
La maqueta es HTML/CSS; esta guía dice cómo traducir cada pieza a React Native + Expo.

## 1. Principios

- **Boutique, no formulario.** Fondo lino cálido, tarjetas blancas, mucho aire, radios grandes, sombras suaves.
- **Contraste tipográfico.** Fraunces (serif) para títulos, números y nombres de looks; Manrope para todo lo demás.
- **La prenda es la protagonista.** Recorte PNG transparente sobre un fondo teñido con su propio color (`tint()`).
- **Una acción principal por pantalla** (botón negro en píldora). Lo secundario, en botones claros o con icono. Lo destructivo, como enlace rojo discreto.
- **Nunca "Sin definir".** Un campo vacío se muestra como chip de borde discontinuo `+ Añadir`.
- **La IA se explica.** El look del día dice *por qué* (colores, clima, uso). Las detecciones muestran su confianza.

## 2. Traducción CSS → React Native

| Maqueta | RN / Expo |
|---|---|
| Variables `:root` | `src/theme` (fusionar con `tokens.ts`) |
| `box-shadow` | prop de estilo `boxShadow` (RN ≥ 0.76) |
| Sombra con forma de prenda | iOS: `shadow*` en un contenedor **sin** `backgroundColor` alrededor del `Image`. Web: `filter: 'drop-shadow(...)'`. Android: aceptar sin sombra o sombra suave en la tarjeta |
| `radial-gradient` / `linear-gradient` | `expo-linear-gradient` (instalar con `npx expo install` si falta) |
| `backdrop-filter: blur` | `BlurView` de `expo-blur`, con fallback a `rgba(255,255,255,0.8)` |
| `color-mix()` | `tint(hex)` de `tokens.ts` |
| CSS grid `auto-fill` | `FlatList` con `numColumns` calculado con `useWindowDimensions` (≈ ancho / 190, mín. 2) y `key` dependiente de `numColumns` |
| Chips con scroll horizontal | `ScrollView horizontal showsHorizontalScrollIndicator={false}` |
| `:hover` | `Pressable` → `({ hovered, pressed })`. En web, leve `translateY(-2..-4)`; en táctil, `scale(0.98)` al pulsar |
| Animaciones (`@keyframes`) | `react-native-reanimated` (entrada de pantalla, barra de progreso, línea de escaneo) |
| `position: sticky` | Solo en web (`Platform.OS === 'web'`); en nativo, nada |
| Iconos SVG inline | `@expo/vector-icons` (Feather) |
| Prendas dibujadas en SVG | **Las imágenes reales** con `expo-image`, `contentFit="contain"` |

## 3. Componentes base (crear en `src/components/ui/` o donde encaje con el proyecto)

| Componente | Descripción |
|---|---|
| `Screen` | Fondo `bg`, padding lateral 16, ancho máx. 1120 centrado, `paddingBottom` para no tapar el nav flotante |
| `Eyebrow` | Texto 12px, mayúsculas, tracking 1.4, `ink2` |
| `Title` | Fraunces 34–44px; admite una palabra en *cursiva* color `accent` |
| `Button` | Variantes `primary` (fondo `ink`, texto blanco), `secondary` (blanco + sombra), `accent` (terracota); píldora, padding 15×22, icono opcional |
| `Card` | Blanca, `radius.md`, `shadow.card` |
| `Pill` | Estado: `ok` (En el armario/Nueva), `info` (Lavando), `warn` (Revisar), `ghost` (Archivada). Opción con punto de color delante |
| `FilterChip` | Píldora con borde `line`; activa = fondo `ink` y texto blanco; contador en `ink3` |
| `Segmented` | Fondo `surface2`, opción activa blanca con sombra mínima |
| `ColorSwatch` | Círculo 22px + nombre, dentro de píldora con borde |
| `ColorDots` | Puntos de 14px solapados con borde del color de fondo |
| `FormalityMeter` | 5 segmentos 26×6, rellenos en `ink`, + etiqueta (Muy informal … Formal) |
| `SeasonPicker` | 4 cuadrados de 38px con icono; activo con fondo `accentSoft`, inactivo con opacidad 0,45 |
| `AddChip` | Borde discontinuo 1,5px `line`, texto `ink3`: “+ Añadir” |
| `GarmentImage` | Fondo `tint(color)` + `expo-image` recortada + sombra |
| `GarmentCard` | `GarmentImage` (ratio 4:5, `radius.md`), Pill de estado arriba a la izquierda, nombre, “Puesta N veces” / “Sin estrenar”, `ColorDots` |
| `StatRow` | 3 columnas con separadores; número en Fraunces 28 |
| `Banner` | Aviso con icono, texto y botón (p. ej. pendientes de revisión, fondo `warnSoft`) |
| `Toast` | Píldora oscura que aparece encima del nav durante unos 2 s |
| `FloatingTabBar` | Ver §4 |

## 4. Navegación — `FloatingTabBar`

- Se pasa con la prop `tabBar` de `<Tabs>` en Expo Router. Ocultar la cabecera y la barra por defecto.
- Píldora flotante centrada, a 18px del borde inferior (+ `safeAreaInsets.bottom`); fondo `rgba(31,27,22,0.92)` con blur; padding 6; `shadow.raised`.
- Orden: **Hoy · Armario · [Añadir] · Historial**.
- Pestaña inactiva: solo icono, color `#CFC6BA`. Activa: fondo `bg`, texto `ink`, **icono + etiqueta** (animar el ancho).
- **Añadir**: círculo de 44px color `accent`, icono `+` blanco, sin etiqueta.
- Revisión, Detalle y Ajustes no aparecen en la barra.
- Cabecera de las pestañas: logo “Armario” en Fraunces 600 + un punto `accent` en cursiva; a la derecha, Ajustes y avatar.

## 5. Pantallas

### Hoy
1. Eyebrow con la fecha (“Jueves, 1 de octubre”) + título “Buenos días. Hoy te *proponemos*…”.
2. Píldora con el tiempo (si el backend no lo tiene, omitirla o dejarla preparada).
3. **Look del día** (2 columnas en ≥ 880px):
   - Izquierda: lienzo grande (`radius.lg`, degradado lino) con las prendas del outfit superpuestas (capa arriba a la izquierda, top en el centro, pantalón abajo a la derecha, calzado abajo a la izquierda) y una ligera rotación. Pill de formalidad + badge de coincidencia si existe.
   - Derecha (Card): eyebrow “Look del día”, nombre del look en Fraunces 28, lista “por qué” (icono en cuadrado `surface2` + **negrita** + explicación), miniaturas de las prendas (que abren Detalle), botones **Me lo pongo** (primary) y **Otra sugerencia** (secondary, solo icono).
4. “Otras opciones para hoy”: scroll horizontal de tarjetas con fondo teñido.
5. Dos tarjetas de aviso: prendas lavando y % del armario usado (lleva a Historial).

### Armario
1. Eyebrow “N prendas · M activas” + título “Tu armario” + buscador (píldora con icono de lupa).
2. Fila de `FilterChip` de categorías **con contador** (scroll horizontal).
3. `Segmented` de estados: Activas / Lavando / Archivadas / Todas (con contador).
4. “Pendientes de revisión” **deja de ser un filtro**: pasa a ser un `Banner` warn (“3 prendas pendientes de revisión…” + **Revisar**) que lleva a la ruta Revisión. Ocultarlo si hay 0.
5. Cuadrícula de `GarmentCard`; la última tarjeta es “+ Añadir prenda” con borde discontinuo (salvo en Archivadas).
6. Estado vacío: “Nada por aquí” en Fraunces + texto de ayuda.

### Añadir
1. Eyebrow “Nueva prenda” + “Añade a tu *armario*” + subtítulo.
2. Zona de subida (`radius.lg`, borde discontinuo): icono de cámara en un cuadrado `accentSoft`, botones **Hacer foto** (primary) y **Galería** (secondary), conectados a `expo-image-picker`.
3. Los 3 pasos (Sube, Recortamos, Detectamos) + una tarjeta de consejo.
4. **Procesamiento** (con el polling de TanStack Query ya existente): barra de progreso en degradado terracota, “Hemos encontrado N prendas”, tarjeta por prenda con recorte, categoría y confianza en `ok`; si aún está analizando, una línea de escaneo animada. Acciones **Descartar** / **Añadir N prendas**.

### Historial
1. KPIs (2 columnas en móvil, 4 en escritorio): looks del mes, % del armario usado, coste por uso, prendas olvidadas; con una tendencia pequeña debajo. **Mostrar solo los que el API pueda calcular.**
2. Calendario mensual: celdas cuadradas, `radius.sm`; los días con outfit llevan fondo teñido y la prenda principal asomando en la esquina; hoy con borde `accent`.
3. Dos listas: “Las que más usas” (con barra de uso) y “Dales otra oportunidad” (con botón **Sugerir**).

### Detalle de prenda
1. Hero 4:5 (`radius.lg`) con un degradado basado en `tint(color)`, la prenda grande con sombra, botones circulares translúcidos (volver, favorita) y badge “Recortada y analizada automáticamente”.
2. Eyebrow con la categoría, título con el nombre (si no hay nombre, generar “Categoría + color + material”), Pills de estado.
3. `StatRow`: veces puesta / última vez / outfits.
4. Botón primary “Crear outfit con esta prenda”.
5. Card “Atributos” con “Editar”: Colores (`ColorSwatch`), Estilo (chips), Formalidad (`FormalityMeter`), Temporada (`SeasonPicker`), Estampado, Material, Abrigo, Marca, Notas. Vacíos = `AddChip`.
6. Fila de 3 acciones con icono: Revisar / A lavar / Archivar. Debajo, “Eliminar prenda” como enlace rojo (con confirmación).
7. En ≥ 880px: dos columnas, hero a la izquierda.

### Revisión y Ajustes
Sin maqueta: aplicar el mismo sistema (Screen, Title, Card, Button, chips) de forma coherente.
