# Preguntas frecuentes de los jueces

Este documento responde las preguntas que esperamos de los jueces sobre el módulo de bienestar. Cada respuesta dice lo que el sistema hace hoy y, cuando el diseño va más allá, qué está implementado y qué no. Describe `main` al 2026-11-15. Si este documento y el código no coinciden, manda el código.

### ¿Cómo saben que detecta estrés?

No decimos que detecte estrés, ni ningún estado clínico. Detecta **cambios sostenidos respecto al normal de cada persona**: por ejemplo, que su HRV baje, su tensión reportada suba y su ceño fruncido aumente durante 3 días o más. Lo que sí está verificado:

- La historia de la demo (una persona estable, una que necesita apoyo desde el día 14, una con discrepancia y una con un solo día malo que no alerta) se cumple en las 20 semillas del test y con la semilla 7 de la demo.
- Tres bitácoras reales de reposo, mandadas como la de hoy, no generaron alerta (z más alto: 1.07).
- Un ceño fruncido actuado llega al tope de la escala (z = 5).

No hay validación clínica: todos los umbrales son provisionales ([fusion.md](fusion.md)).

### Las expresiones faciales no son fiables. ¿Por qué usarlas?

Estamos de acuerdo en que son una señal débil. Por eso:

- La visión es una fuente entre cuatro. Una sola fuente nunca pasa de `attention`; `needs_support` exige al menos dos fuentes distintas.
- No leemos emociones. Sólo medimos fatiga (ojos cerrados, apertura de ojos, bostezos, cabeceos) y una señal de tensión: el ceño, como cambio respecto al **neutral del día de esa misma persona**.
- Los labios apretados se miden pero no puntúan, porque hablar los confundía y sólo hay una sesión de referencia ([decisions.md](decisions.md#4-los-labios-apretados-quedan-fuera-de-la-fusión)).

### ¿Funciona en microgravedad?

No lo sabemos: no tenemos datos de microgravedad. El diseño ayuda en dos cosas. La línea base se forma con los primeros días de cada persona en la misión, así que no depende de cómo era en tierra. Y en visión, el ancla del neutral sigue cambios lentos de la cara (como la cara hinchada en microgravedad) pero no un mal día. Validarlo es un siguiente paso ([limitations-and-next-steps.md](limitations-and-next-steps.md)).

### ¿Esto no es vigilancia?

El diseño parte de privacidad y consentimiento:

- **Todo se procesa a bordo.** No hay llamadas a la nube.
- **No se guarda video.** El proceso de visión sólo manda números derivados; `wellbeing.db` no tiene imágenes ni plantillas faciales.
- **La bitácora es un acto deliberado:** el astronauta se sienta ~60 s frente a la cámara. Las cámaras de ambiente (una por módulo) sólo mandan números: tiempo acompañado, distancia y movimiento relativo al cuerpo. Las zonas sin cámara (dormitorio, higiene) son parte del diseño.
- **Cada quien ve lo suyo.** La tripulación sólo ve el semáforo y la tendencia; el detalle está detrás del PIN de cada persona.
- **Nada sale de la nave sin consentimiento.** La telemetría nunca lleva datos de bienestar, y un paquete al psicólogo en Tierra exige la confirmación del astronauta.

Lo que todavía no está: la API no tiene autenticación (la separación la hace la consola) y el consentimiento a ser monitoreado no se registra en la API.

### ¿Y si alguien miente en el checklist?

Para eso está la **discrepancia**: el checklist dice que todo está bien, pero otras fuentes (visión, fisiología, co-presencia) muestran un cambio sostenido. En la demo, ast-03 contesta "estoy bien" y su sueño, su HRV y su tiempo con la tripulación caen desde el día 15: sale `needs_support` con discrepancia. La nota no acusa: dice que, por sí sola, no significa nada y que es una invitación a revisarse.

Además, el diseño busca que no haga falta mentir: como la tripulación sólo ve el semáforo, nadie ve las respuestas de otro.

### ¿Las alertas no generan estigma o ansiedad?

Varias decisiones van en esa dirección:

- **Lenguaje de apoyo**, nunca clínico. Un test revisa que las notas no usen palabras como "disorder", "depress", "anxiety" o "patient".
- **Sólo cambios sostenidos.** Un mal día nunca alerta (ast-04 en la demo).
- La vista Crew sugiere **gestos pequeños** ("Share a meal or ask how their week is going") y dice "No need to mention this screen".
- La pestaña de bienestar **nunca levanta una alarma** en la consola.

No lo hemos probado con astronautas.

### ¿No lo apagarían los astronautas?

Es un riesgo real y no lo hemos probado. Lo que lo reduce: cada persona ve su propio detalle, decide qué se envía a Tierra y puede retirar su consentimiento; el checklist dura unos 45 s; no se graba video. Si alguien deja de mandar datos, el sistema no lo castiga ni lo señala como alterado: pasa a `stale` ("No recent data") cuando su último dato tiene más de 2 días.

### ¿Qué pasa con el retraso de comunicación con Tierra?

Todo el módulo corre a bordo y no necesita enlace. El envío al psicólogo en Tierra es asíncrono: el paquete queda en cola a bordo (`queued`). Hoy se queda ahí por diseño, porque la telemetría nunca transporta bienestar; el canal dedicado y consentido es el siguiente paso ([decisions.md](decisions.md#3-los-paquetes-a-tierra-se-quedan-en-cola-a-bordo)).

### ¿Y si alguien llega ya mal a la misión?

Es una limitación. La línea base son los primeros días con dato de cada persona, así que si ya llega alterada, ese es su "normal", y el sistema sólo verá cambios a partir de ahí. El sistema detecta cambios, no estados absolutos. Existe el parámetro `adaptation_days` para saltarse días iniciales, pero vale 0. Los valores absolutos del checklist siguen visibles para la persona y se pueden compartir, con su consentimiento, con el psicólogo.

### ¿Por qué no usar sólo cuestionarios?

La psicóloga que consultamos dijo que el checklist diario corto es lo más esencial, y es el centro del sistema. Pero los cuestionarios estandarizados son largos, y alguien puede contestar "bien" cuando no lo está. Por eso: un checklist corto (7 preguntas, unos 45 s) más fuentes pasivas, que siguen aportando si alguien no contesta un día y que permiten la discrepancia. Según la misma psicóloga, más datos le sirven más al psicólogo.

### Los datos son simulados. ¿Qué es real?

Lo decimos abiertamente. En la demo, el historial de 21 días es **simulado** y lo marcan la API (`simulated`) y la consola (SIMULATED). La bitácora de hoy de ast-01 es **real** (LIVE), y ese día sale como `mixed`. Los rangos simulados de reposo vienen de bitácoras reales de una persona; los de los días alterados son supuestos ([calibration.md](calibration.md)). El código de la fusión es el mismo para datos reales y simulados.

### ¿Y el sesgo del reconocimiento facial?

El reconocimiento facial (SFace) sólo confirma quién es quién: el astronauta se registra con `enroll`, y las plantillas se quedan en el equipo de visión, nunca se envían. Si la coincidencia no es clara, la bitácora sale como `manual`, y una cara sin coincidencia en el modo ambiente queda como `unknown-<track>`, que nunca tiene evaluación. En el diseño, en una nave real la identidad principal vendría de un wearable (proximidad), que **no está implementado**. Las métricas se miden contra el neutral de la misma persona, no contra un promedio de caras. Aun así, no hemos medido si la detección de la cara funciona igual de bien en personas distintas: sólo calibramos con una.
