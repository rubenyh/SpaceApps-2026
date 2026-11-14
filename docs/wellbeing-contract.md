# Contrato de bienestar (salud mental) · onboard-api

Estado: **v1, implementado** (rama `agent/hiram/wellbeing-backend`) · Dueño: Hiram · Consumidores: consola (Cedric), proceso de visión (`wellbeing-vision`, endpoints 6 y 7 según su borrador).

El módulo `onboard_api.wellbeing` detecta **cambios sostenidos de cada astronauta respecto a su propia línea base**. No diagnostica: sus salidas son de apoyo ("necesita apoyo"), nunca etiquetas clínicas.

- Los nombres de campos y valores van en inglés (igual que el resto de la API). Los textos para mostrar (`support_notes`, `data_notices`, preguntas del checklist) ya vienen en español.
- Todas las fechas-hora son ISO 8601 UTC con `Z`. Un **día** (`day`) es la fecha UTC `YYYY-MM-DD` (día de misión).
- Errores: `404 {"detail": "..."}` si el astronauta no existe; `422` para validación (mismo formato que FastAPI en el resto de la API).
- El módulo guarda sus datos en su propia base (`data/wellbeing.db`). Lee la base de Rubén (`astronauts`, `readings` de `heart_rate`) **sólo en modo lectura**.

## Índice de endpoints

| # | Método y ruta | Para qué | Vista | Estado |
|---|---|---|---|---|
| 1 | `GET /wellbeing/parameters` | Umbrales y componentes de la fusión (todos PROVISIONALES) | — | listo |
| 2 | `GET /wellbeing/checkin-form` | Preguntas del checklist para pintar el formulario | personal | listo |
| 3 | `PUT /astronauts/{astronaut_id}/wellbeing/checkins/{day}` | Guardar (o reemplazar) el checklist del día | personal | listo |
| 4 | `GET /astronauts/{astronaut_id}/wellbeing/checkins` | Historial de checklists | personal | listo |
| 5 | `POST /wellbeing/signals` | HRV, FC en reposo y sueño (Apple Watch o simulador) | ingesta | listo |
| 6 | `POST /wellbeing/vision-sessions` | Métricas derivadas de cámara (sin video) | ingesta | listo |
| 7 | `POST /wellbeing/co-presence` | Quién compartió módulo con quién y cuánto tiempo | ingesta | listo |
| 8 | `GET /wellbeing/crew` | Semáforo de toda la tripulación | **tripulación** | listo |
| 9 | `GET /astronauts/{astronaut_id}/wellbeing` | Evaluación completa de una persona | **personal** | listo |
| 10 | `GET /astronauts/{astronaut_id}/wellbeing/timeline` | Serie diaria con el día de inicio de la alteración | **personal** | listo |
| 11 | `POST /wellbeing/ground-packages` | Crear un paquete para el psicólogo en Tierra (requiere consentimiento) | personal | listo |
| 12 | `GET /wellbeing/ground-packages` | Listar paquetes de un astronauta | personal | listo |
| 13 | `GET /wellbeing/ground-packages/{id}/content` | Ver exactamente qué se enviaría | personal | listo |
| 14 | `POST /wellbeing/ground-packages/{id}/withdraw` | Retirar el consentimiento de un paquete aún no enviado | personal | listo |

"Vista" indica qué pantalla debe usarlo. **No hay autenticación en la API**: la separación tripulación/personal la hace la consola. La vista de tripulación debe usar **sólo** el endpoint 8.

## SIMULADO y PROVISIONAL

**SIMULADO.** Cada dato de entrada lleva `source`. Es simulado si `source` es `"simulated"`, `"demo"` o empieza por `"simulated:"`. Las respuestas ya lo calculan:

- Cada registro de entrada devuelto trae `simulated: boolean`.
- `WellbeingAssessment.simulated_days` y `live_days`: cuántos días de la historia usan datos simulados o reales.
- `CrewMemberSummary.simulated`: `true` si algún dato de los últimos 14 días es simulado.
- `TimelineDay.simulated`: `true` si algún dato de ese día es simulado.

Regla de interfaz sugerida: mostrar la etiqueta `SIMULADO` en cualquier panel cuyo dato tenga `simulated: true`.

**PROVISIONAL.** Todos los umbrales de la fusión son parámetros de diseño, **sin validación clínica**. Por eso:

- `WellbeingAssessment.provisional`, `IndicatorState.provisional` y `WellbeingParameters.provisional` siempre son `true` en v1.
- `WellbeingParameters.basis` explica el origen de los umbrales.

Regla de interfaz sugerida: etiqueta `PROV.` junto al nivel, igual que en la parte física.

## Estados y niveles

Se reutiliza la convención física donde aplica (`no_data`, `stale`). `no_range` se sustituye por `baseline_pending`, porque aquí no hay rangos fijos: cada persona se compara contra sí misma.

`SupportLevel` (nivel general de una persona, semáforo):

