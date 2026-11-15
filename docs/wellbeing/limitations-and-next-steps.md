# Limitaciones y siguientes pasos

Este documento lista, con honestidad, lo que el módulo de bienestar no hace o no ha probado, y los siguientes pasos que el equipo ya identificó. Describe `main` al 2026-11-15. Si este documento y el código no coinciden, manda el código.

## Limitaciones

### Validez

| Limitación | Detalle |
|---|---|
| **Sin validación clínica** | Todos los umbrales (z ≥ 1.5, 3 días sostenidos, pisos de escala, ventanas) son parámetros de diseño del equipo. Toda respuesta lleva `provisional: true`. El checklist lo escribió el equipo, inspirado en escalas breves, y no está validado para uso diario. |
| **Calibrado con una sola persona** | Los rangos de visión salen de bitácoras de un integrante del equipo, a ~50 cm y con una cámara. Pueden no valer para otras caras, cámaras, luz o distancias ([calibration.md](calibration.md)). |
| **Historial simulado** | En la demo, los 21 días de historia son simulados; sólo la bitácora de hoy es real. La consola y la API lo marcan (`simulated`, `mixed`). La historia del simulador falló en 1 de 100 semillas de referencia (inicio un día antes). |
| **Sin datos de microgravedad** | Todo se midió en tierra. No hay datos de cómo cambian la cara, el sueño o el movimiento en microgravedad. |
| **La expresión facial es una señal débil** | Por eso la visión es una fuente entre cuatro, y sólo el ceño puntúa como tensión. Una sola fuente nunca pasa de `attention`. |
| **Movimiento y co-presencia supuestos** | `MOTION_REST`, `MOTION_ALTERED` y la co-presencia simulada no tienen ninguna medición real, porque todavía no hay mediciones del modo ambiente. Los pisos de escala de `motion` tampoco están medidos. |
| **La línea base es fija** | Se forma con los primeros días con dato y no se renueva. Si alguien empieza ya alterado, ese es su "normal" ([judges-faq.md](judges-faq.md#y-si-alguien-llega-ya-mal-a-la-misión)). `adaptation_days` permite saltarse días iniciales, pero vale 0. |
| **No todo lo medido puntúa** | `lip_press_*` y `blink_rate_per_min` se guardan pero no entran en la fusión ([decisions.md](decisions.md#4-los-labios-apretados-quedan-fuera-de-la-fusión)). |

### Privacidad y acceso

| Limitación | Detalle |
|---|---|
| **La API no tiene autenticación** | La separación Crew / Personal la hace la consola. Los PIN son locales de demo ([`wellbeingPins.ts`](../../apps/spaceship-app/src/lib/wellbeingPins.ts)); cualquiera con acceso a la API puede leer el detalle. |
| **No se verifica quién pide un paquete** | `captain` y `ground_psychologist` son valores que se escriben, no identidades comprobadas. El consentimiento sí es obligatorio (`422` sin él). |
| **No hay concepto de fin de misión** | Nada limita cuándo puede iniciar un envío el psicólogo. |
| **El consentimiento a ser monitoreado no se registra** | Es un principio del diseño y un texto en la consola. La API sólo registra el consentimiento de los paquetes a Tierra. |
| **Las plantillas faciales son biométricas** | Viven sólo en `data/faces/` del equipo de visión, fuera de git, y nunca se envían. Borrar el archivo quita a la persona; no hay un comando para eso. |
| **Excepción en la vista Crew** | El panel "Today's video log" muestra el z de fatiga y tensión de la bitácora en vivo de hoy de una persona. Es una excepción aprobada para la demo a "Crew sólo usa `CrewMemberSummary`" (PR #38). |
| **Los paquetes nunca salen** | Se quedan en `queued` por diseño. El estado `sent` existe, pero nada lo asigna ([decisions.md](decisions.md#3-los-paquetes-a-tierra-se-quedan-en-cola-a-bordo)). |

### Funciones que no existen todavía

| Limitación | Estado |
|---|---|
| Validación de la visión con cámaras reales | **Pendiente** (PR #33): FPS y reconocimiento a 1280x720, `facing_ratio` con parejas reales y la nueva regla de habla en bitácoras nuevas. |
| Identidad por proximidad de un wearable | No implementada. Sólo existe el valor `wearable` en el contrato. |
| App de HealthKit | No construida. Sólo hay importador del export de Apple Health y un export sintético de ejemplo. La app de reloj del repo (`apps/watch-app`) no manda señales de bienestar. |
| Zona de misión en Docker | En Docker bienestar corre en `UTC`. **Pendiente** del PR #82. |
| Zona horaria por astronauta | No existe: una sola zona para todo el módulo. |
| Huecos del contrato con la consola (PR #38) | `WellbeingAssessment` no trae `z_threshold` (la consola lo toma de la línea de tiempo); el progreso de calibración es aproximado; no hay hora de la bitácora; los paquetes no tienen `withdrawn_at` ni `sent_at`. |

## Siguientes pasos

| Paso | Por qué | Fuente |
|---|---|---|
| Validar en misiones análogas | Hoy no hay validación clínica ni datos de personas en aislamiento. | Plan del equipo |
| Más sesiones de calibración, con más personas | Sustituir rangos de una sola persona; medir bostezos y cabeceos reales. | [calibration.md](calibration.md) |
| Más bitácoras de labios apretados y una combinación que no diluya al ceño | Condición para volver a puntuar los labios. | Comentario en `COMPONENTS`, [`engine.py`](../../services/onboard-api/src/onboard_api/wellbeing/engine.py) |
| Canal dedicado y consentido hacia Tierra | Hoy los paquetes se quedan en cola; la telemetría nunca lleva bienestar. | Decisión del equipo del 2026-11-15, PR #41 |
| Medir el modo ambiente real | Reemplazar `MOTION_REST` / `MOTION_ALTERED` y la co-presencia simulada por mediciones. | Comentario en [`simulator.py`](../../services/onboard-api/src/onboard_api/wellbeing/simulator.py) |
| Integrar el PR #82 | Días de misión en `America/Tijuana` también en Docker. | PR #82 |
| Autenticación real de la tripulación | Que la separación de vistas no dependa de la consola. | Comentario en [`wellbeingPins.ts`](../../apps/spaceship-app/src/lib/wellbeingPins.ts) |
| Cerrar los huecos del contrato con la consola | `z_threshold` en la evaluación, hora de la bitácora, fechas de retiro y envío. | PR #38 |
