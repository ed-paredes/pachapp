# 00 — Índice de especificaciones

Estado: Draft

## Propósito

Este directorio contiene las especificaciones granulares de la iteración 1 de "Armario inteligente" (pachapp): un armario digital personal con recomendador de outfits por color, estilo y novedad. Las specs traducen a requisitos verificables el borrador original del usuario (`spec-armario-inteligente(1).md`) y la arquitectura C4 aprobada (`docs/architecture/c4.md`), resolviendo los puntos donde ambos documentos difieren a favor de la arquitectura aprobada.

## Alcance de la iteración 1

Todo corre como procesos locales en el PC del usuario (sin contenedores, sin servidor remoto): API FastAPI, worker de procesado, motor de outfits, base de datos SQLite y almacenamiento de imágenes en disco local, más una app Expo (React Native + web). La única dependencia externa es un LLM con visión (una llamada por prenda). No hay autenticación, ni copias de seguridad automáticas, ni acceso remoto: la API solo escucha en la LAN doméstica.

**Explícitamente fuera de alcance en la iteración 1** (ver la sección "Aplazado" de c4.md):

- Infraestructura: Docker Compose, VPS o servidor doméstico, acceso remoto con Tailscale, builds con EAS.
- Autenticación (login, token de sesión).
- Copias de seguridad (Litestream, `rclone`).
- Caché offline del armario y exportación de datos (JSON + ZIP).
- Try-on virtual, ahora llamado "v2" (D12); su tabla `user_photo` (id, img, pose frontal/lateral, created_at) no se crea en la iteración 1 — el esquema queda documentado en 02-data-model.md, sección "Fuera de alcance / próximas iteraciones", listo para cuando se retome.
- Clima y ocasión como criterios de outfit (ya excluidos en el borrador original).
- Temporada como criterio de outfit (D8, retirado tras una decisión posterior del usuario) — `garment.seasons` se sigue extrayendo y guardando, pero el motor no lo usa.

## Convenciones de las specs

- Cada spec tiene: título, estado, alcance, fuera de alcance, dependencias (otras specs y IDs de decisión de c4.md), requisitos con IDs estables (`PREFIJO-REQ-NNN`) en MUST/SHOULD/MAY (traducido como DEBE/DEBERÍA/PUEDE), escenarios Dado/Cuando/Entonces con IDs (`PREFIJO-SCN-NNN`), criterios de aceptación medibles, y una sección de preguntas abiertas.
- Las specs están redactadas en español (registro neutro/profesional). Los identificadores de código, nombres de tabla/columna, valores de enum, rutas de endpoint, targets del Makefile e IDs de requisito se mantienen en inglés/tal cual, ya que son artefactos técnicos consumidos literalmente por el código.
- Los textos de interfaz de usuario (nombres de pantalla, etiquetas de botón, plantillas de explicación) se mantienen citados en español, ya que así los verá el usuario final.
- Cuando una decisión aprobada de c4.md (D0–D17) entra en conflicto con el borrador original, la decisión de c4.md prevalece; el conflicto y su resolución se documentan explícitamente en la sección "Conflictos resueltos" de la spec correspondiente.
- Cuando hace falta fijar un valor técnico no especificado por ninguna de las dos fuentes, se marca `(valor por defecto, ajustable)` en lugar de inventarse como si fuera una decisión de producto cerrada.

## Glosario (términos de UI en español ↔ identificadores en inglés)

| Español (UI) | Identificador (código) |
| --- | --- |
| Hoy | `Today` |
| Armario | `Wardrobe` |
| Añadir | `Add` |
| Revisión | `Review` |
| Detalle de prenda | `GarmentDetail` |
| Favoritos | `Favorites` |
| Historial | `History` |
| Ajustes | `Settings` |
| prenda | `garment` |
| armario | `wardrobe` |
| recorte | `cutout` |
| top | `top` |
| bottom / pantalón | `bottom` |
| vestido / mono | `one_piece` |
| jersey / sudadera / cárdigan / sobrecamisa | `mid_layer` |
| abrigo / chaqueta de exterior | `outerwear` |
| calzado | `shoes` |
| complemento | `accessory` |
| activo | `active` |
| lavando | `laundry` |
| archivado | `archived` |
| liso | `solid` |
| rayas | `striped` |
| cuadros | `plaid` |
| estampado | `printed` |
| textura | `textured` |
| primavera / verano / otoño / invierno | `spring` / `summer` / `autumn` / `winter` |
| clásico / street / minimal / deportivo / casual | `classic` / `street` / `minimal` / `sport` / `casual` |
| no me gusta | acción `dislike` |
| siguiente | acción `next` |
| favorito | acción `favorite` |
| me lo pongo hoy | acción `wear-log` |
| revisión terminada | acción `review-complete` (`POST /garments/{id}/review/complete`) |
| pendiente de revisión | `needs_review` |
| verificado por el usuario | `user_verified` |

