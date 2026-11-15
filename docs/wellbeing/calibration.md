# Calibración de los rangos de visión

Este documento explica de dónde sale cada rango de visión que usan el simulador y la fusión, qué está medido y qué es supuesto, y cómo recalibrar. Describe `main` al 2026-11-15. Si este documento y el código no coinciden, manda el código. Los valores viven en [`simulator.py`](../../services/onboard-api/src/onboard_api/wellbeing/simulator.py) (`VISION_REST`, `VISION_ALTERED`, `MOTION_REST`, `MOTION_ALTERED`) y en `COMPONENTS` de [`engine.py`](../../services/onboard-api/src/onboard_api/wellbeing/engine.py) (pisos de escala).

**Todo es PROVISIONAL.** Las bitácoras son de **una sola persona** del equipo. Son rangos de simulación y pisos de diseño, no rangos clínicos.

> **Versión de visión.** R1–R3 y L2 se grabaron antes del último cambio del detector de habla (commit `19b5d86`, PR #33), que también cuenta los vaivenes de `mouthPress` como habla. Al repetir sus trazas con el código nuevo, el habla en R1–R3 pasa de 7/1/6 % a 59/67/83 % del tiempo y L2 sigue en 0 % (su pico de 0.466 se mantiene). Ese detector sólo decide qué cuadros cuentan para los labios, que no puntúan. **Pendiente:** grabar bitácoras nuevas con la versión de `main` para confirmar los rangos.

## Las sesiones

| Sesión | Qué es | Versión de visión |
|---|---|---|
| R1, R2, R3 | Bitácoras de reposo, 60 s a ~50 cm, hablando a la cámara. | Corregida (filtro de habla en labios, neutral robusto). 2026-11-15. |
| L2 | Bitácora en silencio con los labios apretados. | Corregida. 2026-11-15. |
| S1, S2, S3 | Sesiones anteriores de reposo. | Anterior. |
| Referencias actuadas | Un ceño fruncido actuado (pico 0.663). | Anterior. |

Valores medidos (base de diseño del equipo, PR #57):

| Métrica | R1–R3 (reposo, hablando) | L2 (labios apretados, en silencio) |
|---|---|---|
| PERCLOS | 0.062–0.107 | 0.005 |
| Parpadeos por minuto | 14.5–24.2 | 2.0 (no es reposo) |
| Apertura de ojos frente al neutral | 0.944–1.131 | 0.888 |
| Ceño: media / pico 1 s | 0.005–0.038 / 0.011–0.109 | 0.005 / 0.061 |
| Labios: media / pico 1 s | 0.001–0.002 / 0.0 (una sesión `null`) | 0.164 / 0.466 |

Con la versión anterior (S1–S3), sólo hablar daba picos de labios de 0.41–0.49. Por eso los labios salieron de la fusión antes del filtro de habla ([decisions.md](decisions.md#4-los-labios-apretados-quedan-fuera-de-la-fusión)).

**Nota sobre R3.** Los labios de R3 en `rest3.jsonl` (0.037 / 0.238) salieron del detector de habla anterior. Al reprocesar su trace con el código nuevo de visión dan `null`. No cambia ningún rango; la misma nota está en `simulator.py`.

## Días de reposo (`VISION_REST`)

| Métrica | Rango simulado | Origen | ¿Medido? |
|---|---|---|---|
| `blink_rate_per_min` | 14.0–25.0 | R1–R3: 14.5–24.2 | Medido (no puntúa) |
| `eye_openness_vs_neutral` | 0.94–1.13 | R1–R3: 0.944–1.131 | Medido |
| `perclos` | 0.06–0.11 | R1–R3: 0.062–0.107. Se puede cambiar con `--perclos`. | Medido |
| `yawn_count` | 0–2 | 0 en R1–R3, hasta 2 en una sesión anterior | Supuesto |
| `nod_count` | 0–2 | 0 en R1–R3, hasta 2 en una sesión anterior | Supuesto |
| `brow_lower_delta` | 0.015–0.03 | Bitácoras de reposo anteriores; R1–R3 (0.005–0.038) coinciden | Medido |
| `brow_lower_peak_1s` | 0.045–0.13 | Bitácoras de reposo anteriores; R1–R3 (0.011–0.109) coinciden | Medido |
| `lip_press_delta` | 0.0–0.003 | R1–R3: 0.001–0.002 (sin cuadros con habla) | Medido (no puntúa) |
| `lip_press_peak_1s` | 0.0–0.0 | R1–R3: 0.0 (una sesión `null`) | Medido (no puntúa) |

## Días alterados (`VISION_ALTERED`)

Todos son **supuestos**, sólo para la historia de la demo (más fatiga y tensión). Anclas:

| Métrica | Rango simulado | Ancla |
|---|---|---|
| `perclos` | Del reposo: de `alto + 0.10` a `alto + 0.20` (0.21–0.31 con el rango por defecto) | Derivado (`_vision_ranges`) |
| `eye_openness_vs_neutral` | 0.70–0.80 | Supuesto |
| `yawn_count`, `nod_count` | 2–4 | Supuesto |
| `brow_lower_delta` | 0.06–0.10 | Supuesto |
| `brow_lower_peak_1s` | 0.35–0.65 | Anclado en el ceño actuado (0.663) |
| `lip_press_delta` / `lip_press_peak_1s` | 0.10–0.20 / 0.35–0.50 | Anclados en L2 (0.164 / 0.466) |
| `blink_rate_per_min` | 14.0–25.0 | Igual que reposo |

## Movimiento en modo ambiente (`MOTION_REST`, `MOTION_ALTERED`)

**Supuestos, sin ninguna medición real.** El modo ambiente ya está en `main` (PR #33), pero todavía no hay mediciones guardadas para calibrar. Las ventanas del simulador son de 10 min; las reales, de 60 s.

| Métrica | Reposo | Alterado |
|---|---|---|
| `speed` (anchos de hombro por segundo) | 0.25–0.45 | 0.08–0.18 |
| `stationary_ratio` | 0.45–0.65 | 0.80–0.92 |
| `fidget_index` | 0.05–0.15 | igual |
| `torso_angle_dev` (grados frente a la postura neutral propia) | 5.0–15.0 | igual |

La co-presencia simulada (6 franjas compartidas de 30 min al día; quien se aísla se une a una sola) también es supuesta.

## Pisos de escala

El piso evita que una línea base muy estable vuelva enormes los cambios mínimos. Los de visión:

| Componente | Piso | De dónde sale |
|---|---|---|
| `vision.perclos` | 0.03 | Variación de día a día en reposo (una sesión real, ~50 cm). |
| `vision.eye_openness_vs_neutral` | 0.05 | Igual. |
| `vision.yawns_per_min`, `vision.nods_per_min` | 0.5 | Un bostezo de más en una bitácora de 90 s ya suma +0.67/min. |
| `vision.brow_lower_delta` | 0.03 | Variación en reposo. |
| `vision.brow_lower_peak_1s` | 0.08 | Variación de picos reales en reposo (0.046–0.129, 3 bitácoras). Antes 0.05 (PR #32). |
| `vision.speed`, `vision.stationary_ratio`, `vision.fidget_index` | 0.05 | No documentado en el código. **Pendiente** de medir con el modo ambiente. |
| `vision.torso_angle_dev` | 2.0 | No documentado en el código. **Pendiente** de medir con el modo ambiente. |

Lo que comprueban los tests ([`test_wellbeing_engine.py`](../../services/onboard-api/tests/test_wellbeing_engine.py), `test_brow_peak_floor_matches_real_rest_spread`): con una línea base de picos de reposo reales, el pico de S2 (0.129) da z < 0.5; en el peor caso (línea base en el pico más bajo) da z < 1.1; el ceño actuado (0.663) llega al tope, z = 5.

## Resultados verificados

- La historia del simulador (ast-01 `ok`, ast-02 `needs_support` desde el día 14, ast-03 con discrepancia, ast-04 `ok` con un solo día malo) se cumple con la semilla 7 de la demo y con las 20 semillas del test (`test_simulated_crew_tells_the_demo_story`), también en `America/Tijuana`.
- En una corrida de referencia con 100 semillas falló 1 (el inicio de ast-02 se adelantó un día por ruido; PR #41).
- Las bitácoras reales de reposo R1–R3, mandadas cada una como la bitácora en vivo de hoy de ast-01, no generaron alerta: ast-01 siguió en `ok`, sin fuentes sostenidas. El z adverso más alto fue PERCLOS en R1, 1.07 (PR #57).

## Cómo recalibrar

1. **Grabar bitácoras** con la misma captura: de frente, ~50 cm, buena luz. Varias de reposo y, si se quiere revisar los labios, varias de labios apretados en silencio. Para no mandarlas a la API y guardar los números por cuadro:

   ```powershell
   cd services\wellbeing-vision
   uv run wellbeing-vision bitacora --astronaut ast-01 --seconds 60 --dry-run --out rest4.jsonl --trace rest4.csv
   ```

   `--dry-run` imprime el JSON en vez de enviarlo; `--out` lo agrega a un archivo; `--trace` guarda números derivados por cuadro (sin imágenes). Detalle: [wellbeing-vision/README.md](../../services/wellbeing-vision/README.md).
2. **Actualizar las constantes** en `simulator.py` (`VISION_REST`, `VISION_ALTERED`, `MOTION_*`), con el comentario de qué está medido y qué es supuesto. Si cambia la variación en reposo, revisar el piso en `COMPONENTS` de `engine.py`.
3. **Sólo PERCLOS, sin tocar código:** `--perclos LOW HIGH` en `demo_reset.py` o en `simulate_wellbeing.py`.
4. **Volver a correr los tests** de la historia y de los pisos:

   ```powershell
   cd services\onboard-api
   uv run pytest -q tests/test_wellbeing_simulator.py tests/test_wellbeing_engine.py tests/test_wellbeing_mission_tz.py
   ```

5. **Volver a cargar la demo** con la API arriba: `uv run python scripts/demo_reset.py --tz America/Tijuana`, y comprobar la tabla de los 4 casos ([runbook](../wellbeing-demo-runbook.md)). Después, mandar una bitácora real de reposo como la de hoy de ast-01 y confirmar que no alerta.
