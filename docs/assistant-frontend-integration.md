# Integración del asistente con la consola (Tauri)

Contrato: `services/onboard-api/src/onboard_api/schemas/assistant.py`, reflejado en `apps/spaceship-app/src/api/types.ts`. Si este documento y el código difieren, manda el código.

El asistente médico es soporte informativo. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado.

## Estado actual

- Envío: `sendAssistantMessage()` en [`apps/spaceship-app/src/api/assistant.ts`](../apps/spaceship-app/src/api/assistant.ts) hace `POST /assistant/messages`.
- URL base: `API_BASE_URL` en [`apps/spaceship-app/src/api/client.ts`](../apps/spaceship-app/src/api/client.ts). Usa `VITE_ONBOARD_API_URL` y, si no existe, `http://127.0.0.1:8000`. Tiempo de espera: 10 s.
- [`AsistenteScreen.tsx`](../apps/spaceship-app/src/screens/AsistenteScreen.tsx) envía `message`, `astronaut_id`, `reported_by` (selector "Informa") y `reported_symptoms` (selector de síntoma con Sí / No / No se sabe). Muestra todos los campos de la respuesta en el orden indicado abajo, con `matched_rules` en un detalle plegado. Los selectores no envían `onset`, `severity`, `persistence`, `started_at` ni `context`.
- Aclaraciones: tras una respuesta con `needs_clarification`, el siguiente mensaje se envía con `buildRequest()` de [`lib/assistant.ts`](../apps/spaceship-app/src/lib/assistant.ts): el mensaje original más el texto nuevo, la misma persona evaluada y la misma persona que informa, y los síntomas anteriores combinados con los nuevos. "Nuevo reporte" cancela la aclaración. Prueba: `node src/lib/assistant.check.ts`.

**Nada se transmite.** `notify` indica a quién debe avisar la tripulación. El POST no envía avisos a bordo ni a tierra. El estado "enviado" se reserva para un futuro componente de telemetría que confirme la entrega (Planned).

## Petición

| Campo | Tipo | Uso |
|---|---|---|
| `message` | string, 1 a 4000 caracteres | Texto del reporte o de la consulta. Obligatorio. |
| `astronaut_id` | string o null | Persona evaluada. Sin él no se consultan lecturas. |
| `reported_by` | string o null | Compañero que envía el reporte, si no es la persona evaluada. |
| `reported_symptoms` | lista, máx. 40 | Observaciones estructuradas. Si un código también aparece en el texto, prevalece el dato estructurado. |

Cada elemento de `reported_symptoms`: `symptom` (código de `SYMPTOM_CODES` en `types.ts`), `status` (`present` por defecto, `absent`, `unknown`), y opcionales `onset` (`sudden`, `gradual`), `severity` (`mild`, `moderate`, `severe`), `persistence` (`ongoing`, `resolved`, `recurrent`), `started_at` (ISO 8601 con zona horaria), `context` (máx. 200 caracteres).

```json
{
  "astronaut_id": "ana",
  "reported_by": "luis",
  "message": "Ana dice que siente presión en el pecho y sudor frío",
  "reported_symptoms": [
    { "symptom": "chest_pain", "status": "present", "persistence": "ongoing" }
  ]
}
```

## Aclaraciones (endpoint sin estado)

Cuando `needs_clarification` es `true`, se muestra `clarifying_question` y se espera la respuesta del usuario. El servidor no guarda conversación. Para responder, la consola reenvía al mismo endpoint:

1. el `message` original (se le puede añadir el texto nuevo),
2. el mismo `astronaut_id` y `reported_by`,
3. los `reported_symptoms` previos más los nuevos.

Ejemplo. Primer envío: `{"astronaut_id": "ana", "message": "Me duele la cabeza"}` devuelve la pregunta del ejemplo de aclaración de abajo. El usuario responde que empezó de golpe y es muy intenso. Reenvío:

