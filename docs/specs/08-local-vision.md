# 08 — Visión local (recorte, atributos, embedding)

Estado: Draft

Deriva de `SPEC-ML.md` (raíz del repo), adaptado a la arquitectura aprobada: sustituye la implementación de los pasos `cutout`, `ai_attributes` y `embedding` del pipeline del worker (03-garment-ingestion.md) por modelos abiertos que corren en el propio proceso worker. El LLM con visión, antes obligatorio, queda como respaldo opcional y desactivado por defecto.

## Objetivo y alcance

**Objetivo.** Que el recorte, los atributos y el embedding de una prenda se calculen en local, sin coste por prenda ni dependencia obligatoria de un LLM, y que la clasificación mejore con las correcciones que el usuario ya guarda en `ai_correction`.

**Dentro de alcance**

- Quitar el fondo con BiRefNet (vía `rembg`).
- Embeddings y clasificación zero-shot con Marqo-FashionSigLIP (vía `open_clip`).
- Refinamiento por vecinos (kNN) sobre las prendas con `user_verified = true`.
- LLM con visión como respaldo cuando la confianza sea baja, desactivable y desactivado por defecto.
- Script de evaluación con un conjunto de imágenes etiquetadas.

**Fuera de alcance**

- Try-on virtual y segmentación de ropa en fotos de persona (`mattmdjaga/segformer_b2_clothes`) — parte de "v2" (D12), fuera de la iteración 1.
- Modelo entrenado de compatibilidad de outfits.
- Inferencia en el dispositivo (ONNX / Transformers.js).
- Docker/VPS para servir estos modelos — ver "Despliegue" más abajo; aplazado junto con el resto de infraestructura (c4.md, sección "Aplazado").

## Dependencias

- Decisiones de c4.md: D11 (versión de modelo fijada — el mismo principio se aplica aquí al modelo de embedding), D14 (datos/caché fuera de `/mnt/*`), D16 (Settings único, Pydantic v2), D17 (categoría `mid_layer`), D19 (revisión con un único botón — gobierna qué alimenta el kNN).
- Specs: 01-dev-tooling.md (estructura del monorepo, Makefile, settings), 02-data-model.md (enums, columnas `garment`), 03-garment-ingestion.md (pasos del pipeline que esta spec reimplementa), 04-wardrobe-api.md (API-REQ-019, acción "Revisión terminada").
- Sustituye/detalla: `SPEC-ML.md` (raíz), del que hereda el objetivo, los modelos y el algoritmo, adaptados aquí a la estructura y settings reales.

## Modelos y licencias

| Uso | Modelo | Licencia | Notas |
| --- | --- | --- | --- |
| Quitar fondo | `birefnet-general-lite` vía `rembg` (copia fp16 en `cuda`) | MIT | Por defecto desde 2026-09-29 (ver nota en VIS-REQ-026); `birefnet-general` sigue disponible vía `PACHAPP_ML_BG_MODEL` |
| Embeddings + zero-shot | `hf-hub:Marqo/marqo-fashionSigLIP` vía `open_clip` | Apache 2.0 | La dimensión del embedding se lee del modelo en tiempo de ejecución; no se fija en el código |
| Recorte solo de la prenda (U5) | `fashn-ai/fashn-human-parser` (SegFormer-B4, 18 clases), revisión fijada en `PACHAPP_ML_PARSE_FASHN_REVISION` | Licencia fuente de NVIDIA SegFormer (no comercial; aceptada, uso personal) | Se carga bajo demanda en el primer job (fp16 en `cuda`, ~320 MB de pico en torch) y se mantiene residente; ver VIS-REQ-031 |
| Respaldo | LLM con visión vía API (`PACHAPP_LLM_*`) | — | Solo si `PACHAPP_ML_LLM_FALLBACK=true` |

**VIS-REQ-001.** El sistema NO DEBE usar `RMBG-2.0` como modelo de recorte por defecto, por su licencia no comercial; PUEDE activarse a mano vía `PACHAPP_ML_BG_MODEL=rmbg-2.0` para uso estrictamente personal, con esa condición documentada en `.env.example`.

**VIS-REQ-002.** La revisión (commit/tag) del modelo de embedding DEBE fijarse en `PACHAPP_ML_EMBED_REVISION`, análogo a `PACHAPP_LLM_MODEL_ID` (D11): sin alias `latest`, para que los embeddings existentes sigan siendo comparables entre arranques del worker.

## Paquete y límites de proceso

**VIS-REQ-003.** El código de visión DEBE vivir en un nuevo paquete `backend/src/ml/` (junto a `api`, `worker`, `engine`, `shared`), añadido a `[tool.hatch.build.targets.wheel].packages` en `backend/pyproject.toml`.

