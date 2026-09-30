# Hito A — guía de pruebas manuales

Guía para probar a mano, tú solo, el Hito A: **subir una foto y que la prenda
aparezca en el armario**. Cada paso tiene el comando exacto y el resultado
esperado. Si algo no coincide, ve a la sección 9 (qué reportar).

Todos los comandos son para **zsh dentro de WSL**, salvo que se indique otra
cosa. Sustituye `~/pachapp-worktrees/hito-a` por la ruta de tu checkout si
usas otro (por ejemplo, `main` una vez fusionado).

## 0. Qué se prueba y qué NO

**Se prueba (Hito A):**

- Subida de fotos (`POST /garments`) y procesamiento en segundo plano por el
  worker: preparar, recortar el fondo (BiRefNet), extraer colores y cerrar la
  prenda.
- API del armario: listado con filtros y paginación, detalle, edición,
  archivar/reactivar, reintentar, eliminar, ajustes.
- App (Expo, web y móvil): Añadir, Armario, Revisión, Detalle de prenda y
  Ajustes.

**NO se espera todavía:**

- **Atributos de IA.** El clasificador zero-shot (`ml/`, tarea T3) está en
  `main` pero **todavía no está conectado al worker** (tarea A15). Los pasos
  `ai_attributes` y `embedding` del worker son no-ops: avanzan el progreso y no
  escriben nada. Una prenda recién procesada tiene, por tanto:
  - **Con valor:** imagen original, recorte (`cutout/<id>.png`), miniatura
    (`thumb/<id>.webp`), `colors` (hasta 4, con nombre de la paleta de 20,
    `hex` y proporción), `is_neutral`, `color_confidence`.
  - **Vacío (`null`):** `category`, `subcategory`, `pattern`, `formality`,
    `style_tags`, `seasons`, `warmth`, `material`, `ai_confidence`. En la app
    la categoría se ve como **«Sin categoría»**.
  - **`needs_review`:** solo se activa si la confianza del color es menor que
    `color_review_threshold` (0,7 por defecto) o si el recorte falló de forma
    «suave» (máscara vacía, se usa la foto entera). Una foto normal y nítida
    **no** queda pendiente de revisión aunque no tenga categoría. Esto es lo
    esperado en este hito; las categorías se rellenan a mano en Revisión.
- **Outfits, Hoy, Historial, Favoritos:** son pantallas vacías o de relleno.
  Por eso tampoco se puede provocar `GARMENT_HAS_HISTORY` (hace falta que la
  prenda esté en un outfit); ese caso solo lo cubren los tests automáticos.

## 1. Preparación

### 1.1 Prerrequisitos

- WSL2 (Ubuntu) con `uv` y Node 22 instalado **dentro de WSL** con `nvm`.
  `make` se niega a usar el Node de Windows (`/mnt/c`). Comprueba:

  ```zsh
  command -v node && node --version   # debe ser /home/... y v22.x, nunca /mnt/...
  uv --version
  curl --version | head -1
  python3 --version
  ```

- GPU NVIDIA opcional. Sin GPU el recorte corre en CPU y es bastante más
  lento por foto (el dispositivo se elige solo: `PACHAPP_ML_DEVICE=auto`).
- Las consultas a la base de datos de esta guía usan `python3` (no hace falta
  instalar `sqlite3` ni `jq`).

### 1.2 Rama a probar

```zsh
cd ~/pachapp-worktrees/hito-a
git branch --show-current       # feat/hito-a
git status --short
```

Una vez fusionado en `main`, usa tu clon principal (`/mnt/d/Educcio/Software/pachapp`)
con `main` actualizado. Desde ahí, todo es igual.

### 1.3 Fichero `.env.test` (datos de prueba aislados)

Usamos un directorio de datos de prueba para no tocar datos reales. El
directorio de datos **debe estar en ext4 de WSL** (nunca bajo `/mnt/*`); si no,
la API y el worker se niegan a arrancar con un error explícito.

```zsh
cd ~/pachapp-worktrees/hito-a
cat > .env.test <<'ENV'
PACHAPP_DATA_DIR=~/pachapp-data-test
PACHAPP_API_HOST=0.0.0.0
PACHAPP_API_PORT=8000
PACHAPP_CORS_ORIGINS=["http://localhost:8081"]
PACHAPP_ML_EMBED_REVISION=c56244cc94f92419e8369fa71efdaf403b124ce8
EXPO_PUBLIC_API_BASE_URL=http://localhost:8000
ENV
```

Notas:

- `.env.test` está en `.gitignore` (`.env.*`): no se sube.
- Sin `PACHAPP_ML_CACHE_DIR`, los modelos se buscan en
  `~/pachapp-data-test/models`, que es donde ya están descargados en esta
  máquina. Si los tienes en otra carpeta, añade
  `PACHAPP_ML_CACHE_DIR=<esa carpeta>`; si no los tienes, haz el paso 1.5.
- En zsh no uses `GID` ni `UID` como nombres de variable: son variables
  especiales numéricas. Por eso esta guía usa `GAR` para el id de la prenda.
- `PACHAPP_ML_EMBED_REVISION` es obligatorio (un commit fijo, no `main` ni
  `latest`); el valor es el de `.env.example`.
- No pongas comentarios al final de las líneas: `make` incluye el fichero tal
  cual.
- Todas las órdenes `make` de esta guía llevan `ENV_FILE=.env.test`. Si prefieres
  exportarlo una vez por terminal, añade `export ENV_FILE=.env.test`.

### 1.4 Instalar y migrar

```zsh
make install
make migrate ENV_FILE=.env.test
```

Esperado:

- `make install` termina sin error (`uv sync` + `npm install`).
- `make migrate` muestra líneas `Running upgrade ...` de Alembic y termina bien.
  Crea `~/pachapp-data-test/db/pachapp.sqlite3` y la fila única de ajustes con
  los valores por defecto.

