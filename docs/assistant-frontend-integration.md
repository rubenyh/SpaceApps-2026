# Integración del asistente con la consola (Tauri)

Contrato: `services/onboard-api/src/onboard_api/schemas/assistant.py`, reflejado en `apps/spaceship-app/src/api/types.ts`. Si este documento y el código difieren, manda el código.

El asistente médico es soporte informativo. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado.

## Estado actual

- Envío: `sendAssistantMessage()` en [`apps/spaceship-app/src/api/assistant.ts`](../apps/spaceship-app/src/api/assistant.ts) hace `POST /assistant/messages`.
- URL base: `API_BASE_URL` en [`apps/spaceship-app/src/api/client.ts`](../apps/spaceship-app/src/api/client.ts). Usa `VITE_ONBOARD_API_URL` y, si no existe, `http://127.0.0.1:8000`. Tiempo de espera: 10 s.
- [`AsistenteScreen.tsx`](../apps/spaceship-app/src/screens/AsistenteScreen.tsx) envía `message`, `astronaut_id`, `reported_by` (selector "Informa") y `reported_symptoms` (selector de síntoma con Sí / No / No se sabe). Muestra todos los campos de la respuesta en el orden indicado abajo, con `matched_rules` en un detalle plegado. Los selectores no envían `onset`, `severity`, `persistence`, `started_at` ni `context`.
- Aclaraciones: tras una respuesta con `needs_clarification`, el siguiente mensaje se envía con `buildRequest()` de [`lib/assistant.ts`](../apps/spaceship-app/src/lib/assistant.ts): el mensaje original más el texto nuevo, la misma persona evaluada y la misma persona que informa, y los síntomas anteriores combinados con los nuevos. "Nuevo reporte" cancela la aclaración. Prueba: `node src/lib/assistant.check.ts`. Todavía no reenvía `clarification` (ver [Aclaraciones](#aclaraciones-endpoint-sin-estado)).

**Nada se transmite.** `notify` indica a quién debe avisar la tripulación. El POST no envía avisos a bordo ni a tierra. El estado "enviado" se reserva para un futuro componente de telemetría que confirme la entrega (Planned).

## Petición

| Campo | Tipo | Uso |
|---|---|---|
| `message` | string, 1 a 4000 caracteres | Texto del reporte o de la consulta. Obligatorio. |
| `astronaut_id` | string o null | Persona evaluada. Sin él no se consultan lecturas. |
| `reported_by` | string o null | Compañero que envía el reporte, si no es la persona evaluada. |
| `reported_symptoms` | lista, máx. 40 | Observaciones estructuradas. Si un código también aparece en el texto, prevalece el dato estructurado. |
| `clarification` | objeto o null | Caso abierto devuelto por la respuesta anterior, reenviado sin cambios para contestar su pregunta. |

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

Cuando `needs_clarification` es `true`, se muestra `clarifying_question` y se espera la respuesta del usuario. El servidor no guarda conversación: el caso abierto viaja en el campo `clarification` de la respuesta (workflows `medical` y `clarify`).

| Campo de `clarification` | Uso |
|---|---|
| `question_id` | `routing` (¿síntoma actual o información general?), `symptom` (¿qué sientes?) o `<protocol_id>.<question_key>` de una ficha. |
| `question` | Texto de la pregunta pendiente. |
| `astronaut_id` | Persona del caso. Si el siguiente POST trae otro `astronaut_id`, el caso se ignora y empieza uno nuevo. |
| `observations` | Observaciones acumuladas: `symptom`, `status`, `origin` (`text`, `llm`, `structured`), `evidence` (palabras del usuario) y calificadores. |

### Cómo la retomará Tauri (pendiente en la consola)

1. Guardar `clarification` de la última respuesta junto a la pregunta mostrada.
2. Al responder, enviar `message` **solo con el texto nuevo**, el mismo `astronaut_id` y `reported_by`, y `clarification` sin modificar. Los `reported_symptoms` de los selectores se siguen enviando igual.
3. Si la nueva respuesta trae otra `clarification`, sustituir la guardada. Si trae `null` (acción, alarma o fuera de cobertura), el caso terminó.
4. "Nuevo reporte" o cambiar de astronauta borra la `clarification` guardada.

Hoy `buildRequest()` en [`lib/assistant.ts`](../apps/spaceship-app/src/lib/assistant.ts) concatena el mensaje original con la respuesta y no envía `clarification`. Ese modo sigue funcionando (por ejemplo, el mensaje `hola` + salto de línea + `malestar físico` pregunta qué siente), pero no permite interpretar un "sí" o un "no" según la pregunta. Cambio previsto en `types.ts`: añadir `clarification?: Clarification | null` a `AssistantRequest` y `AssistantResponse`.

Ejemplo. Primer envío: `{"astronaut_id": "ana", "message": "Me duele la cabeza"}` devuelve `question_id: "neurologic_red_flags.headache_red_flags"` y la pregunta del ejemplo de aclaración de abajo. Reenvío:

```json
{
  "astronaut_id": "ana",
  "message": "Empezó de repente y es muy intenso",
  "clarification": { "question_id": "neurologic_red_flags.headache_red_flags", "question": "...", "astronaut_id": "ana", "observations": [ { "symptom": "headache", "status": "present", "origin": "text", "evidence": "me duele la cabeza" } ] }
}
```

Devuelve `urgency: "immediate"` y `protocol_id: "neurologic_red_flags"` (prueba `test_follow_up_qualifies_the_open_symptom`). También sirve reenviar el síntoma estructurado (`sudden_severe_headache` con `status: "present"`).

### Cómo se interpreta cada turno

1. **Alarmas primero.** `SOS` (en mayúsculas, o `auxilio`, `socorro`, `mayday`), los eventos activos de la nave y las frases de alarma de las reglas se evalúan sobre el mensaje nuevo más las observaciones del caso. Una respuesta escueta a una pregunta de un solo síntoma ("sí, un poco", "sí, mucho", "no") la resuelven las reglas en este paso. Si hay alarma, la respuesta sale de las fichas locales sin consultar SQLite, ChromaDB ni Ollama.
2. **Intérprete local.** Sin alarma, Qwen (`ONBOARD_OLLAMA_CHAT_MODEL`, espera máxima `ONBOARD_OLLAMA_INTERPRET_TIMEOUT_SECONDS`, 8 s por defecto) lee el mensaje nuevo con la pregunta pendiente y los datos ya reportados. Devuelve JSON validado con Pydantic: síntoma, estado (`present`, `absent`, `unknown`) y la frase que lo respalda. Se descarta cualquier observación cuya frase no esté en el mensaje, que contradiga a las reglas, o que sea un "sí"/"no" aplicado a un síntoma por el que no se preguntó. Qwen solo completa datos que faltan; un dato confirmado cambia solo con una corrección explícita en el texto o en `reported_symptoms`. Si Qwen falla o tarda, deciden las reglas y el caso sigue abierto.
3. **Reglas.** Las observaciones resultantes pasan otra vez por las alarmas y después por las fichas. Un reporte sin síntoma concreto ("malestar físico") recibe la pregunta "¿Qué sientes ahora?…". `out_of_coverage` queda para un síntoma o evento concreto que el catálogo no cubre ("me duele el oído"), o para un segundo turno que sigue sin nombrar un síntoma.

Los avisos de lecturas (`data_notices`) solo aparecen cuando la ficha decidida usa ese sensor. Una pregunta sin ficha no los muestra.

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
  "clarifying_question": null,
  "clarification": null
}
```

## Ejemplo: aclaración

Petición: `{"astronaut_id": "ana", "message": "Me duele la cabeza"}`. Respuesta real del servicio el 2026-11-14, sin lecturas registradas para `ana`. La ficha neurológica no usa lecturas, así que no hay avisos de sensores:

```json
{
  "reply": "Dolor de cabeza sin datos de inicio e intensidad: confirmar si hay señales de alarma neurológica.\n\nAlteración súbita del habla, asimetría facial, debilidad de un lado, pérdida súbita de visión o dolor de cabeza súbito e intenso pueden indicar un evento neurológico agudo. Ictus o AIT requieren descarte ante señales focales, aunque ya hayan cedido. Un dolor de cabeza sin esas señales se valora por su propio contexto o por la ruta de cabina. Soporte informativo únicamente: no es un diagnóstico ni una decisión de tratamiento; la valoración corresponde al responsable médico a bordo.\n\n¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
  "workflow": "medical",
  "needs_clarification": true,
  "sources": [
    { "id": "neurologic_red_flags@1.0.0#cdc_stroke_signs", "title": "CDC: Signs and Symptoms of Stroke", "section": "Señales de ictus", "url": "https://www.cdc.gov/stroke/signs-symptoms/", "kind": "protocol" },
    { "id": "neurologic_red_flags@1.0.0#medlineplus_headache", "title": "MedlinePlus: Headache", "section": "Resumen", "url": "https://medlineplus.gov/headache.html", "kind": "protocol" }
  ],
  "data_notices": [],
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
  "clarifying_question": "¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
  "clarification": {
    "question_id": "neurologic_red_flags.headache_red_flags",
    "question": "¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
    "astronaut_id": "ana",
    "observations": [
      { "symptom": "headache", "status": "present", "origin": "text", "evidence": "me duele la cabeza", "temporality": "current", "subject": "self", "onset": null, "severity": null, "persistence": null, "context": null }
    ]
  }
}
```
