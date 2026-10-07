# Spec — Probador virtual ("Verlo puesto") con CatVTON

Estado: borrador para implementar · Fecha: 2026-10-04

## 1. Objetivo

Que el usuario pueda ver un outfit (el look del día o cualquier combinación de prendas) **puesto sobre un modelo neutro**, generado en local con **CatVTON** en la GPU del backend.

Hoy el look se muestra como un collage de recortes. "Verlo puesto" es una vista **adicional, bajo demanda y asíncrona**: no sustituye al collage ni bloquea la pantalla Hoy.

## 2. Alcance

**Incluido (v1)**
- Generar una imagen "puesta" para 1–3 prendas de ropa (parte de arriba, parte de abajo, vestido/mono, capa intermedia y abrigo).
- Un único **maniquí/modelo neutro** por defecto, servido por el backend.
- Trabajo asíncrono con progreso, siguiendo el **mismo patrón de jobs** que el pipeline de subidas (`status`, `step`, `progress`, `error`).
- Caché de resultados: la misma combinación no se genera dos veces.
- Botón "Verlo puesto" en la tarjeta del look (Hoy) y en las alternativas.

**Excluido (v1)**
- Fotos del propio usuario como modelo (requiere consentimiento y tratamiento de datos sensibles; queda para v2).
- Calzado y complementos dentro de la imagen generada (CatVTON no los soporta bien): se muestran como miniaturas junto al resultado.
- Varias poses o tipos de cuerpo (preparar el modelo de datos para ello, pero con un solo maniquí).
- Generación automática nocturna (posible v2 una vez medido el rendimiento).

## 3. Restricciones

| Restricción | Implicación |
|---|---|
| **GPU con 6 GB de VRAM** | fp16, resolución reducida, descarga a CPU, una generación cada vez; ver §6 |
| La GPU ya se usa para recortar y detectar | Bloqueo de GPU compartido; liberar memoria antes y después; ver §6.4 |
| **Licencia de CatVTON: CC BY-NC-SA 4.0** (no comercial) | Válido para uso personal. **No usar en un producto comercial** sin cambiar de modelo o de proveedor. Dejarlo anotado en el README del backend. |
| Sin GPU en CI | La pipeline se abstrae tras una interfaz y se sustituye por un *fake* en los tests |
| La app debe seguir funcionando si la función está desactivada o falla | Feature flag `TRYON_ENABLED`; el front oculta el botón si el API no la ofrece |

## 4. Fase 0 — Spike (obligatoria, antes de integrar nada)

Script independiente `backend/scripts/tryon_spike.py` (o la ruta equivalente del proyecto) que:

1. Descarga el código y los pesos de CatVTON siguiendo **su README oficial** (repo `Zheng-Chong/CatVTON`, pesos en Hugging Face). **Verificar** las versiones, el modelo base de inpainting y la API de inferencia en el repo: no asumirlas.
2. Genera 1 prenda de arriba, 1 de abajo y 1 outfit de 2 pasadas sobre el maniquí, con 3 configuraciones:
   - A: 768×576, 30 pasos
   - B: 512×384, 30 pasos
   - C: 768×576, 20 pasos
3. Mide y escribe en `tryon_spike_report.md`: **pico de VRAM** (`torch.cuda.max_memory_allocated`), tiempo por pasada, tiempo total, si hubo error por falta de memoria, y guarda las imágenes resultantes.
4. Prueba **dos maniquíes candidatos** (ver §5.1) y compara la calidad.

**Criterio para continuar:** al menos una configuración termina sin falta de memoria, en **≤ 90 s por outfit de 2 prendas**, con calidad aceptable a juicio del usuario. Si no se cumple → **parar** y proponer alternativas (API externa, maniquí 2D).

## 5. Diseño

### 5.1 Maniquí