| Valor | Mostrar como | Cuándo |
|---|---|---|
| `ok` | BIEN | Ninguna fuente muestra un cambio sostenido |
| `attention` | ATENCIÓN | Una fuente con cambio sostenido, o discrepancia (ver abajo) |
| `needs_support` | NECESITA APOYO | Dos o más fuentes distintas con cambio sostenido |
| `baseline_pending` | CALIBRANDO | Aún no hay días suficientes para la línea base |
| `stale` | SIN DATOS RECIENTES | El último dato es más viejo que `stale_after_days` |
| `no_data` | SIN DATOS | No hay ningún dato de bienestar |

`IndicatorStatus` (por indicador): `ok`, `attention`, `baseline_pending`, `stale`, `no_data`. El nivel `needs_support` sólo existe a nivel persona, porque requiere que coincidan varias fuentes.

**Fuentes** (`SourceKind`): `checkin` (autorreporte), `vision` (cámara), `physiology` (Watch y pulso de Rubén), `social` (co-presencia). La confianza cuenta fuentes **distintas** que coinciden.

**Indicadores** (`IndicatorKind`): `sleep`, `fatigue`, `stress`, `activation`, `social`, `mood`.

## Cómo se calcula (resumen)

1. Cada dato se agrupa por día en un **componente** (por ejemplo `checkin.mood`, `signal.hrv_sdnn`). La lista completa está en `GET /wellbeing/parameters`.
2. **Línea base por componente:** los primeros `baseline_days` días con dato (tras `adaptation_days`). Es válida con al menos `baseline_min_days`. Se usa mediana y MAD; la escala nunca baja de `scale_floor`.
3. **z adverso:** desviación respecto a la línea base, con signo tal que positivo = peor (menos sueño, más estrés…). En `activation` cuenta en ambas direcciones. Se recorta a ±`z_cap`.
4. Un día está **desviado** si el z del indicador (o de la fuente) es ≥ `z_threshold`. Es **sostenido** si hay ≥ `sustain_days` días desviados seguidos hasta el último dato. Un día sin datos no rompe la racha; un día con datos normales, sí.
5. **Nivel:** según cuántas fuentes tienen cambio sostenido (tabla de arriba).
6. **Confianza:** con cambio sostenido, 1 fuente = `low`, 2 = `medium`, 3 o más = `high`. Si el nivel es `ok`, la confianza refleja la cobertura: cuántas fuentes tienen datos recientes y línea base (1 = `low`, 2 = `medium`, 3 o más = `high`).
7. **Discrepancia:** el checklist no muestra cambio sostenido, pero al menos una fuente pasiva sí. Sube el nivel a `attention` como mínimo.
8. **Inicio (`onset_date`):** el primer día de la racha sostenida más antigua. Responde a "¿desde cuándo?".
9. **Tendencia:** media del z de los últimos `trend_window_days` días frente a los anteriores. Una diferencia mayor que `trend_min_delta` da `worsening` o `improving`.

**Calidad de datos.** Se ignoran los `quality: "bad"`. Los `"suspect"` también se excluyen de la fusión (conservador), pero se cuentan y se avisan en `data_notices`. Aplica igual a las lecturas `heart_rate` de Rubén.

---

## 1. `GET /wellbeing/parameters`

```json
{
  "provisional": true,
  "basis": "Parámetros de diseño del equipo, sin validación clínica. Se comparan desviaciones contra la línea base personal.",
  "z_threshold": 1.5,
  "sustain_days": 3,
  "baseline_days": 7,
  "baseline_min_days": 5,
  "adaptation_days": 0,
  "stale_after_days": 2,
  "trend_window_days": 3,
  "trend_min_delta": 0.5,
  "z_cap": 5.0,
  "components": [
    {"component": "checkin.sleep_hours", "source": "checkin", "indicator": "sleep", "adverse_direction": "low", "scale_floor": 1.0, "unit": "h"},
    {"component": "signal.hrv_sdnn", "source": "physiology", "indicator": "stress", "adverse_direction": "low", "scale_floor": 5.0, "unit": "ms"}
  ]
}
```

(`components` trae la lista completa; aquí se recorta.)

## 2. `GET /wellbeing/checkin-form`

Preguntas propias del equipo (no copiadas de cuestionarios). Escala 0–4 salvo las horas de sueño. `higher_is_better` indica la dirección: en `stress`, 4 es peor.

```json
{
  "version": "v1",
  "estimated_seconds": 45,
  "items": [
    {"key": "sleep_hours", "prompt": "¿Cuántas horas dormiste anoche?", "kind": "hours", "min": 0, "max": 24, "step": 0.5, "min_label": "0 h", "max_label": "24 h", "higher_is_better": true},
    {"key": "sleep_quality", "prompt": "¿Qué tan bien dormiste?", "kind": "scale", "min": 0, "max": 4, "step": 1, "min_label": "Muy mal", "max_label": "Muy bien", "higher_is_better": true},
    {"key": "energy", "prompt": "¿Cuánta energía tienes hoy?", "kind": "scale", "min": 0, "max": 4, "step": 1, "min_label": "Agotado/a", "max_label": "Mucha energía", "higher_is_better": true},
    {"key": "mood", "prompt": "¿Cómo está tu ánimo hoy?", "kind": "scale", "min": 0, "max": 4, "step": 1, "min_label": "Muy bajo", "max_label": "Muy bueno", "higher_is_better": true},
    {"key": "interest", "prompt": "¿Disfrutaste o te interesó lo que hiciste hoy?", "kind": "scale", "min": 0, "max": 4, "step": 1, "min_label": "Nada", "max_label": "Mucho", "higher_is_better": true},
    {"key": "stress", "prompt": "¿Cuánta tensión o preocupación sentiste hoy?", "kind": "scale", "min": 0, "max": 4, "step": 1, "min_label": "Nada", "max_label": "Mucha", "higher_is_better": false},
    {"key": "crew_connection", "prompt": "¿Qué tan conectado/a te sentiste con la tripulación?", "kind": "scale", "min": 0, "max": 4, "step": 1, "min_label": "Aislado/a", "max_label": "Muy conectado/a", "higher_is_better": true},
    {"key": "comment", "prompt": "¿Algo que quieras comentar? (opcional, privado)", "kind": "text", "max_length": 500, "optional": true}
  ]
}
```