**VIS-REQ-004.** `ml` DEBE ser usado únicamente por `worker`. `api` NO DEBE importar `ml` bajo ninguna circunstancia — los modelos (BiRefNet, SigLIP, y el cliente LLM de respaldo) NUNCA se cargan en el proceso API, solo en el worker (coincide con c4.md, tabla de contenedores). `engine` sigue sin I/O y por tanto tampoco importa `ml` (DEV-REQ-002).

**VIS-REQ-005.** DEBE existir un test (análogo al de "sin I/O" de `engine`, DEV-REQ-002) que falle si algún módulo bajo `backend/src/api/` importa, directa o transitivamente, `ml` — por ejemplo, un test de `tests/unit/` que inspeccione el grafo de imports de `api` o que verifique con `grep`/`ast` que ningún fichero de `api` contiene `import ml` / `from ml`.

## Configuración

Todas las claves nuevas usan el prefijo `PACHAPP_ML_` en el mismo modelo `Settings` de `pydantic-settings` (D16), igual que el resto de `01-dev-tooling.md`. *(Valores por defecto, ajustables, salvo donde se indique obligatorio.)*

| Clave | Valor por defecto | Notas |
| --- | --- | --- |
| `PACHAPP_ML_DEVICE` | `auto` | `auto` \| `cpu` \| `cuda` \| `mps`; `auto` prueba `cuda` > `mps` > `cpu` |
| `PACHAPP_ML_CACHE_DIR` | `${PACHAPP_DATA_DIR}/models` | Caché de todos los modelos (BiRefNet/rembg y SigLIP/open_clip); sujeta a la misma guardia `/mnt/*` que `PACHAPP_DATA_DIR` (D14) |
| `PACHAPP_ML_BG_MODEL` | `birefnet-general-lite` | Ver VIS-REQ-001 y la nota de VIS-REQ-026 |
| `PACHAPP_ML_BG_FP16` | `true` | Usa una copia fp16 del modelo de recorte solo cuando el dispositivo resuelto es `cuda` (`cpu`/`mps` conservan fp32); la conversión se hace una vez en `make ml-preload` (`onnx` + `onnxconverter-common`) |
| `PACHAPP_ML_GARMENT_PARSE` | `true` | Recorte solo de la prenda con el parser FASHN tras el matte de BiRefNet (VIS-REQ-031); `false` conserva el recorte de BiRefNet tal cual |
| `PACHAPP_ML_EMBED_MODEL` | `hf-hub:Marqo/marqo-fashionSigLIP` | Identificador de `open_clip` |
| `PACHAPP_ML_EMBED_REVISION` | *(ninguno — obligatorio)* | Ver VIS-REQ-002 |
| `PACHAPP_ML_MARGIN_THRESHOLD` | `0.15` | Diferencia mínima top1 − top2; ver regla de `needs_review` más abajo |
| `PACHAPP_ML_KNN_K` | `7` | Vecinos para el refinamiento kNN |
| `PACHAPP_ML_KNN_MIN_VERIFIED` | `30` | Prendas `user_verified=true` necesarias para activar el kNN |
| `PACHAPP_ML_LLM_FALLBACK` | `false` | Activa el respaldo LLM (ver más abajo) |
| `PACHAPP_ML_EVAL_DIR` | `${PACHAPP_DATA_DIR}/eval/garments` | Fixtures de evaluación; ver sección "Evaluación" |

### Reconciliación con settings ya existentes

**VIS-REQ-006.** El umbral de confianza que SPEC-ML llamaba `ML_CONF_THRESHOLD` NO DEBE convertirse en una clave `PACHAPP_ML_*` nueva: es el mismo umbral que ya gobierna `needs_review` en `02-data-model.md` (`setting.needs_review_threshold`, DAT-REQ-002, `0.7` por defecto, ajustable vía `PATCH /settings`). Un solo umbral, no dos.

**VIS-REQ-007.** El umbral de duplicados que SPEC-ML llamaba `ML_DUPLICATE_THRESHOLD` (`0.95`) NO DEBE convertirse en una clave `PACHAPP_ML_*` nueva: reutiliza `setting.duplicate_warning_threshold`, ya definido por D9/ING-REQ-023 (`0.92` por defecto, rango calibrado `0.90–0.95`). Un solo umbral, no dos.

Nota de diseño: esto deja dos familias de configuración distintas y reales en este repo — el modelo `Settings` de `pydantic-settings` (variables de entorno, D16, para lo operativo: device, modelos, caché, kNN) y la fila singleton `setting` de la base de datos (para lo ajustable por el usuario vía la API: pesos, umbrales de revisión y duplicados). `PACHAPP_ML_MARGIN_THRESHOLD` queda en la primera familia porque es nuevo y no tiene overlap con la segunda; si más adelante se quiere que el usuario lo ajuste desde la pantalla de Ajustes como los otros umbrales, movería a `setting` en una migración aparte (ver "Preguntas abiertas").

