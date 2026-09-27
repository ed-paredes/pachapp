# 05 — Motor de outfits

Estado: Draft

## Alcance

Plantillas con capas, filtros duros (incluyendo orden/compatibilidad de capas), componentes de puntuación con sus fórmulas, cómo afectan las capas/complementos a cada puntuación, el algoritmo de generación en dos etapas con su presupuesto de complejidad, diversidad MMR, prenda fijada, cambio de una sola pieza, plantillas de explicación, determinismo/semilla, y el contrato del endpoint `generate`. **Nota (D8):** la temporada NO participa en filtros ni en puntuación en la iteración 1 — ver "Cambios de decisión" más abajo.

## Fuera de alcance

La persistencia de outfits (solo persisten las interacciones — 06-feedback-history.md), la mejora de "regresión logística entrenada con el feedback" que el borrador nombra como trabajo futuro (explícitamente fuera de la iteración 1).

## Dependencias

- Decisiones: D1 (motor en dos etapas), D17 (capas: `mid_layer`, N complementos, `outfit_item.layer`), D18 (reglas de color básicas), D19 (no afecta a esta spec directamente). D8 fue descartado en la iteración 1 (sin filtro ni puntuación por temporada) — ver "Cambios de decisión" más abajo.
- Modelo de datos: `garment`, `outfit`, `outfit_item`, `setting` (02-data-model.md). `engine` DEBE ser funciones puras sin I/O (DEV-REQ-002); el router de la API se encarga de obtener las entradas y de persistir ante la interacción.

## Plantillas

- **Plantilla A:** `top + bottom + shoes`.
- **Plantilla B:** `one_piece + shoes`.
- Ambas plantillas admiten además, opcionalmente: 1 `mid_layer`, 1 `outerwear`, hasta `setting.max_accessories` prendas `accessory` (por defecto 2), nunca dos complementos del mismo `subcategory` (D17).

**ENG-REQ-001.** El motor DEBE generar los candidatos base de ambas plantillas de forma independiente y clasificarlos en un único conjunto combinado (no dos pools de top-K separados) antes de la extensión con capas.

## Filtros duros

Se aplican antes de puntuar (etapa 1) o antes de la clasificación final (adiciones de la etapa 2), en este orden:

**ENG-REQ-002.** Solo las prendas con `garment.status = active` son elegibles para cualquier hueco.

**ENG-REQ-003.** La dispersión de formalidad entre **todas** las prendas presentes en el outfit candidato (base + cualquier extensión) DEBE ser `≤ 1` (`max(formality) - min(formality) ≤ 1`). Esto amplía la regla del borrador, que solo se aplicaba a la base, para cubrir también capas/complementos, ya que D17 convierte a estos en miembros del outfit de pleno derecho.

**ENG-REQ-004. (Retirado — ver D8.)** ~~Cada prenda del outfit candidato DEBE incluir la temporada actual en su lista `seasons`.~~ D8 fue descartado por decisión del usuario: la iteración 1 NO aplica ningún filtro ni puntuación por temporada. Esto retira tanto el filtro de temporada actual que esta spec definía (que a su vez sustituía la regla original del borrador de "al menos una temporada compartida entre las prendas") como esa regla original — ninguna de las dos está activa. `garment.seasons` se sigue extrayendo (03-garment-ingestion.md) y almacenando (02-data-model.md) para uso futuro, pero el motor no lo lee. Ver "Cambios de decisión" más abajo.

**ENG-REQ-005.** Ningún outfit candidato puede tener un conjunto de prendas idéntico (por conjunto de `garment_id`, sin importar el orden) al de ningún outfit referenciado por una entrada de `wear_log` en los últimos `setting.no_repeat_days` (por defecto 14) días.

**ENG-REQ-006.** Si la petición incluye una lista `fixed_garment_ids`, cada prenda de la lista DEBE aparecer en todos los outfits candidatos, en el hueco que le corresponda según su `category` (ver Prenda fijada / cambio de una sola pieza más abajo).