## 3. `PUT /astronauts/{astronaut_id}/wellbeing/checkins/{day}`

Idempotente: un checklist por astronauta y día. Si se manda otra vez el mismo día, reemplaza al anterior. `day` es `YYYY-MM-DD`; la consola manda el día UTC actual.

Request:

```json
{
  "sleep_hours": 6.5,
  "sleep_quality": 2,
  "energy": 2,
  "mood": 3,
  "interest": 3,
  "stress": 2,
  "crew_connection": 3,
  "comment": null,
  "source": "crew"
}
```

`source` es opcional (por defecto `"crew"`). El simulador usa `"simulated"`.

Response `200`:

```json
{
  "astronaut_id": "ast-01",
  "day": "2026-11-14",
  "sleep_hours": 6.5,
  "sleep_quality": 2,
  "energy": 2,
  "mood": 3,
  "interest": 3,
  "stress": 2,
  "crew_connection": 3,
  "comment": null,
  "source": "crew",
  "submitted_at": "2026-11-14T18:02:11.000000Z",
  "simulated": false
}
```

Errores: `404` si el astronauta no existe. `422` si un valor está fuera de escala, si `day` no es fecha o si `day` es futuro.

## 4. `GET /astronauts/{astronaut_id}/wellbeing/checkins?since=YYYY-MM-DD&until=YYYY-MM-DD`

Ambos parámetros son opcionales e inclusivos. Devuelve `Checkin[]` del más reciente al más antiguo. **Incluye `comment`: sólo para la vista personal.**

## 5. `POST /wellbeing/signals`

Señales fisiológicas para la fusión. La unidad es fija por tipo:

| `kind` | `unit` | Notas |
|---|---|---|
| `hrv_sdnn` | `ms` | HRV SDNN del Apple Watch (esporádica, no continua) |
| `resting_heart_rate` | `bpm` | FC en reposo diaria del Watch |
| `sleep_hours` | `h` | Horas dormidas; `recorded_at` = hora de despertar (cuenta para ese día) |

Request:

```json
{
  "astronaut_id": "ast-01",
  "kind": "hrv_sdnn",
  "value": 48.2,
  "unit": "ms",
  "recorded_at": "2026-11-14T07:10:00Z",
  "quality": "good",
  "source": "apple_watch_export"
}
```

Response `201`: lo mismo más `"id": 17`, `"received_at": "..."` y `"simulated": false`. Errores: `404` si el astronauta no existe; `422` si la unidad no coincide con el `kind`.

## 6. `POST /wellbeing/vision-sessions`

Métricas derivadas de cámara: **nunca imágenes ni plantillas faciales**. Se manda un registro por bitácora. En modo ambiente, uno por persona y por ventana.

Request (bitácora):

```json
{
  "astronaut_id": "ast-01",
  "session_type": "bitacora",
  "module_id": "modulo-a",
  "source": "vision:cam0",
  "started_at": "2026-11-14T08:00:00Z",
  "ended_at": "2026-11-14T08:01:30Z",
  "quality": "good",
  "valid_frame_ratio": 0.94,
  "identity": {"method": "face", "match_score": 0.71},
  "neutral_ok": true,
  "fatigue": {"blink_rate_per_min": 18.2, "perclos": 0.07, "eye_openness_vs_neutral": 0.88, "yawn_count": 1, "nod_count": 0},
  "tension": {"brow_lower_delta": 0.12, "lip_press_delta": 0.05, "brow_lower_peak_1s": 0.31, "lip_press_peak_1s": null},
  "motion": null,
  "provisional": true
}
```

En modo ambiente (`"session_type": "ambiente"`), `motion` lleva:

```json
"motion": {"speed": 0.35, "stationary_ratio": 0.6, "fidget_index": 0.12, "torso_angle_dev": 14.0}
```