### Caché de modelos

**VIS-REQ-008.** El worker DEBE fijar, a partir de `PACHAPP_ML_CACHE_DIR`, tanto la variable de entorno `HF_HOME` (caché de Hugging Face Hub, usada por `open_clip`) como el directorio de modelos de `rembg` (`U2NET_HOME`) en su propio arranque de proceso (`worker.main`) — antes de cargar cualquier modelo. NO DEBE fijarse `HF_HOME` como variable suelta en `.env`/`.env.example`; ambas rutas se derivan de `PACHAPP_ML_CACHE_DIR` en código, para que quede sujeto a la validación D14 igual que `PACHAPP_DATA_DIR`.

## Estructura del código

```
backend/src/ml/
  __init__.py
  registry.py        # carga perezosa y única de modelos; selección de device
  background.py       # BackgroundRemover (BiRefNet vía rembg)
  embedder.py         # GarmentEmbedder (imagen y texto, SigLIP vía open_clip)
  taxonomy.py         # etiquetas por atributo y sus prompts en inglés
  zero_shot.py        # ZeroShotClassifier
  knn.py              # KNNRefiner sobre prendas con user_verified=true
  fallback.py         # LLMFallback (opcional, PACHAPP_ML_LLM_FALLBACK)
  pipeline.py          # orquesta cutout + zero-shot/kNN + embedding, devuelve GarmentAnalysis
  preload.py           # CLI: descarga/valida los modelos en PACHAPP_ML_CACHE_DIR (make ml-preload)
  eval.py              # CLI: métricas sobre PACHAPP_ML_EVAL_DIR (make ml-eval)
backend/src/worker/
  reembed.py           # CLI: recalcula embeddings/clasificación cuando cambia el modelo (make reembed)
```

**VIS-REQ-009.** `preload.py` y `eval.py` DEBEN exponerse como módulos ejecutables (`python -m ml.preload`, `python -m ml.eval`), y `reembed.py` como `python -m worker.reembed` — coherente con el resto de entradas del backend (`python -m worker.main`, 01-dev-tooling.md). El `Makefile` raíz DEBE añadir los targets `ml-preload`, `ml-eval` y `reembed` que invocan estos módulos con `uv run`.

**VIS-REQ-010.** `colors.py` (extracción de color por KMeans en CIELAB) NO se mueve a `ml`: ya está definido en 03-garment-ingestion.md (algoritmo de extracción de color) y no depende de ningún modelo de Hugging Face; se implementa como parte del paso `color` del worker, fuera de `ml`.

Interfaces mínimas (Python, tipado orientativo):

```python
class BackgroundRemover(Protocol):
    def remove(self, img: Image.Image) -> Image.Image: ...  # RGBA recortado a la bbox

class GarmentEmbedder(Protocol):
    dim: int             # leído del modelo en tiempo de ejecución, nunca fijo en el código
    model_id: str        # "<PACHAPP_ML_EMBED_MODEL>@<PACHAPP_ML_EMBED_REVISION>"
    def embed_image(self, img: Image.Image) -> np.ndarray: ...  # normalizado L2
    def embed_texts(self, texts: list[str]) -> np.ndarray: ...  # normalizado L2, con caché

class AttributePrediction(BaseModel):
    value: str | int | list[str]
    confidence: float
    source: Literal["zero_shot", "knn", "blend", "llm", "user"]

class GarmentAnalysis(BaseModel):
    cutout: Image.Image
    embedding: np.ndarray
    embedding_model: str          # id@revision, ver VIS-REQ-002
    embedding_dim: int
    attributes: dict[str, AttributePrediction]
    needs_review: bool
    possible_duplicate_of: str | None
```

## Taxonomía y prompts

**VIS-REQ-011.** Las claves de `TAXONOMY` por atributo de una sola etiqueta o multietiqueta DEBEN ser exactamente los valores de los enums de `02-data-model.md` (`GarmentCategory`, `GarmentPattern`, `StyleTag`), no las claves literales (algunas en español) de `SPEC-ML.md`. Los prompts en sí siguen en inglés (el modelo se entrenó en inglés); cada valor tiene varios prompts y se promedia el embedding de texto de cada uno (ensemble), cacheado al arrancar el worker.

