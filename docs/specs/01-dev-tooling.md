# 01 — Herramientas y entorno de desarrollo

Estado: Draft

## Alcance

Estructura del monorepo, proyecto(s) Python/uv, herramientas de lint/format/type/test para backend y app, targets del `Makefile` raíz, claves de `.env`/settings, puertos, configuración de WSL2, configuración de CORS.

## Fuera de alcance

Docker Compose, despliegue en VPS/servidor doméstico, Tailscale, builds con EAS, pipelines de CI/CD (todo aplazado según la sección "Aplazado" de c4.md).

## Dependencias

- Decisiones: D0, D13, D14, D15, D16.
- Consumido por: el resto de specs (todas asumen que esta estructura y estos comandos existen).

## Estructura del repositorio

```
pachapp/
  backend/
    pyproject.toml
    uv.lock
    src/
      api/        # App FastAPI: routers, schemas, dependencias
      worker/      # Proceso worker: pasos del pipeline, job runner
      engine/      # Motor de outfits: funciones puras, sin I/O
      ml/          # Visión local (BiRefNet, SigLIP zero-shot/kNN); solo usado por worker, ver 08-local-vision.md
      shared/      # Modelos SQLModel, settings Pydantic, enums, repositorios
    alembic/
      env.py
      versions/
    tests/
      unit/
      contract/            # Test de contrato del JSON del LLM (D11)
  app/
    package.json
    app.json
    app/                   # Rutas de Expo Router
    src/
      api-client/           # Tipos generados desde OpenAPI + fetch/hooks escritos a mano
      components/
      screens/
      hooks/
    tests/
  docs/
    architecture/c4.md
    specs/
  Makefile
  .env.example
```

**DEV-REQ-001.** El backend DEBE ser un único proyecto `uv` (un solo `pyproject.toml`/`uv.lock` bajo `backend/`) que contenga los paquetes `api`, `worker`, `engine`, `ml` y `shared`, de modo que la API y el worker compartan un mismo virtualenv y un mismo conjunto de definiciones SQLModel/Pydantic. *(valor por defecto, ajustable — una alternativa sería un workspace `uv` con `pyproject.toml` por paquete si el venv compartido genera conflictos de dependencias entre rembg/open_clip y FastAPI.)*

**DEV-REQ-002.** `engine` NO DEBE contener I/O (ni sesión de BD ni cliente HTTP) para seguir siendo testeable como funciones puras según D1. `ml` (08-local-vision.md) DEBE ser usado únicamente por `worker`; `api` NO DEBE importarlo, para que los modelos de visión nunca se carguen en el proceso API (ver 08-local-vision.md, VIS-REQ-004/005 para el test que lo garantiza).

**DEV-REQ-003.** La app DEBE ser un único proyecto Expo (React Native + TypeScript) en `app/`, usando Expo Router, con destino iOS/Android (Expo Go) y web (`react-native-web`).

## Versión de Python y gestor de paquetes

**DEV-REQ-004.** El backend DEBE usar Python 3.12. *(valor por defecto, ajustable — `backend/pyproject.toml` ya fija `requires-python = ">=3.12,<3.13"`; la compatibilidad real con las dependencias pesadas de `ml` (rembg, open_clip, scikit-learn) se valida en el paso 1 del plan de implementación de 08-local-vision.md, no aquí.)*

**DEV-REQ-005.** Las dependencias del backend DEBEN gestionarse con `uv` (`uv sync`, `uv add`), según D16.

**DEV-REQ-006.** Las dependencias de la app DEBEN gestionarse con npm (`package-lock.json`). *(valor por defecto, ajustable — pnpm/yarn son alternativas válidas; la propia documentación de Expo usa npm por defecto.)*

## Herramientas de lint / format / type / test

| Aspecto | Backend | App |
| --- | --- | --- |
| Lint | `ruff check` | `eslint` (config de Expo) |
| Format | `ruff format` | `prettier` |
| Type check | `ty` (Astral) | `tsc --noEmit` (`strict: true` en `tsconfig.json`) |
| Tests | `pytest` (+ `pytest-cov` opcional) | `jest` vía `jest-expo` + `@testing-library/react-native` |