| Campo | Tipo | Rango | Uso en la fusión |
|---|---|---|---|
| `session_type` | `"bitacora"` \| `"ambiente"` | | — |
| `module_id` | string | 1–32 | — |
| `valid_frame_ratio` | número | 0–1 | calidad (se guarda) |
| `identity.method` | `"face"` \| `"wearable"` \| `"manual"` | | — |
| `identity.match_score` | número \| null | 0–1 | — |
| `neutral_ok` | boolean | | si es `false`, se ignoran las métricas relativas al neutral (`eye_openness_vs_neutral` y todo `tension.*`, picos incluidos) |
| `fatigue.blink_rate_per_min` | número \| null | ≥0 | se guarda; no entra en v1 (su dirección es ambigua) |
| `fatigue.perclos` | número \| null | 0–1 | fatigue ↑ |
| `fatigue.eye_openness_vs_neutral` | número \| null | ≥0 (1 = igual al neutral) | fatigue ↓ |
| `fatigue.yawn_count` | entero \| null | ≥0 | fatigue ↑ (por minuto de sesión) |
| `fatigue.nod_count` | entero \| null | ≥0 | fatigue ↑ (por minuto de sesión) |
| `tension.brow_lower_delta` | número \| null | 0–1 | stress ↑ |
| `tension.lip_press_delta` | número \| null | 0–1 | stress ↑ |
| `tension.brow_lower_peak_1s` | número \| null, **opcional** | 0–1 | stress ↑. Nivel más alto sostenido ≥ 1 s; `null` si nunca hubo 1 s seguido con la cara visible |
| `tension.lip_press_peak_1s` | número \| null, **opcional** | 0–1 | stress ↑. Igual que el anterior, para labios apretados |
| `motion.speed` | número \| null | ≥0 (aprox., anchos de hombro/s) | activation ↕ |
| `motion.stationary_ratio` | número \| null | 0–1 | activation ↕ |
| `motion.fidget_index` | número \| null | ≥0 | activation ↑ |
| `motion.torso_angle_dev` | número \| null | ≥0 (grados frente a la postura neutral) | activation ↑ |
| `provisional` | boolean | | se guarda; las salidas siempre son provisionales en v1 |

- `fatigue`, `tension` y `motion` pueden ser `null`, pero debe venir al menos uno.
- Los picos (`*_peak_1s`) son opcionales: un envío sin ellos sigue siendo válido. Entran a la fusión como componentes propios del indicador `stress`, porque una mueca de 1–2 s casi no mueve el promedio de una bitácora de 90 s pero sí el pico.
- El día de la sesión es el de `started_at`. Varias sesiones del mismo día se promedian.
- `astronaut_id` puede ser `"unknown-<track>"` (persona no identificada). Se acepta y se guarda, pero **nunca entra en ninguna línea base** ni en la fusión.

Response `201`: lo mismo más `id`, `received_at` y `simulated`. Errores: `404` si el astronauta no existe (y no es `unknown-*`); `422` si `ended_at < started_at`, si no viene ningún grupo de métricas o si algo está fuera de rango.

## 7. `POST /wellbeing/co-presence`

Una ventana (60 s) de un módulo: quién estuvo y qué pares compartieron espacio.

Request:

```json
{
  "module_id": "modulo-a",
  "source": "vision:cam0",
  "window_start": "2026-11-14T12:00:00Z",
  "window_end": "2026-11-14T12:01:00Z",
  "occupants": [
    {"astronaut_id": "ast-01", "seconds_present": 58},
    {"astronaut_id": "ast-02", "seconds_present": 45}
  ],
  "pairs": [
    {"a": "ast-01", "b": "ast-02", "seconds_together": 40, "mean_distance_shoulders": 2.3, "facing_ratio": 0.4}
  ],
  "quality": "good",
  "provisional": true
}
```

- `quality` es opcional (por defecto `"good"`).
- `occupants` no puede repetir ids. Cada par (`a`, `b`) debe ser de dos ocupantes distintos de la ventana.
- `seconds_present` y `seconds_together` van de 0 a la duración de la ventana.
- `mean_distance_shoulders` (anchos de hombro) y `facing_ratio` (orientación 2D) son aproximados: se guardan y no entran en la fusión v1.
- Se aceptan ids `"unknown-<track>"`. No tienen línea base. El tiempo que un astronauta conocido pasa con un desconocido sí cuenta como tiempo acompañado.

Componente usado: `social.accompanied_minutes` por día (menos = peor). En cada ventana se toma el mayor `seconds_together` de los pares de la persona; es una cota inferior que evita contar doble cuando hay tres o más personas. Una ventana donde la persona está sin pares cuenta como tiempo observado solo (0 min acompañado).

Response `201`: lo mismo más `id`, `received_at` y `simulated`. Errores: `404` si algún id no existe (salvo `unknown-*`); `422` si la validación falla.

## 8. `GET /wellbeing/crew` (vista tripulación)

Una entrada por astronauta registrado, ordenados por `astronaut_id`. **Sin detalle**: ni indicadores, ni fecha de inicio, ni comentarios.

```json
{
  "generated_at": "2026-11-14T18:05:00.000000Z",
  "provisional": true,
  "members": [
    {"astronaut_id": "ast-01", "display_name": "X", "level": "ok", "trend": "stable", "simulated": true},
    {"astronaut_id": "ast-02", "display_name": "Y", "level": "needs_support", "trend": "worsening", "simulated": true},
    {"astronaut_id": "ast-03", "display_name": "Z", "level": "baseline_pending", "trend": "unknown", "simulated": false}
  ]
}
```