```python
TAXONOMY = {
    "category": {  # GarmentCategory — cobertura completa de las 7 claves (D17)
        "top":        ["a t-shirt", "a shirt", "a polo shirt", "a blouse"],
        "bottom":     ["jeans", "trousers", "chinos", "shorts", "a skirt"],
        "one_piece":  ["a dress", "a jumpsuit"],
        "mid_layer":  ["a sweater", "a hoodie", "a cardigan", "an overshirt"],
        "outerwear":  ["a jacket", "a coat", "a blazer", "a parka"],
        "shoes":      ["sneakers", "boots", "leather shoes", "sandals"],
        "accessory":  ["a belt", "a scarf", "a cap", "a bag", "a watch"],
    },
    "pattern": {  # GarmentPattern — cobertura completa de las 5 claves
        "solid":     ["a plain solid-color garment"],
        "striped":   ["a striped garment"],
        "plaid":     ["a plaid garment", "a checked garment"],
        "printed":   ["a garment with a printed pattern", "a floral print garment"],
        "textured":  ["a textured knit garment", "a ribbed garment"],
    },
    "material": {  # texto libre (sin enum en 02-data-model.md); candidatos en español, igual que el resto de valores libres de la UI
        "algodón": ["a cotton garment"], "denim": ["a denim garment"],
        "lana": ["a wool garment"], "cuero": ["a leather item"],
        "lino": ["a linen garment"], "sintético": ["a polyester garment"],
    },
    "formality": {  # ordinal 1–5, coincide con garment.formality
        1: ["sportswear", "gym clothes"],
        2: ["casual everyday clothes"],
        3: ["smart casual clothes"],
        4: ["business clothes"],
        5: ["formal suit clothing", "black tie attire"],
    },
    "style_tags": {  # StyleTag — cobertura PARCIAL: 5 de 8 claves, ver "Preguntas abiertas"
        "casual": ["casual style"], "classic": ["classic style"],
        "street": ["streetwear style"], "minimal": ["minimalist style"],
        "sport": ["athletic style"],
        # "elegant", "bohemian", "preppy": sin prompts todavía — ver Preguntas abiertas
    },
}
PROMPT_TEMPLATES = ["a photo of {}", "{}, product photo on a plain background"]
```

**VIS-REQ-012.** La **subcategoría** (`garment.subcategory`, texto libre) DEBE fijarse a partir del prompt ganador dentro de la categoría elegida, traducido mediante un diccionario prompt→subcategoría (p. ej. "chinos" → `"chinos"`). Las **temporadas** (`garment.seasons`) y el **abrigo** (`garment.warmth`) NO se clasifican con el modelo: se derivan por reglas simples a partir de `material` y `subcategory` (ver campos en 02-data-model.md).

## Algoritmo de clasificación

Para cada atributo de una sola etiqueta (`category`, `subcategory` vía categoría, `pattern`, `material`):

**VIS-REQ-013.** El worker DEBE calcular primero un zero-shot: `logits = 100 · (img_emb @ label_embs.T)`, softmax sobre los valores del atributo.

**VIS-REQ-014.** Si hay al menos `PACHAPP_ML_KNN_MIN_VERIFIED` prendas con `user_verified = true` (D19 — ver más abajo qué alimenta este conjunto), el worker DEBE además calcular un refinamiento kNN: los `PACHAPP_ML_KNN_K` vecinos más cercanos por coseno entre esas prendas verificadas, con voto ponderado por similitud, dando `p_knn`.

**VIS-REQ-015.** La probabilidad final DEBE ser la mezcla `p = α · p_zs + (1 − α) · p_knn`, con `α = max(0.2, 1 − n_verified / 200)` (si no hay kNN activo, `p = p_zs`, es decir `α = 1`).

**VIS-REQ-016.** El worker DEBE marcar el atributo como de baja confianza (dispara `needs_review`, ver más abajo) cuando el top-1 de `p` sea `< setting.needs_review_threshold` (VIS-REQ-006) **o** cuando `top-1 − top-2 < PACHAPP_ML_MARGIN_THRESHOLD` — la regla de margen es nueva respecto a `02-data-model.md` DAT-REQ-002 y se define aquí en detalle.

En la iteración 1 esta regla dispara `needs_review` únicamente para `category` y `pattern`. `material` y `formality` se guardan con su valor y su confianza en `ai_confidence` (y siguen apareciendo como de baja confianza en la evaluación), pero no disparan `needs_review` hasta que exista kNN o calibración (decisión del usuario, 2026-09-29; motivo: con la regla literal ~90 % de las prendas de la evaluación pública quedaban marcadas, casi todas por `material`/`formality`, cuyas probabilidades zero-shot no están calibradas). `subcategory` y `style_tags` tampoco lo disparan.

Casos especiales:

**VIS-REQ-017.** `formality` (ordinal) DEBE calcularse como la media ponderada de las probabilidades (o de los vecinos si el kNN está activo), redondeada al entero más cercano en `[1, 5]`; su confianza es `1 − desviación_típica / 2`.

**VIS-REQ-018.** `style_tags` (multietiqueta) DEBE calcularse con una sigmoide por etiqueta sobre la similitud imagen–texto; se incluyen las etiquetas que superen un umbral `(valor por defecto, ajustable)`, con un máximo de 3.