**ENG-REQ-007 (D18).** Máximo **2** colores no neutros dominantes (por `colors[0]`, `is_neutral=false`) entre las **prendas de ropa** del outfit (`top`, `bottom`, `one_piece`, `mid_layer`, `outerwear`, `shoes`; base + extensiones de capa) — los complementos (`accessory`) NO cuentan para este máximo (D18, ver ENG-REQ-011). Este es un filtro duro (los outfits que lo superan se rechazan), no una penalización en la puntuación. El máximo de 2 es **fijo y no configurable** (D18 lo decide explícitamente así, revirtiendo el `setting.max_non_neutral_colors` configurable que una revisión anterior había introducido) — ver Conflictos resueltos y Cambios de decisión.

**ENG-REQ-008.** Ningún par de prendas `accessory` del mismo outfit puede compartir `subcategory` (D17).

## Algoritmo de generación en dos etapas (D1)

**Etapa 1 — candidatos base.**
Enumerar las combinaciones de la `Plantilla A` (`top × bottom × shoes`) y la `Plantilla B` (`one_piece × shoes`), aplicando ENG-REQ-002, ENG-REQ-003 y ENG-REQ-006 como filtros vectorizados por bloques (ENG-REQ-004 está retirado, ver D8) (máscaras booleanas de numpy sobre arrays de atributos por prenda precalculados) antes de puntuar — los filtros recortan el espacio combinatorio en torno a 5–10× según la evidencia de D1 en c4.md. Puntuar cada base superviviente usando los cuatro componentes calculados sobre el conjunto de prendas solo-base (color/estilo/novedad/preferencia — ver abajo). Tomar las `K ≈ 300` mejores bases por puntuación, entre ambas plantillas combinadas. *(K es un valor por defecto, ajustable.)*

**Etapa 2 — extensión con capas.**
Para cada una de las K bases, extender de forma independiente y greedy (no mediante búsqueda combinatoria completa, para mantenerse dentro del presupuesto de complejidad):

1. Considerar los candidatos `mid_layer` elegibles de la base (que pasen todos los filtros duros junto con la base); elegir el único que maximice la puntuación total **marginal**, o ninguno si ningún candidato mejora la puntuación de la base sola. Si `fixed_garment_ids` fija un `mid_layer`, usarlo directamente y saltar la selección.
2. Repetir de forma independiente para `outerwear`.
3. Añadir de forma greedy hasta `max_accessories` complementos, uno cada vez, eligiendo en cada paso el complemento elegible y de subtipo aún no usado que maximice la puntuación marginal, deteniéndose antes si ningún candidato restante mejora la puntuación.

Repuntuar el outfit totalmente extendido (todos los huecos presentes) usando los cuatro componentes sobre el conjunto completo de prendas, y luego volver a comprobar ENG-REQ-003/007/008 (las extensiones pueden violar la dispersión de formalidad, el conteo de colores o las reglas de subtipo de complementos aunque la base por sí sola fuera válida). Si el recálculo falla, aplicar el procedimiento de repliegue de ENG-REQ-023 antes de descartar el candidato.

**ENG-REQ-009.** La extensión de la etapa 2 DEBE ser greedy por hueco (mid_layer, luego outerwear, luego complementos en secuencia), no exhaustiva sobre todas las combinaciones de elecciones de capas — necesario para mantener el producto de 300 bases × búsqueda de capas dentro del presupuesto de <1s. *(valor por defecto, ajustable — intercambia una elección combinada de capas teóricamente mejor por un tiempo de ejecución acotado; aceptable porque las capas son una porción menor de la puntuación total que el color/estilo.)*

**ENG-REQ-010.** Tras la etapa 2, aplicar MMR (abajo) sobre el pool repuntuado y que pasa los filtros para seleccionar las 5 propuestas finales.

