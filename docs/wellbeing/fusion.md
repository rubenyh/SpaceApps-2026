# Cómo se calcula la evaluación (fusión)

Este documento explica, paso a paso, cómo el módulo convierte checklists, señales, visión y co-presencia en un nivel de apoyo por persona. Todo sale de [`engine.py`](../../services/onboard-api/src/onboard_api/wellbeing/engine.py) y [`settings.py`](../../services/onboard-api/src/onboard_api/wellbeing/settings.py). Describe `main` al 2026-11-15. Si este documento y el código no coinciden, manda el código. El resumen corto y el formato JSON están en [wellbeing-contract.md](../wellbeing-contract.md#cómo-se-calcula-resumen).

**Todos los valores de este documento son PROVISIONALES:** parámetros de diseño del equipo, no puntos de corte clínicos. `GET /wellbeing/parameters` devuelve los valores en uso y `provisional: true`.

## En una frase

Cada dato se resume en un valor por día; cada persona se compara con sus propios primeros días; un día "se aleja" si el z adverso llega a 1.5; un cambio cuenta sólo si se sostiene 3 días con datos; el nivel depende de cuántas fuentes distintas tienen un cambio sostenido.

## Parámetros actuales

| Parámetro (`WELLBEING_*`) | Valor | Qué controla |
|---|---|---|
| `z_threshold` | 1.5 | z adverso a partir del cual un día está desviado. |
| `sustain_days` | 3 | Días desviados seguidos para que el cambio cuente como sostenido. |
| `baseline_days` | 7 | Días con dato que forman la línea base de cada componente. |
| `baseline_min_days` | 5 | Mínimo de días para que una línea base sea válida. |
| `adaptation_days` | 0 | Días iniciales que se saltan antes de empezar la línea base. |
| `stale_after_days` | 2 | Más días que esto sin datos = `stale`. |
| `trend_window_days` | 3 | Ventana de la tendencia. |
| `trend_min_delta` | 0.5 | Diferencia mínima de z para decir `improving` o `worsening`. |
| `z_cap` | 5.0 | El z se recorta a ±5. |
| `min_heart_rate_readings` | 10 | Lecturas `heart_rate` buenas necesarias en un día para calcular el mínimo diario. |

Cómo cambiarlos: [CONFIGURATION.md](../CONFIGURATION.md#wellbeing-module-inside-onboard-api-wellbeing_).

## 1. Agregación diaria

Todo se agrupa por **día de misión** en `WELLBEING_MISSION_TZ` ([architecture.md](architecture.md#zona-horaria-de-misión)). El resultado es un valor por componente y por día (`build_daily_inputs`).

| Entrada | Cómo se vuelve un valor diario |
|---|---|
| Checklist | Un checklist por persona y día (un segundo envío del mismo día lo reemplaza). Cada respuesta es su valor. El comentario no entra en la fusión. |
| Señales (`hrv_sdnn`, `resting_heart_rate`, `sleep_hours`) | Media de las señales del día, por tipo. |
| Bitácora de visión | Por sesión: `perclos`; `eye_openness_vs_neutral` sólo si `neutral_ok`; bostezos y cabeceos **por minuto** (conteo / duración de la sesión). Las métricas de tensión sólo si `neutral_ok`, porque se miden contra el neutral del día. Después, media de las sesiones del día. |
| Visión en modo ambiente | Las 4 métricas de `motion`, media de las sesiones del día. No necesitan neutral. |
| Co-presencia | Por cada ventana en la que aparece la persona: el máximo de `seconds_together` entre sus pares, en minutos. Se suman las ventanas del día. Usar el máximo da un mínimo seguro que no cuenta dos veces a un grupo. |
| Pulso de onboard (`heart_rate` en bpm) | Percentil 10 (rango más cercano) de las lecturas buenas del día: el "mínimo diario". Sólo si hay al menos `min_heart_rate_readings` (10). |

**Calidad.** `quality: "bad"` se ignora. `"suspect"` también se excluye, pero se cuenta y se avisa en `data_notices` ("N low-quality data point(s) left out of the analysis"). Aplica a señales, visión, co-presencia y pulso.

**Se guarda pero no puntúa:** `blink_rate_per_min`, `lip_press_delta` y `lip_press_peak_1s` no son componentes. Por qué los labios no: [decisions.md](decisions.md#4-los-labios-apretados-quedan-fuera-de-la-fusión). Las identidades `unknown-<track>` se guardan, pero la vista Crew sólo lista a los astronautas de `onboard.db`.

## 2. Componentes

Cada componente pertenece a una **fuente** y a un **indicador**. La "dirección adversa" dice qué lado es peor: `low` (bajar es peor), `high` (subir es peor) o `both` (cualquier cambio cuenta). El **piso de escala** evita que una línea base muy estable convierta cambios mínimos en z enormes.

| Componente | Fuente | Indicador | Dirección adversa | Piso de escala | Unidad |
|---|---|---|---|---|---|
| `checkin.sleep_hours` | `checkin` | `sleep` | `low` | 1.0 | h |
| `checkin.sleep_quality` | `checkin` | `sleep` | `low` | 1.0 | 0-4 |
| `signal.sleep_hours` | `physiology` | `sleep` | `low` | 0.5 | h |
| `checkin.energy` | `checkin` | `fatigue` | `low` | 1.0 | 0-4 |
| `vision.perclos` | `vision` | `fatigue` | `high` | 0.03 | ratio |
| `vision.eye_openness_vs_neutral` | `vision` | `fatigue` | `low` | 0.05 | ratio |
| `vision.yawns_per_min` | `vision` | `fatigue` | `high` | 0.5 | 1/min |
| `vision.nods_per_min` | `vision` | `fatigue` | `high` | 0.5 | 1/min |
| `checkin.stress` | `checkin` | `stress` | `high` | 1.0 | 0-4 |
| `signal.hrv_sdnn` | `physiology` | `stress` | `low` | 5.0 | ms |
| `signal.resting_heart_rate` | `physiology` | `stress` | `high` | 2.0 | bpm |
| `onboard.heart_rate_low` | `physiology` | `stress` | `high` | 2.0 | bpm |
| `vision.brow_lower_delta` | `vision` | `stress` | `high` | 0.03 | 0-1 |
| `vision.brow_lower_peak_1s` | `vision` | `stress` | `high` | 0.08 | 0-1 |
| `vision.speed` | `vision` | `activation` | `both` | 0.05 | shoulders/s |
| `vision.stationary_ratio` | `vision` | `activation` | `both` | 0.05 | ratio |
| `vision.fidget_index` | `vision` | `activation` | `high` | 0.05 | index |
| `vision.torso_angle_dev` | `vision` | `activation` | `high` | 2.0 | deg |
| `social.accompanied_minutes` | `social` | `social` | `low` | 10.0 | min |
| `checkin.crew_connection` | `checkin` | `social` | `low` | 1.0 | 0-4 |
| `checkin.mood` | `checkin` | `mood` | `low` | 1.0 | 0-4 |
| `checkin.interest` | `checkin` | `mood` | `low` | 1.0 | 0-4 |

De dónde salen los pisos de visión: [calibration.md](calibration.md#pisos-de-escala).

## 3. Línea base personal

Para cada componente (`_evaluate_component`):

1. **Primer día:** el primer día con cualquier dato de esa persona. La línea base empieza `adaptation_days` (0) días después.
2. **Días de línea base:** los primeros `baseline_days` (7) días **con dato de ese componente** desde ahí. Los días sin dato no cuentan ni rompen nada.
3. **Lista:** si hay al menos `baseline_min_days` (5) de esos días. Si no, el componente queda pendiente.
4. **Centro:** la mediana de esos días.
5. **Escala:** `max(1.4826 × MAD, piso de escala)`. MAD es la mediana de las desviaciones absolutas respecto a la mediana; 1.4826 × MAD estima la desviación estándar en datos normales y resiste valores atípicos.

La línea base es **fija**: son los primeros días, no una ventana móvil. Sólo los días **posteriores** al último día de la línea base reciben z; ningún día de la línea base puede salir "desviado".

## 4. z adverso

```
delta = (valor − mediana) / escala
z = −delta   si la dirección adversa es low
z = +delta   si es high
z = |delta|  si es both
z se recorta a [−5, +5]
```

Positivo = más lejos del normal de la persona, en la dirección peor. Negativo = mejor que su normal (no cuenta como desviación).

## 5. z diario por indicador y por fuente

- **Indicador:** media de los z de sus componentes con dato ese día.
- **Fuente:** para cada indicador, media de los z de los componentes de esa fuente; el z diario de la fuente es el **más alto** de esos promedios (su indicador más fuerte ese día).

Ejemplo: si un día la visión da fatiga z = 2.1 y estrés z = 0.4, la fuente `vision` vale 2.1 ese día.

## 6. Rachas sostenidas

Un día está **desviado** si su z ≥ `z_threshold` (1.5). La racha se cuenta hacia atrás desde el último día evaluado (`_sustained_run`):

- Un **día sin datos** no aparece, así que **no rompe** la racha.
- Un **día con datos** bajo el umbral **sí la rompe**.
- La racha es **sostenida** si tiene al menos `sustain_days` (3) días desviados.

Las rachas se calculan por indicador (para su estado) y por fuente (para el nivel general). Una fuente sólo cuenta si tiene alguna línea base lista y su último dato no es viejo.

## 7. Niveles

Nivel general (`level`), en este orden:

| Nivel | Cuándo |
|---|---|
| `no_data` | No hay ningún dato hasta el día evaluado. |
| `baseline_pending` | Ningún componente tiene la línea base lista. |
| `stale` | El último día con datos tiene más de `stale_after_days` (2) días. |
| `needs_support` | 2 o más fuentes distintas con cambio sostenido. |
| `attention` | 1 fuente con cambio sostenido. |
| `ok` | Ninguna fuente con cambio sostenido. |

Estado por indicador (`status`): `no_data` (ningún componente con datos), `stale` (su último dato es viejo), `baseline_pending` (ninguno listo), `attention` (racha sostenida del indicador) u `ok`. `needs_support` sólo existe a nivel persona, porque exige que coincidan fuentes distintas.

## 8. Confianza

Cuenta fuentes **distintas**:

- Con cambio sostenido: cuántas fuentes lo muestran.
- Sin cambio (`ok`, y también `baseline_pending`, `stale`, `no_data`): cuántas fuentes tienen línea base y datos recientes.

1 o ninguna = `low`, 2 = `medium`, 3 o más = `high`.

## 9. Discrepancia

`discrepancy` es verdadero si el checklist tiene línea base y datos recientes, **no** muestra cambio sostenido, y al menos una fuente pasiva (`vision`, `physiology`, `social`) **sí** lo muestra. Como esa fuente pasiva ya cuenta para el nivel, una discrepancia siempre viene con `attention` o `needs_support`. La nota que la acompaña dice que, por sí sola, no significa nada: es una invitación a revisarse.

## 10. Inicio y días sostenidos

- **`onset_date`:** el día de inicio más antiguo entre las rachas sostenidas de las fuentes. Responde a "¿desde cuándo?". Es `null` si el nivel no es `attention` ni `needs_support`.
- **`sustained_days`:** días desde `onset_date` hasta el último día con datos, ambos incluidos.
- Por indicador, `deviant_since` es el inicio de su propia racha.

## 11. Tendencia

1. z general por día = media de los z de los indicadores ese día.
2. Hacen falta al menos `2 × trend_window_days` (6) días con z.
3. Se compara la media de los últimos 3 días con la de los 3 anteriores. Si sube más de 0.5: `worsening`; si baja más de 0.5: `improving`; si no, `stable`.

Con `no_data`, `stale` o menos de 6 días con z, la tendencia es `unknown`.

## 12. Línea de tiempo "a cada día"

`GET …/wellbeing/timeline` evalúa **cada día sólo con los datos disponibles hasta ese día** (`service.get_timeline`). Así, la línea de tiempo muestra cuándo el sistema habría avisado de verdad, nunca de forma retroactiva: con 5 días alterados, los dos primeros salen `ok` y la alerta aparece al tercero (test `test_assessment_timeline_and_crew_after_a_derailment`).

## 13. Origen: en vivo, simulado o mixto

Cada dato es simulado si su `source` es `simulated`, `demo` o empieza por `simulated:`; si no, es en vivo. El origen se calcula **por valor**: un componente, un indicador o un día es `live`, `simulated` o `mixed` (los dos el mismo día). `live_days`, `simulated_days` y `mixed_days` cuentan días sin traslape, y `data_notices` lo resume cuando hay datos simulados. Así, una bitácora en vivo de hoy sobre un historial simulado sale `live` en sus componentes y el día sale `mixed`, nunca entero como simulado (test `test_live_log_on_a_simulated_day_is_marked_live_and_mixed`). Por qué: [decisions.md](decisions.md#7-historial-simulado-y-datos-en-vivo-separados-por-valor).

## Textos para el usuario

`support_notes` y `data_notices` salen en inglés, como la consola, con lenguaje de apoyo. El test `test_user_texts_are_english_and_never_clinical` comprueba en los 6 niveles que no aparezcan palabras como "diagnos", "disorder", "depress", "anxiety", "illness", "sick" o "patient".