- Imagen de cuerpo entero, de frente, pose neutra (brazos ligeramente separados del cuerpo), fondo liso claro y ropa ajustada y neutra. Relación de aspecto 3:4.
- CatVTON está entrenado con personas: probablemente un **modelo humano neutro** funcione mejor que un maniquí de plástico. El spike decide.
- Origen: imagen generada para este fin o de stock con licencia que lo permita. Guardar en `assets/tryon/mannequins/<id>/` con `person.png` y `meta.json` (licencia, origen).
- **Máscaras precalculadas:** como el maniquí es fijo, se calculan **una sola vez** las máscaras `upper`, `lower` y `overall` (con el AutoMasker de CatVTON, que usa DensePose y SCHP) y se guardan como PNG junto a la imagen. **En ejecución no se cargan DensePose ni SCHP** (ahorra VRAM y tiempo). Script: `scripts/tryon_build_masks.py <mannequin_id>`.

### 5.2 De categoría a tipo de prenda de CatVTON

| Categoría de la app | `cloth_type` | Máscara |
|---|---|---|
| Pantalón (incl. shorts, faldas) | `lower` | `lower` |
| Top | `upper` | `upper` |
| Capa intermedia | `upper` | `upper` |
| Abrigo | `upper` | `upper` |
| Vestido / mono | `overall` | `overall` |
| Calzado, Complemento | — | No se genera; miniatura aparte |

Las claves internas de categoría del backend (`shoes`, etc.) deben mapearse en un único sitio (`tryon/mapping.py`).

### 5.3 Orden de pasadas

CatVTON viste **una prenda por pasada**. La salida de una pasada es la imagen de entrada de la siguiente; la máscara se toma siempre del maniquí base (la pose no cambia).

Orden: `overall` **o** (`lower` → `upper` interior → capa intermedia → abrigo).

- Máximo **3 pasadas** en v1 (configurable). Si un outfit tiene más prendas superiores, se toma la más exterior y la interior y se descartan las intermedias (se informa en la respuesta `skipped_garment_ids`).
- Vestido/mono + abrigo → `overall` y luego `upper`.

### 5.4 Imagen de la prenda

- Usar el **recorte** (`img_cutout`) compuesto sobre **fondo blanco**, centrado y escalado a la resolución de trabajo con margen. Comprobar en el spike si funciona mejor que la foto original; si el original es mejor, usarlo.
- Nota: los recortes actuales a veces incluyen restos del modelo (piel, otras prendas). Empeoran el resultado; está fuera del alcance de esta spec, pero hay que anotarlo en el informe del spike si se observa.

### 5.5 Parámetros por defecto (ajustables con variables de entorno)

| Variable | Por defecto | Notas |
|---|---|---|
| `PACHAPP_TRYON_ENABLED` | `false` | Feature flag |
| `PACHAPP_TRYON_WIDTH` × `PACHAPP_TRYON_HEIGHT` | 576 × 768 | Según el V0; múltiplos de 8 |
| `PACHAPP_TRYON_STEPS` | 20 | Según el V0 |
| `PACHAPP_TRYON_GUIDANCE` | 2.5 | |
| `PACHAPP_TRYON_SEED` | 42 | Resultado reproducible |
| `PACHAPP_TRYON_DTYPE` | `fp16` | GPUs Turing (RTX 20xx / GTX 16xx): **no** usar bf16 |
| `PACHAPP_TRYON_MAX_PASSES` | 3 | |
| `PACHAPP_TRYON_IDLE_UNLOAD_SECONDS` | 300 | Descargar el modelo de la GPU tras estar inactivo; 0 = nunca |
| `PACHAPP_TRYON_OOM_RETRY_WIDTH` × `PACHAPP_TRYON_OOM_RETRY_HEIGHT` | 384 × 512 | Reintento único tras un OOM de CUDA |
| `PACHAPP_TRYON_MANNEQUIN` | `m12-woman-crop-shorts` | Maniquí por defecto (`assets/tryon/mannequins/<id>/`) |
| `PACHAPP_TRYON_ASSETS_DIR` / `PACHAPP_TRYON_CATVTON_DIR` | `<repo>/assets/tryon` / `<data dir>/vendor/CatVTON` | Activos versionados / clon externo fijado de CatVTON |
| `PACHAPP_TRYON_BASE_REVISION` / `PACHAPP_TRYON_ATTN_REVISION` | commits fijados | Se rechazan refs móviles |