**ENG-REQ-023.** Si el re-chequeo de filtros duros tras la extensión completa (ENG-REQ-003/007/008) falla para un candidato, el motor NO DEBE descartarlo de inmediato. DEBE, en este orden: (1) identificar el hueco opcional implicado en la violación (el `mid_layer`, el `outerwear`, o el complemento concreto añadido más recientemente que la causó) y probar la siguiente mejor opción disponible para ese hueco entre los candidatos elegibles restantes, repitiendo el re-chequeo; (2) si ninguna alternativa para ese hueco pasa los filtros, omitir ese hueco opcional por completo (recaer en la base sin esa capa/complemento concreto) y repetir el re-chequeo sobre el resto de la extensión; (3) solo si, tras omitir el hueco opcional implicado, el outfit resultante (que puede ser la base sin extender) sigue sin pasar los filtros duros, descartar el candidato por completo como último recurso. Este repliegue por hueco se aplica de forma independiente a `mid_layer`, `outerwear` y a cada `accessory` según cuál haya causado el fallo.

## Puntuación

```
S = 0.35·C_color + 0.25·C_estilo + 0.25·C_novedad + 0.15·C_preferencia
```

Los pesos son `setting.weight_*`, con los valores anteriores por defecto (valores iniciales del borrador), ajustables por el usuario vía `PATCH /settings` (DAT-REQ-011).

### `C_color` (D18 — reglas básicas)

Calculado solo sobre los colores no neutros presentes entre las **prendas de ropa** (`top`, `bottom`, `one_piece`, `mid_layer`, `outerwear`, `shoes`); los complementos (`accessory`) NO participan en este cálculo ni cuentan para el máximo (D18, ver ENG-REQ-011 y ENG-REQ-007):

- 0 o 1 colores no neutros presentes (el resto neutros): puntuación alta (los neutros combinan con todo).
- Exactamente 2 colores no neutros (el máximo permitido, D18): puntuar por la relación de tono entre sus ángulos de matiz derivados de `lab`, con **solo tres niveles**: análogos (`Δh ≤ 30°`) → alto; complementarios (`Δh` entre `150°–210°`) → medio; cualquier otro caso → bajo.
- Penalización fuerte: 2 o más prendas con un patrón "llamativo" (`pattern ∈ {striped, plaid, printed}`, es decir, no `solid`/`textured`) presentes a la vez (se mantiene de la versión anterior).

D18 elimina explícitamente el bono de tono sobre tono y el nivel de tríada que esta spec incluía antes — no se implementan.

Valores numéricos concretos para los tres niveles (antes descritos solo cualitativamente como "alto/medio/bajo"):

```python
# (valor por defecto, ajustable)
HUE_SCORE_ANALOGOUS = 0.9       # Δh ≤ 30°
HUE_SCORE_COMPLEMENTARY = 0.5   # Δh entre 150° y 210°
HUE_SCORE_OTHER = 0.1            # cualquier otro Δh
```

**ENG-REQ-011.** Las prendas `mid_layer` y `outerwear` cuentan para el filtro duro de color (ENG-REQ-007) y para la puntuación por relación de matiz exactamente igual que las prendas de huecos base — no están exentas. Las prendas `accessory` NO cuentan para el filtro duro de color ni participan en la puntuación por relación de matiz (D18): un complemento de color vivo no bloquea el límite de 2 ni se computa en `C_color`, aunque sigue contribuyendo con normalidad a `C_estilo`, `C_novedad` y `C_preferencia` como cualquier otra prenda del outfit.

### `C_estilo`

- Baja varianza de `formality` entre todas las prendas presentes (normalizada a `[0,1]`, menor varianza → mayor puntuación).
- `style_tags` compartidos: similitud de Jaccard media por pares de los conjuntos de `style_tags` entre todas las prendas presentes.
- Similitud coseno media por pares de los `embedding` CLIP entre todas las prendas presentes.

Combinar los tres subcomponentes con igual peso en `C_estilo`, salvo/hasta que se ajusten. *(valor por defecto, ajustable.)*

### `C_novedad`

Penalización de recencia por prenda: `p_i = e^{-días\_desde\_último\_uso_i / 7}` (≈1 si se llevó hoy, →0 según pasan los días; las prendas nunca llevadas se tratan con un número de días muy grande, `p_i ≈ 0`). La contribución de novedad por prenda es `1 - p_i`.

`C_novedad = media(1 - p_i sobre todas las prendas presentes) - penalización_pareja + bono_olvidada`, acotado a `[0,1]`.

