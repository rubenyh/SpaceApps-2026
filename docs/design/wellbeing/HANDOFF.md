# Wellbeing tab — Design handoff

Spec de implementación de la pestaña **Wellbeing** (salud mental) de la Spaceship Console.
Stack: React 19 + Vite + Tauri. Ventana 1280×800 (mínimo 1024×700), sólo tema oscuro.
Todo el texto visible de la UI va en **inglés**.

## Cómo leer este paquete

- `screens/*.dc.html` es la **referencia visual exacta**: layout, tamaños, copy y tokens. Ábrelos como HTML para leerlos.
  - **No los copies tal cual.** Usan sintaxis de plantilla del editor de diseño (`<x-dc>`, `<sc-for>`, `<sc-if>`, `{{hole}}`, `support.js`) y estilos inline. Tradúcelos a componentes React que usen `tokens.css` y las clases existentes del repo.
  - Las variables CSS de `:root` en cada archivo son una copia de `tokens.css`. Usa el `tokens.css` del repo, no esas copias.
- Este archivo dice **qué** construir y **con qué datos**. Si este documento y el HTML no coinciden, manda este documento.
- El contrato de datos es `docs/wellbeing-contract.md` (en el repo). Los nombres de campos de abajo salen de ahí.

| Archivo | Pantalla |
|---|---|
| `Main.dc.html` | 1 · Crew view + 6 · Today's video log |
| `Personal.dc.html` | 2 · Personal view + 3 · Timeline de 30 días (ejemplo ast-02) |
| `Checkin.dc.html` | 4 · Daily check-in |
| `Ground.dc.html` | 5 · Send to ground psychologist (consentimiento) |
| `States.dc.html` | Estados: discrepancia, calibrating, no data, stale, error de servicio, PIN lock, check-in guardado |
| `Handoff.dc.html` | Tablas de mapeo (mismo contenido que este archivo) |

## Navegación

- Nueva pestaña `Wellbeing` en `TabBar`, **sin** flags de alerta ni de stale.
- Dentro: `SegmentedControl` **Crew / Personal**. Personal usa el astronauta elegido en el `Header`.
- Personal es una sola página con scroll: Summary → Indicators → Timeline.
- Desde Personal hay dos sub-pantallas con "Back to Personal": **Daily check-in** y **Share with ground psychologist**.
- Personal, Check-in y Ground pasan antes por `PersonalLock` (PIN por astronauta). **Es obligatorio**: sin el bloqueo, cualquiera puede ver el detalle desde el selector del Header y la etiqueta "Private" sería falsa.
- Mientras Wellbeing está activa, el footer muestra la leyenda de bienestar.

## Endpoints

| Uso | Endpoint | Tipo |
|---|---|---|
| Crew view | `GET /wellbeing/crew` | `CrewWellbeing` |
| Personal | `GET /astronauts/{id}/wellbeing` | `WellbeingAssessment` |
| Timeline | `GET /astronauts/{id}/wellbeing/timeline?days=30` | `WellbeingTimeline` |
| Formulario | `GET /wellbeing/checkin-form` | `CheckinForm` |
| Guardar check-in | `PUT /astronauts/{id}/wellbeing/checkins/{day}` | — |
| Crear paquete | `POST /wellbeing/ground-packages` (requiere `consent.astronaut_confirmed: true`; sin eso responde 422) | `GroundPackage` |
| Vista previa | `GET /wellbeing/ground-packages/{id}/content` | — |
| Retirar | `POST /wellbeing/ground-packages/{id}/withdraw` | — |

## Mapeo de SupportLevel a estilo (sin colores nuevos)

| level | Label | Color | Borde | Ícono | Nota |
|---|---|---|---|---|---|
| `ok` | Doing well | `--state-normal` | `--border-normal` | círculo + check | igual que normal físico |
| `attention` | Attention | `--state-stale` | `2px solid` | círculo + onda | sólido, para no confundirse con "No recent data" |
| `needs_support` | Needs support | `--state-alert`, fondo `--state-alert-tint` | `--border-alert` | corazón (no triángulo) | **sin `--alert-pulse`**; la tarjeta ofrece una acción de apoyo |
| `baseline_pending` | Baseline pending | `--state-norange` | `--border-norange` (3px double) | círculo punteado + punto | "Baseline pending: insufficient data to compare with your usual." |
| `stale` | No recent data | `--state-stale` | `--border-stale` (dashed) | reloj | mostrar `latest_day` |
| `no_data` | Insufficient data | `--state-nodata` | `--border-nodata` (dotted) | círculo punteado + raya | valores como `---` |