**DEV-REQ-007.** `tsconfig.json` DEBE tener `"strict": true`.

**DEV-REQ-008.** Todos los contratos del backend (esquemas de request/response de la API, modelo de salida del LLM, settings) DEBEN ser modelos Pydantic v2 según D16. Los settings DEBEN usar `pydantic-settings`.

## Targets del Makefile

El `Makefile` raíz es el único punto de entrada (D16). Semántica exacta:

| Target | Semántica |
| --- | --- |
| `make install` | `cd backend && uv sync`; `cd app && npm install`. |
| `make run` | Arranca la API: `cd backend && uv run uvicorn api.main:app --reload --host $(PACHAPP_API_HOST) --port $(PACHAPP_API_PORT)`. |
| `make run-worker` | Arranca el proceso worker: `cd backend && uv run python -m worker.main`. Bucle de polling, carga los modelos ML al inicio (BiRefNet, SigLIP; ver 08-local-vision.md). |
| `make run-ui` | Arranca el servidor de desarrollo de Expo: `cd app && npx expo start`. Web accesible en `:8081`. |
| `make test` | Ejecuta `cd backend && uv run pytest` y `cd app && npm test`. Falla si alguno falla. |
| `make lint` | Ejecuta `ruff check backend/` y `npm --prefix app run lint`. |
| `make fmt` | Ejecuta `ruff format backend/` y `npm --prefix app run format` (prettier `--write`). |
| `make typecheck` | Ejecuta `ty check backend/src` y `npm --prefix app run typecheck` (`tsc --noEmit`). |
| `make migrate` | `cd backend && uv run alembic upgrade head`. Un target separado `make migrate-new name=<msg>` ejecuta `alembic revision --autogenerate -m <msg>` para crear nuevas migraciones. |
| `make gen-client` | Exporta el esquema OpenAPI en proceso (`cd backend && uv run python -m api.export_openapi`, sin servidor en ejecución) y ejecuta `openapi-typescript` contra el resultado, escribiendo los tipos en `app/src/api-client/schema.ts`. |
| `make ml-preload` | `cd backend && uv run python -m ml.preload`. Descarga/valida los modelos de visión en `PACHAPP_ML_CACHE_DIR` (08-local-vision.md). |
| `make ml-eval` | `cd backend && uv run python -m ml.eval`. Métricas de clasificación sobre `PACHAPP_ML_EVAL_DIR` (08-local-vision.md); no requiere la base de datos. |
| `make reembed` | `cd backend && uv run python -m worker.reembed`. Recalcula embeddings/clasificaciones tras un cambio de modelo, sin tocar campos con `source="user"` (08-local-vision.md). |

**DEV-REQ-009.** Todos los targets DEBEN poder ejecutarse desde la raíz del repo sin `cd` manual.

**DEV-REQ-010.** La salida de `make gen-client` DEBE quedar versionada en el repo (los tipos generados no están en `.gitignore`) para que la app pueda compilar sin que la API esté corriendo.

## Claves de settings / `.env`

Todas las claves se leen mediante un modelo `Settings` de `pydantic-settings` en `shared`, con estos valores por defecto. *(Todos los valores siguientes son por defecto, ajustables.)*