- `penalización_pareja`: restar una penalización fija (por defecto `0.15`, ajustable) si algún par de prendas presentes se llevó junto en un outfit referenciado por `wear_log` dentro de `setting.no_repeat_days` (reutilizando la misma ventana que ENG-REQ-005, en lugar de una ventana separada — el borrador no especifica la ventana de pareja).
- `bono_olvidada`: sumar un bono fijo (por defecto `0.1`, ajustable) por prenda no usada en ≥60 días ("prendas olvidadas" del borrador), acotado para que el bono total no exceda `0.3`.

**ENG-REQ-012.** Las prendas `mid_layer`/`outerwear`/`accessory` contribuyen a `C_novedad` por prenda exactamente igual que las de huecos base (su propia decaída de recencia cuenta).

### `C_preferencia`

Para cada par de prendas presentes en el outfit, consultar cuántas veces ese par exacto coincidió en filas de `outfit_item` pertenecientes a outfits favoritos (`is_favorite=true` o `rating=1`) frente a descartados (`rating=-1`). Sumar `+1` por cada coincidencia favorita, `-1` por cada coincidencia descartada, entre todos los pares; normalizar (p. ej. vía `tanh` o min-max frente al número máximo posible de pares) a `[0,1]`, con `0.5` como línea base neutra (sin historial). *(valor por defecto, ajustable — la fórmula es una heurística provisional; el borrador nombra explícitamente una futura mejora con regresión logística como fuera de alcance para la iteración 1.)*

**ENG-REQ-013.** Los pares de complementos y capas participan en la misma consulta de preferencia por pares que los pares de huecos base — sin excepción por tipo de hueco.

## Diversidad MMR

**ENG-REQ-014.** Del pool resultante de la etapa 2 (ya filtrado por los filtros duros, puntuado), seleccionar los 5 finales mediante Maximal Marginal Relevance: elegir iterativamente `argmax_o [λ·score(o) - (1-λ)·max_sim(o, seleccionados)]`, donde `sim(o, o')` = similitud de Jaccard de los conjuntos de ids de prenda de ambos outfits, y `λ = 0.7` por defecto (ajustable; un valor mayor favorece la puntuación bruta sobre la diversidad).

**ENG-REQ-015.** Tope duro: ninguna prenda puede aparecer en más de 2 de las 5 propuestas finales (regla explícita del borrador). Si el candidato seleccionado por MMR violara esto, se descarta y se continúa con el siguiente mejor candidato.

## Prenda fijada / cambio de una sola pieza

**ENG-REQ-016.** `POST /outfits/generate` acepta `fixed_garment_ids: list[UUID]` (sustituye al diseño anterior de un mapa `{slot: garment_id}`, que no podía expresar dos complementos fijados a la vez porque ambos comparten la clave `accessory` — hallazgo A3 de la revisión). El hueco de cada prenda fijada se infiere de su `garment.category` (que coincide 1:1 con los valores de `OutfitSlot`). Para las prendas fijadas cuya categoría es un hueco de plantilla base (`top`, `bottom`, `one_piece`, `shoes`), la etapa 1 se filtra a solo combinaciones que incluyan esa prenda en ese hueco. Para las prendas fijadas cuya categoría es un hueco de capa/complemento (`mid_layer`, `outerwear`, `accessory`), se usan de forma forzada en la etapa 2 para cada base superviviente (evitando la selección greedy para esa instancia de hueco concreta; con varias prendas `accessory` fijadas, todas se fuerzan, y la selección greedy de complementos solo sigue buscando para las posiciones restantes hasta `max_accessories`), mientras que los huecos de capa no fijados se siguen buscando con normalidad.

**ENG-REQ-017.** "Cambiar solo esta pieza" se implementa haciendo que el cliente vuelva a llamar a `generate` con `fixed_garment_ids` fijado a los `garment_id` de todas las prendas del outfit mostrado actualmente **excepto** la que se está cambiando, más `replace_garment_id` fijado al `garment_id` de la prenda que ocupa el hueco a cambiar. El motor DEBE excluir `replace_garment_id` de todo resultado devuelto (no solo del hueco que se está cambiando) para garantizar un resultado distinto. No hace falta un endpoint de swap separado (ver Conflictos resueltos).