**VIS-REQ-019.** Cada valor de `garment.ai_confidence` DEBE tener la forma `{value, confidence, source}` con `source ∈ {zero_shot, knn, blend, llm, user}` — ver "Cambios en el modelo de datos".

**VIS-REQ-020.** El respaldo LLM (`fallback.py`) SOLO DEBE invocarse cuando `PACHAPP_ML_LLM_FALLBACK=true` **y**, tras la mezcla zero-shot/kNN, `category` o `formality` sigan por debajo del umbral de confianza. Su respuesta se guarda con `source = "llm"` para esos campos únicamente.

**VIS-REQ-021.** Cuando `PACHAPP_ML_LLM_FALLBACK=true`, `PACHAPP_LLM_PROVIDER`, `PACHAPP_LLM_MODEL_ID` y `PACHAPP_LLM_API_KEY` DEBEN ser obligatorios y el arranque del worker DEBE fallar de inmediato si falta alguno (mismo patrón fail-fast que DEV-REQ-011, pero condicionado al flag). Cuando `PACHAPP_ML_LLM_FALLBACK=false` (por defecto), estas tres variables NO DEBEN exigirse.

**VIS-REQ-022.** Duplicados: si la similitud coseno con alguna prenda `status=active` existente supera `setting.duplicate_warning_threshold` (VIS-REQ-007), el worker DEBE rellenar `job.result.duplicate_candidate_garment_id` — mismo comportamiento no bloqueante que ING-REQ-023/024.

**VIS-REQ-023.** El kNN y la comprobación de duplicados DEBEN comparar únicamente embeddings con el mismo `embedding_model` (id@revisión, VIS-REQ-002) — un cambio de modelo o de revisión no debe mezclar vectores incompatibles; ver `reembed` más abajo.

**VIS-REQ-024.** El conjunto que alimenta el kNN (VIS-REQ-014) DEBE ser exactamente las prendas con `user_verified = true`. Por D19, ese campo solo pasa a `true` mediante `POST /garments/{id}/review/complete` (04-wardrobe-api.md, API-REQ-019) — corregir campos individuales vía `PATCH` (que sí escribe `ai_correction`, usado para el few-shot del respaldo LLM) NO añade la prenda al conjunto kNN por sí solo.

## Cambios en el modelo de datos

Respecto a `02-data-model.md` (detalle de la adaptación; los requisitos normativos están ahí: DAT-REQ-002, DAT-REQ-020 y DAT-REQ-021):

- `garment.embedding`: BLOB float32, dimensión leída del modelo (p. ej. SigLIP ViT-B/16 suele ser 768-d, pero el código NUNCA debe fijar ese número).
- Nuevas columnas `garment.embedding_model` (`id@revisión`, VIS-REQ-002) y `garment.embedding_dim` (entero, igual a `GarmentEmbedder.dim` en el momento de la escritura).
- `garment.ai_confidence`: pasa de `dict[str, float]` a `dict[str, {value, confidence, source}]` (VIS-REQ-019).
- Nuevo comando `reembed` (`python -m worker.reembed`, VIS-REQ-009): recalcula `embedding`, `embedding_model`, `embedding_dim` y las clasificaciones derivadas de todas las prendas activas cuando cambia `PACHAPP_ML_EMBED_MODEL`/`PACHAPP_ML_EMBED_REVISION`, **sin** tocar ningún campo cuyo `ai_confidence[campo].source == "user"` (o, para prendas sin ese detalle todavía, cuyo valor provenga de una fila `ai_correction` posterior a la última clasificación automática).

## Concurrencia y rendimiento

**VIS-REQ-025.** La iteración 1 DEBE correr con un único proceso worker y un único job a la vez (límite nuevo que introduce esta spec, motivado por la RAM que ocupan BiRefNet + FASHN + SigLIP cargados a la vez; c4.md no lo fijaba). Correr más de un proceso worker NO rompe la reclamación atómica del job (DAT-REQ-009 sigue garantizando que cada job lo procesa exactamente un worker), pero queda sin soporte en la iteración 1 por presupuesto de RAM, no por una limitación de la reclamación.

**Hardware de referencia (comprobado 2026-09-28):** NVIDIA RTX 2060 6 GB visible desde WSL2 (driver 591.86), 8 cores, ~7 GB de RAM disponibles en WSL2. `PACHAPP_ML_DEVICE=auto` debe preferir `cuda` en esta máquina.

**VIS-REQ-026.** Objetivo de rendimiento por prenda, de principio a fin del pipeline de visión (cutout + zero-shot + embedding, sin contar un eventual respaldo LLM): `< 10 s` en CPU (2 vCPU / 4 GB, objetivo de referencia de SPEC-ML) y `< 2 s` con GPU o Apple Silicon. En la máquina de referencia de arriba, con torch CUDA instalado, aplica el objetivo de `< 2 s`; con la variante CPU de torch (ver pregunta abierta), aplica el de `< 10 s`.