Sin `CPU_OFFLOAD`: la pipeline de CatVTON no es una `DiffusionPipeline` (§12.9). Los pesos van a `PACHAPP_ML_CACHE_DIR`, no a un `TRYON_WEIGHTS_DIR`.

## 6. Arquitectura del backend

### 6.1 Módulos (adaptar a la estructura existente)

```
tryon/
  mapping.py      # categoría → cloth_type/máscara, orden de pasadas
  cache.py        # cálculo de cache_key
  engine.py       # interfaz TryOnEngine + CatVTONEngine (carga perezosa, descarga)
  fake_engine.py  # para tests: devuelve una imagen determinista sin GPU
  service.py      # orquesta: valida, consulta la caché, crea el job, ejecuta las pasadas
  router.py       # endpoints FastAPI
```

### 6.2 Interfaz del motor

```python
class TryOnEngine(Protocol):
    def load(self) -> None: ...
    def unload(self) -> None: ...
    def dress(self, person: Image, garment: Image, mask: Image, cloth_type: str, params: TryOnParams) -> Image: ...
```

### 6.3 Ejecución

- Reutilizar el **mecanismo de jobs/cola que ya usa el pipeline de subidas** (no crear otro sistema). Si los jobs de subida y de prueba comparten worker, la prioridad la tienen las subidas.
- **Pasos del job** (`step`): `queued` → `loading_model` → `dressing_1` … `dressing_n` → `finalizing` → `done` / `failed`. El `progress` se reparte de forma proporcional entre las pasadas (con callback por paso de difusión si la pipeline lo permite).
- Concurrencia de generación = 1.

### 6.4 Gestión de memoria de la GPU

- **Bloqueo de GPU global** (el mismo que usen recortes y detección, o uno nuevo que todos respeten). La prueba virtual lo adquiere para toda la secuencia de pasadas.
- Antes de cargar CatVTON: descargar o mover a CPU los modelos de recorte y detección si están residentes, y llamar a `torch.cuda.empty_cache()`.
- fp16, SDPA (o xformers si está disponible), VAE slicing/tiling y `enable_model_cpu_offload` si `TRYON_CPU_OFFLOAD`.
- Carga perezosa; descarga tras `TRYON_IDLE_UNLOAD_SECONDS` sin uso.
- **Falta de memoria (OOM):** capturar `torch.cuda.OutOfMemoryError`, liberar, **reintentar una vez a 512×384**; si vuelve a fallar → `failed` con `error="out_of_memory"`.

### 6.5 Caché

`cache_key = sha256(mannequin_id, mannequin_version, [ (garment_id, hash_de_imagen_del_recorte) en orden de pasada ], width, height, steps, guidance, seed, model_version)`

- Si existe un render `done` con esa clave → se devuelve directamente.
- Si una prenda se edita y cambia su recorte, la clave cambia sola.
- Limpieza: borrar los renders sin acceder desde hace más de N días (configurable; puede quedar para v2).

### 6.6 Modelo de datos

Tabla `tryon_renders` (ajustar al ORM y las convenciones de migraciones del proyecto):

| Campo | Tipo |
|---|---|
| `id` | uuid |
| `cache_key` | text, único |
| `mannequin_id` | text |
| `garment_ids` | uuid[] / json (orden de pasada) |
| `skipped_garment_ids` | json |
| `outfit_id` | uuid nullable |
| `status`, `step`, `progress`, `error` | igual que los jobs existentes |
| `img_path` | text nullable (`tryon/<id>.webp`) |
| `params` | json |
| `duration_ms`, `peak_vram_mb` | int nullable |
| `created_at`, `last_accessed_at` | timestamptz |

### 6.7 API

Seguir el estilo de los endpoints existentes y **regenerar el cliente** (`make gen-client`).