**ENG-REQ-024.** Cuando `fixed_garment_ids` incluye una prenda cuya categoría es `mid_layer`, `outerwear` o `accessory` (una "prenda fijada de capa"), la etapa 1 DEBE restringirse a bases compatibles con esa prenda: dentro de `≤ 1` de su `formality` (para que ENG-REQ-003 pueda seguir cumplirse tras la extensión forzada); y, **solo si la prenda fijada es `mid_layer` u `outerwear` no neutra** (los `accessory` no cuentan para el filtro de color según D18/ENG-REQ-011, así que una prenda fijada de tipo `accessory` no impone esta restricción), que la base tenga como máximo **1** color no neutro propio (de los 2 permitidos en total, D18). Sin esta restricción, la etapa 1 podría llenar las K mejores bases con combinaciones que luego resulten incompatibles con la prenda fijada en la etapa 2, dejando menos de 5 propuestas válidas sin necesidad. *(La restricción de temporada que esta regla incluía antes está retirada — ver D8/ENG-REQ-004.)*

**ENG-REQ-025.** Si, tras aplicar ENG-REQ-024 y completar el pipeline de dos etapas, el número de propuestas válidas resultantes es menor que 5, el motor DEBERÍA ampliar dinámicamente `K` (p. ej. duplicarlo respecto al valor de `setting`, hasta un tope superior de seguridad como `K ≤ 2000`) y repetir la etapa 1/2 antes de conformarse con menos de 5 propuestas — solo aplica cuando hay una prenda fijada de capa/complemento (ENG-REQ-024), ya que es el caso donde el filtrado adicional reduce más el pool. Si tras ampliar `K` hasta el tope siguen sin alcanzarse 5 propuestas, aplica ENG-REQ-022 (se devuelven las que haya, incluyendo posiblemente 0). *(Valor de partida de K, factor de ampliación y tope superior: valores por defecto, ajustables.)*

**ENG-REQ-026.** `fixed_garment_ids` NO DEBE incluir más de una prenda para ningún hueco de instancia única (`top`, `bottom`, `one_piece`, `shoes`, `mid_layer`, `outerwear`), NO DEBE incluir más prendas `accessory` que `setting.max_accessories`, y NO DEBE incluir dos prendas `accessory` con el mismo `subcategory` (refleja ENG-REQ-008). Una petición que viole cualquiera de estas condiciones DEBE rechazarse con `400`.

## Plantillas de explicación

**ENG-REQ-018.** Cada propuesta DEBE incluir una `explanation` de una frase en español, generada a partir de `score_breakdown` eligiendo el/los 1–2 componentes con mayor contribución normalizada y rellenando una plantilla acorde, p. ej.:

- Liderada por color: `"{Color1} y {color2}: {relación} clásicos."` (p. ej. "Marino y camel: neutros clásicos.")
- Liderada por novedad: `"Hace {N} semanas que no usas {prenda}."`
- Liderada por estilo: `"Look {estilo} coherente de arriba abajo."`
- Combinada (los 2 componentes principales empatan de cerca): concatenar ambas frases.

*(Conjunto exacto de plantillas y umbrales de selección: valor por defecto, ajustable — el borrador da un solo ejemplo, no un conjunto exhaustivo.)*

## Determinismo / semilla

**ENG-REQ-019.** La puntuación en sí DEBE ser totalmente determinista dadas entradas idénticas (sin aleatoriedad en los cuatro componentes de puntuación). La única fuente de no-determinismo es el desempate durante la extensión greedy de la etapa 2 y la selección MMR cuando varios candidatos puntúan igual; un campo opcional de la petición `seed: int` se propaga a un RNG con semilla usado **solo** para el desempate, con un valor fijo por defecto (p. ej. `0`) cuando se omite, para que los tests puedan verificar una salida exacta.

## Contrato de `POST /outfits/generate`

**ENG-REQ-020.** Petición:

