# Integración del asistente con la consola (Tauri)

Contrato: `services/onboard-api/src/onboard_api/schemas/assistant.py`, reflejado en `apps/spaceship-app/src/api/types.ts`. Si este documento y el código difieren, manda el código.

El asistente médico es soporte informativo. **La misión no lleva personal clínico a bordo y el enlace con tierra puede faltar**: las respuestas dan pasos de primeros auxilios con fuente que un astronauta despierto puede hacer solo, separan lo que requiere otro tripulante o equipo, nombran el procedimiento de la misión al que apuntan y entregan un informe para copiar. Urgencia, acción y pasos salen de las fichas versionadas (v2.0.0) y funcionan con Ollama y ChromaDB caídos.

## Estado actual

- Envío: `sendAssistantMessage()` en [`apps/spaceship-app/src/api/assistant.ts`](../apps/spaceship-app/src/api/assistant.ts) hace `POST /assistant/messages`.
- URL base: `API_BASE_URL` en [`apps/spaceship-app/src/api/client.ts`](../apps/spaceship-app/src/api/client.ts). Usa `VITE_ONBOARD_API_URL` y, si no existe, `http://127.0.0.1:8000`. Tiempo de espera: 60 s para el asistente (`ASSISTANT_TIMEOUT_MS` en `api/assistant.ts`) y 10 s para las demás peticiones.
- [`AsistenteScreen.tsx`](../apps/spaceship-app/src/screens/AsistenteScreen.tsx) envía `message`, `astronaut_id`, `reported_by` (selector "Informa") y `reported_symptoms` (selector de síntoma con Sí / No / No se sabe). Muestra todos los campos de la respuesta en el orden indicado abajo, con `matched_rules` en un detalle plegado. Los selectores no envían `onset`, `severity`, `persistence`, `started_at` ni `context`.
- Aclaraciones: tras una respuesta con `needs_clarification`, el siguiente mensaje se envía con `buildRequest()` de [`lib/assistant.ts`](../apps/spaceship-app/src/lib/assistant.ts). Si la respuesta traía `clarification`, la reenvía sin cambios y `message` lleva solo el texto nuevo. Si no, une el mensaje original y el texto nuevo. En ambos casos conserva la persona evaluada y la que informa, y combina los síntomas anteriores con los nuevos. "Nuevo reporte" cancela la aclaración. Prueba: `node src/lib/assistant.check.ts`. Detalle: [Aclaraciones](#aclaraciones-endpoint-sin-estado).

**Nada se transmite.** `notify` indica a quién contárselo (tripulación, control de misión si hay enlace). La única excepción es el informe de caso: la respuesta trae `report.id` y `report.transmission` `draft`, y solo se envía a tierra cuando la tripulación pulsa **Send to base** (`POST /case-reports/{id}/send`; estados `draft`, `queued`, `received`, `failed`). Contrato: [case-report](../contracts/case-report/README.md). No hay envío automático.

Workflow `status`: preguntas rápidas sobre las lecturas propias ("Summarize my status today", "Which readings am I missing?"). Sin LLM ni ChromaDB; devuelve sin cambios la `clarification` pendiente. Campos nuevos de la respuesta: `assessed_at`, `readings_snapshot` (con `freshness` `current`, `stale` o `future`), `assessment` (`urgency`, `urgency_label`, `reported`, `action`, `escalation`) y `report.readings`. Fuente: [`schemas/assistant.py`](../services/onboard-api/src/onboard_api/schemas/assistant.py).

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

### Cómo la retoma la consola

1. Guardar `clarification` de la última respuesta junto a la pregunta mostrada.
2. Al responder, enviar `message` **solo con el texto nuevo**, el mismo `astronaut_id` y `reported_by`, y `clarification` sin modificar. Los `reported_symptoms` de los selectores se siguen enviando igual.
3. Si la nueva respuesta trae otra `clarification`, sustituir la guardada. Si trae `null` (acción, alarma o fuera de cobertura), el caso terminó.
4. "Nuevo reporte" o cambiar de astronauta borra la `clarification` guardada.

`buildRequest()` en [`lib/assistant.ts`](../apps/spaceship-app/src/lib/assistant.ts) sigue estos pasos cuando la respuesta trae `clarification` (campo de `AssistantRequest` y `AssistantResponse` en `types.ts`). Si una respuesta pide aclaración sin `clarification`, concatena el mensaje original con la respuesta. Ese modo de respaldo funciona (por ejemplo, `hola` + salto de línea + `malestar físico` pregunta qué siente), pero no permite interpretar un "sí" o un "no" según la pregunta.

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
2. **Intérprete local.** Sin alarma, Qwen (`ONBOARD_OLLAMA_CHAT_MODEL`, espera máxima `ONBOARD_OLLAMA_INTERPRET_TIMEOUT_SECONDS`, 15 s por defecto) lee el mensaje nuevo con la pregunta pendiente y los datos ya reportados. Devuelve JSON validado con Pydantic: síntoma, estado (`present`, `absent`, `unknown`) y la frase que lo respalda. Se descarta cualquier observación cuya frase no esté en el mensaje, que contradiga a las reglas, o que sea un "sí"/"no" aplicado a un síntoma por el que no se preguntó. Qwen solo completa datos que faltan; un dato confirmado cambia solo con una corrección explícita en el texto o en `reported_symptoms`. Si Qwen falla o tarda, deciden las reglas y el caso sigue abierto.
3. **Reglas.** Las observaciones resultantes pasan otra vez por las alarmas y después por las fichas. Un reporte sin síntoma concreto ("malestar físico") recibe la pregunta "¿Qué sientes ahora?…". `out_of_coverage` queda para un síntoma o evento concreto que el catálogo no cubre ("me duele el oído"), o para un segundo turno que sigue sin nombrar un síntoma.

Los avisos de lecturas (`data_notices`) solo aparecen cuando la ficha decidida usa ese sensor. Una pregunta sin ficha no los muestra.

## Qué mostrar y en qué orden

| Orden | Campos | Cómo |
|---|---|---|
| 1 | `urgency`, `action`, `mission_procedures`, `steps`, `notify` | Bloque principal. `immediate` domina la pantalla. Debajo de la acción, el procedimiento de la misión (si `loaded` es `false`: "no cargado en el asistente, usa la copia de la misión") y los pasos agrupados por `who`: `self` (puedes hacerlo solo), `crew` (requiere otro tripulante), `equipment` (requiere equipo). Cada paso muestra sus fuentes (`source_ids` apuntan a `sources[].id`). |
| 2 | `clarifying_question` | Solo si `needs_clarification`. Una sola vez. |
| 3 | `report` | "Review & send to base": texto (`text`), lecturas del informe (`readings`), botón de copiar y **Send to base**, con el estado de entrega (`transmission`: Draft, Queued, Received by base, Failed). |
| 4 | `reply` | Explicación. Ya empieza por `action` y puede contener la pregunta: la consola quita ambas (`explanation()` en `lib/assistant.ts`) para no repetirlas. |
| 5 | `missing_guidance` | Guía que las fichas no tienen, dicha de forma explícita. |
| 6 | `protocol_id`, `additional_protocol_ids`, `findings`, `possible_causes` | Evidencia. Las lecturas simuladas (`source` `simulated`, `demo` o `simulated:*`) llevan "SIMULADA". `possible_causes` nunca como probabilidad. |
| 7 | `data_notices` | Lecturas ausentes, antiguas o dudosas y fallos de guías o del modelo local. |
| 8 | `sources` | Lista numerada: `title`, `section`, `url`; `kind` `protocol` (ficha) o `guide` (corpus). |
| 9 | `disclaimer` | Siempre visible cuando venga. |

`matched_rules` (regla, versión de ficha, urgencia) es trazabilidad técnica. Puede ir en un detalle plegado.

Etiquetas de `urgency`:

| Valor | Etiqueta sugerida |
|---|---|
| `immediate` | Emergencia: actúa ahora |
| `review_required` | Actúa ahora y vigila |
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

Los dos ejemplos son anteriores al envío de informes: hoy `transmission` vale `draft` y la respuesta incluye además `report.id`, `report.readings`, `assessed_at`, `readings_snapshot` y `assessment`.

Petición: `{"astronaut_id": "ana", "message": "Siento presión en el pecho desde hace un rato y sudor frío"}`. Respuesta real del servicio (fichas v2.0.0, Ollama y ChromaDB caídos; los textos dependen de las fichas y pueden cambiar):

```json
{
  "reply": "Posible emergencia cardíaca: pide ayuda ahora; no esperes a ver si los síntomas desaparecen.\n\nDolor, presión o molestia torácica nueva o inexplicada. Si el patrón es preocupante (presión, dolor intenso, persistente o que reaparece, o acompañado de falta de aire, sudor frío o mareo), el síndrome coronario agudo es una causa prioritaria que requiere descarte; eso no significa que sea la causa más probable. Soporte informativo únicamente: no es un diagnóstico ni una decisión de tratamiento. No hay personal clínico a bordo: los pasos son primeros auxilios y vigilancia; el tratamiento depende de los procedimientos de la misión.",
  "workflow": "medical",
  "needs_clarification": false,
  "sources": [
    {
      "id": "chest_pain@2.0.0#cdc_heart_attack",
      "title": "CDC: About Heart Attack and Symptoms",
      "section": "Síntomas de infarto",
      "url": "https://www.cdc.gov/heart-disease/about/heart-attack.html",
      "kind": "protocol"
    },
    {
      "id": "chest_pain@2.0.0#medlineplus_chest_pain",
      "title": "MedlinePlus: Chest Pain",
      "section": "Resumen",
      "url": "https://medlineplus.gov/chestpain.html",
      "kind": "protocol"
    }
  ],
  "data_notices": [
    "Alarma inmediata: la decisión usa solo fichas locales, sin esperar a las guías ni al modelo local. Las lecturas solo se añaden como evidencia y nunca rebajan la alarma.",
    "Sin lectura de pulso.",
    "Sin lectura de SpO₂."
  ],
  "disclaimer": "Soporte informativo únicamente. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado.",
  "urgency": "immediate",
  "action": "Posible emergencia cardíaca: pide ayuda ahora; no esperes a ver si los síntomas desaparecen.",
  "notify": [
    "tripulación",
    "control de misión (si hay enlace)"
  ],
  "steps": [
    {
      "text": "Pide ayuda de emergencia ahora con el medio de la misión (alarma de la nave, tripulación, control de misión si hay enlace). No esperes a ver si mejora.",
      "who": "self",
      "source_ids": [
        "chest_pain@2.0.0#cdc_heart_attack"
      ]
    },
    {
      "text": "Tripulante formado en RCP o desfibrilador: prepáralo y úsalo si hace falta hasta que haya más ayuda.",
      "who": "crew",
      "source_ids": [
        "chest_pain@2.0.0#cdc_heart_attack"
      ]
    }
  ],
  "mission_procedures": [
    {
      "title": "Procedimiento de dolor torácico de la misión",
      "loaded": false
    }
  ],
  "missing_guidance": [
    "Las fuentes de la ficha no indican medicación para el dolor torácico: depende del procedimiento de la misión."
  ],
  "report": {
    "text": "INFORME DE CASO MÉDICO (generado a bordo; soporte informativo, no es un diagnóstico)\nGenerado: 2026-11-15T01:46:47Z\nAstronauta: ana · Reporta: la propia persona\nEstado de envío: not_sent (pendiente). El asistente no transmite nada: cópialo y envíalo por el canal de la misión cuando haya enlace.\n\nUrgencia (reglas): immediate\nAcción recomendada: Posible emergencia cardíaca: pide ayuda ahora; no esperes a ver si los síntomas desaparecen.\nProcedimiento de la misión: Procedimiento de dolor torácico de la misión (NO cargado en el asistente)\n\nSíntomas reportados:\n- Dolor o presión torácica: presente (actual); inicio: desconocido; intensidad: desconocida; evolución: persistente. Origen: texto \"presion en el pecho\".\n- Sudor frío: presente (actual); inicio: desconocido; intensidad: desconocida; evolución: persistente. Origen: texto \"sudor frio\".\n\nLecturas pertinentes:\n- SpO₂: sin lectura (valor desconocido).\n- Pulso: sin lectura (valor desconocido).\n\nInformación que falta:\n- Inicio de dolor o presión torácica: desconocido.\n- Intensidad de dolor o presión torácica: desconocida.\n- Inicio de sudor frío: desconocido.\n- Intensidad de sudor frío: desconocida.\n- Sin lectura de pulso.\n- Sin lectura de SpO₂.\n- Las fuentes de la ficha no indican medicación para el dolor torácico: depende del procedimiento de la misión.\n\nReglas aplicadas: chest_pain.concerning_pattern (chest_pain@2.0.0)",
    "transmission": "not_sent"
  },
  "protocol_id": "chest_pain",
  "additional_protocol_ids": [],
  "matched_rules": [
    {
      "rule_id": "chest_pain.concerning_pattern",
      "protocol_id": "chest_pain",
      "protocol_version": "2.0.0",
      "urgency": "immediate"
    }
  ],
  "findings": [
    {
      "kind": "symptom",
      "detail": "Dolor o presión torácica; persistente (\"presion en el pecho\")",
      "source": "report"
    },
    {
      "kind": "symptom",
      "detail": "Sudor frío; persistente (\"sudor frio\")",
      "source": "report"
    },
    {
      "kind": "data_gap",
      "detail": "Sin lectura de SpO₂.",
      "source": "sqlite:spo2"
    },
    {
      "kind": "data_gap",
      "detail": "Sin lectura de Pulso.",
      "source": "sqlite:heart_rate"
    }
  ],
  "possible_causes": [
    {
      "id": "acs",
      "label": "Síndrome coronario agudo (requiere descarte)",
      "status": "rule_out",
      "evidence_for": [
        "Dolor o presión torácica",
        "Sudor frío"
      ],
      "missing_data": [],
      "source_ids": [
        "cdc_heart_attack",
        "medlineplus_chest_pain"
      ]
    }
  ],
  "clarifying_question": null,
  "clarification": null
}
```

## Ejemplo: aclaración

Petición: `{"astronaut_id": "ana", "message": "Me duele la cabeza"}`. Respuesta real del servicio (fichas v2.0.0, Ollama y ChromaDB caídos), sin lecturas registradas para `ana`. La ficha neurológica no usa lecturas, así que no hay avisos de sensores:

```json
{
  "reply": "Dolor de cabeza sin inicio ni intensidad conocidos: comprueba si hay señales de alarma neurológica.\n\nAlteración súbita del habla, asimetría facial, debilidad de un lado, pérdida súbita de visión o dolor de cabeza súbito e intenso pueden indicar un evento neurológico agudo. Ictus o AIT requieren descarte ante señales focales, aunque ya hayan cedido. Un dolor de cabeza sin esas señales se valora por su propio contexto o por la ruta de cabina. Soporte informativo únicamente: no es un diagnóstico ni una decisión de tratamiento. No hay personal clínico a bordo: los pasos son primeros auxilios y vigilancia; el tratamiento depende de los procedimientos de la misión.\n\n¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
  "workflow": "medical",
  "needs_clarification": true,
  "sources": [
    {
      "id": "neurologic_red_flags@2.0.0#cdc_stroke_signs",
      "title": "CDC: Signs and Symptoms of Stroke",
      "section": "Señales de ictus",
      "url": "https://www.cdc.gov/stroke/signs-symptoms/",
      "kind": "protocol"
    },
    {
      "id": "neurologic_red_flags@2.0.0#medlineplus_headache",
      "title": "MedlinePlus: Headache",
      "section": "Resumen",
      "url": "https://medlineplus.gov/headache.html",
      "kind": "protocol"
    }
  ],
  "data_notices": [],
  "disclaimer": "Soporte informativo únicamente. El diagnóstico y las decisiones de tratamiento corresponden a personal cualificado.",
  "urgency": "undetermined",
  "action": "Dolor de cabeza sin inicio ni intensidad conocidos: comprueba si hay señales de alarma neurológica.",
  "notify": [
    "control de misión (si hay enlace)"
  ],
  "steps": [
    {
      "text": "Comprueba: ¿empezó de repente y es muy intenso? ¿cuesta hablar, ves mal, se cae un lado de la cara o pierdes fuerza en un lado? Si es así, trátalo como emergencia.",
      "who": "self",
      "source_ids": [
        "neurologic_red_flags@2.0.0#cdc_stroke_signs"
      ]
    }
  ],
  "mission_procedures": [],
  "missing_guidance": [],
  "report": {
    "text": "INFORME DE CASO MÉDICO (generado a bordo; soporte informativo, no es un diagnóstico)\nGenerado: 2026-11-15T01:46:47Z\nAstronauta: ana · Reporta: la propia persona\nEstado de envío: not_sent (pendiente). El asistente no transmite nada: cópialo y envíalo por el canal de la misión cuando haya enlace.\n\nUrgencia (reglas): undetermined\nAcción recomendada: Dolor de cabeza sin inicio ni intensidad conocidos: comprueba si hay señales de alarma neurológica.\n\nSíntomas reportados:\n- Dolor de cabeza: presente (actual); inicio: desconocido; intensidad: desconocida; evolución: desconocida. Origen: texto \"me duele la cabeza\".\n\nLecturas pertinentes:\n- SpO₂: sin lectura (valor desconocido).\n- Pulso: sin lectura (valor desconocido).\n\nInformación que falta:\n- Inicio de dolor de cabeza: desconocido.\n- Intensidad de dolor de cabeza: desconocida.\n\nReglas aplicadas: neurologic_red_flags.headache_check (neurologic_red_flags@2.0.0)",
    "transmission": "not_sent"
  },
  "protocol_id": "neurologic_red_flags",
  "additional_protocol_ids": [],
  "matched_rules": [
    {
      "rule_id": "neurologic_red_flags.headache_check",
      "protocol_id": "neurologic_red_flags",
      "protocol_version": "2.0.0",
      "urgency": "undetermined"
    }
  ],
  "findings": [
    {
      "kind": "symptom",
      "detail": "Dolor de cabeza (\"me duele la cabeza\")",
      "source": "report"
    }
  ],
  "possible_causes": [],
  "clarifying_question": "¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
  "clarification": {
    "question_id": "neurologic_red_flags.headache_red_flags",
    "question": "¿El dolor de cabeza empezó de repente y es muy intenso, o se acompaña de alteración del habla, cara caída, debilidad de un lado o pérdida de visión?",
    "astronaut_id": "ana",
    "observations": [
      {
        "symptom": "headache",
        "status": "present",
        "origin": "text",
        "evidence": "me duele la cabeza",
        "temporality": "current",
        "subject": "self",
        "onset": null,
        "severity": null,
        "persistence": null,
        "context": null
      }
    ]
  }
}
```