```zsh
ls ~/pachapp-data-test/db/
# pachapp.sqlite3  (puede haber también -wal y -shm cuando la API esté activa)
```

### 1.5 Modelos de visión (solo la primera vez)

```zsh
make ml-preload ENV_FILE=.env.test
```

Esperado: descarga BiRefNet y SigLIP (~5 GB la primera vez; las siguientes solo
valida la caché). Si hay GPU CUDA, convierte una vez el modelo de fondo a fp16
(~40 s). Al final imprime el fichero de fondo, su precisión y el tiempo por
imagen en caliente. Si falla, **no sigas**: el recorte no funcionará.

### 1.6 Fotos de prueba

Prepara una carpeta con **al menos 10 fotos** de prendas (JPG/PNG) accesible
desde el navegador de Windows, por ejemplo `C:\Users\<tú>\Pictures\prendas`.
Desde WSL esa carpeta es `/mnt/c/Users/<tú>/Pictures/prendas`. Variedad útil:

- 6-7 fotos normales de una sola prenda sobre fondo liso (camiseta, pantalón,
  zapatos...).
- 1 foto de una prenda blanca o negra sobre fondo del mismo color (recorte
  difícil).
- 1 foto con varias prendas o muy desordenada.
- 1 foto grande (>4000 px de lado) si tienes.

Para los pasos por API, fija una variable con una foto:

```zsh
FOTO=/mnt/c/Users/TU_USUARIO/Pictures/prendas/camiseta.jpg
ls -lh "$FOTO"
```

### 1.7 Empezar desde cero (reset)

Cuando quieras repetir una prueba desde un armario vacío (API y worker
**parados**):

```zsh
rm -rf ~/pachapp-data-test/db ~/pachapp-data-test/images
make migrate ENV_FILE=.env.test
```

Esto conserva `~/pachapp-data-test/models`. Nunca borres `~/pachapp-data`
(datos reales).

## 2. Arranque

Abre **tres terminales** (o pestañas de tmux/Windows Terminal), todas en la
raíz del repo (`cd ~/pachapp-worktrees/hito-a`).

**Terminal 1 — API:**

```zsh
make run ENV_FILE=.env.test
```

Esperado: uvicorn con recarga automática, `Uvicorn running on
http://0.0.0.0:8000` y `Application startup complete.`

**Terminal 2 — worker:**

```zsh
make run-worker ENV_FILE=.env.test
```

Esperado en el log:

```
INFO:__main__:pachapp worker started (poll interval: 500ms)
INFO:worker.claim:recovered stuck jobs left by a previous worker: 0 requeued, 0 failed (budget spent)
```

y, con el primer trabajo, una línea
`INFO:ml.registry:Loading rembg session 'birefnet-general-lite' on device=cuda ...`
(con GPU; `device=cpu` si no hay CUDA). El worker
**no imprime una línea por cada foto procesada con éxito**; solo avisa de
reintentos, fallos y trabajos huérfanos. La primera foto tarda más porque el
modelo de recorte se carga de forma perezosa en el primer trabajo.

**Terminal 3 — app:**

```zsh
make run-ui ENV_FILE=.env.test
```

Esperado: Expo arranca y muestra un QR y el menú. La versión web está en
<http://localhost:8081>. Si sale `EXPO_PUBLIC_API_BASE_URL is empty or unset`,
revisa `.env.test`.

**Comprobación de salud (terminal 4 o la que quieras):**

```zsh
API=http://localhost:8000
curl -s $API/health
# {"status":"ok"}
```

La documentación interactiva de la API está en <http://localhost:8000/docs>.

## 3. Prueba rápida por API (curl)

Ejecuta esto primero: si la API funciona aquí, cualquier fallo posterior en la
app es de la app.

Helpers de una línea (pégalos en la terminal donde vayas a trabajar):

```zsh
API=http://localhost:8000
DB=~/pachapp-data-test/db/pachapp.sqlite3
jget() { python3 -c 'import sys,json; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }
pj() { python3 -m json.tool; }
q() { python3 -c 'import sqlite3,sys; cur=sqlite3.connect(sys.argv[1]).execute(sys.argv[2]); print([d[0] for d in cur.description]); [print(r) for r in cur]' "$DB" "$1"; }
```

### 3.1 Subir una foto

```zsh
R=$(curl -s -w '\n%{http_code}\n' -F "file=@$FOTO" $API/garments); print -r -- "$R"
```

Esperado: código HTTP **202** y un cuerpo con dos ids:

```json
{ "garment_id": "...", "job_id": "..." }
```

Guarda los ids:

```zsh
GAR=$(print -r -- "$R" | head -1 | jget garment_id)
JID=$(print -r -- "$R" | head -1 | jget job_id)
echo $GAR $JID
```

### 3.2 Seguir el trabajo hasta que termine

```zsh
while true; do S=$(curl -s $API/jobs/$JID); print -r -- "$S"; [[ $S == *'"status":"done"'* || $S == *'"status":"failed"'* ]] && break; sleep 1; done
```

Esperado: una secuencia de líneas como

```
{"status":"pending","step":null,"progress":0,"error":null,"result":null}
{"status":"running","step":"preprocess","progress":0,...}
{"status":"running","step":"cutout","progress":10,...}
{"status":"running","step":"color","progress":30,...}
{"status":"running","step":"ai_attributes","progress":45,...}
...
{"status":"done","step":"consolidate","progress":100,"error":null,"result":null}
```