| Clave | Valor por defecto | Notas |
| --- | --- | --- |
| `PACHAPP_DATA_DIR` | `~/pachapp-data` | Directorio base para BD + imágenes. NO DEBE resolver bajo `/mnt/*` (D14). |
| `PACHAPP_DB_PATH` | `${PACHAPP_DATA_DIR}/db/pachapp.sqlite3` | Fichero SQLite, modo WAL. |
| `PACHAPP_IMAGES_ROOT` | `${PACHAPP_DATA_DIR}/images` | Raíz para las rutas relativas de imagen (ver 02-data-model.md). |
| `PACHAPP_API_HOST` | `0.0.0.0` | Debe escuchar en todas las interfaces para el acceso por LAN (D13). |
| `PACHAPP_API_PORT` | `8000` | |
| `PACHAPP_CORS_ORIGINS` | `["http://localhost:8081"]` | Ampliar con el origen `LAN-IP:8081` según D15; ver abajo. |
| `PACHAPP_LLM_PROVIDER` | *(ninguno — obligatorio solo si `PACHAPP_ML_LLM_FALLBACK=true`)* | p. ej. `anthropic`, `google`. Desde 08-local-vision.md, el LLM es un respaldo opcional (por defecto desactivado), no el clasificador primario. |
| `PACHAPP_LLM_MODEL_ID` | *(ninguno — obligatorio solo si el respaldo está activo, fijado según D11)* | Identificador/versión de modelo exacto, no un alias "latest". |
| `PACHAPP_LLM_API_KEY` | *(ninguno — obligatorio solo si el respaldo está activo, secreto)* | |
| `PACHAPP_ML_*` | Ver 08-local-vision.md | Device, modelos de visión, caché, kNN, respaldo LLM (`PACHAPP_ML_DEVICE`, `PACHAPP_ML_CACHE_DIR`, `PACHAPP_ML_BG_MODEL`, `PACHAPP_ML_EMBED_MODEL`, `PACHAPP_ML_EMBED_REVISION`, `PACHAPP_ML_MARGIN_THRESHOLD`, `PACHAPP_ML_KNN_K`, `PACHAPP_ML_KNN_MIN_VERIFIED`, `PACHAPP_ML_LLM_FALLBACK`, `PACHAPP_ML_EVAL_DIR`) — lista completa y valores por defecto en 08-local-vision.md, para no duplicarla aquí. |
| `PACHAPP_WORKER_POLL_INTERVAL_MS` | `500` | Intervalo de polling del worker sobre la tabla `job`. |
| `PACHAPP_DB_BUSY_TIMEOUT_MS` | `5000` | `busy_timeout` de SQLite (D4). |
| `PACHAPP_UPLOAD_MAX_PX` | `2048` | Tamaño objetivo de redimensionado en cliente antes de subir; el servidor también lo aplica como tope duro. |
| `PACHAPP_THUMB_PX` | `640` | Tamaño del lado largo de la miniatura. |
| `EXPO_PUBLIC_API_BASE_URL` | *(ninguno — obligatorio)* | Lado app; debe apuntar al `host:port` de la API accesible por LAN. |

**DEV-REQ-011.** Los secretos (`PACHAPP_LLM_API_KEY`) NO DEBEN tener un valor por defecto versionado. Cuando `PACHAPP_ML_LLM_FALLBACK=true` (08-local-vision.md), el arranque del worker DEBE fallar de forma inmediata y clara si falta `PACHAPP_LLM_API_KEY`, `PACHAPP_LLM_PROVIDER` o `PACHAPP_LLM_MODEL_ID`; cuando el respaldo está desactivado (valor por defecto), estas tres variables NO DEBEN exigirse.

## Puertos

- API: `8000`.
- Metro / Expo web: `8081`.

## CORS

**DEV-REQ-012.** La API DEBE configurar `CORSMiddleware` con `allow_origins` conteniendo exactamente el origen del servidor de desarrollo web de Expo (`http://localhost:8081`) y el equivalente en la LAN (`http://<lan-ip>:8081`), según D15. `allow_credentials` DEBE ser `false` (sin sesión/auth en la iteración 1). `allow_methods`/`allow_headers` PUEDEN ser permisivos (`["*"]`).

## Notas de configuración de WSL2

Refleja D13/D14 tal cual; se repite aquí como checklist operativo para `make install`/`make run`:

**DEV-REQ-013.** El `.wslconfig` del host Windows DEBE fijar `networkingMode=mirrored` (Windows 11 22H2+), con reglas de firewall de Hyper-V que permitan entrante en `8000` y `8081`. Plan B: `netsh interface portproxy` + una regla de Firewall de Windows; `expo start --tunnel` solo como último recurso (dependencia externa).