```python
class GenerateOutfitsRequest(BaseModel):
    fixed_garment_ids: list[UUID] | None = None   # hueco inferido de garment.category; una entrada = "prenda fijada" clásica
    replace_garment_id: UUID | None = None          # cambio de una sola pieza: excluir esta prenda de todos los resultados
    seed: int | None = None
```

Respuesta `200`:

```python
class OutfitProposal(BaseModel):
    items: list[OutfitItemProposal]  # {garment_id, slot, layer}
    score: float
    score_breakdown: ScoreBreakdown
    explanation: str

class GenerateOutfitsResponse(BaseModel):
    proposals: list[OutfitProposal]   # hasta 5
    generated_at: datetime
```

**ENG-REQ-021.** Las propuestas **no** se persisten en el momento de la generación (D6) — no se crea ninguna fila `outfit`/`outfit_item` hasta que ocurre una interacción calificante (06-feedback-history.md).

**ENG-REQ-022.** Si, tras aplicar ENG-REQ-024/025 cuando corresponda, existen menos de 5 outfits válidos tras el filtrado duro (p. ej. armario muy pequeño, o `fixed_garment_ids` demasiado restrictivo), la respuesta DEBE seguir siendo `200` con `proposals` conteniendo el número válido encontrado (incluyendo posiblemente `0`), nunca un error — un armario pequeño o vacío es un estado normal, no un fallo.

## Escenarios

**ENG-SCN-001 — Camino feliz a escala.**
Dadas 300 prendas activas que abarcan todas las categorías, incluyendo `mid_layer`/`outerwear`/`accessory`,
Cuando se llama a `POST /outfits/generate` sin filtros,
Entonces la respuesta se devuelve en menos de 1 segundo y contiene 5 propuestas variadas (objetivo de la Fase 3 del borrador).

**ENG-SCN-002 — Prenda fijada.**
Dado que se pasa el id de una prenda `top` concreta en `fixed_garment_ids=[top_id]`,
Cuando se generan propuestas,
Entonces cada una de las 5 propuestas incluye exactamente esa prenda en el hueco `top` (inferido de su `category`).

**ENG-SCN-002b — Prenda fijada de complemento múltiple.**
Dado que se pasan dos prendas `accessory` de distinto `subcategory` en `fixed_garment_ids=[belt_id, scarf_id]`,
Cuando se generan propuestas,
Entonces cada una de las propuestas incluye ambos complementos (algo que el diseño anterior con `fixed_slots: dict[OutfitSlot, UUID]` no podía expresar, ya que ambas entradas comparten la clave `accessory`).

**ENG-SCN-003 — Cambio de una sola pieza.**
Dado un outfit mostrado con prendas `A` (top), `B` (bottom), `C` (shoes) y el usuario pide cambiar solo el calzado,
Cuando el cliente llama a `generate` con `fixed_garment_ids=[A, B]` y `replace_garment_id=C`,
Entonces todas las propuestas devueltas mantienen las prendas `A` y `B` en sus huecos correspondientes y `C` no aparece en ningún hueco de ninguna propuesta.

**ENG-SCN-004 (Retirado — ver D8).** ~~Filtro duro de temporada.~~ Este escenario probaba ENG-REQ-004, retirado por D8: la iteración 1 no filtra ni puntúa por temporada, así que una prenda `outerwear` de lana SÍ puede aparecer en cualquier propuesta en cualquier época del año, independientemente de su campo `seasons`.

**ENG-SCN-005 — Filtro duro de conteo de colores, con repliegue.**
Dado que la base `top` rojo + `bottom` + `shoes` (1 color no neutro, dentro del límite fijo de 2, D18) ya tiene un `outerwear` verde elegido en el paso anterior de la etapa 2 (2 colores no neutros, en el límite), y el mejor `mid_layer` candidato es azul (elevaría el conteo de las prendas de ropa a 3),
Cuando la etapa 2 vuelve a comprobar los filtros duros tras intentar añadir ese `mid_layer`,
Entonces, por ENG-REQ-023, el motor NO descarta directamente el candidato: primero prueba el siguiente mejor `mid_layer` elegible que no rompa el límite de color; si ninguno lo cumple, omite el hueco `mid_layer` por completo y conserva `top + outerwear + bottom + shoes` (2 colores no neutros) como propuesta válida. Un `accessory` de cualquier color, en cambio, nunca puede causar esta violación (D18/ENG-REQ-011: los complementos no cuentan para el límite de color).