```json
{
  "astronaut_id": "ana",
  "message": "Me duele la cabeza",
  "reported_symptoms": [
    { "symptom": "sudden_severe_headache", "status": "present", "onset": "sudden", "severity": "severe" }
  ]
}
```

Con `ONBOARD_DEMO_EVENTS_PATH` sin definir, este reenvío devolvió `urgency: "immediate"` y `protocol_id: "neurologic_red_flags"` (verificado el 2026-11-14). Las respuestas negativas se envían con `"status": "absent"`.

Si `workflow` es `"clarify"` (mensaje demasiado vago, sin ficha), la pregunta es de enrutado. En ese caso se reenvía el mensaje original con la respuesta añadida al texto.

## Qué mostrar y en qué orden

| Orden | Campos | Cómo |
|---|---|---|
| 1 | `urgency`, `action`, `notify` | Bloque principal. `immediate` debe dominar la pantalla (color, tamaño, arriba del todo). `notify` se muestra como "Avisar a: ...". No se muestra como enviado. |
| 2 | `reply` | Texto explicativo. Ya empieza por `action` cuando hay ficha. |
| 3 | `clarifying_question` | Solo si `needs_clarification`. Destacada, con el campo de respuesta. |
| 4 | `protocol_id`, `additional_protocol_ids` | Ficha principal y fichas adicionales activadas. |
| 5 | `findings` | Evidencia usada: `kind` (`symptom`, `reading`, `event`, `data_gap`), `detail`, `source`. |
| 6 | `possible_causes` | `label` con su etiqueta de estado, `evidence_for`, `missing_data`. Nunca como probabilidad ni porcentaje, ni ordenadas como "más probable". |
| 7 | `data_notices` | Lecturas ausentes, antiguas o dudosas y fallos de guías o del modelo local. |
| 8 | `sources` | `title`, `section` y enlace `url`. Distinguir `kind`: `protocol` (ficha revisada) y `guide` (fragmento recuperado del corpus). |
| 9 | `disclaimer` | Siempre visible cuando venga. |

`matched_rules` (regla, versión de ficha, urgencia) es trazabilidad técnica. Puede ir en un detalle plegado.

Etiquetas de `urgency`:

| Valor | Etiqueta sugerida |
|---|---|
| `immediate` | Alerta inmediata a bordo |
| `review_required` | Pedir valoración al responsable médico |
| `undetermined` | Falta un dato decisivo |
| `informational` | Información general |
| `null` | Sin triaje (`workflow` `clarify` o `unsupported`) |

Etiquetas de `possible_causes[].status`:

| Valor | Etiqueta sugerida |
|---|---|
| `compatible` | Compatible con lo reportado |
| `rule_out` | Requiere descarte |
| `insufficient_evidence` | Evidencia insuficiente |

## Ejemplo: alarma

Petición: `{"astronaut_id": "ana", "message": "Siento presión en el pecho desde hace un rato y sudor frío"}`. Respuesta real del servicio el 2026-11-14 (los textos dependen de las fichas y pueden cambiar):