## 9. `GET /astronauts/{astronaut_id}/wellbeing` (vista personal)

```json
{
  "astronaut_id": "ast-02",
  "generated_at": "2026-11-14T18:05:00.000000Z",
  "level": "needs_support",
  "confidence": "high",
  "trend": "worsening",
  "onset_date": "2026-11-07",
  "sustained_days": 8,
  "discrepancy": false,
  "sustained_sources": ["checkin", "physiology", "social"],
  "latest_day": "2026-11-14",
  "indicators": [
    {
      "kind": "sleep",
      "status": "attention",
      "z": 2.4,
      "deviant_since": "2026-11-07",
      "sources": ["checkin", "physiology"],
      "latest_day": "2026-11-14",
      "provisional": true,
      "components": [
        {
          "component": "checkin.sleep_hours",
          "source": "checkin",
          "latest_value": 4.5,
          "unit": "h",
          "z": 2.8,
          "baseline_median": 7.0,
          "baseline_scale": 0.74,
          "baseline_days": 7,
          "baseline_from": "2026-10-25",
          "baseline_to": "2026-10-31",
          "baseline_ready": true,
          "latest_day": "2026-11-14"
        }
      ]
    }
  ],
  "support_notes": [
    "Varias fuentes muestran cambios sostenidos desde el 2026-11-07. Puede ayudar hablarlo con alguien de confianza de la tripulación.",
    "Si quieres, puedes enviar un resumen al psicólogo en Tierra. Sólo se envía con tu consentimiento."
  ],
  "data_notices": [
    "Historial simulado: 21 de 21 días."
  ],
  "simulated_days": 21,
  "live_days": 0,
  "provisional": true
}
```

- `indicators` trae siempre los 6 indicadores, en orden: `sleep`, `fatigue`, `stress`, `activation`, `social`, `mood`.
- `z` es `null` si no hay dato evaluable.
- `onset_date`, `deviant_since` y `sustained_days` son `null` o `0` cuando no hay cambio sostenido.
- `sustained_sources` lista las fuentes con cambio sostenido.

## 10. `GET /astronauts/{astronaut_id}/wellbeing/timeline?days=30`

`days` va de 1 a 120 (por defecto 30). Devuelve un día por fecha del calendario hasta hoy, también los días sin datos. Cada día se evalúa **con los datos disponibles hasta ese día**: el nivel de un día no cambia aunque lleguen datos posteriores.

```json
{
  "astronaut_id": "ast-02",
  "generated_at": "2026-11-14T18:05:00.000000Z",
  "onset_date": "2026-11-07",
  "z_threshold": 1.5,
  "provisional": true,
  "days": [
    {
      "day": "2026-11-06",
      "level": "ok",
      "has_data": true,
      "has_checkin": true,
      "simulated": true,
      "indicators": {"sleep": 0.3, "fatigue": 0.1, "stress": 0.4, "activation": null, "social": -0.2, "mood": 0.0},
      "sources": {"checkin": 0.4, "vision": null, "physiology": 0.2, "social": -0.2}
    },
    {
      "day": "2026-11-07",
      "level": "ok",
      "has_data": true,
      "has_checkin": true,
      "simulated": true,
      "indicators": {"sleep": 1.9, "fatigue": 1.2, "stress": 1.7, "activation": null, "social": 1.6, "mood": 1.1},
      "sources": {"checkin": 1.9, "vision": null, "physiology": 1.7, "social": 1.6}
    }
  ]
}
```

- `indicators.*` y `sources.*` son z adversos (positivo = peor), o `null`.
- El nivel de un día pasa a `attention` o `needs_support` cuando la racha alcanza `sustain_days`, no antes. `onset_date` marca dónde empezó la racha: es el punto que hay que dibujar como "inicio de la alteración".

## 11–14. Envío a psicólogo en Tierra

`POST /wellbeing/ground-packages`:

```json
{
  "astronaut_id": "ast-02",
  "requested_by": "captain",
  "requested_by_name": "Capitán",
  "consent": {"astronaut_confirmed": true, "statement_version": "v1"},
  "period_from": "2026-10-25",
  "period_to": "2026-11-14",
  "include": ["assessment", "timeline", "checkins"],
  "note": "Revisión sugerida tras una semana de cambios sostenidos."
}
```

- `requested_by`: quién inicia el envío. Siempre requiere el consentimiento del astronauta.
  - `"self"`: el propio astronauta.
  - `"captain"`: el capitán, con consentimiento del astronauta.
  - `"ground_psychologist"`: un psicólogo al terminar la misión, que revisa y decide si alguien necesita seguimiento, con consentimiento.
- `period_from` ≤ `period_to` ≤ hoy (UTC). El contenido se evalúa con los datos hasta el final de `period_to`.
- `include`: `"assessment"`, `"timeline"`, `"checkins"` o `"comments"`. Los comentarios libres sólo van si se piden explícitamente, y exigen `"checkins"`.
- `422` si `consent.astronaut_confirmed` no es `true` (o falta `consent`), si el periodo es inválido o está en el futuro, o si `include` está vacío, repite valores o trae `"comments"` sin `"checkins"`. **No existe envío automático.**
- `404` si el astronauta no existe.
- El objeto `consent` no se devuelve: queda registrado como `consent_statement_version` y `consent_recorded_at`.

