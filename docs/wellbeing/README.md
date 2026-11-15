# Módulo de bienestar (salud mental)

Este documento es la entrada al módulo de bienestar: qué problema resuelve, qué hace hoy y dónde está cada detalle. Está pensado para el equipo y para los jueces. Describe `main` al 2026-11-15. Si este documento y el código no coinciden, manda el código.

Etiquetas de estado usadas en `docs/wellbeing/`:

- **Implementado**: está en `main` y se puede ejecutar.
- **Planeado**: es parte del diseño del equipo, sin código en `main`.
- **Pendiente**: en curso en un PR abierto, o sin decidir.

**El módulo no diagnostica.** Señala cambios sostenidos para que las personas se apoyen entre sí. Habla de "necesita apoyo", nunca de etiquetas clínicas. Todos los umbrales son parámetros de diseño **PROVISIONALES**, sin validación clínica.

## El problema

En una misión larga, el estado mental de cada astronauta cambia, y nadie debería quedarse solo. El equipo quiere detectar **cambios en el estado de cada persona respecto a su propio normal**, no "leer emociones". Para eso combina un checklist diario, análisis de cámara y datos fisiológicos, y ayuda a la tripulación a funcionar como red de apoyo.

Base de diseño del equipo: una psicóloga consultada nos dijo que es viable, pero que las emociones no se pueden analizar "de la nada", porque no hay un estándar universal. Hace falta conocer el comportamiento normal de cada persona (su línea base) y detectar alteraciones respecto a él. Lo más esencial es un checklist diario corto, llenado por el propio astronauta, para saber **desde cuándo** empezó la alteración y profundizar a partir de ahí. También nos dijo que es muy importante que la tripulación vea el análisis para formar una red de apoyo. Detalle: [decisions.md](decisions.md#1-línea-base-personal-en-vez-de-un-estándar).

## La idea central

**Cada persona se compara consigo misma.** Para cada dato (horas de sueño, ánimo del checklist, PERCLOS de la cámara, HRV del reloj…) el sistema aprende la mediana y la variación habitual de esa persona en sus primeros días. Después mide cuánto se aleja cada día, en la dirección "peor" (z adverso). Sólo avisa si el cambio **se sostiene varios días**: una lectura aislada nunca genera alerta. Si varias fuentes distintas coinciden, sube el nivel.

Cómo se calcula, paso a paso: [fusion.md](fusion.md).

## Las 4 fuentes

| Fuente (`source`) | Qué aporta | Estado hoy en `main` |
|---|---|---|
| `checkin` (autorreporte) | Checklist diario de 7 preguntas (sueño, calidad de sueño, energía, ánimo, interés, tensión, conexión con la tripulación) más un comentario privado opcional. Unos 45 s. Preguntas en [`checkin_form.py`](../../services/onboard-api/src/onboard_api/wellbeing/checkin_form.py). | **Implementado**: API y pantalla de check-in en la consola. |
| `vision` (cámara) | Bitácora diaria (`bitacora`): fatiga (PERCLOS, apertura de ojos, bostezos, cabeceos) y tensión (ceño). Modo ambiente (`ambiente`): movimiento (`motion`). Sólo métricas derivadas, nunca imágenes. | **Implementado** en el proceso `wellbeing-vision`: bitácora y modo ambiente con dos cámaras (PR #33). En la demo, la historia de días anteriores es simulada. |
| `physiology` | HRV (SDNN), frecuencia cardiaca en reposo y horas de sueño desde un export de Apple Health. Además, el pulso (`heart_rate`) que ya registra la parte física, leído en sólo lectura. | **Implementado**: importador del export (`export.zip` / `export.xml`) y un export sintético de ejemplo. No hay app de HealthKit. |
| `social` (co-presencia) | Minutos acompañado al día, a partir de ventanas de co-presencia por módulo. | **Implementado**: el modo ambiente (`ambiente`) manda ventanas de co-presencia por módulo (PR #33). En la demo, la historia de días anteriores es simulada. |

### Visión

El proceso [`wellbeing-vision`](../../services/wellbeing-vision/README.md) corre junto a `onboard-api` y sólo manda números derivados: nunca guarda ni envía cuadros de video. Tiene tres partes:

- **Bitácora diaria (`bitacora`):** el astronauta habla ~60 s a la cámara, a unos 50 cm. Primero se calibra un neutral del día y después se miden fatiga y tensión **respecto a ese neutral**. Mirar hacia abajo (leer) no cuenta como fatiga ni tensión. Manda un resumen a `POST /wellbeing/vision-sessions`.
- **Identidad (`enroll`, `identify`):** reconocimiento facial con plantillas locales. La bitácora confirma que la cara es la del astronauta indicado (`identity.method: "face"`). Si no hay una coincidencia clara, sale `manual`; si la cara parece de otra persona, no se manda nada.
- **Modo ambiente (`ambiente`):** dos cámaras, una por módulo. Cada 60 s manda la co-presencia del módulo y una sesión de movimiento por persona.

Detalle en [architecture.md](architecture.md#visión). **Pendiente** de validar con cámaras reales (lo dice el PR #33): FPS y reconocimiento a 1280x720, `facing_ratio` con parejas reales y la nueva regla de habla en bitácoras nuevas.

## Qué entrega

| Salida | Qué significa |
|---|---|
| Nivel de apoyo (`level`, semáforo) | `ok`, `attention` (una fuente con cambio sostenido), `needs_support` (dos o más fuentes), o un estado sin juicio: `baseline_pending` (calibrando), `stale` (sin datos recientes), `no_data`. |
| Desde cuándo (`onset_date`) | Primer día del cambio sostenido. Responde a "¿cuándo empezó?", lo que la psicóloga pidió como lo más útil. También `sustained_days`. |
| Discrepancia (`discrepancy`) | El checklist dice que todo está bien, pero otras fuentes muestran un cambio sostenido. Es una invitación a revisarse, no una acusación. |
| Tendencia (`trend`) | `improving`, `stable`, `worsening` o `unknown`. |
| Confianza (`confidence`) | `low`, `medium` o `high`, según cuántas fuentes distintas coinciden (o, sin cambio, cuántas tienen datos). |
| Origen (`latest_origin`, `origin`) | `live`, `simulated` o `mixed`, calculado por valor. La consola marca LIVE y SIMULATED. |

También: estado por indicador (`sleep`, `fatigue`, `stress`, `activation`, `social`, `mood`), línea de tiempo diaria y notas en lenguaje de apoyo (`support_notes`, en inglés como la consola). Formato exacto: [wellbeing-contract.md](../wellbeing-contract.md).

## Quién ve qué

| Quién | Qué ve | Cómo se aplica hoy |
|---|---|---|
| Tripulación | Sólo el semáforo de cada persona, su tendencia y el origen del dato (`GET /wellbeing/crew`), más sugerencias de gestos de apoyo ("Check in with…"). | La consola usa ese endpoint, que no trae detalle. Excepción aprobada para la demo: el panel "Today's video log" muestra el z de fatiga y tensión de la bitácora en vivo de hoy de una persona. |
| Cada astronauta | Su detalle completo: indicadores, componentes, línea de tiempo, checklists y comentario privado. | Vista Personal de la consola, detrás de un PIN por astronauta. Los PIN son locales de demo ([`wellbeingPins.ts`](../../apps/spaceship-app/src/lib/wellbeingPins.ts)). **La API no tiene autenticación.** |
| Psicólogo en Tierra | Sólo lo que el astronauta acepta enviar, en un paquete con periodo y contenido elegidos. | Paquete con consentimiento explícito (`422` sin él). Queda en cola a bordo (`queued`) **por diseño**: la telemetría de la nave nunca lleva datos de bienestar. Ver [decisions.md](decisions.md#3-los-paquetes-a-tierra-se-quedan-en-cola-a-bordo). |

Por qué niveles distintos: si todos vieran todo, la gente contestaría el checklist con menos honestidad (base de diseño del equipo).

**Consentimiento.** El envío a Tierra lo puede iniciar el propio astronauta (`self`), el capitán (`captain`) o un psicólogo en Tierra (`ground_psychologist`); en los tres casos sólo el astronauta confirma, y puede retirar el consentimiento mientras el paquete está en cola. El consentimiento a ser monitoreado es un principio del diseño y un texto en la consola ("All crew members agreed to wellbeing monitoring before the mission"); **no se registra en la API**.

**Privacidad.** Todo se procesa a bordo. No se guarda video: `wellbeing.db` sólo tiene métricas derivadas. Las zonas sin cámara (dormitorio, higiene) son parte del diseño; el código no tiene ninguna configuración de zonas.

## Índice

En esta carpeta:

| Documento | Para qué |
|---|---|
| [architecture.md](architecture.md) | Componentes, flujo de datos, bases de datos, zona horaria de misión, integración con el resto del sistema. |
| [fusion.md](fusion.md) | Cómo se calcula todo: agregación diaria, componentes, línea base, z, rachas, niveles, confianza, discrepancia, tendencia. |
| [decisions.md](decisions.md) | Decisiones de diseño con su contexto y consecuencias. |
| [calibration.md](calibration.md) | De dónde sale cada rango, qué está medido y qué es supuesto, y cómo recalibrar. |
| [limitations-and-next-steps.md](limitations-and-next-steps.md) | Limitaciones honestas y siguientes pasos. |
| [judges-faq.md](judges-faq.md) | Preguntas probables de los jueces, con respuestas basadas en lo que hace el sistema hoy. |

Documentos existentes (no se repiten aquí):

| Documento | Para qué |
|---|---|
| [wellbeing-contract.md](../wellbeing-contract.md) | Contrato de la API: 14 endpoints, JSON, tipos TypeScript, orígenes y estados. |
| [wellbeing-demo-runbook.md](../wellbeing-demo-runbook.md) | Comandos y guion de la demo. |
| [wellbeing-vision/README.md](../../services/wellbeing-vision/README.md) | CLI de visión y cómo capturar la bitácora. |
| [data-dictionary.md](../../db/data-dictionary.md#data-dictionary-wellbeing-database) | Tablas de `wellbeing.db`. |
| [CONFIGURATION.md](../CONFIGURATION.md#wellbeing-module-inside-onboard-api-wellbeing_) | Variables `WELLBEING_*` y `WELLBEING_VISION_*`. |
| [ARCHITECTURE.md](../ARCHITECTURE.md) | Vista de todo el sistema. |
| [design/wellbeing/HANDOFF.md](../design/wellbeing/HANDOFF.md) | Diseño de la pestaña de bienestar de la consola. |
