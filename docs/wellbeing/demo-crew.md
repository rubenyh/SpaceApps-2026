# Tripulación de la demo

> **PERFILES FICTICIOS.** Estas cuatro personas no existen. Sus nombres, roles e historias son inventados para la demo, y todo su historial es **simulado** (la API lo marca `simulated` y la consola, SIMULATED). La única excepción es la bitácora en vivo de hoy, que es real ([runbook](../wellbeing-demo-runbook.md)).

Los datos salen de [`simulator.py`](../../services/onboard-api/src/onboard_api/wellbeing/simulator.py) (21 días, semilla 7 en la demo). Los días se cuentan desde el primero de la historia (día 0); hoy es el día 20.

| Id | Nombre | Rol | Historia | Qué se ve en la vista Crew |
|---|---|---|---|---|
| `ast-01` | Elena Ruiz | Comandante | Estable. Hace la bitácora en vivo. | `ok` |
| `ast-02` | Marco Tanaka | Ingeniero de vuelo | Turnos cambiados por una reparación larga desde el día 14. | `needs_support` desde el día 14 |
| `ast-03` | Sofía Mendel | Médica de a bordo | Contesta "todo bien", pero sus señales caen desde el día 15. | `needs_support` desde el día 15, con discrepancia |
| `ast-04` | Daniel Okafor | Especialista científico | Un solo mal día (día 17), al siguiente normal. | `ok` |

**Dónde están los nombres y los roles:**
- **Nombres:** son el `display_name` de cada astronauta en `onboard-api`. `demo_reset.py` los registra y, si ya existen con otro nombre, los renombra con `PATCH /astronauts/{id}`.
- **Pestañas físicas:** el simulador de sensores (`firmware/simulator.py`) sólo genera a Elena Ruiz. `scripts/seed_demo.py` registra a Elena Ruiz y a Marco Tanaka con los mismos nombres.
- **Roles:** no están en el contrato ni en la API, sólo en este documento y en comentarios del código.

**Comentarios del checklist:** los comentarios de cada perfil son privados. Sólo se ven en la vista personal, en el panel "My check-in notes", detrás del PIN de cada persona. Nunca aparecen en la vista Crew. En un paquete a Tierra sólo van si se marcan a propósito (está desactivado por defecto), y el paquete exige el consentimiento de la persona.

## Elena Ruiz (`ast-01`) · Comandante

- **En los datos:** estable los 21 días. Su historial de visión llega hasta ayer, para que la bitácora en vivo de hoy se compare con una línea base ya formada. También tiene el export de ejemplo del Watch (SIMULADO).
- **Comentario:** uno solo, el día 9: "Good run on the treadmill today."
- **En la demo:** hace la bitácora en vivo. Sus métricas de visión salen LIVE y el día de hoy, MIXED. Si se usa el modo ambiente en vivo, su actividad y su vida social también salen LIVE.
- **Qué decir:** "Elena es la referencia: todo dentro de su rango habitual. Lo que ven ahora es real, medido hace un minuto contra su propia línea base."

## Marco Tanaka (`ast-02`) · Ingeniero de vuelo

- **En los datos:** desde el día 14, el checklist, la fisiología (HRV, frecuencia en reposo, sueño), la co-presencia y la visión se alejan de su línea base. Al tercer día seguido, el cambio es sostenido: `needs_support`, con `onset_date` en el día 14 y 4 fuentes de acuerdo. Su `activation` (movimiento en las cámaras de ambiente) sale en `attention`.
- **Comentarios** (días 14, 15, 17, 19 y 20):
  - "Moved to night shifts for the coolant pump repair."
  - "Short night. Woke up before the alarm."
  - "Another long shift. Ate on my own, too tired to join the others."
  - "Still on the repair schedule. Hard to switch off after a shift."
  - "Tired. Skipped movie night."
- **Qué decir:** "A Marco le cambiaron los turnos por una reparación larga. Duerme menos, se aísla y su ánimo baja. El sistema no alarma el primer día: espera a que el cambio dure tres días y a que varias fuentes coincidan, y dice desde cuándo. Sus propios comentarios explican el contexto, y sólo él los ve."

## Sofía Mendel (`ast-03`) · Médica de a bordo

- **En los datos:** su checklist sigue normal. Desde el día 15 caen su sueño, su HRV y su convivencia, y la visión también cambia. Sale `needs_support` con `discrepancy: true`: el checklist dice que está bien, pero otras fuentes muestran un cambio sostenido.
- **Comentarios** (días 15, 17 y 19), positivos aunque sus señales caigan:
  - "All good. Busy day in the med bay."
  - "Fine, lots to do. No complaints."
  - "All good here."
- **Qué decir:** "Sofía siente que tiene que estar bien por su rol, y en el checklist contesta que todo va bien. El sistema no la contradice ni la diagnostica: le muestra, en privado, que sus señales y su checklist no coinciden, como una invitación a revisarse o a hablar con alguien."

## Daniel Okafor (`ast-04`) · Especialista científico

- **En los datos:** estable, salvo el día 17, en el que bajan su checklist, su bitácora de visión y su movimiento en las cámaras de ambiente. Al día siguiente vuelve a lo normal. Sale `ok`.
- **Comentario:** uno solo, el día 17: "The crystal growth run failed after three weeks of prep. Rough day."
- **Qué decir:** "Daniel tuvo un mal día: un experimento fallido. Todos tenemos días así. El sistema no alarma por un día aislado: sólo cuenta un cambio que dura."

## Verificación

- `test_simulated_crew_tells_the_demo_story` comprueba los 4 casos con 20 semillas.
- `test_checkin_comments_follow_each_story` comprueba los comentarios:
  - Marco no tiene ninguno antes del día 14.
  - Sofía no tiene ninguno antes del día 15.
  - Daniel sólo tiene uno, el día 17.
  - Elena tiene uno o ninguno.
  - Ningún comentario usa lenguaje clínico.
- Los comentarios están fijos por día, así que no cambian los valores simulados: con cada semilla, los datos son los mismos que antes de agregarlos.