Response `201`:

```json
{
  "id": "6b1f0a52-3c1e-4c55-9a0e-2f8d4f7f1c11",
  "astronaut_id": "ast-02",
  "requested_by": "captain",
  "requested_by_name": "Capitán",
  "period_from": "2026-10-25",
  "period_to": "2026-11-14",
  "include": ["assessment", "timeline", "checkins"],
  "note": "Revisión sugerida tras una semana de cambios sostenidos.",
  "status": "queued",
  "consent_statement_version": "v1",
  "consent_recorded_at": "2026-11-14T18:10:00.000000Z",
  "created_at": "2026-11-14T18:10:00.000000Z"
}
```

`status`: `"queued"` (en cola a bordo; el envío asíncrono llega con la telemetría), `"withdrawn"` (consentimiento retirado) o `"sent"` (futuro).

- `GET /wellbeing/ground-packages?astronaut_id=ast-02` → `GroundPackage[]`, del más reciente al más antiguo.
- `GET /wellbeing/ground-packages/{id}/content` → `{ "package": GroundPackage, "assessment": WellbeingAssessment | null, "timeline": WellbeingTimeline | null, "checkins": Checkin[] | null }`. Muestra lo que se enviaría. Sin `"comments"` en `include`, los `comment` salen como `null`. `404` si el paquete no existe; `409` si se retiró el consentimiento.
- `POST /wellbeing/ground-packages/{id}/withdraw` → `GroundPackage` con `status: "withdrawn"`. Es idempotente: retirar uno ya retirado lo devuelve igual. `409` si ya está `sent`; `404` si no existe.

`captain` y `ground_psychologist` no se verifican (la API no tiene usuarios). La consola debe pedir la confirmación del propio astronauta antes de mandar `astronaut_confirmed: true`.

---

## Tipos TypeScript (para `apps/spaceship-app/src/api/types.ts`)

