# 07 — App y UI

Estado: Draft

## Alcance

Pantallas de la iteración 1 (Hoy, Armario, Añadir, Revisión, Detalle de prenda, Favoritos, Historial, Ajustes sin exportación), navegación, estados (cargando/vacío/error/procesando), cómo se renderizan los outfits con capas, diferencias web vs nativo, uso del cliente de API vía TanStack Query, polling de jobs.

## Fuera de alcance

Login/sesión (aplazado), exportación de datos (aplazada, ver Conflictos), try-on/v2, offline/caché (aplazado).

## Dependencias

- Decisiones: D0 (Expo local, sin build propia), D12 (try-on = v2), D13/D15 (la app llega a la API por LAN/CORS), D19 (botón "Revisión terminada" en la pantalla de Revisión, UI-REQ-021).
- Endpoints: 03-garment-ingestion.md (subida y `job`), 04-wardrobe-api.md (CRUD de prendas y settings), 05-outfit-engine.md (`generate`), 06-feedback-history.md (feedback, favoritos, historial).

## Pantallas de la iteración 1

| Pantalla (ES) | Identificador | Propósito |
| --- | --- | --- |
| Hoy | `Today` | Pantalla de inicio; muestra la propuesta de outfit actual con feedback. |
| Armario | `Wardrobe` | Cuadrícula de prendas, filtros, insignia de pendientes de revisión. |
| Añadir | `Add` | Captura de fotos, progreso de subida/procesado. |
| Revisión | `Review` | Foto recortada + chips editables por atributo + botón "Revisión terminada" (D19). |
| Detalle de prenda | `GarmentDetail` | Atributos, uso, outfits en los que aparece, cambio de estado. |
| Favoritos | `Favorites` | Outfits guardados, reutilizables con un toque. |
| Historial | `History` | Calendario + estadísticas simples. |
| Ajustes | `Settings` | Pesos del motor, días de no repetir, N de complementos — **sin** exportación (ver Conflictos). |

**UI-REQ-001.** No hay pantalla de login/sesión en la iteración 1 — la app se conecta directamente a `EXPO_PUBLIC_API_BASE_URL` sin ningún paso de autenticación (D11/aplazado).

## Navegación

**UI-REQ-002.** En móvil, la navegación inferior (bottom tabs) DEBE contener exactamente 4 destinos: Hoy, Armario, Añadir, Historial (coincide con el borrador). Revisión, Detalle de prenda, Favoritos y Ajustes se alcanzan mediante navegación en pila (stack) desde estas u otras pantallas (p. ej. Favoritos desde un enlace en Hoy/Historial, Ajustes desde un icono de cabecera).

**UI-REQ-003.** En web, la misma estructura de Expo Router (tabs) se reutiliza sin una navegación separada específica de web. *(valor por defecto, ajustable — ver Preguntas abiertas sobre topbar/sidebar en anchos grandes.)*

## Estados: cargando / vacío / error / procesando

**UI-REQ-004.** Armario: estado de carga con skeleton de cuadrícula; estado vacío con copy en español invitando a "Añadir" la primera prenda; insignia visible en las miniaturas de prendas con `needs_review = true`.

**UI-REQ-005.** Hoy: spinner mientras `POST /outfits/generate` está en curso; estado de error con botón de reintento si la generación falla; estado vacío ("Aún no tienes suficientes prendas para generar un outfit") cuando `proposals` vuelve vacío (ENG-REQ-022).

**UI-REQ-006.** Añadir: cada foto en curso de subida/procesado muestra su propia barra de progreso independiente, derivada del polling de `GET /jobs/{id}` (`job.progress`/`job.step`); el usuario puede encadenar varias fotos seguidas sin esperar a que termine el procesado de la anterior.

**UI-REQ-007.** Historial: estado vacío ("Todavía no has registrado ningún outfit") cuando no hay filas de `wear_log` en el mes consultado.