**DEV-REQ-014.** `PACHAPP_DATA_DIR` DEBE resolver a una ruta en el sistema de ficheros ext4 de WSL2 (p. ej. `~/pachapp-data`), nunca bajo `/mnt/d` ni ninguna ruta `/mnt/*` montada por 9P — necesario para el bloqueo por memoria compartida del modo WAL de SQLite y para el rendimiento de I/O de imágenes. El repositorio/código SÍ PUEDE vivir en `/mnt/d` (como este repositorio).

## Escenarios

**DEV-SCN-001 — Arranque desde clon limpio.**
Dado un entorno WSL2 Ubuntu recién instalado con `.wslconfig` en modo mirrored ya configurado,
Cuando el usuario ejecuta `make install`,
Entonces `uv sync` termina en `backend/` y `npm install` termina en `app/` sin pasos manuales adicionales.

**DEV-SCN-002 — Ejecución local en tres procesos.**
Dado que `make install` ha terminado y `.env` tiene `PACHAPP_DATA_DIR` apuntando bajo el home de WSL2,
Cuando el usuario ejecuta `make run`, `make run-worker` y `make run-ui` en tres terminales,
Entonces la API escucha en `0.0.0.0:8000`, el worker empieza a hacer polling sobre la tabla `job`, y Expo arranca en `:8081`, y un móvil en la misma Wi-Fi puede alcanzar la API por la IP LAN del PC.

**DEV-SCN-003 — Regeneración del cliente tras un cambio de esquema.**
Dado que un modelo Pydantic de request/response de un router ha cambiado,
Cuando el usuario ejecuta `make gen-client`,
Entonces `app/src/api-client/schema.ts` se regenera y `make typecheck` en la app señala cualquier punto de llamada ahora roto.

**DEV-SCN-004 — Directorio de datos mal configurado.**
Dado que `PACHAPP_DATA_DIR` está fijado a una ruta bajo `/mnt/d`,
Cuando `make run` arranca la API,
Entonces el arranque DEBE fallar de inmediato con un error explícito que cite D14, en lugar de correr silenciosamente con el comportamiento WAL de SQLite degradado.

## Criterios de aceptación

- `make install && make run && make run-worker && make run-ui` levanta los tres procesos sin intervención manual más allá de crear `.env`.
- Un móvil en la misma red Wi-Fi que el PC puede cargar la app en Expo Go y alcanzar la API (valida D13 de extremo a extremo).
- `make lint`, `make fmt`, `make typecheck`, `make test` terminan con código 0 sobre un checkout limpio.
- `make gen-client` produce tipos del lado app que compilan contra el esquema actual de la API.

## Preguntas abiertas

- Versión exacta de Python (3.12 vs 3.13) — `pyproject.toml` ya pinea `>=3.12,<3.13`; queda por validar en el paso 1 de 08-local-vision.md que rembg/open_clip/scikit-learn instalan sin fricción en esa versión (y la variante de torch, CPU vs CUDA — ver 08-local-vision.md).
- `ty` (Astral) está en desarrollo activo/preview a fecha de esta spec — si su cobertura de casos resulta insuficiente durante la implementación, `mypy` o `pyright` quedan como alternativas de repliegue, pero la decisión tomada es usar `ty` como type checker del backend.
- Backend en un único proyecto con venv compartido (DEV-REQ-001) vs un workspace `uv` con `pyproject.toml` por paquete — solo importa si las dependencias pesadas exclusivas del worker (torch, open_clip_torch, rembg, pillow, numpy, scikit-learn — que llegan con el paso 1 de 08-local-vision.md) ralentizan de forma notable los flujos de desarrollo que solo tocan la API.
- ~~Si `make gen-client` debería soportar exportar el esquema sin necesidad de un servidor en ejecución (`python -c "... print(app.openapi())"`) para evitar el problema de bootstrapping "el servidor debe estar corriendo" señalado arriba.~~ Resuelto: sí — `make gen-client` exporta el esquema en proceso vía `api.export_openapi` (ver tabla de targets arriba); nunca requiere `make run`.