```ts
// --- Wellbeing (salud mental) ---

export type SupportLevel =
  | "ok"
  | "attention"
  | "needs_support"
  | "baseline_pending"
  | "stale"
  | "no_data";
export type IndicatorStatus = "ok" | "attention" | "baseline_pending" | "stale" | "no_data";
export type IndicatorKind = "sleep" | "fatigue" | "stress" | "activation" | "social" | "mood";
export type WellbeingSource = "checkin" | "vision" | "physiology" | "social";
export type Confidence = "low" | "medium" | "high";
export type Trend = "improving" | "stable" | "worsening" | "unknown";
export type AdverseDirection = "low" | "high" | "both";
export type SignalKind = "hrv_sdnn" | "resting_heart_rate" | "sleep_hours";
export type VisionSessionType = "bitacora" | "ambiente";
export type IdentityMethod = "face" | "wearable" | "manual";
export type GroundRequester = "self" | "captain" | "ground_psychologist";
export type GroundInclude = "assessment" | "timeline" | "checkins" | "comments";
export type GroundPackageStatus = "queued" | "withdrawn" | "sent";

/** Indicators always come in this order. */
export const INDICATOR_KINDS: IndicatorKind[] = [
  "sleep",
  "fatigue",
  "stress",
  "activation",
  "social",
  "mood",
];

export interface ComponentParameter {
  component: string;
  source: WellbeingSource;
  indicator: IndicatorKind;
  adverse_direction: AdverseDirection;
  scale_floor: number;
  unit: string;
}

export interface WellbeingParameters {
  /** Always true in v1: design parameters, not clinical thresholds. */
  provisional: boolean;
  basis: string;
  z_threshold: number;
  sustain_days: number;
  baseline_days: number;
  baseline_min_days: number;
  adaptation_days: number;
  stale_after_days: number;
  trend_window_days: number;
  trend_min_delta: number;
  z_cap: number;
  components: ComponentParameter[];
}

export interface CheckinFormItem {
  key: string;
  prompt: string;
  kind: "hours" | "scale" | "text";
  min?: number;
  max?: number;
  step?: number;
  min_label?: string;
  max_label?: string;
  higher_is_better?: boolean;
  max_length?: number;
  optional?: boolean;
}

export interface CheckinForm {
  version: string;
  estimated_seconds: number;
  items: CheckinFormItem[];
}

export interface CheckinUpsert {
  /** Hours, 0–24, step 0.5. */
  sleep_hours: number;
  /** 0–4 scales. In `stress`, 4 is worse; in the rest, 4 is better. */
  sleep_quality: number;
  energy: number;
  mood: number;
  interest: number;
  stress: number;
  crew_connection: number;
  /** Optional, max 500 chars. Private: never shown in the crew view. */
  comment?: string | null;
  /** Default "crew". */
  source?: string;
}

export interface Checkin extends Required<Omit<CheckinUpsert, "comment">> {
  astronaut_id: string;
  /** YYYY-MM-DD (UTC mission day). */
  day: string;
  comment: string | null;
  submitted_at: string;
  simulated: boolean;
}

export interface SignalCreate {
  astronaut_id: string;
  kind: SignalKind;
  value: number;
  /** hrv_sdnn: "ms", resting_heart_rate: "bpm", sleep_hours: "h". */
  unit: string;
  recorded_at: string;
  quality: Quality;
  source: string;
}

export interface Signal extends SignalCreate {
  id: number;
  received_at: string;
  simulated: boolean;
}

export interface VisionIdentity {
  method: IdentityMethod;
  match_score?: number | null;
}

export interface VisionFatigue {
  blink_rate_per_min?: number | null;
  perclos?: number | null;
  eye_openness_vs_neutral?: number | null;
  yawn_count?: number | null;
  nod_count?: number | null;
}

export interface VisionTension {
  brow_lower_delta?: number | null;
  lip_press_delta?: number | null;
  /** Highest level held for at least 1 s; null if never 1 s with the face visible. */
  brow_lower_peak_1s?: number | null;
  lip_press_peak_1s?: number | null;
}

export interface VisionMotion {
  speed?: number | null;
  stationary_ratio?: number | null;
  fidget_index?: number | null;
  torso_angle_dev?: number | null;
}

export interface VisionSessionCreate {
  /** Known astronaut id, or "unknown-<track>" (never used for baselines). */
  astronaut_id: string;
  session_type: VisionSessionType;
  module_id: string;
  source: string;
  started_at: string;
  ended_at: string;
  quality: Quality;
  valid_frame_ratio: number;
  identity: VisionIdentity;
  neutral_ok: boolean;
  fatigue: VisionFatigue | null;
  tension: VisionTension | null;
  motion: VisionMotion | null;
  provisional: boolean;
}

export interface VisionSession extends VisionSessionCreate {
  id: number;
  received_at: string;
  simulated: boolean;
}

export interface CoPresenceOccupant {
  astronaut_id: string;
  seconds_present: number;
}

export interface CoPresencePair {
  a: string;
  b: string;
  seconds_together: number;
  mean_distance_shoulders?: number | null;
  facing_ratio?: number | null;
}

export interface CoPresenceCreate {
  module_id: string;
  source: string;
  window_start: string;
  window_end: string;
  occupants: CoPresenceOccupant[];
  pairs: CoPresencePair[];
  /** Default "good". */
  quality?: Quality;
  provisional: boolean;
}

export interface CoPresence extends Required<CoPresenceCreate> {
  id: number;
  received_at: string;
  simulated: boolean;
}

export interface CrewMemberSummary {
  astronaut_id: string;
  display_name: string;
  level: SupportLevel;
  trend: Trend;
  /** True if any input in the last 14 days is simulated. */
  simulated: boolean;
}

export interface CrewWellbeing {
  generated_at: string;
  provisional: boolean;
  members: CrewMemberSummary[];
}

export interface ComponentState {
  component: string;
  source: WellbeingSource;
  latest_value: number | null;
  unit: string;
  /** Adverse z: positive = worse than the personal baseline. */
  z: number | null;
  baseline_median: number | null;
  baseline_scale: number | null;
  baseline_days: number;
  baseline_from: string | null;
  baseline_to: string | null;
  baseline_ready: boolean;
  latest_day: string | null;
}

export interface IndicatorState {
  kind: IndicatorKind;
  status: IndicatorStatus;
  z: number | null;
  deviant_since: string | null;
  sources: WellbeingSource[];
  latest_day: string | null;
  provisional: boolean;
  components: ComponentState[];
}

export interface WellbeingAssessment {
  astronaut_id: string;
  generated_at: string;
  level: SupportLevel;
  confidence: Confidence;
  trend: Trend;
  /** First day of the oldest sustained change ("since when"). */
  onset_date: string | null;
  sustained_days: number;
  /** Self-report looks fine while passive signals show a sustained change. */
  discrepancy: boolean;
  sustained_sources: WellbeingSource[];
  latest_day: string | null;
  /** Always the 6 indicators, in INDICATOR_KINDS order. */
  indicators: IndicatorState[];
  /** Spanish, support language. Personal view only. */
  support_notes: string[];
  data_notices: string[];
  simulated_days: number;
  live_days: number;
  provisional: boolean;
}

export interface TimelineDay {
  day: string;
  level: SupportLevel;
  has_data: boolean;
  has_checkin: boolean;
  simulated: boolean;
  indicators: Record<IndicatorKind, number | null>;
  sources: Record<WellbeingSource, number | null>;
}

export interface WellbeingTimeline {
  astronaut_id: string;
  generated_at: string;
  onset_date: string | null;
  z_threshold: number;
  provisional: boolean;
  days: TimelineDay[];
}

export interface GroundPackageCreate {
  astronaut_id: string;
  requested_by: GroundRequester;
  requested_by_name: string;
  consent: { astronaut_confirmed: boolean; statement_version: string };
  period_from: string;
  period_to: string;
  include: GroundInclude[];
  note?: string | null;
}

export interface GroundPackage {
  id: string;
  astronaut_id: string;
  requested_by: GroundRequester;
  requested_by_name: string;
  period_from: string;
  period_to: string;
  include: GroundInclude[];
  note: string | null;
  status: GroundPackageStatus;
  consent_statement_version: string;
  consent_recorded_at: string;
  created_at: string;
}

export interface GroundPackageContent {
  package: GroundPackage;
  assessment: WellbeingAssessment | null;
  timeline: WellbeingTimeline | null;
  checkins: Checkin[] | null;
}
```

