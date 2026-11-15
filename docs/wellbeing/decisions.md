# Decisiones de diseño del módulo de bienestar

Este documento reúne las decisiones de diseño del módulo de bienestar, en formato corto (Contexto / Decisión / Consecuencias). Cada una lleva su fecha y su fuente: PR, commit o archivo. Describe `main` al 2026-11-15. Si este documento y el código no coinciden, manda el código.

Las fechas son las de los commits (hora local del equipo). Los PR se fusionaron entre el 2026-11-14 y el 2026-11-15.

| # | Decisión | Estado | Fecha |
|---|---|---|---|
| 1 | [Línea base personal en vez de un estándar](#1-línea-base-personal-en-vez-de-un-estándar) | Aceptada | 2026-11-14 |
| 2 | [Base de datos propia (`wellbeing.db`)](#2-base-de-datos-propia-wellbeingdb) | Aceptada | 2026-11-14 |
| 3 | [Los paquetes a Tierra se quedan en cola a bordo](#3-los-paquetes-a-tierra-se-quedan-en-cola-a-bordo) | Aceptada | 2026-11-15 |
| 4 | [Los labios apretados quedan fuera de la fusión](#4-los-labios-apretados-quedan-fuera-de-la-fusión) | Aceptada | 2026-11-14, confirmada 2026-11-15 |
| 5 | [Zona horaria de misión](#5-zona-horaria-de-misión) | Aceptada | 2026-11-14 |
| 6 | [Textos para el usuario en inglés](#6-textos-para-el-usuario-en-inglés) | Aceptada | 2026-11-14 |
| 7 | [Historial simulado y datos en vivo, separados por valor](#7-historial-simulado-y-datos-en-vivo-separados-por-valor) | Aceptada | 2026-11-14 |
| 8 | [Identidad por rostro y wearable](#8-identidad-por-rostro-y-wearable) | Parcial: ver estado | 2026-11-14 |
| 9 | [Rangos calibrados con una sola persona](#9-rangos-calibrados-con-una-sola-persona) | Aceptada, provisional | 2026-11-15 |

## 1. Línea base personal en vez de un estándar

**Contexto.** No hay un estándar universal de emociones. Una psicóloga consultada por el equipo nos dijo que el proyecto es viable, pero que no se pueden analizar emociones "de la nada": hace falta el comportamiento normal de cada persona y, desde ahí, detectar alteraciones. Lo más esencial es un checklist diario corto del propio astronauta, para saber cuándo empezó una alteración. Los cuestionarios estandarizados son largos; con el tiempo, los psicólogos aprenden qué preguntas clave hacer. Más datos ayudan al psicólogo.

**Decisión.** Cada componente se compara con la propia línea base de la persona (mediana y MAD de sus primeros días), no con rangos de población. Se combinan cuatro fuentes y se avisa sólo ante cambios sostenidos. El checklist es corto (7 preguntas, unos 45 s), escrito por el equipo e inspirado en escalas breves, sin copiar ningún cuestionario estandarizado.

**Consecuencias.**
- Positivas: funciona sin un estándar que no existe; responde a "¿desde cuándo?" (`onset_date`); una persona con un normal distinto no queda marcada por ser distinta.
- Negativas: hacen falta al menos 5 días con dato antes de comparar (`baseline_pending`); si alguien empieza ya alterado, su línea base lo refleja ([judges-faq.md](judges-faq.md#y-si-alguien-llega-ya-mal-a-la-misión)).
- El checklist diario no es una herramienta clínica validada ([`checkin_form.py`](../../services/onboard-api/src/onboard_api/wellbeing/checkin_form.py)).

**Fuente:** consulta del equipo con una psicóloga; contrato en el PR #12 (commit `89ab0cd`); [`engine.py`](../../services/onboard-api/src/onboard_api/wellbeing/engine.py).

## 2. Base de datos propia (`wellbeing.db`)

**Contexto.** `onboard.db` es de la parte física (Rubén): astronautas, sensores, lecturas, incidentes. Su esquema y el arranque de la app son de otro equipo ("The onboard app's lifespan is not ours to change", [`database.py`](../../services/onboard-api/src/onboard_api/wellbeing/database.py)). El publicador de telemetría a Tierra lee `onboard.db`.

**Decisión.** Bienestar guarda sus datos en un archivo aparte, `wellbeing.db`, con sus propias migraciones en `db/migrations/wellbeing/` y el mismo runner que onboard. `onboard.db` se abre sólo en lectura (`mode=ro`), siempre a través de `AstronautRepository` y `ReadingRepository`. No se cambia el arranque de la app: las migraciones corren en la primera conexión.

**Consecuencias.**
- Positivas: el publicador de telemetría ni siquiera ve los datos de bienestar; los datos de Rubén nunca se escriben desde bienestar; se pueden respaldar o borrar por separado (`demo_reset.py` vacía sólo `wellbeing.db`).
- Negativas: no hay llaves foráneas entre archivos, así que la API comprueba que el astronauta exista (`404`). Si `onboard.db` no existe, las rutas de bienestar responden `503`.

**Fuente:** PR #12 (commits `b64626e`, `449e47e`, `d1b7cd7`); [`database.py`](../../services/onboard-api/src/onboard_api/wellbeing/database.py).

## 3. Los paquetes a Tierra se quedan en cola a bordo

**Contexto.** El envío al psicólogo en Tierra debe ser manual, nunca automático, y siempre con el consentimiento del astronauta. Lo puede iniciar el propio astronauta, el capitán o un psicólogo al final de la misión. La comunicación con Tierra tiene retraso, así que es asíncrona. `ground-api` no tiene dónde recibir paquetes, y el contrato de telemetría v1 sólo admite lecturas e incidentes.

**Decisión** (decisión final del equipo, 2026-11-15). Un paquete sólo se crea con `consent.astronaut_confirmed: true` (si no, `422`) y queda en estado `queued` a bordo **por diseño**. La telemetría de la nave nunca transporta datos de bienestar. El siguiente paso es un canal dedicado y consentido.

**Consecuencias.**
- Es privacidad por diseño: ningún dato de bienestar sale de la nave por el canal de telemetría.
- El astronauta puede ver exactamente qué se enviaría (`GET …/content`; los comentarios privados sólo van si los incluye) y retirar su consentimiento mientras está en cola (`withdrawn`; el contenido deja de estar accesible, `409`).
- El estado `sent` existe en el esquema, pero hoy nada lo asigna.
- La API no verifica quién es el capitán ni el psicólogo (no hay usuarios), y no hay concepto de fin de misión.

**Fuente:** PR #12 (commit `ffcf123`), PR #41 y PR #34 (commits `cb80b2b`, `4ae9c16`); [`0002_ground_packages.sql`](../../db/migrations/wellbeing/0002_ground_packages.sql); [telemetría](../../contracts/telemetry/README.md).

## 4. Los labios apretados quedan fuera de la fusión

**Contexto.** Visión mide `lip_press_delta` y `lip_press_peak_1s`. Con la primera versión, sólo hablar daba picos de 0.41–0.49, más que apretar los labios a propósito. Con el filtro de habla, los labios separan bien (reposo ~0, apretados 0.164 / 0.466), pero sólo hay **una** sesión de labios apretados (L2). El ceño es la señal de tensión validada.

**Decisión.** Los labios se aceptan (también como `null`) y se guardan, pero **no puntúan**. No son componentes de `stress`.

**Consecuencias.**
- Hablar o apretar los labios nunca dispara estrés.
- Si se agregaran como dos componentes más de `stress`, cerca de 0 en reposo, **diluirían al ceño**: la misma mueca breve de ceño da `attention` sin los labios y `ok` con ellos (test `test_lip_press_stays_out_of_stress`).
- Para revisarlo hacen falta más bitácoras de labios apretados y una combinación que no promedie al ceño hacia abajo.

**Fuente:** PR #12 (commit `7359e74`), PR #57 (commit `e258b6d`); comentario en `COMPONENTS` de [`engine.py`](../../services/onboard-api/src/onboard_api/wellbeing/engine.py).

## 5. Zona horaria de misión

**Contexto.** Los días se agrupaban en UTC. En la demo en Mexicali (`America/Tijuana`), los datos de después de las 16:00 locales caían en el día siguiente, y un checklist de "hoy" podía salir como futuro.

**Decisión.** `WELLBEING_MISSION_TZ` (nombre IANA, por defecto `UTC`, como la Estación Espacial) define el día de misión de todo el módulo. Los timestamps se siguen guardando en UTC; los días se calculan al consultar.

**Consecuencias.**
- Cambiar la zona reagrupa los datos sin migrar, salvo `checkins.day`, que se guarda tal cual.
- La zona es una sola para todo el módulo, no por astronauta.
- Los scripts leen la zona de la API (`GET /wellbeing/parameters`) y `demo_reset.py --tz` se detiene si no coincide.
- En Docker sigue siendo `UTC` hasta que entre el PR #82 (**Pendiente**).

**Fuente:** PR #32 (commit `f39e5bb`); [`settings.py`](../../services/onboard-api/src/onboard_api/wellbeing/settings.py); [`test_wellbeing_mission_tz.py`](../../services/onboard-api/tests/test_wellbeing_mission_tz.py).

## 6. Textos para el usuario en inglés

**Contexto.** La consola está en inglés (#16). El backend devolvía las notas en español.

**Decisión.** `support_notes`, `data_notices`, `basis` y las preguntas del checklist salen en inglés, con el mismo tono de apoyo. La documentación del módulo sigue en español.

**Consecuencias.** Un test vigila que las notas sean ASCII y nunca usen términos clínicos en ninguno de los 6 niveles (`test_user_texts_are_english_and_never_clinical`).

**Fuente:** PR #32 (commit `bf1497a`).

## 7. Historial simulado y datos en vivo, separados por valor

**Contexto.** Una demo de un día no puede mostrar cambios sostenidos de semanas. Hace falta historial, y hay que decir con honestidad qué es real y qué no.

**Decisión.** El historial de 21 días es **simulado** y lo dice: todo lleva `source: "simulated"` (o `demo`, o `simulated:*`). El origen se calcula por valor (`live`, `simulated`, `mixed`) en componentes, indicadores, días y evaluación. Las bitácoras simuladas llegan hasta ayer, para que la bitácora en vivo de hoy se compare sola contra una línea base ya formada.

**Consecuencias.**
- Una bitácora en vivo sobre un día simulado sale `live` en sus componentes y el día `mixed`, nunca entero como simulado.
- La consola muestra "history is SIMULATED; today's video log is LIVE".
- Volver a correr el simulador reemplaza las filas simuladas y conserva las reales.

**Fuente:** PR #12 (commit `189aa0e`); [`simulator.py`](../../services/onboard-api/src/onboard_api/wellbeing/simulator.py).

## 8. Identidad por rostro y wearable

**Contexto.** Para asignar cada dato a la persona correcta hace falta identidad. En el diseño del equipo, el rostro identifica cuando se ve la cara, pero en una nave real la identidad principal vendría de un wearable (proximidad).

**Decisión.** El contrato tiene `identity.method` con tres valores: `face`, `wearable`, `manual`, más `match_score`. Las personas no identificadas se mandan como `unknown-<track>`: se guardan y no se rechazan.

**Estado en `main`.**
- `manual`: **Implementado**. La bitácora real lo usa (el astronauta se indica con `--astronaut`).
- `face`: sólo como valor del contrato y en bitácoras simuladas. El reconocimiento facial está **Pendiente** del PR #33.
- `wearable`: sólo como valor del contrato y en las ventanas ambiente simuladas. La identidad por proximidad de un wearable **no está implementada**.

**Fuente:** contrato en el PR #12 (commit `f66f403`); `IdentityMethod` en [`schemas.py`](../../services/onboard-api/src/onboard_api/wellbeing/schemas.py); [`bitacora.py`](../../services/wellbeing-vision/src/wellbeing_vision/bitacora.py).

## 9. Rangos calibrados con una sola persona

**Contexto.** El simulador y los pisos de escala de visión necesitan rangos realistas. Sólo hubo tiempo de grabar bitácoras de un integrante del equipo.

**Decisión.** Los rangos de reposo de visión se calibran con bitácoras reales de una persona (versión corregida de visión, 60 s a ~50 cm). Lo que no se midió se marca como supuesto. Todo es PROVISIONAL.

**Consecuencias.**
- Los rangos pueden no valer para otras caras, cámaras o distancias.
- Recalibrar es barato: ver [calibration.md](calibration.md#cómo-recalibrar).
- Con las bitácoras reales de reposo R1–R3 como la de hoy de ast-01, no hubo alerta (z adverso más alto: PERCLOS 1.07).

**Fuente:** PR #57 (commit `6988af3`), antes PR #12 (commit `f7219f6`); [calibration.md](calibration.md).
