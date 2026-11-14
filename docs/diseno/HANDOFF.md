# Rediseño de la consola biomédica: guía de implementación

Este paquete es la referencia visual para reimplementar la interfaz sobre el código
actual (Tauri + React). Los HTML de `pantallas/` son **maquetas estáticas**: hay que
reconstruirlas como componentes React con los datos reales, no copiarlas tal cual.

## Contenido

| Archivo | Qué es |
|---|---|
| `tokens.css` | Variables CSS finales. Copiar a `:root` (p. ej. `src/styles/tokens.css`). |
| `pantallas/01-estado.html` … `06-registros.html` | Las seis pestañas. |
| `pantallas/estado-*.html` | Servicio no disponible, sin tripulación, sin lecturas, cargando. |
| `pantallas/hoja-de-componentes.html` | Todas las piezas reutilizables y sus variantes. |
| `pantallas/tokens.html` | Muestras de color y escala tipográfica. |

Abre cualquier HTML en el navegador (1280×800) para ver el diseño. Los estilos van en
línea: úsalos para leer medidas, colores y espaciados, y tradúcelos a CSS con los tokens.

## Restricciones (no negociables)

- Solo React + CSS + SVG escritos a mano. Sin librerías de componentes ni de gráficas.
- Sin fuentes empaquetadas: `--font-sans` (pila del sistema).
- Ventana 1280×800, mínimo 1024×700. No es responsive para móvil.
- Todo el texto visible en español. Ningún texto por debajo de 14 px. Objetivos táctiles ≥ 44 px.
- Nada de valores, unidades o rangos inventados: si algo no está definido, la interfaz lo dice.

## Estructura de la ventana

```
<Header>      60 px  banda azul (--color-brand) + línea roja de 3 px
              marca · "Consola biomédica" · selector de tripulante | reloj UTC · indicador de conexión
<Tabs>        52 px  Estado · Signos vitales · Músculo · Orina · Asistente · Registros
              activa = subrayado 3 px --color-accent; pestaña con problema = icono del estado peor
<main>        flex: 1, padding 20 px, gap 16 px
<Footer>      40 px  leyenda de estados + nota de rangos provisionales
```

## Lógica de estado de una lectura

Cada lectura tiene valor, unidad, hora de captura, calidad (buena/dudosa/mala) y origen.
Calcula el estado en este orden:

1. Sin ninguna lectura → `SIN DATOS` (mostrar `---`).
2. Antigüedad > umbral → `DATO VIEJO` (pulso y SpO₂: 5 min; orina: 24 h; músculo: 7 días).
3. Sin rango definido → `SIN RANGO`.
4. Fuera de rango → `ALERTA`.
5. Si no → `NORMAL`.

Rangos provisionales: pulso 60–100 lpm, SpO₂ 95–100 %, pH 4.6–8.0. Músculo,
salinidad y color no tienen rango.

Excepciones:
- **Temperatura de orina** (32–38 °C) indica si la muestra es válida. Fuera de rango →
  etiqueta `Muestra dudosa` (borde gris, icono `?`), **nunca** ALERTA.
- **Radiación**: panel propio con aviso fijo («indicador indirecto, no es dosimetría»).
  Hoy siempre SIN DATOS. Si llega un dato, mostrar solo «Posible exposición, requiere
  confirmación»; nunca dosis ni unidades de dosis, y nunca con aspecto de «todo bien».

## Codificación visual de estados (debe funcionar en blanco y negro)

| Estado | Borde | Icono | Texto | Extra |
|---|---|---|---|---|
| ALERTA | `--border-alert` | triángulo con `!` | "Alerta" | etiqueta rellena `--state-alert-fill`, fondo teñido, el icono pulsa |
| NORMAL | `--border-normal` | círculo con check | "Normal" | — |
| DATO VIEJO | `--border-stale` | reloj | "Dato viejo" | valor atenuado (`--color-text-faint`), antigüedad en ámbar |
| SIN DATOS | `--border-nodata` | círculo tachado | "Sin datos" | valor `---`, "Nunca medido" |
| SIN RANGO | `--border-norange` | rombo | "Sin rango" | sin juicio de bueno/malo |

La pulsación usa `animation: var(--alert-pulse)` y se desactiva con
`prefers-reduced-motion` (ya está en `tokens.css`). Añadir también un ajuste en la app.

## Componentes sugeridos

- `StatusPill` (estado) · `StateIcon` (estado, tamaño)
- `ReadingCard` (nombre, órgano, lectura, explicación, contenido inferior)
- `ReadingValue` · `Age` («Hace 12 s», «Hace 26 h», «Nunca medido») · `QualityMark` · `ProvTag`
- `RangeTrack` (valor, escala, rango, estado): zona normal sombreada + marcador
- `LineChart` (SVG): rejilla, zona normal con «PROV.», línea, marcador final con forma de estado
- `BodyMap` (SVG): silueta + 4 órganos con el estilo de su estado (corazón → pulso,
  pulmones → SpO₂, extremidades → músculo, riñones → orina)
- `AlertBanner` · `StaleBanner` · `ServiceErrorBanner` · `EmptyState` · `Skeleton`
- `SegmentedControl` (7 D / 30 D / Todo; Salinidad / pH)
- `ChatMessage` en variantes `user`, `answer` y `clarification`; cada respuesta del
  asistente lleva el descargo «Información de apoyo, no es un diagnóstico».

## Pantalla ESTADO (la más importante)

Debe responder «¿estoy bien?» en dos segundos:
1. Arriba, un aviso con la lectura más urgente («Necesita tu atención: tu pulso está
   alto») y un enlace a su pestaña. Sin alertas, un resumen neutro.
2. Cuadrícula `370px | 1fr | 370px`: SpO₂ y músculo a la izquierda, mapa corporal al
   centro, pulso y orina a la derecha.

## Estados vacíos y de error

- **Servicio no disponible**: aviso «SERVICIO ONBOARD NO DISPONIBLE» + botón Reintentar,
  con los últimos valores conocidos debajo como DATO VIEJO. Nunca una pantalla en blanco.
- **Sin tripulación**: estado vacío centrado y pestañas deshabilitadas.
- **Sin lecturas**: todas las tarjetas en SIN DATOS.
- **Cargando**: esqueletos con la misma estructura + indicador de carga.