Reglas (del código del worker): `step` se escribe **al empezar** cada paso y
`progress` **al terminarlo**, con la tabla `preprocess 10`, `cutout 30`,
`color 45`, `ai_attributes 75`, `embedding 90`, `consolidate 100`. Por eso
verás `step: cutout` con `progress: 10`. Los pasos `ai_attributes` y
`embedding` pasan casi instantáneamente (son no-ops). Es normal no ver todos
los estados intermedios si el paso es muy rápido.

### 3.3 Ver la prenda

```zsh
curl -s $API/garments/$GAR | pj
```

Esperado (campos clave):

- `status: "active"`, `category: null`, `subcategory: null`, `pattern: null`,
  `formality/warmth: null`, `style_tags/seasons: null`.
- `colors`: lista de 1 a 4 entradas `{"name": ..., "hex": "#...", "proportion": ...}`;
  los nombres salen de la paleta de 20 (`negro`, `blanco`, `gris`, `beige`,
  `camel`, `marino`, `denim`, `marrón`, `rojo`, `burdeos`, `rosa`, `naranja`,
  `amarillo`, `verde`, `oliva`, `azul`, `celeste`, `morado`, `turquesa`,
  `caqui`); `is_neutral` true/false; `color_confidence` entre 0 y 1.
- `img_original: "original/<id>.jpg"`, `img_cutout: "cutout/<id>.png"`,
  `img_thumb: "thumb/<id>.webp"` (rutas **relativas**).
- `needs_review`: `true` solo si `color_confidence` < 0,7 (umbral por defecto) o
  el recorte falló; con fotos de varios colores es habitual que salga `true`
  (ver sección 0).
- `job`: `{"status":"done","step":"consolidate","progress":100,...}`.
- `outfit_count: 0`, `wear_count: 0`.

### 3.4 Listado

```zsh
curl -s "$API/garments" | pj | head -40
curl -s "$API/garments?needs_review=true" | pj
curl -s "$API/garments?status=archived" | pj
curl -s "$API/garments?page=1&page_size=2" | pj
curl -s "$API/garments?page_size=500"     # 422: page_size máximo 200
```

Esperado: `{"items":[...],"total":N,"page":1,"page_size":50}`. Orden por
`created_at` descendente por defecto; sin `status` devuelve todos los estados;
filtros inválidos dan **422** con el formato estándar de FastAPI.

### 3.5 Imágenes

```zsh
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' $API/images/thumb/$GAR.webp
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' $API/images/cutout/$GAR.png
curl -s -o /dev/null -w '%{http_code} %{content_type}\n' $API/images/original/$GAR.jpg
```

Esperado: `200 image/webp`, `200 image/png`, `200 image/jpeg`. Para verlas,
abre en el navegador de Windows `http://localhost:8000/images/cutout/<GAR>.png`
(el PNG debe tener el fondo transparente) o en el explorador:

```zsh
explorer.exe "$(wslpath -w ~/pachapp-data-test/images/cutout)"
```

### 3.6 Errores esperados

```zsh
# Archivo que no es una imagen
echo "esto no es una foto" > /tmp/no-imagen.txt
curl -s -w '\n%{http_code}\n' -F "file=@/tmp/no-imagen.txt" $API/garments
# 400  {"error":{"code":"INVALID_IMAGE","message":"El archivo no es una imagen válida.","details":null}}

# Archivo de más de 25 MiB
head -c 26M /dev/zero > /tmp/grande.bin
curl -s -w '\n%{http_code}\n' -F "file=@/tmp/grande.bin" $API/garments
# 400  code IMAGE_TOO_LARGE, "El archivo es demasiado grande (máximo 25 MiB)."

# Prenda y trabajo inexistentes
curl -s -w '\n%{http_code}\n' $API/garments/no-existe
# 404  code GARMENT_NOT_FOUND
curl -s -w '\n%{http_code}\n' $API/jobs/no-existe
# 404  code JOB_NOT_FOUND

# Reintentar una prenda cuyo trabajo NO falló
curl -s -w '\n%{http_code}\n' -X POST $API/garments/$GAR/retry
# 409  code JOB_NOT_FAILED
```