> **Decisión (2026-09-29, usuario): modelo de recorte por defecto = `birefnet-general-lite` en fp16.** En la RTX 2060 6 GB, BiRefNet fp32 a 1024 px supera la VRAM libre (~5,5 GB) y el controlador desborda a memoria compartida. Medido en régimen estable, por imagen (solo ORT): `birefnet-general` fp32 14 s (4,2 s con `cudnn_conv_algo_search=HEURISTIC` y `arena_extend_strategy=kSameAsRequested`); `birefnet-general` fp16 9 s; `birefnet-general-lite` fp32 6,5 s; `birefnet-general-lite` fp16 0,66 s, con máscaras IoU ≥ 0,9998 frente a fp32. Solo la variante lite fp16 cumple `< 2 s`. La calidad se confirma con la puerta de 18/20 recortes limpios (paso 2).

> **Nota de rendimiento (2026-09-29).** Con SigLIP (torch) residente en la misma GPU, el recorte pasó de ~0,6 s a 2,3–3,2 s por prenda de forma intermitente: el arena CUDA de onnxruntime crece hasta llenar la VRAM libre (~5,5 GB) aunque el modelo lite fp16 solo necesita ~3,3 GB de pico a 1024 px, y cuando SigLIP y el escritorio de Windows ocupan parte de la VRAM el controlador desborda a memoria compartida. Con VRAM reservada a propósito en el mismo proceso (1,6 GB) `session.run` pasaba de 0,6 s a 5,6 s. Se fija un tope duro `gpu_mem_limit = 4 GiB` (solo para `birefnet-general-lite` en fp16; con 3 GiB falla por falta de memoria) y `cudnn_conv_use_max_workspace=0`: el recorte queda en ~0,6 s por prenda incluso con VRAM ocupada, con máscaras idénticas byte a byte. `python -m ml.eval --pipeline` solapa el pre/post-procesado en CPU con la inferencia en GPU (misma salida, +7–12 % de prendas/s en lote).

## Despliegue

**VIS-REQ-027.** En la iteración 1, todo corre como procesos locales bajo WSL2 (D0) — sin Docker ni build de imagen. `make ml-preload` DEBE descargar/validar los modelos en `PACHAPP_ML_CACHE_DIR` antes del primer `make run-worker` (análogo al `preload_models.py` de `SPEC-ML.md`, adaptado de un paso de build de imagen a un target local).

Aplazado: empaquetar estos modelos en una imagen Docker o en un VPS (ver c4.md, sección "Aplazado" — infraestructura fuera de la iteración 1 en su totalidad); cuando se retome, `PACHAPP_ML_CACHE_DIR` como volumen persistente sustituye directamente al `HF_HOME=/data/...` de `SPEC-ML.md`.

## Evaluación

**VIS-REQ-028.** Las fotos de evaluación (20–40 imágenes reales etiquetadas) DEBEN vivir fuera del repositorio por defecto, bajo `PACHAPP_ML_EVAL_DIR` (por defecto `${PACHAPP_DATA_DIR}/eval/garments`, `*.jpg` + `labels.json` con categoría/subcategoría/estampado/formalidad) — son fotos personales del usuario. `python -m ml.eval` DEBE aceptar además un argumento de línea de comandos que sobreescriba el directorio.

**VIS-REQ-029.** `make test` NO DEBE descargar ningún modelo ni tocar la red: los tests unitarios de `ml` (selección de device, mezcla zero-shot/kNN, umbral de duplicados, mapeo de taxonomía) DEBEN usar embeddings sintéticos generados en el propio test, nunca el modelo real ni `PACHAPP_ML_EVAL_DIR`.

**VIS-REQ-031.** Recorte solo de la prenda (U5c, decisión del dueño 2026-10-05). Con `PACHAPP_ML_GARMENT_PARSE=true` y un remover que devuelva el matte sin recortar, el paso `cutout` ejecuta el parser FASHN justo después del matte de BiRefNet, en serie y en el mismo hilo del job (VIS-REQ-025). Hay persona en la foto solo con evidencia corporal real: píxeles de cara ≥ 0,5 % de la imagen, o de brazos/manos/piernas ≥ 5 % (el pelo, el torso o cualquier clase "de piel" por sí solos no cuentan). Sin persona se conserva el recorte de BiRefNet sin cambios. Con persona: ropa (top, mid_layer, outerwear, bottom, one_piece) = intersección del matte con el grupo de clases de la categoría (p. ej. bottom = pantalón + falda) rellenando los huecos cerrados que no sean cuerpo; calzado y accesorios = matte menos las clases de cuerpo; categoría desconocida (la categoría se lee de la base de datos y una subida nueva aún no la tiene porque `ai_attributes` corre después de `cutout`) = la mayor región entre ropa, calzado y accesorios: si gana calzado o accesorio, matte menos cuerpo; si gana ropa, intersección con esa región, salvo que un grupo de calzado/accesorio no elegido cubra ≥ 10 % del matte (`MIN_UNSELECTED_ITEM_RATIO`), en cuyo caso se conserva con matte menos cuerpo y `consolidate` marca `needs_review`. Si la máscara de la prenda queda por debajo del 1 % de la imagen, o el parser falla, se conserva el matte y `consolidate` marca `needs_review`. El paso `color` muestrea el recorte erosionado 4 px, sin la piel ni otras prendas del borde. Los tests usan parsers falsos, sin modelos ni red (VIS-REQ-029).