```json
{
  "reply": "Avisar de inmediato al responsable médico a bordo y seguir la ficha de dolor torácico de la misión.\n\nDolor, presión o molestia torácica nueva o inexplicada. Si el patrón es preocupante (presión, dolor intenso, persistente o que reaparece, o acompañado de falta de aire, sudor frío o mareo), el síndrome coronario agudo es una causa prioritaria que requiere descarte; eso no significa que sea la causa más probable. Soporte informativo únicamente: no es un diagnóstico ni una decisión de tratamiento; la valoración corresponde al responsable médico a bordo.",
  "workflow": "medical",
  "needs_clarification": false,
  "sources": [
    { "id": "chest_pain@1.0.0#cdc_heart_attack", "title": "CDC: About Heart Attack and Symptoms", "section": "Síntomas de infarto", "url": "https://www.cdc.gov/heart-disease/about/heart-attack.html", "kind": "protocol" },
    { "id": "chest_pain@1.0.0#medlineplus_chest_pain", "title": "MedlinePlus: Chest Pain", "section": "Resumen", "url": "https://medlineplus.gov/chestpain.html", "kind": "protocol" }
  ],
  "data_notices": [
    "Alarma inmediata: la respuesta usa solo fichas locales; no se esperó a consultar lecturas, guías ni el modelo local."
  ],
  "disclaimer": "Soporte informativo únicamente. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado.",
  "urgency": "immediate",
  "action": "Avisar de inmediato al responsable médico a bordo y seguir la ficha de dolor torácico de la misión.",
  "notify": ["responsable médico a bordo", "tripulación"],
  "protocol_id": "chest_pain",
  "additional_protocol_ids": [],
  "matched_rules": [
    { "rule_id": "chest_pain.concerning_pattern", "protocol_id": "chest_pain", "protocol_version": "1.0.0", "urgency": "immediate" }
  ],
  "findings": [
    { "kind": "symptom", "detail": "Dolor o presión torácica; persistente (\"presion en el pecho\")", "source": "report" },
    { "kind": "symptom", "detail": "Sudor frío; persistente (\"sudor frio\")", "source": "report" }
  ],
  "possible_causes": [
    {
      "id": "acs",
      "label": "Síndrome coronario agudo (requiere descarte)",
      "status": "rule_out",
      "evidence_for": ["Dolor o presión torácica", "Sudor frío"],
      "missing_data": [],
      "source_ids": ["cdc_heart_attack", "medlineplus_chest_pain"]
    }
  ],
  "clarifying_question": null
}
```

## Ejemplo: aclaración

Petición: `{"astronaut_id": "ana", "message": "Me duele la cabeza"}`. Respuesta real del servicio el 2026-11-14, sin lecturas registradas para `ana`:

```json
{
  "reply": "Dolor de cabeza sin datos de inicio e intensidad: confirmar si hay señales de alarma neurológica.\n\nAlteración súbita del habla, asimetría facial, debilidad de un lado, pérdida súbita de visión o dolor de cabeza súbito e intenso pueden indicar un evento neurológico agudo. Ictus o AIT requieren descarte ante señales focales, aunque ya hayan cedido. Un dolor de cabeza sin esas señales se valora por su propio contexto o por la ruta de cabina. Soporte informativo únicamente: no es un diagnóstico ni una decisión de tratamiento; la valoración corresponde al responsable médico a bordo.\n\n¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
  "workflow": "medical",
  "needs_clarification": true,
  "sources": [
    { "id": "neurologic_red_flags@1.0.0#cdc_stroke_signs", "title": "CDC: Signs and Symptoms of Stroke", "section": "Señales de ictus", "url": "https://www.cdc.gov/stroke/signs-symptoms/", "kind": "protocol" },
    { "id": "neurologic_red_flags@1.0.0#medlineplus_headache", "title": "MedlinePlus: Headache", "section": "Resumen", "url": "https://medlineplus.gov/headache.html", "kind": "protocol" }
  ],
  "data_notices": ["Astronauta 'ana' no registrado: no hay lecturas."],
  "disclaimer": "Soporte informativo únicamente. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado.",
  "urgency": "undetermined",
  "action": "Dolor de cabeza sin datos de inicio e intensidad: confirmar si hay señales de alarma neurológica.",
  "notify": ["responsable médico a bordo"],
  "protocol_id": "neurologic_red_flags",
  "additional_protocol_ids": [],
  "matched_rules": [
    { "rule_id": "neurologic_red_flags.headache_check", "protocol_id": "neurologic_red_flags", "protocol_version": "1.0.0", "urgency": "undetermined" }
  ],
  "findings": [
    { "kind": "symptom", "detail": "Dolor de cabeza (\"me duele la cabeza\")", "source": "report" }
  ],
  "possible_causes": [],
  "clarifying_question": "¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?"
}
```