- `GET /tryon/capabilities` → `{ enabled: bool, supported_categories: [...], max_passes: 3 }`. El front lo usa para mostrar u ocultar el botón.
- `POST /tryon` body `{ garment_ids: uuid[] } | { outfit_id: uuid }`, `mannequin_id?`
  - `200` si ya estaba en caché (`status: "done"`), `202` si se ha creado el job.
  - `422` si no hay ninguna prenda compatible; `503` si `TRYON_ENABLED=false`.
- `GET /tryon/{id}` → estado del render (para el polling).
- La imagen se sirve con el mismo mecanismo que `images/cutout/...` → `images/tryon/<id>.webp`.

Respuesta:

```json
{
  "id": "…",
  "status": "running",
  "step": "dressing_2",
  "progress": 55,
  "error": null,
  "img": null,
  "garment_ids": ["…", "…"],
  "skipped_garment_ids": ["…"],
  "unsupported_garment_ids": ["…zapatillas…"]
}
```

## 7. Frontend (Expo)

Seguir el sistema de diseño ya implementado (tokens de `src/theme`, componentes base).

- **Botón "Verlo puesto"** (secundario, icono de persona o percha) en la tarjeta del look de Hoy y en cada alternativa. Solo si `capabilities.enabled`.
- Al pulsarlo: `POST /tryon` y luego **polling con TanStack Query** (`refetchInterval` mientras `status` sea `queued` o `running`), igual que las subidas.
- **Vista del resultado** en el mismo lienzo del look, con un control segmentado **Collage | Puesto**:
  - Mientras genera: el collage se ve atenuado + barra de progreso terracota + texto del paso ("Preparando el probador…", "Vistiendo la parte de abajo…", "Vistiendo la parte de arriba…", "Últimos retoques…") + "Puede tardar alrededor de un minuto. Puedes seguir usando la app."
  - Resultado: imagen generada a 3:4 + miniaturas del calzado y los complementos debajo ("No incluidos en la imagen") + una etiqueta pequeña "Imagen generada · aproximación".
  - Error: `ErrorState` común con un texto amable ("No hemos podido probar este look. Inténtalo de nuevo.") y **Reintentar**.
- Si el usuario se va de la pantalla, el job sigue. Al volver, se muestra el resultado (la caché de TanStack Query + `GET /tryon/{id}`).
- Accesibilidad: `accessibilityLabel` en el resultado ("Outfit puesto en un modelo: jersey negro, pantalón beige").

## 8. Tests

- **Backend (sin GPU, con `FakeEngine`)**: mapeo de categorías, orden de pasadas y descarte, `cache_key` (estable y que cambia al cambiar un recorte), estados del job, endpoint en caché vs. nuevo, `503` con el flag desactivado, `422` sin prendas compatibles, ruta de OOM (el fake lanza el OOM la primera vez → reintento a resolución baja).
- **Frontend**: el botón se oculta si la función no está activa; estados en curso, resultado y error; el control Collage | Puesto.
- **Manual / benchmark**: `scripts/tryon_spike.py` reutilizable para medir tras cambios de parámetros.

## 9. Criterios de aceptación

1. Con `TRYON_ENABLED=true`, el look del día de 2–3 prendas de ropa genera una imagen "puesta" **sin falta de memoria en 6 GB**, en un tiempo dentro del objetivo medido en el spike.
2. Pedir otra vez el mismo look devuelve el resultado **al instante** desde la caché.
3. Recortar y detectar prendas nuevas sigue funcionando mientras hay una prueba en cola (sin conflictos de GPU ni errores por falta de memoria).
4. Con `TRYON_ENABLED=false` la app funciona igual que antes y no aparece el botón.
5. `tsc`, ESLint, Jest y los tests del backend pasan; el cliente está regenerado.
6. La licencia no comercial está documentada.

## 10. Fases

0. **Spike + informe** (§4) → para y espera la validación del usuario.
1. Maniquí + máscaras precalculadas + `CatVTONEngine` + gestión de GPU.
2. Servicio, caché, tabla, jobs y endpoints + tests del backend + `make gen-client`.
3. Frontend: botón, polling, vista Collage | Puesto, estados + tests.
4. Pulido: textos, limpieza de la caché y documentación.

## 11. Preguntas abiertas

