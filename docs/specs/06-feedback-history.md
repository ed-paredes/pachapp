# 06 — Feedback e historial

Estado: Draft

## Alcance

Acciones de feedback (no me gusta, siguiente, favorito, me lo pongo hoy), política de persistencia de outfits, reglas de `wear_log`, contadores derivados, ventana de no repetición, endpoints de favoritos e historial/estadísticas.

## Fuera de alcance

El algoritmo de generación y los filtros/puntuación que consumen este historial (05-outfit-engine.md, que referencia esta spec para la fuente de los datos de `wear_log`/`rating`/`is_favorite`).

## Dependencias

- Decisiones: D6 (persistir solo outfits con interacción), D7 (`wear_log` con `UNIQUE(date)`, campos derivados en la misma transacción).
- Modelo de datos: `outfit`, `outfit_item`, `wear_log`, `garment.wear_count`/`last_worn_at` (02-data-model.md).

## Acciones de feedback

| Acción | Botón (UI, español) | Efecto |
| --- | --- | --- |
| No me gusta | "No me gusta" | Persiste el outfit (D6) con `rating = -1` vía `POST /outfits` (o `POST /outfits/{id}/dislike` si ya estaba persistido). No crea `wear_log`. |
| Siguiente | "Siguiente" | No persiste nada; simplemente descarta la propuesta actual y muestra otra de las ya generadas o dispara una nueva generación. |
| Favorito | "Favorito" (deslizar a la derecha en móvil) | Persiste el outfit (D6) con `is_favorite = true` vía `POST /outfits` (o `POST /outfits/{id}/favorite` si ya estaba persistido). Si `rating` seguía en `0`, se fija a `+1`. |
| Me lo pongo hoy | "Me lo pongo hoy" | Asegura que el outfit está persistido (vía `POST /outfits` si aún no lo estaba), crea una fila `wear_log` para hoy vía `POST /wear-log`, y recalcula `wear_count`/`last_worn_at` de cada prenda incluida. |

**FBH-REQ-001.** "Siguiente" NO DEBE crear ninguna fila en `outfit` ni `outfit_item` — es la única acción de las cuatro que no cuenta como interacción calificante según D6.

**FBH-REQ-002.** "No me gusta" sobre una propuesta aún no persistida DEBE llamar a `POST /outfits` (FBH-REQ-017) con `rating = -1` y el resto de campos de la propuesta (`source=generated`, `items`, `score`, `score_breakdown`, `explanation`); no crea `wear_log`. Si el outfit ya estaba persistido (p. ej. ya se había favoritado en la misma vista), DEBE usarse en su lugar `POST /outfits/{id}/dislike` (FBH-REQ-019) para no crear una fila duplicada.

**FBH-REQ-003.** "Favorito" sobre una propuesta aún no persistida DEBE llamar a `POST /outfits` (FBH-REQ-017) con `is_favorite = true`; si el `rating` implícito de la propuesta es `0`, se envía como `+1`. Si el outfit ya estaba persistido, DEBE usarse `POST /outfits/{id}/favorite` (FBH-REQ-013) en su lugar. Si el outfit ya tenía `rating = -1` (caso improbable en el flujo normal, ya que un outfit descartado no debería volver a mostrarse), el rating existente no se sobrescribe automáticamente.

**FBH-REQ-004.** `rating` y `is_favorite` son campos independientes en el modelo de datos (DAT-REQ-005), pero en la práctica de la UI de la iteración 1 no existe un botón de "me gusta" genérico separado de "favorito" — solo estas cuatro acciones.

## Política de persistencia de outfits

**FBH-REQ-005.** Un outfit generado se persiste de forma perezosa (`outfit` + sus `outfit_item`) en el primer momento en que el usuario realiza "no me gusta", "favorito" o "me lo pongo hoy" sobre él — nunca en el momento de la generación (D6, ver también ENG-REQ-021 en 05-outfit-engine.md).