**VIS-REQ-032.** Re-recorte de prendas existentes (U5d). `python -m worker.recut` (`make recut-garments`, con el worker parado, VIS-REQ-025) recorre cada prenda con foto original y aplica la misma regla de VIS-REQ-031 (matte de BiRefNet + parser FASHN, con la categoría almacenada si existe). Solo cuando produce un recorte nuevo de la prenda, reescribe `cutout/{id}.png` y `thumb/{id}.webp` de forma atómica (el archivo anterior permanece hasta que el nuevo está completo), recalcula los colores (salvo que el usuario los haya corregido: fila `ai_correction` con `field="colors"`), el embedding SigLIP y los atributos IA que sigan vacíos y no sean del usuario (mismas reglas que `make backfill-ai`; los valores ya presentes no se recalculan). Sin persona, matte vacío o máscara demasiado pequeña se conserva el recorte anterior; la máscara pequeña marca `needs_review` salvo en prendas con `user_verified=true`; un fallo del parser cuenta como error y se reintenta en la siguiente ejecución. `garment.cutout_method` (DAT, columna nullable añadida por migración) registra el método/versión y hace la ejecución idempotente. Opciones: `--dry-run` (no carga modelos ni escribe), `--limit N`, `--ids`, `--out DIR` (hojas de contacto original | recorte antiguo | recorte nuevo) y un resumen final. Con `PACHAPP_ML_GARMENT_PARSE=false` el comando se niega a ejecutarse. `make ml-preload` también descarga el parser FASHN en la revisión fijada. Los tests usan fakes, sin modelos ni red (VIS-REQ-029).

**VIS-REQ-030.** `python -m ml.eval` DEBE reportar precisión por atributo, matriz de confusión de `category`, porcentaje marcado `needs_review` y tiempo medio por prenda.

## Plan de implementación

1. **Registro de modelos y device.** Hecho cuando: `make ml-preload` descarga BiRefNet y SigLIP en `PACHAPP_ML_CACHE_DIR`, y `ml.registry` informa qué `PACHAPP_ML_DEVICE` quedó seleccionado. Confirmar aquí con el usuario la variante de torch (CPU vs CUDA, ver Preguntas abiertas).
2. **Recorte con BiRefNet.** Hecho cuando: las fotos de `PACHAPP_ML_EVAL_DIR` salen recortadas sin restos visibles de fondo en al menos 18 de 20.
3. **Embedder y zero-shot.** Hecho cuando: `make ml-eval` da al menos un 85 % de acierto en `category` sin kNN.
4. **Integración en el pipeline del worker.** Hecho cuando: subir una foto desde la app rellena todos los atributos con su `source` y su `confidence` (VIS-REQ-019), y `embedding`/`embedding_model`/`embedding_dim` quedan escritos.
5. **kNN y mezcla.** Hecho cuando: con 30 prendas `user_verified=true`, `category` supera el 90 % y `formality` acierta ±1 en al menos el 90 %.
6. **Duplicados y `reembed`.** Hecho cuando: subir dos veces la misma prenda avisa del duplicado (VIS-REQ-022) y `make reembed` no toca los campos con `source="user"`.
7. **Respaldo LLM (opcional).** Hecho cuando: con `PACHAPP_ML_LLM_FALLBACK=true`, solo se llama al LLM para las prendas bajo el umbral tras la mezcla (VIS-REQ-020), y queda registrado cuántas llamadas se hicieron.

Pasos 1–3 no requieren la base de datos (solo imágenes + fixtures) y se priorizan antes que el resto del trabajo de Fase 1 pendiente; los pasos 4–7 dependen de que `02-data-model.md`/`03-garment-ingestion.md` ya estén implementados (ver nota de prioridad en `00-index.md`).

## Escenarios

**VIS-SCN-001 — Clasificación solo zero-shot (armario nuevo).**
Dado un armario con menos de 30 prendas `user_verified=true`,
Cuando se sube una prenda nueva,
Entonces `ai_attributes` usa `α=1` (solo `p_zs`), cada atributo queda con `source="zero_shot"`, y no se invoca el kNN.