`IndicatorStatus` usa el mismo mapa, pero `ok` se muestra como "Within usual", `attention` como "Changed vs. usual" y `stale` como "Insufficient data (stale)". Etiquetas en [`lib/wellbeing.ts`](../../../apps/spaceship-app/src/lib/wellbeing.ts).
Ningún estado de bienestar pulsa. El estado siempre lleva ícono + texto + borde, nunca sólo color.

## Mapeo de Origin

| origin | Chip | Estilo del chip | Celda de la timeline |
|---|---|---|---|
| `live` | LIVE | texto y borde 1px `--color-accent`, punto relleno, bold | relleno accent + "L" |
| `simulated` | SIMULATED | texto `--color-text-faint`, borde 1px dashed | trama diagonal 45° + "S" |
| `mixed` | MIXED | texto `--color-text-muted`, borde 1px solid, punto a medias | mitad trama, mitad accent + "M" |
| `null` | (sin chip) | — | borde 2px dotted nodata, vacía |

## Pantallas

### 1 · Crew view (`Main.dc.html`)
- Usa **sólo** `CrewMemberSummary`. Nunca muestres discrepancia, indicadores, `support_notes` ni `data_notices`.
- Grid de tarjetas de 2 columnas: `display_name`, `WellbeingPill(level)`, `TrendMark(trend)` y `OriginMark` (LIVE o MIXED resaltado; SIMULATED atenuado).
- Las tarjetas `needs_support` usan borde de alerta y fondo tint, sin pulso.
- Panel "The crew as a support network": una sugerencia por miembro en `attention` o `needs_support`, por ejemplo "Check in with Ana", con un gesto concreto y sin juicio.
- Banner de honestidad siempre visible: historial SIMULATED y datos de hoy LIVE, umbrales provisionales. También el tag `PROV.` y `generated_at`.
- Debajo, una nota de consentimiento: todos aceptaron el monitoreo y la vista de tripulación sólo muestra nivel y tendencia.
- Tarjeta 6, "Today's video log": fatiga y tensión del día contra la línea base, con chip LIVE y borde accent.

### 2 · Personal view (`Personal.dc.html`)
- Barra superior: aviso "Private: only you can see this detail" con candado, estado del check-in de hoy con botón Edit, botón "Share with ground psychologist…" y botón para bloquear.
- **Summary**: `WellbeingPill` grande, `PROV.`, `OriginMark`.
  - Frase del tipo "...away from your usual for {sustained_days} days, since {onset_date}". Si `onset_date` es null, se oculta.
  - Stats: Since, Sustained, Trend, `ConfidenceMeter`, `sustained_sources`.
  - Columna derecha: `support_notes[]` como "What might help" y `data_notices[]` como notas de calidad.
  - Si `discrepancy` es true, se muestra el bloque de discrepancia (ver `States.dc.html`): borde `--border-dubious`, copy "Your check-ins and other signals don't match".
- **Indicators**: 6 filas en orden fijo `sleep, fatigue, stress, activation, social, mood`. Cada fila lleva:
  - Nombre, estado, `ZTrack`, z, fuentes (`sources`), origen y un botón expandir de 44 px con `aria-expanded`.
  - Al expandir: tabla de `components[]` con component, source, `latest_value` + unit, `baseline_median`, z, y día y origen. Encima, "Deviating since {deviant_since} · baseline from {baseline_days} days, {baseline_from} – {baseline_to}".
- **ZTrack**: escala z de −2 a +4. La zona de `0` a `z_threshold` se pinta con `--range-zone`, y en el umbral va una línea dashed. Si z es null, la pista se ve punteada y vacía con `---`.

### 3 · Timeline (dentro de Personal)
- Una columna por día de `days[]`. Filas: marcador, fecha, origen, nivel (ícono) y las 6 tiras de indicadores.
- La barra de cada indicador mide `min(z,4)/4` de la altura de la celda. Bajo el umbral se dibuja con contorno verde y `--range-zone`; desde el umbral, con relleno `--state-stale`. Así la diferencia no depende sólo del color.
- Si z es null en un día con datos, la celda es dotted. Si `has_data` es false, la columna entera va dotted y el nivel como `---`.
- Onset: borde izquierdo de 2px `--color-text` en la columna de `onset_date`, con la etiqueta "Since {fecha}".
- El día de hoy lleva fondo `--color-surface-2` y la etiqueta "Today".
- Leyenda: S = simulated (trama), L = live, cuadro dotted = no data.

### 4 · Daily check-in (`Checkin.dc.html`)
- Se renderiza desde `CheckinForm.items[]`. El copy del diseño es de ejemplo; usa `prompt`, `min_label` y `max_label` del backend.
- `hours`: stepper con botones −/+ de 52 px, paso `step` (0.5), rango 0–24.
- `scale`: 5 botones de 60×52 con `aria-pressed` y etiquetas en los extremos. Si `higher_is_better === false` (estrés), se agrega "Here, 4 means more stress".
- `text`: textarea con `max_length` 500 y contador, con la etiqueta "Private. Never shown to the crew."
- Estados: nuevo, enviado ("Submitted 08:12 · editing") y guardado (ver `States.dc.html`). Se puede editar el check-in de hoy.