## Lista de specs

| Spec | Resumen |
| --- | --- |
| `01-dev-tooling.md` | Estructura del monorepo, herramientas Python/uv y app, targets del Makefile, settings/.env, WSL2, CORS. |
| `02-data-model.md` | Todas las tablas, columnas, enums, esquemas JSON, relaciones y política de migraciones. |
| `03-garment-ingestion.md` | Endpoint de subida, ciclo de vida del job, pipeline del worker, contrato del LLM, duplicados, `needs_review`. |
| `04-wardrobe-api.md` | Endpoints CRUD de prendas, flujo de revisión, settings, paginación, formato de error, servido de imágenes. |
| `05-outfit-engine.md` | Plantillas, filtros duros, puntuación en cuatro componentes, algoritmo en dos etapas, MMR, endpoint `generate`. |
| `06-feedback-history.md` | Acciones de feedback, contrato de `POST /outfits` para persistir una propuesta, política de persistencia de outfits, `wear_log`, favoritos, historial/estadísticas. |
| `07-app-ui.md` | Pantallas, navegación, estados, renderizado de outfits con capas, diferencias web/nativo, polling de jobs. |

## Tabla de trazabilidad (decisión de c4.md → secciones de spec)

| ID | Decisión | Specs donde se implementa |
| --- | --- | --- |
| D0 | Ejecución local sin contenedores, lanzada desde el Makefile raíz | 01-dev-tooling.md |
| D1 | Motor en dos etapas (bases → extensión con capas → MMR) | 05-outfit-engine.md |
| D4 | Concurrencia en SQLite: WAL, `busy_timeout`, reclamación atómica del job | 02-data-model.md, 03-garment-ingestion.md |
| D5 | Tablas añadidas: `job`, `setting`, `ai_correction` | 02-data-model.md |
| D6 | Persistir solo outfits con interacción | 02-data-model.md, 06-feedback-history.md, 05-outfit-engine.md |
| D7 | `wear_log` con `UNIQUE(date)`, campos derivados en la misma transacción | 02-data-model.md, 06-feedback-history.md |
| D8 | **(Retirado.)** Filtro de temporada actual — descartado en la iteración 1 por decisión posterior del usuario: sin filtros ni puntuación por temporada; `garment.seasons` se sigue extrayendo y guardando para uso futuro | 05-outfit-engine.md (ENG-REQ-004, marcado retirado), 02-data-model.md, 03-garment-ingestion.md (columna `seasons` se mantiene) |
| D9 | Duplicados por CLIP: umbral calibrado, solo aviso | 03-garment-ingestion.md |
| D10 | Confianza del color activa `needs_review` | 02-data-model.md, 03-garment-ingestion.md |
| D11 | Versión del LLM fijada + test de contrato; API sin estado de sesión | 03-garment-ingestion.md, 04-wardrobe-api.md, 07-app-ui.md |
| D12 | El try-on pasa a llamarse "v2" (fuera de alcance) | 00-index.md (este documento) |
| D13 | Red en WSL2 (modo mirrored) | 01-dev-tooling.md |
| D14 | Datos en el ext4 de WSL2, no en `/mnt/d` | 01-dev-tooling.md |
| D15 | CORS en FastAPI para la web de Expo | 01-dev-tooling.md, 04-wardrobe-api.md |
| D16 | Herramientas de desarrollo: uv, Pydantic v2, Makefile único | 01-dev-tooling.md |
| D17 | Capas en la v1: `mid_layer`, N complementos, `outfit_item.layer` | 02-data-model.md, 05-outfit-engine.md, 07-app-ui.md |
| D18 | Reglas de color básicas: neutros combinan con todo; máximo 2 colores no neutros entre prendas de ropa (complementos no cuentan); tono en 3 niveles (análogos/complementarios/resto); se mantiene la penalización por patrones llamativos; sin bono de tono sobre tono ni tríada; máximo fijo, no configurable | 05-outfit-engine.md (ENG-REQ-007, ENG-REQ-011), 02-data-model.md (columna `max_non_neutral_colors` retirada), 04-wardrobe-api.md |
| D19 | Revisión con un único botón: corregir un campo guarda `ai_correction` pero no quita `needs_review`; solo "Revisión terminada" pone `needs_review=false` y `user_verified=true` | 02-data-model.md (DAT-REQ-018/019), 04-wardrobe-api.md (API-REQ-019/020), 03-garment-ingestion.md, 07-app-ui.md (UI-REQ-021) |