**UI-REQ-008.** Cualquier pantalla que dependa de una petición de red DEBE tener un estado de error explícito con acción de reintento — no solo un spinner infinito o una pantalla en blanco.

## Renderizado de outfits con capas

**UI-REQ-009.** La tarjeta de outfit en Hoy DEBE apilar verticalmente las prendas de huecos "stackeables" (`outerwear`, `mid_layer`, `top`/`one_piece`, `bottom`, `shoes`) ordenadas por `outfit_item.layer` descendente (DAT-REQ-006: `outerwear=4 → mid_layer=3 → top/one_piece=2 → bottom=1 → shoes=0`), de arriba abajo, coincidiendo con el orden natural de vestirse de fuera hacia dentro visualmente.

**UI-REQ-010.** Las prendas `accessory` (`layer = NULL`) DEBEN renderizarse aparte de la pila vertical, como una fila de chips/iconos pequeños debajo o al lado de la tarjeta principal — no forman parte del apilado porque no se "llevan encima" de las demás prendas de la misma forma.

**UI-REQ-011.** "Cambiar solo esta pieza" DEBE mostrarse como una acción por prenda dentro de la tarjeta (p. ej. un icono sobre cada prenda de la pila), que dispara el flujo de ENG-REQ-017: una nueva llamada a `POST /outfits/generate` con `fixed_garment_ids` (todas las prendas actuales salvo la que cambia) y `replace_garment_id` (la prenda que se sustituye).

## Diferencias web vs nativo

**UI-REQ-012.** En web, los botones ("No me gusta", "Favorito", "Siguiente", "Me lo pongo hoy") DEBEN ser siempre visibles y ser la vía principal de interacción, ya que el gesto de deslizar es parcial/poco fiable en `react-native-web` (según c4.md). En nativo, los gestos de deslizar (izquierda = descartar, derecha = favorito) complementan a los mismos botones, que también permanecen visibles.

**UI-REQ-013.** La captura de fotos en Añadir usa la cámara nativa (`expo-image-picker`) en iOS/Android; en web recae en el selector de fichero / cámara del navegador, con fiabilidad limitada según el navegador (ver Preguntas abiertas).

**UI-REQ-020.** La primera vez que se abre la pantalla Añadir, DEBE mostrarse un panel de consejos de captura (paso 1 del pipeline del borrador: prenda sola, extendida sobre fondo liso o colgada en percha, con luz natural), descartable por el usuario. Tras descartarlo, DEBE quedar accesible de nuevo en cualquier momento mediante un icono de ayuda visible en la propia pantalla Añadir (no solo la primera vez). *(Persistencia de "ya visto" vía `localStorage`/almacenamiento local del dispositivo — per-viewer, no sincronizado con el servidor, ya que es una preferencia puramente de UI sin equivalente en el modelo de datos.)*

## Uso del cliente de API vía TanStack Query

**UI-REQ-014.** Cada área de recurso tiene sus propios hooks sobre el cliente generado (`app/src/api-client/schema.ts` + wrappers de fetch a mano): `useGarments`, `useGarment`, `useGenerateOutfits`, `useJob`, `useSettings`, `useHistory`, `useFavorites`, etc.

**UI-REQ-015.** Las mutaciones de feedback llaman a los endpoints exactos de 06-feedback-history.md: `POST /outfits` (FBH-REQ-017) la primera vez que una propuesta mostrada recibe cualquier acción calificante, `POST /outfits/{id}/favorite` (FBH-REQ-013) / `POST /outfits/{id}/dislike` (FBH-REQ-019) cuando la propuesta ya tiene un `outfit_id` conocido por el cliente, y `POST /wear-log` (FBH-REQ-007) para "me lo pongo hoy". DEBEN usar actualizaciones optimistas donde sea razonable (p. ej. marcar un outfit como favorito refleja el cambio de inmediato en la UI) con invalidación de caché tras la confirmación del servidor. El cliente DEBE recordar el `outfit_id` devuelto por la primera llamada a `POST /outfits` para una propuesta mostrada, y usarlo en cualquier acción posterior sobre esa misma propuesta en lugar de volver a llamar a `POST /outfits` (ver FBH-REQ-018 para el respaldo de deduplicación en servidor).