**ENG-SCN-005b — Repliegue hasta omitir una capa completa.**
Dado que, para una base concreta, tanto el `mid_layer` mejor puntuado como todas sus alternativas elegibles harían que el outfit superara el máximo fijo de 2 colores no neutros (D18) junto con el `outerwear` ya elegido en el paso anterior,
Cuando la etapa 2 re-chequea los filtros duros tras intentar cada alternativa de `mid_layer`,
Entonces, agotadas las alternativas de ese hueco, el motor omite el hueco `mid_layer` por completo (ENG-REQ-023, paso 2) y conserva el outfit con `outerwear` pero sin `mid_layer`, en lugar de descartar el candidato entero.

**ENG-SCN-006 — Unicidad de subtipo de complemento.**
Dados dos complementos `belt` (cinturón) elegibles,
Cuando se ejecuta la selección greedy de complementos de la etapa 2,
Entonces solo se añade uno a un outfit dado; el segundo se descarta sin importar su puntuación.

**ENG-SCN-007 — Tope de aparición de MMR.**
Dado que una prenda puntúa más alto en casi todas las combinaciones base,
Cuando se selecciona el top 5,
Entonces esa prenda aparece como máximo en 2 de las 5 propuestas finales.

**ENG-SCN-008 — Ventana de no repetición.**
Dado que un conjunto exacto de prendas se registró vía `wear_log` hace 5 días,
Cuando se generan outfits hoy,
Entonces esa combinación exacta se excluye (`setting.no_repeat_days = 14` por defecto), aunque sus prendas individuales sí puedan aparecer en combinaciones *distintas*.

**ENG-SCN-009 — Armario escaso.**
Dado que solo existen 4 prendas activas, insuficientes para rellenar válidamente ninguna plantilla,
Cuando se llama a `generate`,
Entonces la respuesta es `200` con `proposals: []`, no un error.

**ENG-SCN-010 — Prenda fijada de capa, con ampliación dinámica de K.**
Dado que se fija un `outerwear` de formalidad 4 y color no neutro en `fixed_garment_ids`, y con `K=300` (valor de `setting`) solo 3 de las bases resultantes son compatibles con esa prenda (ENG-REQ-024) tras la etapa 2,
Cuando `generate` detecta menos de 5 propuestas válidas,
Entonces, por ENG-REQ-025, el motor reintenta con `K` ampliado (p. ej. `K=600`) antes de devolver la respuesta, y el resultado final contiene más de 3 propuestas si existen suficientes bases compatibles adicionales entre las prendas activas.

## Criterios de aceptación

- 5 propuestas devueltas en menos de 1 segundo con 300 prendas activas (medido, no estimado) — objetivo de la Fase 3 del borrador.
- UAT manual: de 20 propuestas generadas, el usuario se pondría al menos la mitad (objetivo de la Fase 3 del borrador; cualitativo, no automatizable — se rastrea como comprobación manual, no como test unitario).
- Tras "me lo pongo", ese outfit exacto no vuelve a aparecer en 14 días, y sus prendas bajan visiblemente en el ranking de propuestas siguientes por la penalización de novedad (objetivo de la Fase 4 del borrador; referencia cruzada 06-feedback-history.md para el lado de persistencia).

## Conflictos resueltos (borrador vs c4.md)