## Mapeo de las fases del borrador (0–5) a las specs

El borrador original organiza el trabajo en seis fases secuenciales. Esta tabla las mapea a las specs granulares, señalando qué partes de la Fase 5 se descartan por estar aplazadas.

| Fase del borrador | Contenido original | Specs correspondientes |
| --- | --- | --- |
| Fase 0: base del proyecto | Monorepo, Docker Compose, login | 01-dev-tooling.md cubre el monorepo y las herramientas; **Docker Compose y login se descartan** (aplazados, D0/auth aplazada) — la iteración 1 usa procesos locales sin auth. |
| Fase 1: armario manual | Tablas `garment`/`jobs`, endpoints CRUD, subida con rembg, pantallas Armario/Añadir/Detalle | 02-data-model.md, 03-garment-ingestion.md, 04-wardrobe-api.md, 07-app-ui.md |
| Fase 2: categorización automática | Colores KMeans, LLM con visión, embeddings CLIP, pantalla Revisión | 03-garment-ingestion.md, 04-wardrobe-api.md (flujo de revisión), 07-app-ui.md |
| Fase 3: motor de outfits | Plantillas, filtros, puntuación, endpoint `generate`, pantalla Hoy | 05-outfit-engine.md, 07-app-ui.md |
| Fase 4: favoritos, historial y aprendizaje | Tablas `outfit`/`outfit_item`/`wear_log`, feedback, no repetir, pantallas Favoritos/Historial | 06-feedback-history.md, 05-outfit-engine.md (no repetir), 07-app-ui.md |
| Fase 5: pulido y despliegue | Despliegue VPS/Tailscale, Litestream/R2, builds EAS, caché offline, exportación de datos | **Descartada por completo.** Docker/VPS/Tailscale/EAS, backups (Litestream/R2), caché offline y exportación ZIP están todos en la sección "Aplazado" de c4.md. Lo único de esta fase que sobrevive a la iteración 1 son las dos preparaciones que c4.md sí deja listas: rutas de imagen relativas (03-garment-ingestion.md) y una API sin estado de sesión (04-wardrobe-api.md), ambas pensadas para no tener que rehacer nada cuando se retome esta fase. |
| (Fase 2 del borrador, sección separada): try-on virtual y extras | Fotos del usuario, modelos de try-on, clima, ocasión, huecos en el armario | **Fuera de alcance**, renombrada "v2" (D12). No tiene spec en este directorio. |

## Dependencias entre specs

`01-dev-tooling.md` es la base de la que dependen todas las demás (estructura de proyecto, comandos). `02-data-model.md` es la base de datos de la que dependen `03`, `04`, `05` y `06`. `03-garment-ingestion.md` y `04-wardrobe-api.md` comparten el router de prendas/jobs. `05-outfit-engine.md` consume el historial de `06-feedback-history.md` (favoritos, `wear_log`) como una de sus fuentes de puntuación. `07-app-ui.md` depende de los contratos de endpoint de `03`–`06`.

## Preguntas abiertas transversales

Cada spec detalla sus propias preguntas abiertas en su sección final. Las que afectan a más de una spec:

- **Proveedor y modelo exacto del LLM con visión** — el borrador nombra ejemplos ("Claude Haiku 4.5 o Gemini Flash") sin decidir; c4.md solo exige que el `PACHAPP_LLM_MODEL_ID` esté fijado (D11), no cuál. Afecta a 01-dev-tooling.md (variable de entorno) y 03-garment-ingestion.md (contrato); sigue sin resolver.
- **Cuántas prendas tiene realmente el usuario** — pregunta abierta original del borrador, relevante para validar que K≈300 y su ampliación dinámica (05-outfit-engine.md, ENG-REQ-024/025) son realistas.

Resueltas por decisiones posteriores del usuario (ya no son preguntas abiertas transversales):
- **Temporada (D8):** se descarta por completo — sin filtro ni puntuación por temporada en la iteración 1, y por tanto sin pregunta de hemisferio que resolver (la columna `setting.hemisphere` queda retirada, 02-data-model.md).
- **Máximo de colores no neutros (D18):** queda fijo en 2, no configurable, filtro duro, y los complementos (`accessory`) no cuentan para ese máximo — no queda ninguna de estas tres alternativas abierta (05-outfit-engine.md ENG-REQ-007/011, columna `setting.max_non_neutral_colors` retirada).
- **Flujo de "revisión terminada" (D19):** queda como una acción única y explícita, `POST /garments/{id}/review/complete` (04-wardrobe-api.md API-REQ-019), que es la única vía para limpiar `needs_review` y fijar `user_verified`; corregir campos individuales nunca los cambia (02-data-model.md DAT-REQ-018/019).