**FBH-REQ-006.** Registrar "me lo pongo hoy" tiene dos caminos posibles según el origen del outfit:
- **(a) Outfit recién generado, aún no persistido:** el cliente llama primero a `POST /outfits` (FBH-REQ-017, `source=generated`, con el `score`/`score_breakdown`/`explanation` de la propuesta) para obtener un `outfit_id`, y a continuación llama a `POST /wear-log {outfit_id}` (FBH-REQ-007) referenciando ese id nuevo.
- **(b) Outfit favorito ya existente** (reutilizado desde la pantalla de Favoritos): se usa directamente el `outfit_id` existente; solo se llama a `POST /wear-log`.

## Contrato de `POST /outfits`

**FBH-REQ-017.** `POST /outfits` es el endpoint que persiste por primera vez una propuesta todavía en memoria (D6/ENG-REQ-021). Petición:

```python
class OutfitItemInput(BaseModel):
    garment_id: UUID
    slot: OutfitSlot
    layer: int | None   # ver DAT-REQ-006

class CreateOutfitRequest(BaseModel):
    source: OutfitSource              # generated | manual
    items: list[OutfitItemInput]
    score: float | None = None
    score_breakdown: ScoreBreakdown | None = None
    explanation: str | None = None
    rating: int = 0                    # {-1, 0, 1}
    is_favorite: bool = False
```

Respuesta `201 Created` (o `200`, ver FBH-REQ-018):

```python
class OutfitItemResponse(BaseModel):
    garment_id: UUID
    slot: OutfitSlot
    layer: int | None

class OutfitResponse(BaseModel):
    id: UUID
    created_at: datetime
    source: OutfitSource
    items: list[OutfitItemResponse]
    score: float | None
    score_breakdown: ScoreBreakdown | None
    explanation: str | None
    is_favorite: bool
    rating: int
    name: str | None
```

**FBH-REQ-018.** Manejo de duplicados/idempotencia: si la petición tiene `source=generated` y su conjunto de `garment_id` (sin importar el orden) coincide exactamente con el de un `outfit` ya creado en los últimos 5 minutos (ventana por defecto, ajustable), el servidor DEBE devolver ese outfit existente con `200 OK` en lugar de crear una fila duplicada — protege contra reintentos de red o doble toque sobre la misma propuesta mostrada. Fuera de esa ventana, o con un conjunto de prendas distinto, se crea una fila nueva (`201`). El campo `rating`/`is_favorite` de la petición NO sobrescribe el de un outfit existente devuelto por deduplicación; para modificar un outfit ya persistido se usan los endpoints de acción dedicados (`POST /outfits/{id}/favorite`, `POST /outfits/{id}/dislike`, FBH-REQ-013/019).

**FBH-REQ-019.** `POST /outfits/{id}/dislike` fija `rating = -1` sobre un outfit ya persistido (simétrico a `POST /outfits/{id}/favorite`, FBH-REQ-013) — se usa cuando el cliente ya tiene un `outfit_id` para la propuesta mostrada (p. ej. se favoritó primero y luego se descarta) y por tanto no debe volver a llamar a `POST /outfits`.

## Reglas de `wear_log`

**FBH-REQ-007.** `POST /wear-log` acepta `{outfit_id, date?}` (`date` por defecto hoy). Si ya existe una fila `wear_log` para esa fecha, el servidor responde `409` con la entrada existente en `details` (el cliente puede ofrecer sobrescribir).

**FBH-REQ-008.** `PUT /wear-log/{date}` sobrescribe explícitamente qué outfit se llevó ese día: `{outfit_id}`. Esto DEBE, en la misma transacción: (1) eliminar la asociación previa a efectos de contadores, recalculando `wear_count`/`last_worn_at` del outfit anterior sin contar esta fecha, y (2) aplicar los contadores derivados al nuevo outfit incluyendo esta fecha (D7, DAT-REQ-008).

**FBH-REQ-009.** `DELETE /wear-log/{date}` elimina el registro del día y recalcula los contadores derivados de las prendas del outfit afectado en la misma transacción.