**VIS-SCN-002 — Margen bajo dispara revisión aunque el top-1 sea alto.**
Dada una prenda cuyo zero-shot da `category="top"` con probabilidad `0.72` y `category="mid_layer"` con `0.68` (top-1 − top-2 = 0.04 < `PACHAPP_ML_MARGIN_THRESHOLD=0.15`),
Cuando termina `consolidate`,
Entonces `needs_review=true` por la regla de margen (VIS-REQ-016) aunque el top-1 (`0.72`) supere `setting.needs_review_threshold` (`0.7`).

**VIS-SCN-003 — Respaldo LLM desactivado por defecto.**
Dado `PACHAPP_ML_LLM_FALLBACK=false` (valor por defecto) y una prenda cuya mezcla zero-shot/kNN deja `category` por debajo del umbral,
Cuando termina `ai_attributes`,
Entonces no se realiza ninguna llamada de red al LLM, `category` queda con el valor de la mezcla y `source="blend"` (o `"zero_shot"`), y `needs_review=true`.

**VIS-SCN-004 — `reembed` tras cambiar de modelo.**
Dado que `PACHAPP_ML_EMBED_REVISION` cambia y el usuario corrigió manualmente el campo `pattern` de la prenda X (`ai_confidence.pattern.source == "user"`),
Cuando se ejecuta `make reembed`,
Entonces `embedding`, `embedding_model` y `embedding_dim` de todas las prendas activas se recalculan, pero `pattern` de la prenda X permanece intacto.

**VIS-SCN-005 — El kNN no se activa solo con correcciones.**
Dado un armario con 40 prendas corregidas vía `PATCH` (con filas `ai_correction`) pero ninguna con "Revisión terminada" pulsada,
Cuando se sube una prenda nueva,
Entonces `user_verified=true` sigue en 0 prendas, el kNN no se activa (`α=1`), y solo el zero-shot participa en la clasificación — las correcciones sin verificar alimentan el few-shot del respaldo LLM (si está activo) pero no el kNN (VIS-REQ-024).

## Criterios de aceptación

- `make ml-preload` deja los modelos listos en `PACHAPP_ML_CACHE_DIR` sin ninguna variable `HF_HOME` puesta a mano en `.env`.
- `make ml-eval` produce el reporte de VIS-REQ-030 sobre `PACHAPP_ML_EVAL_DIR` sin tocar la base de datos.
- `make test` pasa sin red y sin `PACHAPP_ML_EVAL_DIR` presente (VIS-REQ-029).
- El test de frontera `api`/`ml` (VIS-REQ-005) falla si alguien añade un `import ml` dentro de `backend/src/api/`.
- Con `PACHAPP_ML_LLM_FALLBACK=false`, arrancar el worker sin `PACHAPP_LLM_*` en `.env` no falla (VIS-REQ-021).

## Preguntas abiertas

- **Variante de torch (CPU vs CUDA).** Pendiente de confirmar con el usuario en el paso 1 del plan de implementación: la máquina de referencia tiene una RTX 2060 6 GB visible desde WSL2, lo que hace viable CUDA, pero el tamaño de descarga/instalación y el consumo de RAM en WSL (~7 GB disponibles) son mayores que con la variante CPU. Determina si aplica el objetivo de rendimiento `<2 s` o `<10 s` por prenda (VIS-REQ-026).
- **Cobertura incompleta de `style_tags`.** El `TAXONOMY` de arriba solo define prompts para 5 de los 8 valores de `StyleTag` (`casual`, `classic`, `street`, `minimal`, `sport`); `elegant`, `bohemian` y `preppy` no tienen prompts en `SPEC-ML.md` y quedan sin definir aquí — hasta que se decidan y calibren, esos tres valores solo pueden llegar a `garment.style_tags` por corrección manual del usuario o (si está activo) por el respaldo LLM, nunca por zero-shot/kNN.
- **Umbral de margen (`PACHAPP_ML_MARGIN_THRESHOLD`) como variable de entorno vs columna de `setting`.** Por ahora vive en el modelo `Settings` (D16) porque es nuevo y no solapa con ningún umbral existente (ver nota de diseño en "Configuración"); si el usuario quiere ajustarlo desde la pantalla de Ajustes como `needs_review_threshold`/`color_review_threshold`/`duplicate_warning_threshold`, requeriría moverlo a la tabla `setting` en una migración aparte — no decidido aquí.
- **Umbral exacto del multietiqueta de `style_tags` (VIS-REQ-018)** y el número máximo de etiquetas (SPEC-ML fija 3) — pendientes de calibración empírica, igual que `color_confidence` en 03-garment-ingestion.md.
- **Cuántas llamadas al LLM de respaldo se esperan en la práctica** una vez activado — no hay datos todavía; el paso 7 del plan de implementación debe registrar el conteo real antes de decidir si merece la pena mantenerlo activado por defecto en algún momento futuro.