Además, una imagen con lado largo mayor que el doble de `upload_max_px`
(4096 px por defecto) también da `IMAGE_TOO_LARGE` ("La imagen es demasiado
grande (máximo 4096px en el lado largo)."). Los errores siguen siempre el
formato `{"error": {"code", "message", "details"}}`, salvo los 422 de
validación, que usan el formato por defecto de FastAPI.

Comprueba que ninguna de estas subidas fallidas creó prendas:

```zsh
q "select count(*) from garment"
```

### 3.7 Edición, ciclo de vida y ajustes por API

```zsh
# Editar atributos (un PATCH parcial)
curl -s -X PATCH -H 'Content-Type: application/json' \
  -d '{"category":"top","pattern":"solid","formality":2}' $API/garments/$GAR | pj | head -30
# Campos prohibidos -> 422
curl -s -w '\n%{http_code}\n' -X PATCH -H 'Content-Type: application/json' \
  -d '{"needs_review":true}' $API/garments/$GAR
# Cerrar la revisión (pone needs_review=false y user_verified=true)
curl -s -X POST $API/garments/$GAR/review/complete | pj | grep -E 'needs_review|user_verified'
# Archivar / reactivar (idempotentes)
curl -s -X POST $API/garments/$GAR/archive    | pj | grep '"status"'   # "archived"
curl -s -X POST $API/garments/$GAR/reactivate | pj | grep '"status"'   # "active"

# Ajustes
curl -s $API/settings | pj
# Pesos que no suman 1 -> 400 INVALID_WEIGHTS
curl -s -w '\n%{http_code}\n' -X PATCH -H 'Content-Type: application/json' \
  -d '{"weight_color":0.9}' $API/settings
```

Esperado en el último: **400**, `code: "INVALID_WEIGHTS"`, mensaje «Los cuatro
pesos deben sumar 1,0 (±0,01); ahora suman 1,55.» y nada cambia en
`GET /settings`. Valores por defecto de `GET /settings`: pesos 0.35 / 0.25 /
0.25 / 0.15, `no_repeat_days` 14, `max_accessories` 2,
`duplicate_warning_threshold` 0.92, `needs_review_threshold` 0.7,
`color_review_threshold` 0.7. Un campo desconocido o `null` en el PATCH de
ajustes da 422.

Un PATCH de `colors` (opcional) crea una corrección de usuario:

```zsh
curl -s -X PATCH -H 'Content-Type: application/json' \
  -d '{"colors":[{"name":"rojo","hex":"#c81e28","lab":[43.31,63.30,39.98],"proportion":1.0}]}' $API/garments/$GAR | pj | grep -A4 '"colors"'
q "select field, ai_value, corrected_value from ai_correction"
```

Cada color necesita `name`, `hex`, `lab` y `proportion`; sin `lab` la API
responde 422. Esperado: una fila con `field = colors`; `color_confidence` pasa a
1.0.

Nota: el PATCH de `category`/`pattern`/`formality` de arriba **no** crea filas
en `ai_correction` en este hito: solo se registra una corrección cuando había un
valor de IA que corregir, y sin A15 no lo hay. Los errores 422 de validación
(campo prohibido, `page_size` fuera de rango, falta `lab`) usan el formato
propio de FastAPI (`{"detail": [...]}`) y no el sobre `{"error": ...}`: es la
excepción documentada en API-REQ-002.

### 3.8 Eliminar

```zsh
curl -s -w '%{http_code}\n' -X DELETE $API/garments/$GAR
# 204 (sin cuerpo)
curl -s -w '\n%{http_code}\n' $API/garments/$GAR      # 404 GARMENT_NOT_FOUND
ls ~/pachapp-data-test/images/*/ | grep $GAR || echo "ficheros borrados"
```

Esperado: 204, la prenda ya no existe y sus tres ficheros de imagen han
desaparecido.

## 4. Prueba en la app, pantalla por pantalla

Abre <http://localhost:8081> en el navegador (Chrome/Edge en Windows) con
**API, worker y UI arrancados**. Barra de pestañas: **Hoy, Armario, Añadir,
Historial**; el icono de engranaje de la cabecera abre **Ajustes**. Hoy e
Historial son de relleno en este hito.

> Consejo: empieza con el armario vacío (sección 1.7). Para probar las
> pantallas de Revisión con campos resaltados, haz antes el paso 4.0.

### 4.0 (Opcional pero recomendado) Forzar «pendiente de revisión»

Como las fotos normales **no** quedan pendientes de revisión (sección 0), sube
el umbral de color al máximo para que casi todas las fotos nuevas se marquen. La
confianza de color suele ser menor que 1,0 (un color perfectamente plano puede
dar exactamente 1,0 y no marcarse), así que `needs_review` se activará en el
paso final del worker:

```zsh
curl -s -X PATCH -H 'Content-Type: application/json' \
  -d '{"color_review_threshold":1.0}' $API/settings | pj | grep color_review
```

Al terminar toda la sesión, restáuralo:

```zsh
curl -s -X PATCH -H 'Content-Type: application/json' \
  -d '{"color_review_threshold":0.7}' $API/settings | pj | grep color_review
```

Con el umbral a 1,0 tendrás prendas con `needs_review = true`, sin categoría
y con todos los atributos vacíos resaltados (la situación de UI-SCN-003).

### 4.1 Añadir (UI-SCN-002: 10 prendas)

Ve a la pestaña **Añadir**.

1. La primera vez se abre el panel **«Consejos para fotografiar tus prendas»**
   con tres consejos. Pulsa **«Entendido»**. Recarga la página: no debe volver
   a salir solo. El icono de ayuda de la cabecera («Ver consejos de captura») lo
   reabre.
2. Sin fotos, se lee «Añade fotos de tus prendas. Puedes seguir añadiendo
   mientras se procesan las anteriores.» y hay dos botones: **«Hacer foto»** y
   **«Elegir de la galería»**. (En web, usa «Elegir de la galería»: abre el
   selector de archivos; «Hacer foto» usa la cámara del navegador.)
3. Pulsa **«Elegir de la galería»** y selecciona **las 10 fotos a la vez**
   (la selección múltiple está habilitada).
4. Esperado: aparece una tarjeta por foto, cada una con su nombre de archivo y
   su propia barra de progreso. Cada tarjeta pasa por: «Preparando foto» →
   «Subiendo» → «En cola» → etiquetas del paso actual → **«Listo»**. Las
   etiquetas de paso son: «Preparando» (`preprocess`), «Recortando» (`cutout`),
   «Analizando colores» (`color`), «Analizando prenda» (`ai_attributes`),
   «Calculando similitud» (`embedding`) y «Terminando» (`consolidate`). Las dos
   de IA pasan casi sin verse porque aún no hacen nada.
5. El worker procesa **de uno en uno**; las demás tarjetas esperan en «En cola».
   Mientras tanto la pantalla sigue siendo usable: pulsa **«Elegir de la
   galería»** otra vez y añade otra foto; debe entrar en la cola sin afectar a
   las demás.
6. Cuando una tarjeta llega a **«Listo»** aparece el botón **«Revisar»**. No
   navega sola. Púlsalo en una: debe abrir la pantalla de Revisión de esa
   prenda (vuelve atrás después).
7. Criterio de UI-SCN-002: las 10 fotos terminan en «Listo» sin errores.

Sal de la pestaña y vuelve: la lista de tarjetas de Añadir **se conserva
mientras la app siga abierta**, pero **se pierde al recargar la página** (la
cola está solo en memoria; los trabajos siguen su curso en el servidor).

### 4.2 Armario

Ve a **Armario**.

1. Esperado: cuadrícula de 2 columnas (3 si la ventana mide 600 px o más) con
   las 10 prendas, la más reciente primero. Cada celda muestra el recorte
   (miniatura sin fondo) y debajo **«Sin categoría»** (aún no hay IA).
2. Si con el paso 4.0 hay prendas pendientes, cada una muestra la insignia
   **«Revisar»** sobre la imagen.
3. **Prenda en proceso:** sube una foto nueva desde Añadir y vuelve enseguida
   al Armario. Su celda debe mostrar un marcador **«Procesando…»** con el paso
   (por ejemplo «Recortando») y una barra de progreso; cuando termina se
   sustituye por la miniatura **sin recargar** (el listado se refresca cada 2 s
   mientras haya trabajos en curso y luego se detiene).
4. **Filtros** (fila de chips superior, cada chip es un botón que se marca al
   pulsarlo y se desmarca al volver a pulsarlo):
   - Categoría: **Todas, Top, Pantalón, Vestido / mono, Capa intermedia,
     Abrigo, Calzado, Complemento**. Como ninguna prenda tiene categoría,
     cualquier categoría concreta debe dar **«Ninguna prenda coincide con estos
     filtros»** y el botón **«Quitar filtros»**, que vuelve al listado completo.
   - Estado: **Activas, Lavando, Archivadas, Todas**. Por defecto (ningún chip
     marcado) se ven las activas y las que están lavando; **Archivadas**
     muestra solo las archivadas.
   - **«Pendientes de revisión»**: solo las que tienen `needs_review`. Sin el
     paso 4.0 es normal que esté vacío.
5. **Armario vacío:** tras el reset (1.7), el Armario muestra «Tu armario está
   vacío» con el botón **«Añadir prenda»**, que lleva a Añadir.
6. **Cargar más:** con más de 50 prendas aparece **«Cargar más»** al final
   (`page_size` 50). Con 10 prendas no aparece. Para verlo sin subir 51 fotos
   puedes cambiar temporalmente `PAGE_SIZE` en `app/app/(tabs)/wardrobe.tsx`
   (solo para la prueba; no lo dejes cambiado) o comprobar la paginación por
   API (sección 3.4).
7. **Refrescar:** arrastra la lista hacia abajo (móvil) para refrescar. En web
   basta con recargar la página.
8. **Error con la API parada:** con el Armario abierto y cargado, para la API
   (Ctrl+C en la terminal 1) y espera unos segundos o fuerza un refresco.
   Esperado: la cuadrícula ya cargada se **mantiene** y aparece un aviso rojo
   con el mensaje de error y el botón **«Reintentar»**. Arranca la API otra vez
   y pulsa «Reintentar»: el aviso desaparece. Si recargas la página estando la
   API parada, se ve una pantalla de error con **«Reintentar»** en lugar de la
   cuadrícula.
9. Pulsa una celda: abre el Detalle de esa prenda (4.4).

### 4.3 Revisión

Se llega con **«Revisar»** desde Añadir, desde la insignia del Armario (vía
Detalle) o desde el botón **«Revisar»** del Detalle. Usa una prenda creada con
el paso 4.0 (`needs_review = true`).

1. Esperado al abrir: el recorte de la prenda arriba, la insignia
   **«Pendiente de revisión»** y una ficha por atributo: **Categoría,
   Subcategoría, Colores, Estampado, Formalidad (1 = informal, 5 = formal),
   Estilos (máx. 3), Temporadas, Abrigo (1 = fresco, 5 = muy abrigado), Material**.
2. **Resaltado de dudas:** las fichas de los atributos vacíos aparecen
   resaltadas con la etiqueta **«Revisar»** (con `needs_review` activo, todo
   atributo vacío se resalta). La ficha de **Colores** se resalta si la
   confianza del color es menor que `color_review_threshold` (con el paso 4.0,
   sí). Sin el paso 4.0 y con `needs_review = false`, no hay resaltados ni
   insignia: es correcto.
3. **Corregir un chip (UI-SCN-003):** pulsa **Categoría → Top** (selección
   inmediata, sin botón «guardar»). Esperado: el chip queda marcado, y
   **el resaltado de esa ficha NO desaparece**, la insignia «Pendiente de
   revisión» **sigue visible** y la app **no navega**. Comprueba el guardado:

   ```zsh
   curl -s $API/garments/$GAR | pj | grep -E '"category"|needs_review'
   q "select field, ai_value, corrected_value from ai_correction"
   ```

   Esperado: `category: "top"`, `needs_review: true` y una fila en
   `ai_correction` para `category`.

4. Prueba otros controles: **Estampado** (Liso, Rayas, Cuadros, Estampado,
   Textura), **Formalidad** y **Abrigo** (1 a 5), **Estilos** y **Temporadas**
   (varios a la vez: se marcan/desmarcan al pulsar; Estilos admite como máximo 3; Primavera, Verano, Otoño,
   Invierno), **Material** (chips sugeridos: algodón, denim, lana, cuero, lino,
   sintético, y campo de texto libre) y **Subcategoría** (texto libre; se guarda
   al salir del campo o al enviar, solo si cambió y no está vacío).
5. **Colores:** verás los colores actuales con su porcentaje y un selector con
   los **20 nombres de la paleta**. Reglas: mínimo **1** color y máximo **4**
   («Elige hasta 4 colores; el primero es el dominante.»). Con 1 color
   seleccionado, su chip no se puede desmarcar; con 4, los demás chips quedan
   desactivados. Añadir/quitar un color reparte las proporciones y se guarda
   al instante. Comprueba por API que `colors` tiene como mucho 4 entradas, que
   las proporciones suman ~1 y que `color_confidence` es `1.0`.
6. **Error al guardar:** con la ficha abierta, para la API y pulsa un chip.
   Esperado: el chip vuelve a su valor anterior y aparece el mensaje «No se pudo
   guardar el cambio. Inténtalo de nuevo.» bajo la ficha. Arranca la API y
   repite: se guarda.
7. **«Revisión terminada» (UI-SCN-003b):** deja al menos un atributo sin
   corregir (por ejemplo **Material**) y pulsa **«Revisión terminada»**.
   Esperado: la app **vuelve al Armario**; la celda ya **no** muestra la
   insignia «Revisar». Por API: `needs_review: false` y `user_verified: true`;
   los atributos que no corregiste siguen siendo `null`.
8. Reabre la prenda en Revisión: sin `needs_review` ya no hay resaltados ni
   insignia.

### 4.4 Detalle de prenda

Desde el Armario, abre una prenda.

1. Esperado: el recorte, el título (categoría o «Sin categoría»), el estado
   («Activa», «Lavando» o «Archivada»), la insignia «Revisar» si está
   pendiente, y las secciones **Atributos** (Subcategoría, Colores,
   Estampado, Formalidad, Estilos, Temporadas, Abrigo, Material, Marca,
   Notas) y de uso (**Veces puesta, Última vez, Outfits**). Los campos vacíos
   muestran **«Sin definir»** y «Última vez» muestra «Nunca».
2. **Estado:** pulsa **«Marcar como lavando»**: el estado pasa a «Lavando» y el
   botón cambia a **«Marcar como activa»**; pulsa este y vuelve a «Activa».
   En el Armario, con el filtro «Lavando» debe aparecer mientras esté así.
3. **Archivar:** pulsa **«Archivar»**: estado «Archivada», el botón pasa a
   **«Reactivar»** y la prenda **desaparece del listado por defecto** del
   Armario (solo se ve con el chip «Archivadas» o «Todas»). **«Reactivar»** la
   devuelve a «Activa».
4. **Revisar:** el botón **«Revisar»** abre la pantalla de Revisión (4.3).
5. **Eliminar:** pulsa **«Eliminar»**. Esperado: aparece la confirmación
   **«¿Eliminar esta prenda?» / «Esta acción no se puede deshacer.»** con
   **«Cancelar»** y **«Eliminar definitivamente»**. «Cancelar» cierra la
   confirmación sin borrar. «Eliminar definitivamente» borra y vuelve al
   Armario; la prenda ya no está y sus ficheros en
   `~/pachapp-data-test/images/` tampoco.
6. **Eliminar mientras se procesa (409):** ver el caso 5.4.
7. **Reintentar un procesamiento fallido:** ver el caso 5.3.
8. **Detalle mientras se procesa:** abre el Detalle de una prenda recién
   subida: debe mostrar «Procesando…», el paso actual y una barra de
   progreso, y al terminar cargar los datos sin recargar.

### 4.5 Ajustes

Pulsa el engranaje de la cabecera.

1. Esperado: sección **«Motor de recomendación»** con los campos **Peso de
   color, Peso de estilo, Peso de novedad, Peso de preferencia, Días sin repetir,
   Máximo de complementos** y el texto **«Suma de pesos: 1,00 (debe ser 1,00)»**;
   sección **«Conexión»** con **«Conectado al servidor»**. Si la API está
   parada: «No se pudo conectar con el servidor.» con «Reintentar».
2. Cambia **Peso de color** a `0,4` y **Peso de estilo** a `0,2` (se acepta la
   coma decimal), deja los demás y pulsa **«Guardar»**. Esperado: «Ajustes
   guardados». Comprueba con `curl -s $API/settings | pj`. Vuelve a dejar
   0,35 / 0,25.
3. **Pesos que no suman 1:** pon **Peso de color** a `0,9` y pulsa
   «Guardar». Esperado: error en línea «Los pesos deben sumar 1,00 (ahora
   suman …).» y **no** se envía nada. (La app comprueba la suma antes de
   enviar, con la misma tolerancia que el servidor; el error `INVALID_WEIGHTS`
   del servidor se verifica por API, sección 3.7.)
4. **Validación de campos:** un peso mayor que 1 o no numérico da «Introduce un
   número entre 0 y 1.»; «Días sin repetir» o «Máximo de complementos»
   negativos o con decimales dan «Introduce un número entero igual o mayor que
   0.».
5. Cambia **Días sin repetir** a `7` y **Máximo de complementos** a `3`,
   «Guardar», recarga la página y reabre Ajustes: los valores persisten.
   Devuélvelos a 14 y 2.
6. Los umbrales (`needs_review_threshold`, `color_review_threshold`, etc. **no**
   se muestran en la app; se cambian por API (sección 4.0).

## 5. Casos de fallo a provocar

### 5.1 Parar el worker a mitad de un trabajo (trabajo huérfano)

1. Sube una foto desde Añadir y, en cuanto pase a «Recortando», para el worker
   con Ctrl+C en la terminal 2. (Lo más fácil es hacerlo con la **primera foto
   tras arrancar el worker**, cuando el modelo tarda en cargar.)
2. Comprueba el estado:

   ```zsh
   q "select id,status,step,progress,attempts,error from job order by created_at desc limit 3"
   ```

   Es posible que quede en `claimed` o `running`; la tarjeta de la app deja de
   avanzar.

3. Arranca el worker otra vez (`make run-worker ENV_FILE=.env.test`). Esperado:
   el log indica «recovered stuck jobs left by a previous worker: 1 requeued, 0
   failed (budget spent)», el trabajo vuelve a `pending` con `attempts = 1` y
   termina en «Listo».
4. **Segunda interrupción:** repite el corte sobre el mismo trabajo una
   segunda vez. Como el presupuesto de reintentos es 1, al rearrancar el
   trabajo pasa a `failed` con el mensaje **«El procesamiento se interrumpió
   repetidamente. Inténtalo de nuevo con otra foto.»** (en la app: «Falló» y
   botón «Reintentar»).

### 5.2 API parada durante una subida

1. Para la API (Ctrl+C en la terminal 1).
2. En Añadir elige una foto. Esperado: la tarjeta termina en error con el
   mensaje **«No se pudo subir la foto. Comprueba la conexión e inténtalo de
   nuevo.»** y dos botones: **«Reintentar»** y **«Quitar»**.
3. Arranca la API y pulsa **«Reintentar»**: la foto se sube y avanza con normalidad
   (no hace falta volver a elegirla). **«Quitar»** descarta la tarjeta.
4. Con la API parada, el resto de pantallas muestran sus estados de error con
   «Reintentar» (ver 4.2 punto 8 y 4.5 punto 1).

### 5.3 Trabajo fallido y «Reintentar»

Forzamos un fallo borrando la foto original antes de que el worker la procese:

1. Para el worker (Ctrl+C en la terminal 2).
2. Sube una foto desde Añadir. Queda «En cola».
3. Localiza el original, haz una copia de seguridad y bórralo:

   ```zsh
   GAR=$(q "select id from garment order by created_at desc limit 1" | tail -1 | tr -d "()',")
   cp ~/pachapp-data-test/images/original/$GAR.jpg /tmp/original-backup.jpg
   rm ~/pachapp-data-test/images/original/$GAR.jpg
   ```

4. Arranca el worker. Esperado: el trabajo pasa a `failed` **sin reintento**
   (error permanente); en la app la tarjeta muestra «Falló», el mensaje **«No
   se pudo leer la foto original. Súbela de nuevo.»** y el botón
   **«Reintentar»**. En el Armario la celda muestra «Falló el procesamiento» y
   en el Detalle se ve el bloque «Falló el procesamiento» con **«Reintentar
   procesamiento»**.
5. Restaura el original y reintenta desde la app:

   ```zsh
   cp /tmp/original-backup.jpg ~/pachapp-data-test/images/original/$GAR.jpg
   ```

   Pulsa **«Reintentar»** (en Añadir) o **«Reintentar procesamiento»** (en el
   Detalle). Esperado: el trabajo vuelve a `pending` con el progreso a 0 y
   `attempts = 0`, el worker lo procesa y termina en «Listo». Si la prenda
   tenía colores corregidos a mano, se conservan (el reintento no los
   sobrescribe).

### 5.4 Eliminar mientras se procesa (409)

Es una carrera, así que puede requerir varios intentos. Con la **primera foto
tras arrancar el worker** (el modelo tarda en cargar) sube una foto por API e
intenta borrarla enseguida:

```zsh
R=$(curl -s -F "file=@$FOTO" $API/garments); GAR=$(print -r -- "$R" | jget garment_id)
sleep 1
curl -s -w '\n%{http_code}\n' -X DELETE $API/garments/$GAR
```

Esperado si el worker ya había tomado el trabajo: **409** con `code:
"GARMENT_PROCESSING"` y el mensaje «La prenda se está procesando; espera a que
termine para eliminarla.»; la prenda sigue existiendo. En la app, el mismo
mensaje aparece en rojo en el Detalle al confirmar «Eliminar definitivamente».
Si el worker aún no había reclamado el trabajo (o está parado), el borrado
**sí se completa** (204) y se descarta el trabajo pendiente: eso también es
correcto.

### 5.5 Foto difícil (recorte suave)

Sube la foto con la prenda del mismo color que el fondo o la foto desordenada.
Esperado: termina en «Listo» igualmente. Si la máscara de recorte sale vacía, se
usa la foto completa como recorte y la prenda queda con **`needs_review =
true`** (insignia «Revisar» en el Armario aunque el umbral de color sea 0,7).
Compara el recorte (`/images/cutout/<id>.png`) con el original.

## 6. Inspección de datos

Usa el helper `q` de la sección 3 (o cualquier cliente SQLite sobre
`~/pachapp-data-test/db/pachapp.sqlite3`).

```zsh
q "select name from sqlite_master where type='table' order by name"
q "select count(*) as prendas from garment"
q "select id, category, needs_review, user_verified, status, color_confidence, img_cutout from garment order by created_at desc limit 5"
q "select id, status, step, progress, attempts, error, claimed_by from job order by created_at desc limit 10"
q "select status, count(*) from job group by status"
q "select field, ai_value, corrected_value, created_at from ai_correction order by created_at desc"
q "select * from setting"
q "select id, colors from garment order by created_at desc limit 1"
```

Esperado:

- Un `job` por cada subida, con `status = done`, `step = consolidate`,
  `progress = 100`, `error` vacío y `claimed_by = <host>:<pid>`.
- En `garment`, las columnas `category`, `subcategory`, `pattern`,
  `formality`, `style_tags`, `seasons`, `warmth`, `material`,
  `ai_confidence`, `embedding` vacías (NULL) para prendas recién procesadas
  (A15 aún no las rellena).
- `ai_correction`: una fila por cada campo de IA que el usuario corrigió en
  Revisión (y una de `colors` la primera vez que se editan los colores).
- `setting`: una sola fila con `id = 1`.

Disposición de imágenes bajo `~/pachapp-data-test/images/` (las rutas en la
base de datos son siempre relativas a esta carpeta):

```zsh
ls ~/pachapp-data-test/images/original | head -3   # <id>.jpg   (la foto subida, JPEG, orientación EXIF aplicada)
ls ~/pachapp-data-test/images/cutout   | head -3   # <id>.png   (RGBA, fondo transparente)
ls ~/pachapp-data-test/images/thumb    | head -3   # <id>.webp  (lado largo <= 400 px)
file ~/pachapp-data-test/images/cutout/$(ls ~/pachapp-data-test/images/cutout | head -1)
```

No deben quedar ficheros temporales ocultos (`.<nombre>.<hex>.tmp`) en esas
carpetas.

## 7. Móvil por LAN (opcional)

Para abrir la app en un móvil con Expo Go, el móvil debe alcanzar la API que
corre en WSL. Resumen de `README.md` y `docs/specs/01-dev-tooling.md`
(DEV-REQ-012/013):

1. En Windows, `%UserProfile%\.wslconfig` con `networkingMode=mirrored`
   (Windows 11 22H2+) y reglas de firewall que permitan entrada en los puertos
   **8000** y **8081**. Reinicia WSL (`wsl --shutdown` en PowerShell) tras
   cambiarlo. Plan B: `netsh interface portproxy` + regla de Firewall de
   Windows; `expo start --tunnel` solo como último recurso.
2. Averigua la IP LAN del PC (por ejemplo `192.168.1.10`) y edita `.env.test`:

   ```
   EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000
   PACHAPP_CORS_ORIGINS=["http://localhost:8081","http://192.168.1.10:8081"]
   ```

   La API escucha en `0.0.0.0` por defecto, así que no hay que tocar el host.

3. Reinicia API y UI (`make run`, `make run-ui`, ambos con `ENV_FILE=.env.test`).
4. Comprobación desde el móvil (mismo Wi-Fi): abre
   `http://192.168.1.10:8000/health` en su navegador; debe verse
   `{"status":"ok"}`. Si no, el problema es de red/firewall, no de la app.
5. Escanea el QR de Expo con Expo Go. Repite la sección 4 en el móvil: aquí sí
   puedes usar **«Hacer foto»** (pide permiso de cámara; si lo niegas verás
   «Necesitamos permiso para usar la cámara. Actívalo en los ajustes del
   dispositivo.») y **«Elegir de la galería»** con selección múltiple.
   Es el escenario real de UI-SCN-002: 10 prendas desde el móvil.

## 8. Opcional: evaluación de los modelos de visión

No forma parte de «subir una foto y ver la prenda», pero sirve para validar el
clasificador zero-shot que se conectará en A15. Requiere `main` con la tarea T3
(si tu rama aún no la incluye, haz rebase sobre `main` primero) y los modelos
descargados (`make ml-preload`).

```zsh
make ml-cutouts ENV_FILE=.env.test    # recortes de las fotos de evaluación, para inspeccionarlos
make ml-eval ENV_FILE=.env.test       # precisión zero-shot por atributo, matriz de confusión de categoría,
                                      # % de needs_review y tiempos
make ml-eval ENV_FILE=.env.test EVAL_DIR=/ruta/a/mis/fotos
```

Las fotos de evaluación viven en `PACHAPP_ML_EVAL_DIR` (por defecto
`<PACHAPP_DATA_DIR>/eval/garments`) y van con un `labels.json`, por ejemplo
`{"a.jpg": {"category": "top", "subcategory": "t-shirt", "pattern": "solid", "formality": 2}}`
(`null` = sin etiqueta). El criterio de aceptación es al menos **85 %** de
precisión en `category` sin kNN. Las fotos se leen de la carpeta indicada
(con `EVAL_DIR`) o de `PACHAPP_ML_EVAL_DIR`. Ver la sección «Vision models» del
`README.md`.

## 9. Qué reportar y cómo reiniciar

### Plantilla para cada fallo

```
Paso: (número de esta guía, p. ej. 4.3-3)
Esperado: (lo que dice la guía)
Obtenido: (lo que pasó, con el texto exacto de cualquier mensaje)
Captura: (pantalla completa, con la consola del navegador si hay error)
Logs: (últimas ~30 líneas de la terminal de la API y del worker)
Datos: (salida de q "select id,status,step,progress,attempts,error from job order by created_at desc limit 5")
Entorno: (rama y commit: git rev-parse --short HEAD; web o móvil; GPU o CPU)
```

Para copiar los logs: selecciona el texto de la terminal, o relanza el proceso
con `make run-worker ENV_FILE=.env.test 2>&1 | tee /tmp/worker.log`.

### Checklist final rápido

- [ ] 3.1-3.3: subida por API -> `done` -> prenda con colores y 3 imágenes.
- [ ] 3.6: `INVALID_IMAGE`, `IMAGE_TOO_LARGE`, 404 y `JOB_NOT_FAILED`.
- [ ] 4.1: 10 fotos desde Añadir terminan en «Listo» (UI-SCN-002).
- [ ] 4.2: las 10 prendas aparecen recortadas en el Armario; filtros y
      marcador «Procesando…».
- [ ] 4.3: corregir un chip no limpia la revisión; «Revisión terminada» sí
      (UI-SCN-003/003b).
- [ ] 4.4: lavando/activa, archivar/reactivar, eliminar con confirmación.
- [ ] 4.5: ajustes guardan y rechazan pesos que no suman 1.
- [ ] 5.1-5.4: worker parado, API parada, trabajo fallido + reintento,
      eliminar en proceso.

### Reiniciar y limpiar

- Borrar todas las prendas y volver a empezar: sección 1.7 (con API y worker
  parados).
- Restaurar el umbral si usaste 4.0:
  `curl -s -X PATCH -H 'Content-Type: application/json' -d '{"color_review_threshold":0.7}' $API/settings`
- Parar todo: Ctrl+C en las tres terminales. Los trabajos a medias se
  recuperan al volver a arrancar el worker.
- Fotos temporales de la prueba: `rm -f /tmp/no-imagen.txt /tmp/grande.bin /tmp/original-backup.jpg`.