**FBH-REQ-010.** `wear_count` de una prenda = número de filas distintas de `wear_log` cuyo outfit contiene esa prenda (vía `outfit_item`). `last_worn_at` = fecha máxima de `wear_log.date` entre esas filas. Ambos se recalculan en cada escritura de `wear_log` (inserción, sobrescritura o borrado), nunca se editan directamente (DAT-REQ-003, DAT-REQ-008).

## Ventana de no repetición

**FBH-REQ-011.** La regla de no repetición (ningún outfit con el mismo conjunto exacto de prendas que uno registrado en `wear_log` en los últimos `setting.no_repeat_days` días) es un filtro duro implementado en el motor de outfits (ENG-REQ-005), pero su fuente de datos es exactamente esta tabla `wear_log` — no hay una tabla o flag separado de "no repetir".

## Favoritos

**FBH-REQ-012.** `GET /outfits/favorites` devuelve los outfits con `is_favorite = true`, paginados, ordenados por `created_at desc` por defecto. Cada elemento incluye sus `outfit_item` resueltos (con datos de prenda suficientes para renderizar la tarjeta sin una petición adicional por prenda).

**FBH-REQ-013.** `POST /outfits/{id}/favorite` fija `is_favorite = true`. `DELETE /outfits/{id}/favorite` (o `PATCH` equivalente) fija `is_favorite = false`. Desmarcar un favorito NO DEBE borrar el outfit ni su historial de `wear_log`.

**FBH-REQ-014.** Un outfit favorito DEBE poder reutilizarse directamente en "me lo pongo hoy" (FBH-REQ-006, camino b) con un solo toque desde la pantalla de Favoritos, sin pasar por la generación.

## Historial / estadísticas

**FBH-REQ-015.** `GET /history/calendar?month=YYYY-MM` devuelve el mapeo fecha → outfit (con sus prendas resueltas) para cada día del mes que tenga una fila en `wear_log`.

**FBH-REQ-016.** `GET /history/stats` devuelve: las `N` prendas más usadas (por `wear_count` descendente; `N` por defecto 10, ajustable) y la lista de prendas activas sin usar en los últimos 90 días (`last_worn_at IS NULL OR last_worn_at < hoy - 90 días`, excluyendo prendas archivadas). *(90 días y N=10 son valores por defecto, ajustables.)*

## Escenarios

**FBH-SCN-001 — Descartar no persiste.**
Dada una propuesta recién generada que el usuario nunca toca con ningún botón,
Cuando la pantalla pasa a la siguiente propuesta ("Siguiente"),
Entonces no se crea ninguna fila `outfit` ni `outfit_item`.

**FBH-SCN-002 — No me gusta persiste con rating negativo.**
Dada una propuesta generada aún no persistida,
Cuando el usuario pulsa "No me gusta",
Entonces el cliente llama a `POST /outfits` con `rating = -1`, se crea el `outfit` con sus `outfit_item`, y no se crea ningún `wear_log`.

**FBH-SCN-002b — No me gusta sobre un outfit ya persistido.**
Dado un outfit que ya se había favoritado en la misma vista (ya tiene `outfit_id`),
Cuando el usuario pulsa "No me gusta" sobre él,
Entonces el cliente llama a `POST /outfits/{id}/dislike` (no a `POST /outfits` de nuevo), y no se crea una fila `outfit` duplicada.

**FBH-SCN-003 — Favorito persiste con rating positivo.**
Dada una propuesta generada con `rating` implícito en `0`, aún no persistida,
Cuando el usuario pulsa "Favorito",
Entonces el cliente llama a `POST /outfits` con `is_favorite = true, rating = +1`, y se crea el `outfit` en consecuencia.

**FBH-SCN-004 — Me lo pongo hoy sobre un outfit nuevo.**
Dada una propuesta generada que el usuario nunca había marcado antes,
Cuando pulsa "Me lo pongo hoy",
Entonces el cliente llama primero a `POST /outfits` (obteniendo `outfit_id`) y luego a `POST /wear-log {outfit_id}` (fecha de hoy), y `wear_count`/`last_worn_at` de cada prenda incluida se actualizan de inmediato.

