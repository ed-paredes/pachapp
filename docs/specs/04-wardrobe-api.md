# 04 — API del armario

Estado: Draft

## Alcance

Endpoints de listado/filtrado/detalle/edición/archivado/estado/reintento/borrado de prendas, flujo de revisión (semántica de `PATCH`, escrituras en `ai_correction`), endpoints de settings, formato de error, paginación, servido de imágenes, generación de cliente TS desde OpenAPI.

## Fuera de alcance

Los detalles internos del pipeline de ingesta (03-garment-ingestion.md), los endpoints de generación/feedback de outfits (05, 06), autenticación (aplazada).

## Dependencias

- Decisiones: D5 (tabla `setting`), D11 (sin auth, API sin estado), D14/D15 (raíz de imágenes, CORS), D16 (Pydantic v2, generación de OpenAPI), D18 (settings de color ya no incluyen un máximo configurable), D19 (revisión con un único botón — API-REQ-019/020).
- Modelo de datos: `garment`, `job`, `setting`, `ai_correction` (02-data-model.md).
- El endpoint de subida (`POST /garments`) y el ciclo de vida del job están definidos en 03-garment-ingestion.md; esta spec cubre el resto de la superficie de `garment`/`job`/`setting`.

## Formato de error

**API-REQ-001.** Los errores a nivel de dominio (4xx/5xx lanzados intencionalmente por el código de la aplicación) DEBEN usar un envoltorio consistente:

```json
{"error": {"code": "GARMENT_NOT_FOUND", "message": "Garment 3f2...  does not exist", "details": null}}
```

`code` es un identificador estable en mayúsculas y guion bajo; `message` es legible por humanos (puede mostrarse tal cual en herramientas de desarrollo, no necesariamente como copy final de usuario); `details` es un objeto opcional con contexto estructurado (p. ej. el id de un recurso en conflicto).

**API-REQ-002.** Los errores `422` de validación de petición por defecto de FastAPI (parámetros de query malformados, campos obligatorios del body ausentes) PUEDEN mantener el formato propio de FastAPI en lugar del envoltorio anterior — documentado como la única excepción, ya que envolver la validación de nivel framework aporta poco valor aquí.

## Paginación

**API-REQ-003.** Los endpoints de listado DEBEN aceptar los parámetros de query `page` (por defecto `1`) y `page_size` (por defecto `50`, máximo `200`) y responder con:

```json
{"items": [...], "total": 137, "page": 1, "page_size": 50}
```

*(Valores por defecto ajustables.)*

## Endpoints de prendas

**API-REQ-004.** `GET /garments` DEBE soportar los filtros: `category`, `color` (coincide contra `colors[].name`), `season` (coincide con la contención de `seasons`), `status`, `needs_review` (booleano). DEBE soportar `sort` (`created_at`, `last_worn_at`, `wear_count`; por defecto `created_at desc`). Se combina con la paginación (API-REQ-003).

**API-REQ-005.** `GET /garments/{id}` DEBE devolver el registro completo de la prenda incluyendo `ai_confidence`, `color_confidence`, y el recuento de outfits en los que aparece (calculado, no almacenado — un join contra `outfit_item`).

**API-REQ-006.** `PATCH /garments/{id}` DEBE aceptar una actualización parcial de cualquier campo editable (`category, subcategory, colors, pattern, formality, style_tags, seasons, warmth, material, brand, notes, status`). NO DEBE aceptar escrituras directas a `wear_count`, `last_worn_at`, `embedding`, `ai_confidence`, `needs_review`, `user_verified` (D19 — ver API-REQ-019/020), `img_*`.

**API-REQ-007.** En cada `PATCH`, por cada campo modificado que tenga una clave en el `ai_confidence` actual de la prenda, el servidor DEBE escribir una fila `ai_correction` (`field`, `ai_value` = el valor que se reemplaza, `corrected_value` = el nuevo valor) **antes** de aplicar la actualización, en la misma transacción (DAT-REQ-012). Esto aplica en cada edición de ese tipo, no solo la primera.

**API-REQ-008 (Retirado — ver D19).** ~~`PATCH` DEBE fijar `user_verified = true` siempre que la petición incluya algún campo que antes formara parte de `ai_confidence`.~~ D19 decide que `user_verified` SOLO cambia mediante la acción explícita "Revisión terminada" (API-REQ-019) — ningún `PATCH` lo fija, ni siquiera como efecto secundario de tocar un campo atribuido a la IA (DAT-REQ-019 en 02-data-model.md).