### 5 · Share with ground psychologist (`Ground.dc.html`)
- Banner fijo: "Nothing is sent automatically" y que el paquete queda en la cola local.
- Formulario:
  - `requested_by` con un SegmentedControl Myself / Captain / Ground psychologist, y `requested_by_name`.
  - `period_from` y `period_to`.
  - `include` con checkboxes; **`comments` apagado por defecto**.
  - `note` opcional.
- Consentimiento: el texto de la declaración, el checkbox "I, {name}, confirm this myself." y `statement_version`. El botón "Add to local queue" sólo se activa con el checkbox marcado. Aunque lo pida el capitán o la psicóloga, confirma el astronauta.
- Columna derecha: vista previa desde `GET …/content` y la lista de paquetes con estado `queued` / `withdrawn` / `sent`. Sólo los `queued` tienen el botón "Withdraw consent".

### Estados especiales (`States.dc.html`)
- `baseline_pending`: "Baseline pending: insufficient data to compare with your usual.", con barra de progreso de días si el backend expone cuántos faltan.
- `stale`: chip "No recent data" o "Old data", el último día, y la pista atenuada con marcador dashed.
- `no_data`, o una fuente faltante (por ejemplo sin Watch): se muestra el hueco y `---`, nunca un valor inventado.
- Error del servicio: `ServiceBanner` "Wellbeing service unavailable", se mantienen los últimos datos marcados como stale, y botón Retry.
- Vacío total: "No wellbeing data yet" con botón "Start today's check-in".

## Componentes

**Reutilizar:** `Header`, `TabBar`, `Panel`, `StatusPill`/`StateIcon` (como base), `SegmentedControl`, `RangeTrack`, `ServiceBanner`, `QualityMark`, y las clases `banner*`, `infobox`, `empty`, `btn`, `btn--ghost`, `caption`, `prov`, `stats`/`stat`, `field`, `sr-only`.

**Nuevos (props sugeridas):**

```ts
WellbeingPill   { level: SupportLevel | IndicatorStatus; kind?: "support" | "indicator"; size?: "sm" | "md" | "lg" }
OriginMark      { origin: Origin | null }                       // null → nada
TrendMark       { trend: Trend }                                // flecha + texto; unknown → "—"
ConfidenceMeter { confidence: Confidence }                      // 3 barras + texto
ZTrack          { z: number | null; threshold: number; min?: number /* -2 */; max?: number /* 4 */ }
IndicatorRow    { indicator: IndicatorState; threshold: number; expanded: boolean; onToggle(): void }
WellbeingTimeline { timeline: WellbeingTimeline }
ScaleInput      { item: CheckinFormItem; value: number | null; onChange(v: number): void }
HoursStepper    { item: CheckinFormItem; value: number | null; onChange(v: number): void }
PersonalLock    { astronautId: string; onUnlock(): void }
```

## Huecos del contrato (decidir antes o durante)

1. **PIN / lock por astronauta**: no existe en el contrato. Para la demo basta un PIN local por astronauta en config.
2. `z_threshold` sólo viene en `WellbeingTimeline`. Personal también lo necesita: pedir ambos endpoints o agregarlo a `WellbeingAssessment`.
3. El contrato no dice cuántos días necesita la línea base (para la barra de "Baseline pending"). Agregar `min_baseline_days` o quitar la barra.
4. La demo tiene 21 días de historial y la timeline pide 30, así que los primeros 9 salen vacíos. Para la demo conviene `days=21`.
5. Las fuentes por indicador y los valores de componentes del diseño son de ejemplo; se renderizan desde `sources` y `components`.

## Prioridad (demo con jueces)

1. Crew view, con el LIVE de ast-01 y la tarjeta del video log.
2. Personal view: summary, onset, indicadores y timeline.
3. Pantalla de consentimiento.
4. Check-in.
5. Estados especiales y lock.

## Criterios de aceptación

- Ningún estado se distingue sólo por color: siempre lleva ícono + texto + borde.
- Ningún elemento de Wellbeing pulsa.
- Texto de 14 px o más; objetivos táctiles de 44 px o más.
- Crew view no recibe ni muestra datos fuera de `CrewMemberSummary`.
- El comentario del check-in nunca aparece fuera de Personal ni en un paquete, salvo que se incluya `comments` a mano.
- `PROV.` y el origen (LIVE / SIMULATED / MIXED) siempre visibles donde haya datos.
- Valores faltantes como `---`.
- Funciona a 1024×700 sin scroll horizontal, salvo la timeline, que puede tener scroll propio.