`Quality` ya existe en `types.ts` (`"good" | "suspect" | "bad"`).

## Notas para la integración

- El router está registrado en `main.py`: todos los endpoints viven en el mismo servidor onboard (`http://127.0.0.1:8000`) y aparecen en `/docs` bajo la etiqueta `wellbeing`.
- Flujo sugerido para la pantalla de consentimiento: el astronauta revisa el periodo e `include` → `POST` con `astronaut_confirmed: true` → `GET …/content` para mostrar lo que va en cola → botón "retirar" con `POST …/withdraw`.
- Simulador de historial: `uv run python scripts/simulate_wellbeing.py` (en `services/onboard-api`). Crea `ast-01`…`ast-04` vía `POST /astronauts` si no existen, y escribe en `wellbeing.db` con `source: "simulated"`: checklists, señales tipo Watch, co-presencia y bitácoras de visión. Las bitácoras simuladas llegan hasta ayer, así que una bitácora en vivo de hoy se evalúa sola contra una línea base ya formada. Los rangos de visión están en `VISION_REST` y `VISION_ALTERED` de `wellbeing/simulator.py`; los medidos y los supuestos están marcados ahí.
- Configuración (variables de entorno): `WELLBEING_DB_PATH` (por defecto `data/wellbeing.db`), `ONBOARD_DB_PATH` (la base de Rubén, sólo lectura), `WELLBEING_Z_THRESHOLD`, `WELLBEING_SUSTAIN_DAYS`, etc. (ver `onboard_api/wellbeing/settings.py`).

## Probarlo en local (PowerShell)

```powershell
cd services\onboard-api
uv sync --locked
$env:PYTHONUTF8 = "1"
uv run fastapi dev
```

En otra terminal:

```powershell
cd services\onboard-api
uv run python scripts/simulate_wellbeing.py
Invoke-RestMethod http://127.0.0.1:8000/wellbeing/crew | ConvertTo-Json -Depth 4
Invoke-RestMethod http://127.0.0.1:8000/astronauts/ast-02/wellbeing | ConvertTo-Json -Depth 6
Start-Process http://127.0.0.1:8000/docs
```

Resultado esperado del historial simulado: `ast-01` y `ast-04` en `ok`, `ast-02` en `needs_support` desde el día 14 del historial, `ast-03` en `needs_support` con `discrepancy: true`.

Flujo del envío a Tierra (con el servidor arriba y el historial simulado cargado):

```powershell
$B = "http://127.0.0.1:8000"
$today = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
$from = (Get-Date).ToUniversalTime().AddDays(-20).ToString("yyyy-MM-dd")
function New-Package($who, $consent) {
  @{ astronaut_id = "ast-02"; requested_by = $who; requested_by_name = "Demo"
     consent = @{ astronaut_confirmed = $consent; statement_version = "v1" }
     period_from = $from; period_to = $today
     include = @("assessment", "timeline", "checkins") } | ConvertTo-Json -Depth 3
}
function Send-Package($who, $consent) {
  Invoke-RestMethod -Method Post "$B/wellbeing/ground-packages" -ContentType "application/json" -Body (New-Package $who $consent)
}

# 1) Sin consentimiento: 422
try { Send-Package "captain" $false } catch { "Sin consentimiento -> HTTP " + [int]$_.Exception.Response.StatusCode }

# 2) Con consentimiento: self, captain y ground_psychologist quedan en cola
$self    = Send-Package "self" $true
$captain = Send-Package "captain" $true
$psych   = Send-Package "ground_psychologist" $true
$self, $captain, $psych | Select-Object requested_by, status, id | Format-Table

# 3) Lo que se enviaria (comentarios privados ocultos)
$c = Invoke-RestMethod "$B/wellbeing/ground-packages/$($captain.id)/content"
"Contenido: nivel {0}, inicio {1}, {2} dias, {3} checklists" -f $c.assessment.level, $c.assessment.onset_date, $c.timeline.days.Count, $c.checkins.Count

# 4) Retirar el consentimiento y comprobar que ya no se puede ver
(Invoke-RestMethod -Method Post "$B/wellbeing/ground-packages/$($captain.id)/withdraw").status
try { Invoke-RestMethod "$B/wellbeing/ground-packages/$($captain.id)/content" } catch { "Contenido tras retirar -> HTTP " + [int]$_.Exception.Response.StatusCode }

# 5) Lista de paquetes (en PowerShell 5.1 el arreglo se guarda primero en una variable)
$list = Invoke-RestMethod "$B/wellbeing/ground-packages?astronaut_id=ast-02"
$list | Select-Object requested_by, status, created_at | Format-Table
```

Resultado esperado: `422` sin consentimiento; tres paquetes `queued`; contenido con nivel `needs_support`; `withdrawn` y `409` al pedir el contenido después de retirar el consentimiento.