- **Generación de combinaciones por fuerza bruta reemplazada por el motor en dos etapas.** La sección del motor del borrador describe evaluar "todas las combinaciones válidas" por fuerza bruta en menos de un segundo. D1 anula explícitamente esto con el algoritmo de base/extensión en dos etapas porque la fuerza bruta completa incluyendo capas es combinatoriamente inviable con 300 prendas (c4.md cita ~112M combinaciones). Esta spec implementa D1, no la descripción de fuerza bruta del borrador.
- **"Cambiar solo esta pieza" no es un endpoint separado.** El borrador sugiere una acción de UI dedicada para regenerar un solo hueco. ENG-REQ-017 la implementa reutilizando `POST /outfits/generate` con `fixed_garment_ids` + `replace_garment_id` en lugar de crear un endpoint de swap propio — un único contrato de generación cubre tanto "generar desde cero" como "prenda fijada" como "cambiar una pieza". (Nota de la revisión independiente, hallazgo M2: `docs/architecture/c4.md` se actualizará por separado para reflejar que no existe un endpoint de swap dedicado.)

## Cambios de decisión (D8 / D18)

Estas decisiones del usuario, posteriores a la versión inicial de esta spec, están ya reflejadas arriba; se documentan aquí para trazabilidad.

- **D8 — temporada retirada por completo.** Una versión anterior de esta spec definía ENG-REQ-004 (filtro duro de temporada actual, basado en `setting.hemisphere`) como reemplazo de la regla original del borrador ("al menos una temporada en común"). El usuario decidió posteriormente descartar D8 sin más: la iteración 1 no aplica ningún filtro ni puntuación por temporada, ni la versión del borrador ni la de D8. ENG-REQ-004 queda retirado (marcado arriba, no eliminado, para trazabilidad); `garment.seasons` se sigue extrayendo y guardando para uso futuro (02-data-model.md, 03-garment-ingestion.md), pero el motor no lo consulta. Se elimina también toda mención al hemisferio y a `setting.hemisphere` (columna retirada de 02-data-model.md).
- **D18 — reglas de color básicas, revertidas desde la versión configurable.** Una revisión independiente anterior había convertido el máximo de colores no neutros en un valor configurable (`setting.max_non_neutral_colors`) y había añadido un bono de tono sobre tono y un nivel de tríada a la puntuación de color. El usuario decidió D18 para simplificar: el máximo vuelve a ser fijo en 2 y no configurable (`setting.max_non_neutral_colors` retirado de 02/04/05), los complementos (`accessory`) dejan de contar para ese máximo, y la puntuación de matiz vuelve a tener solo tres niveles (análogos/complementarios/resto) sin bono de tono sobre tono ni tríada. ENG-REQ-007 y ENG-REQ-011 quedan actualizados con el nuevo comportamiento (ver arriba); no se retira ningún ID porque el concepto sigue vigente, solo cambia su valor y alcance.

## Preguntas abiertas

- Los umbrales exactos de ángulo de matiz (análogos ≤30°, complementarios 150–210°) y sus magnitudes de puntuación numéricas (`HUE_SCORE_ANALOGOUS=0.9`, `HUE_SCORE_COMPLEMENTARY=0.5`, `HUE_SCORE_OTHER=0.1`) se toman como valores de ingeniería razonables, sin probar contra fotos reales de armario — probablemente necesiten calibración.
- La ponderación igual de las tres subpartes de `C_estilo` (varianza de formalidad, solape de tags, similitud de embeddings) es un valor por defecto de ingeniería; no hay indicación de producto sobre su importancia relativa.
- Las magnitudes de `penalización_pareja`/`bono_olvidada` (0.15/0.1) en `C_novedad` son valores por defecto inventados — el borrador nombra los mecanismos pero no sus pesos.
- La fórmula de normalización de `C_preferencia` es un placeholder; el propio borrador marca su eventual reemplazo (regresión logística) como trabajo futuro, así que la heurística de la iteración 1 es inherentemente provisional.
- K≈300 (bases candidatas de la etapa 1) y la estrategia de extensión greedy (frente a combinatoria limitada) de la etapa 2 son valores por defecto de ingeniería de D1/ENG-REQ-009, sin medir todavía contra el presupuesto de <1s en hardware real — necesita un benchmark una vez implementado.
- El factor y el tope de la ampliación dinámica de `K` en ENG-REQ-025 (hallazgo M1) son valores por defecto sin calibrar; necesitan un benchmark de rendimiento igual que el propio K≈300 base, especialmente para el caso de prenda fijada de capa poco compatible con el resto del armario.