**UI-REQ-016.** Las mutaciones de `PATCH /garments/{id}` (pantalla de Revisión y Detalle) invalidan la caché de la lista de Armario y del detalle de esa prenda tras el éxito.

**UI-REQ-021 (D19 — botón "Revisión terminada").** La pantalla de Revisión DEBE mostrar un único botón explícito, con la etiqueta **"Revisión terminada"**, que llama a `POST /garments/{id}/review/complete` (API-REQ-019 en 04-wardrobe-api.md). Corregir un chip individual (vía `PATCH /garments/{id}`) guarda la corrección y actualiza el valor mostrado, pero NO DEBE quitar el resaltado de campos dudosos ni la insignia de "pendiente de revisión" — esos indicadores son puramente informativos durante la edición y solo desaparecen cuando se pulsa "Revisión terminada", que es lo único que limpia `needs_review` y fija `user_verified`. El botón está siempre disponible y es idempotente: puede pulsarse aunque no se haya corregido ningún campo, o aunque sigan quedando campos con confianza baja.

## Polling de jobs

**UI-REQ-017.** Tras `POST /garments`, la app DEBE iniciar el polling de `GET /jobs/{id}` a un intervalo fijo (por defecto 1 s, ajustable) hasta que `status` sea `done` o `failed`.

**UI-REQ-018.** Con varias subidas concurrentes (varias fotos seguidas desde Añadir), cada `job_id` se sondea de forma independiente; la UI muestra el progreso de cada foto por separado, no un progreso agregado único.

**UI-REQ-019.** Al llegar a `done`, la app navega o invita a navegar a la pantalla de Revisión para esa prenda; al llegar a `failed`, se muestra el error con la opción de "Reintentar" (`POST /garments/{id}/retry`, 04-wardrobe-api.md).

## Escenarios

**UI-SCN-001 — Primer arranque, armario vacío.**
Dada una instalación nueva sin prendas,
Cuando el usuario abre la app en móvil (Expo Go) o en el navegador,
Entonces ve la pantalla Hoy o Armario en estado vacío con datos reales del servidor (sin login previo), invitando a ir a Añadir.

**UI-SCN-002 — Alta de 10 prendas.**
Dado el armario vacío,
Cuando el usuario da de alta 10 prendas desde el móvil usando Añadir,
Entonces las 10 aparecen recortadas en la cuadrícula de Armario tras completarse sus jobs.

**UI-SCN-003 — Corregir un chip no limpia la revisión.**
Dada una prenda con `needs_review = true` por baja confianza en `formality` y `category`,
Cuando el usuario abre Revisión y corrige el chip de `formality`,
Entonces se guarda la corrección (`PATCH`, escribe `ai_correction`), el valor mostrado se actualiza, pero el chip de `category` sigue resaltado, la insignia de pendiente de revisión sigue visible, y la app permanece en la pantalla de Revisión (D19) — no navega de vuelta al Armario todavía.

**UI-SCN-003b — "Revisión terminada" cierra la revisión.**
Continuando el escenario anterior, con `category` todavía sin corregir,
Cuando el usuario pulsa "Revisión terminada",
Entonces la app llama a `POST /garments/{id}/review/complete`, `needs_review` pasa a `false`, `user_verified` a `true`, desaparecen el resaltado y la insignia, y la app navega de vuelta al Armario.

**UI-SCN-004 — Outfit con capas en Hoy.**
Dado un outfit propuesto con `outerwear`, `mid_layer`, `top`, `bottom`, `shoes` y un `accessory`,
Cuando se muestra la tarjeta en Hoy,
Entonces las cinco prendas stackeables aparecen apiladas en el orden abrigo → jersey → top → bottom → calzado, y el complemento aparece en una fila separada.