**API-REQ-009 (Retirado — ver D19).** ~~`PATCH` DEBE recalcular `is_neutral` y `needs_review` cuando cambien `colors` o cualquier campo rastreado por `ai_confidence`.~~ D19 decide que corregir un campo individual guarda la corrección (`ai_correction`, API-REQ-007) pero NO cambia `needs_review` — `needs_review` solo pasa a `false` mediante la acción explícita "Revisión terminada" (API-REQ-019), nunca por un recálculo campo a campo dentro de `PATCH` (DAT-REQ-018 en 02-data-model.md). `PATCH` SÍ sigue recalculando `is_neutral` cuando cambia `colors` (eso no depende de `needs_review` y no está afectado por D19).

**API-REQ-010.** `POST /garments/{id}/archive` fija `status = archived`. `POST /garments/{id}/reactivate` fija `status = active`. (`laundry` se fija mediante el campo `status` del `PATCH` genérico, no un endpoint dedicado, ya que es un cambio rutinario más que una transición de ciclo de vida.)

**API-REQ-011.** `POST /garments/{id}/retry` SOLO es válido cuando el job actual de la prenda está en `status=failed`; reinicia ese job a `status=pending, attempts=0, error=null, step=null` para que el worker lo retome desde el principio del pipeline (`step` vuelve a `null` en lugar de conservar el último paso fallido, para que `GET /jobs/{id}` no muestre un paso obsoleto mientras el job espera a ser reclamado de nuevo). `409` si no existe ningún job fallido.

**API-REQ-012.** `DELETE /garments/{id}` elimina permanentemente la fila de la prenda y sus ficheros de imagen. DEBE rechazarse con `409` si la prenda aparece en alguna fila de `outfit_item` (historial de outfits persistido) — el usuario debe archivar en su lugar para preservar la integridad del historial. El borrado está pensado para subidas accidentales/erróneas antes de cualquier interacción.

## Revisión con un único botón (D19)

**API-REQ-019.** `POST /garments/{id}/review/complete` es la **única** acción que fija `needs_review = false` y `user_verified = true` (DAT-REQ-018/019 en 02-data-model.md). No acepta body ni modifica ningún otro campo de la prenda. Es idempotente: puede llamarse aunque `needs_review` ya sea `false` (simplemente confirma/reafirma `user_verified = true`), y no falla si no quedan campos con baja confianza pendientes. Responde `200` con el registro actualizado de la prenda.

**API-REQ-020.** El flujo de revisión completo es: (1) el usuario corrige cero o más campos individuales vía `PATCH /garments/{id}` (cada corrección de un campo antes atribuido a la IA escribe una fila `ai_correction`, API-REQ-007, sin tocar `needs_review` ni `user_verified`, API-REQ-008/009 retirados); (2) el usuario pulsa "Revisión terminada", que llama a `POST /garments/{id}/review/complete` (API-REQ-019). Los chips resaltados por baja confianza en la pantalla de Revisión (07-app-ui.md) permanecen como información visual durante todo el paso 1 — no se limpian campo a campo, solo desaparecen (junto con la insignia de pendiente de revisión) cuando se completa el paso 2.

## Endpoint de estado de job

**API-REQ-013.** `GET /jobs/{id}` DEBE devolver `{status, step, progress, error, result}` (definido completamente en 03-garment-ingestion.md ING-REQ-026); se incluye aquí porque forma parte de la misma superficie de router que la app consulta junto al CRUD de prendas.

## Endpoints de settings

**API-REQ-014.** `GET /settings` devuelve la fila singleton (`weight_color, weight_style, weight_novelty, weight_preference, no_repeat_days, max_accessories, duplicate_warning_threshold, needs_review_threshold, color_review_threshold`). *(`max_non_neutral_colors` y `hemisphere` no existen: D18 fija el máximo de colores no neutros en 2, no configurable, y D8 elimina toda lógica de temporada — ver 02-data-model.md.)*

**API-REQ-015.** `PATCH /settings` acepta una actualización parcial. Si se incluye algún campo `weight_*`, el servidor DEBE validar que los cuatro pesos resultantes sumen `1.0 ± 0.01` (DAT-REQ-011); de lo contrario, `400` con `code=INVALID_WEIGHTS`.

## Servido de imágenes

**API-REQ-016.** Las imágenes DEBEN servirse mediante un montaje estático (`StaticFiles`) en `/images/` con raíz en `PACHAPP_IMAGES_ROOT`, coincidiendo con las rutas relativas guardadas en `garment` (`img_original`, `img_cutout`, `img_thumb` → `/images/original/{id}.jpg`, etc.). Sin control de acceso en la iteración 1 (sin auth), coherente con que la API solo es accesible en la LAN doméstica.