- ¿Qué GPU exacta es? Define fp16 o bf16 y la resolución.
- ¿Maniquí de plástico o modelo humano neutro? ¿Masculino, femenino o ambos? (v1: uno.)
- ¿Recorte sobre fondo blanco o foto original como entrada? (Lo decide el spike.)
- ¿El worker de jobs actual es un proceso aparte o va en el mismo proceso que uvicorn? Afecta a dónde vive el modelo cargado.

## 12. Notas de integración con el repo (2026-10-04)

Respuestas y riesgos detectados al contrastar este borrador con el código y la máquina de referencia. Prevalecen sobre las suposiciones de arriba donde las contradigan.

**Respuestas a las preguntas abiertas (§11)**

- GPU: NVIDIA GeForce RTX 2060, 6 GB (Turing) → `fp16`, nunca `bf16`.
- El worker es un proceso aparte (`python -m worker.main`, `backend/src/worker/`) que ya carga BiRefNet y SigLIP de forma perezosa (`worker.ai.LazyModels`). CatVTON vive en ese mismo proceso: el worker ejecuta una inferencia cada vez (VIS-REQ-025), así que no hace falta un bloqueo de GPU entre procesos; basta con descargar los modelos residentes antes de cargar CatVTON y recargarlos después (§6.4).
- Maniquí y entrada de la prenda (recorte o foto): los decide el spike, como estaba previsto.

**Riesgos y ajustes**

1. VRAM: con el worker cargado se midieron 5,7 de 6 GB ocupados; el probador DEBE descargar BiRefNet y SigLIP antes de cargar CatVTON. La primera subida tras una prueba paga la recarga.
2. RAM de WSL: unos 7 GB en total. `enable_model_cpu_offload` mueve pesos a RAM y un spike anterior (evaluación de U5) murió por falta de memoria con el stack levantado. El spike DEBE ejecutarse con la API, el worker y Expo parados y medir también el pico de RAM, no solo el de VRAM.
3. Jobs: la tabla `job` tiene `garment_id` obligatorio y pasos propios de la subida (`JobStep`). Se adopta la tabla `tryon_renders` de §6.6 con sus propios estados, y el worker la consulta después de los jobs de subida (las subidas tienen prioridad). No se generaliza `job`.
4. Calidad de los recortes: el recorte actual puede incluir piel y otras prendas; U5 (recorte solo de la prenda, `odd/tasks/u5-garment-cutout.md`) es requisito recomendado. El spike compara recortes actuales y recortes limpios.
5. Sin conexión: el APK de Android guarda datos e imágenes para verlos sin backend (`odd/tasks/offline-app.md`). Los renders ya generados deberían guardarse en disco igual que las miniaturas (no previsto arriba; tarea pequeña de la fase 3).
6. Código de CatVTON: no es un paquete pip y su licencia es CC BY-NC-SA 4.0 (con "compartir igual"); se usa como dependencia externa fijada (git o carpeta fuera del repo), no copiado dentro del repositorio.
7. Los looks del motor no se persisten al generarlos (D6): `POST /tryon` por `garment_ids` es la vía principal; `outfit_id` es opcional.
8. Mapeo de categorías de la app: `top`, `mid_layer`, `outerwear` → `upper`; `bottom` → `lower`; `one_piece` → `overall`; `shoes`, `accessory` → no se generan (miniaturas).
9. API real de CatVTON (lectura del código en `7818397f`, detalle en `odd/tasks/virtual-tryon.md`): `CatVTONPipeline` no es una `DiffusionPipeline` de diffusers, así que no hay `enable_model_cpu_offload` ni callback por paso. El progreso se cuenta envolviendo `noise_scheduler.step`. Los pesos en fp16 ocupan unos 2 GB, así que la descarga a CPU de §5.5 queda pendiente de las medidas del spike. El VAE (`stabilityai/sd-vae-ft-mse`) va fijo en el código, sin revisión, y el filtro de seguridad de SD se desactiva. Los pesos van a `PACHAPP_ML_CACHE_DIR`, no a `TRYON_WEIGHTS_DIR`.