**UI-SCN-005 — Fallback a botones en web.**
Dada la app abierta en un navegador de escritorio,
Cuando se muestra una propuesta en Hoy,
Entonces los cuatro botones de feedback están visibles y son funcionales sin necesidad de gesto de deslizar.

**UI-SCN-006 — Error de red con reintento.**
Dada una caída temporal de conexión con la API,
Cuando el usuario intenta generar un outfit,
Entonces la pantalla Hoy muestra un estado de error explícito con un botón "Reintentar" que vuelve a llamar a `generate`.

**UI-SCN-007 — Consejos de captura en el primer uso.**
Dado que el usuario nunca ha abierto la pantalla Añadir en este dispositivo,
Cuando la abre por primera vez,
Entonces ve el panel de consejos de captura (UI-REQ-020); al descartarlo y volver a abrir Añadir en una sesión posterior no vuelve a aparecer automáticamente, pero sigue siendo accesible mediante el icono de ayuda.

## Criterios de aceptación

- El usuario abre la app en el móvil con Expo Go y en el navegador y ve una pantalla vacía con datos reales del servidor, sin ningún paso de login (adaptación del criterio de la Fase 0 del borrador, eliminando la parte de sesión al no haber auth en la iteración 1).
- Dar de alta 10 prendas desde el móvil hace que aparezcan recortadas en la cuadrícula (criterio de la Fase 1 del borrador).
- Todas las pantallas listadas tienen sus cuatro estados (cargando, vacío, error, procesando cuando aplica) implementados y verificables manualmente.

## Conflictos resueltos (borrador vs c4.md)

- **Sin pantalla de login.** El borrador incluye login con contraseña única y token de sesión en su Fase 0. c4.md aplaza toda la autenticación ("antes D3") fuera de la iteración 1 y afirma explícitamente que "la API no tiene login". Resolución: la app se conecta directamente sin ningún flujo de autenticación (UI-REQ-001); el criterio de aceptación de la Fase 0 se adapta quitando el paso de "inicias sesión".
- **Ajustes sin exportación.** El borrador incluye "exportar datos (JSON + imágenes en ZIP)" dentro de la pantalla Ajustes. c4.md aplaza explícitamente la "caché offline y exportación ZIP". Resolución: la pantalla Ajustes de la iteración 1 cubre pesos del motor, días de no repetir y N de complementos, sin ninguna acción de exportación.
- **Ocho pantallas se mantienen, pero cambia su contenido.** El conteo de "ocho pantallas" del borrador coincide numéricamente con esta spec, pero solo porque el borrador ya excluía el login de su lista enumerada de pantallas (lo trataba como parte del scaffolding de la Fase 0, no como una de las "ocho"); no hay conflicto de conteo, solo de contenido de Ajustes.

## Preguntas abiertas

- Diseño exacto de navegación web en anchos grandes: ¿misma barra de tabs inferior que en móvil, o una barra superior/sidebar? (UI-REQ-003) — no especificado en el borrador ni en c4.md.
- Fiabilidad de la captura de cámara en navegador web (Añadir en web) — el borrador no la trata, y `expo-image-picker` en web tiene soporte limitado; puede requerir un fallback explícito a "subir fichero" documentado en la UI.
- Si `DELETE /garments/{id}` (04-wardrobe-api.md) debe exponerse en alguna pantalla de la iteración 1, o quedar como funcionalidad solo de API — el borrador no muestra un botón de borrar, solo archivar.
- Diseño detallado de los skeletons de carga y el copy exacto en español de los estados vacíos/error — no especificado; pendiente de una pasada de diseño visual.
- Alcance de accesibilidad (lectores de pantalla, tamaños de fuente dinámicos) — no mencionado en el borrador ni en c4.md; queda sin decidir para la iteración 1.