## Generación de cliente TS desde OpenAPI

**API-REQ-017.** Cada router DEBE declarar `response_model`s explícitos de Pydantic v2 (nunca dicts sueltos) para que el esquema OpenAPI generado quede totalmente tipado.

**API-REQ-018.** `make gen-client` (01-dev-tooling.md) consume `GET /openapi.json` y regenera `app/src/api-client/schema.ts`; los wrappers de fetch y los hooks de TanStack Query escritos a mano conviven al lado, sin generarse (ver 07-app-ui.md).

## Escenarios

**API-SCN-001 — Listado filtrado.**
Dadas 50 prendas activas y 10 archivadas,
Cuando se llama a `GET /garments?status=active&category=top&page=1&page_size=20`,
Entonces solo se devuelven prendas `top` activas, paginadas, con un `total` correcto.

**API-SCN-002 — La corrección en revisión escribe `ai_correction` sin tocar `needs_review`.**
Dada una prenda con `ai_confidence.category = {value: "top", confidence: 0.6, source: "zero_shot"}`, `category = "top"` y `needs_review = true`,
Cuando `PATCH /garments/{id}` fija `category = "mid_layer"`,
Entonces se escribe una fila `ai_correction` (`field="category", ai_value="top", corrected_value="mid_layer"`), `ai_confidence.category` pasa a `{value: "mid_layer", confidence: 1.0, source: "user"}` (DAT-REQ-016/021, calidad de dato), pero `needs_review` sigue en `true` y `user_verified` sigue en `false` (D19) — ninguno de los dos cambia hasta que se complete la revisión.

**API-SCN-002b — "Revisión terminada" limpia el estado sin importar campos pendientes.**
Dada la misma prenda de API-SCN-002, tras corregir `category` pero dejando `formality` con confianza baja sin corregir,
Cuando el usuario pulsa "Revisión terminada" (`POST /garments/{id}/review/complete`),
Entonces `needs_review` pasa a `false` y `user_verified` a `true`, aunque `formality` siga con la confianza baja original — D19 no exige que todos los campos individuales estén "arreglados", solo que el usuario confirme que terminó de revisar.

**API-SCN-003 — Borrado bloqueado por historial.**
Dada una prenda que aparece en un `outfit_item` persistido (p. ej. se llevó puesta una vez),
Cuando se llama a `DELETE /garments/{id}`,
Entonces el servidor responde `409 {"error": {"code": "GARMENT_HAS_HISTORY", ...}}` y la prenda queda intacta; se espera que el cliente ofrezca `archive` en su lugar.

**API-SCN-004 — Reintento sin job fallido.**
Dado que el job de una prenda está actualmente `done`,
Cuando se llama a `POST /garments/{id}/retry`,
Entonces el servidor responde `409` y no se modifica ningún job.

**API-SCN-005 — Validación de pesos de settings.**
Dado un body `PATCH /settings` `{"weight_color": 0.9}` (dejando los demás sin cambiar, sumando `> 1.0`),
Cuando se procesa la petición,
Entonces se rechaza con `400 INVALID_WEIGHTS` y los settings almacenados no cambian.

## Criterios de aceptación

- Todos los endpoints de listado/detalle/edición/archivado/reintento/borrado están cubiertos por tests `pytest` que ejercitan tanto el éxito como los casos de error documentados.
- `make gen-client` ejecutado contra un servidor en vivo produce tipos TS del lado app sin ningún `any` para ninguna forma de respuesta documentada.
- Editar campos de una prenda en la pantalla de Revisión NO limpia `needs_review`; solo pulsar "Revisión terminada" lo hace, independientemente de qué campos quedaran sin corregir (D19, comprobación manual/UAT, referencia cruzada 07-app-ui.md).

## Preguntas abiertas

- Si `DELETE` debería exponerse en la UI en la iteración 1, o reservarse como una vía de escape solo de API (las pantallas del borrador no muestran un botón de borrar, solo archivar) — 07-app-ui.md debería decidirlo en base a esto.
- Si `GET /garments` necesita búsqueda de texto libre sobre `subcategory`/`notes`/`brand` — no la pide la lista de filtros del borrador (categoría, color, temporada, estado) pero es plausible cuando el armario crezca más allá de ~100 prendas.

Resuelta por decisión del usuario (ya no es una pregunta abierta): D19 zanja definitivamente cómo se limpia `needs_review` — solo mediante la acción explícita "Revisión terminada" (API-REQ-019), nunca por corrección de campos individuales. La pregunta que esta sección tenía abierta al respecto queda cerrada.