**FBH-SCN-005 — Me lo pongo hoy sobre un favorito existente.**
Dado un outfit ya presente en Favoritos,
Cuando el usuario lo reutiliza con "Me lo pongo hoy" desde esa pantalla,
Entonces el cliente llama solo a `POST /wear-log` referenciando el `outfit_id` existente; no se llama a `POST /outfits` ni se duplica el `outfit`.

**FBH-SCN-005b — Deduplicación de `POST /outfits` por reintento.**
Dado que el cliente llama a `POST /outfits` con un conjunto de `garment_id` y, por un reintento de red, la misma petición llega dos veces en menos de 5 minutos,
Cuando el servidor procesa la segunda llamada,
Entonces (FBH-REQ-018) devuelve `200` con el `outfit_id` ya creado por la primera llamada en lugar de crear una fila duplicada.

**FBH-SCN-006 — Conflicto de doble registro el mismo día.**
Dado que ya existe un `wear_log` para hoy,
Cuando el usuario intenta registrar un outfit distinto para hoy vía `POST /wear-log`,
Entonces el servidor responde `409` con la entrada existente, y el cliente puede ofrecer `PUT /wear-log/{date}` para sobrescribir.

**FBH-SCN-007 — Sobrescritura recalcula ambos outfits.**
Dado un `wear_log` de hoy apuntando al outfit X,
Cuando se llama a `PUT /wear-log/{hoy}` con el outfit Y,
Entonces `wear_count`/`last_worn_at` de las prendas de X se recalculan sin contar hoy, y los de Y se recalculan incluyendo hoy, todo en una sola transacción.

**FBH-SCN-008 — Estadísticas de prendas olvidadas.**
Dada una prenda activa sin ningún `wear_log` en los últimos 120 días,
Cuando se llama a `GET /history/stats`,
Entonces esa prenda aparece en la lista de prendas sin usar en 90 días.

## Criterios de aceptación

- Tras marcar "me lo pongo", ese outfit exacto no vuelve a proponerse en los siguientes 14 días, y sus prendas individuales bajan de ranking en propuestas posteriores por la penalización de novedad (objetivo de la Fase 4 del borrador; el lado de filtrado/puntuación vive en 05-outfit-engine.md, el lado de persistencia se verifica aquí).
- `wear_count` y `last_worn_at` de una prenda se reflejan de inmediato en la pantalla de Detalle de prenda tras registrar "me lo pongo hoy" (sin necesidad de refrescar manualmente más allá de la invalidación normal de caché de TanStack Query).
- La pantalla de Historial muestra correctamente el calendario mensual y las estadísticas simples (prendas más usadas, prendas sin usar en 90 días) contra datos reales de `wear_log`.

## Preguntas abiertas

- Comportamiento exacto de UX para el conflicto de doble registro el mismo día (FBH-SCN-006) — ¿diálogo de confirmación antes de sobrescribir, o sobrescritura directa con opción de deshacer? Pertenece a 07-app-ui.md pero necesita una decisión de producto.
- Si "Siguiente" debería registrarse en algún sitio con fines analíticos (p. ej. para alimentar la futura regresión logística de preferencia) — actualmente se decide explícitamente que no persiste nada; marcado como valor por defecto ajustable, no como pregunta bloqueante.
- Valores exactos de los umbrales de estadísticas (90 días para "sin usar", N=10 para "más usadas") — no están en el borrador ni en c4.md; son valores por defecto razonables pendientes de validación con el usuario real.
- Si desmarcar un favorito (FBH-REQ-013) que además tiene `rating = +1` debería también resetear el rating a `0`, o mantenerlo independiente — no especificado; se mantiene independiente por defecto.
- La ventana de deduplicación de 5 minutos de `POST /outfits` (FBH-REQ-018, hallazgo A1 de la revisión) es un valor por defecto sin calibrar contra el comportamiento real de reintentos del cliente; podría necesitar ajuste una vez medida la latencia típica de red en la LAN doméstica.
