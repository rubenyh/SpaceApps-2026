# Runbook de la demo de bienestar

Demo en Mexicali, zona de misión `America/Tijuana`. Todo en PowerShell, desde la raíz del repo `SpaceApps-2026`.

> **Estado de la consola:** la pestaña de bienestar (Cedric) todavía no está en `main`. Mientras no exista, el camino principal son los comandos de respaldo de cada paso (o `http://127.0.0.1:8000/docs`). Cuando la pestaña exista, cada paso dice qué mostrar ahí.

Lo que se ve en vivo es real (la bitácora de hoy de ast-01); el historial de 21 días es **simulado**, y se dice abiertamente.

> **¿Nativo o Docker?** Esta guía levanta la API de forma nativa, porque así corre con la zona de Mexicali. Si el equipo levanta todo con Docker (`.\run.ps1`, ver [`RUN-REPO.md`](RUN-REPO.md)), no abras la Terminal 1: el puerto 8000 ya es del contenedor. En ese caso sigue [Con Docker](#con-docker-runps1) al final de la sección 1.

## 1. Preparación (en este orden)

En **cada** terminal nueva:

```powershell
$env:UV_LINK_MODE = "copy"   # el repo está en OneDrive: evita errores de hardlink en uv
$env:PYTHONUTF8 = "1"
```

**Terminal 1: API** (déjala abierta todo el tiempo)

```powershell
cd services\onboard-api
uv sync --locked
$env:WELLBEING_MISSION_TZ = "America/Tijuana"
$env:ONBOARD_TELEMETRY_ENABLED = "false"   # sin ground-api en el 8001; quítala si también levantas ground
uv run fastapi dev
```

Espera a que diga `Uvicorn running on http://127.0.0.1:8000`. Bienestar nunca usa la telemetría, así que apagarla no cambia nada de esta demo y evita avisos repetidos de "telemetry send failed" en la terminal.

**Terminal 2: datos de la demo** (misma carpeta que la API, para que use el mismo `wellbeing.db`)

```powershell
cd services\onboard-api
uv run python scripts/demo_reset.py --tz America/Tijuana
```

Respalda `data\wellbeing.db` en `data\backups\`. Carga el historial SIMULADO (semilla 7) y el export de ejemplo del Watch para ast-01, y termina con esta tabla, que debe salir así:

```
ast-01     ok               -           no            -
ast-02     needs_support    <día 14>    no            checkin, vision, physiology, social
ast-03     needs_support    <día 15>    sí            vision, physiology, social
ast-04     ok               -           no            -
```

El export del Watch ya va incluido. Sólo si quieres importar un export **real** de la app Salud:

```powershell
uv run python scripts/import_apple_health.py C:\ruta\export.zip --astronaut ast-01
```

**Terminal 3: visión** (la primera vez descarga ~45 MB de modelos)

```powershell
cd services\wellbeing-vision
uv sync --locked
uv run wellbeing-vision models
```

La bitácora en vivo se graba durante la demo (paso 2.4).

**Registrar a la tripulación** (una vez, antes de la demo, en la Terminal 3)

Las plantillas de cara se quedan en `services\wellbeing-vision\data\faces\` (local, nunca se envían ni se suben a git). Regístralas con la **cámara, la distancia y la luz de la demo**:

- Una sola persona en cuadro, sentada donde va a estar en la demo.
- `--samples 30`, girando la cabeza despacio (izquierda, derecha, arriba, abajo) mientras se llena la barra.
- La cámara del teléfono (cam 1) llega en espejo: lleva `--flip 1` en **todos** los comandos.

```powershell
uv run wellbeing-vision enroll --astronaut ast-01 --camera 1 --flip 1 --samples 30
uv run wellbeing-vision enroll --astronaut ast-02 --camera 1 --flip 1 --samples 30
uv run wellbeing-vision enroll --astronaut ast-03 --camera 0 --samples 30
```

Sin `--append`, registrar **reemplaza** las plantillas de esa persona. Si alguien va a salir en las dos cámaras, regístralo después en la otra con `--append`, que suma plantillas:

```powershell
uv run wellbeing-vision enroll --astronaut ast-01 --camera 0 --samples 30 --append
```

Si la cara nueva coincide con otro astronauta (o, con `--append`, no coincide con las plantillas que ya tiene), pregunta antes de guardar. Contesta `n` y revisa quién está frente a la cámara.

Comprueba cada cámara con `identify` (no envía nada; `q` termina e imprime `Recognized: ...`). Cada quien debe salir con su nombre, no como `unknown-N`. En la prueba del 15 de noviembre salieron 0.85 a 0.95 a 1280x720:

```powershell
uv run wellbeing-vision identify --camera 1 --flip 1
uv run wellbeing-vision identify --camera 0
```

**Terminal 4 (opcional): consola**

```powershell
cd apps\spaceship-app
npm.cmd install
npm.cmd run tauri dev
```

Se usa `npm.cmd` y no `npm`, porque PowerShell bloquea `npm.ps1` con la política de ejecución por defecto.

En cualquier terminal de respaldo:

```powershell
$B = "http://127.0.0.1:8000"
```

### Con Docker (`.\run.ps1`)

Si el stack completo ya corre en Docker, no abras la Terminal 1. `wellbeing.db` vive dentro del contenedor, así que el reset se corre ahí (desde la raíz del repo):

```powershell
docker compose exec onboard-api python scripts/demo_reset.py
```

Limitación: el compose todavía no pasa `WELLBEING_MISSION_TZ`, así que en Docker los días van en UTC, y después de las 16:00 de Mexicali los datos caen al día siguiente. Para usar `America/Tijuana` en Docker falta una línea en `docker-compose.yml`, que hay que coordinar con Rubén. Hasta entonces, para la demo de bienestar conviene el camino nativo. La Terminal 3 (visión) y la sección 2 funcionan igual en los dos casos.

## 2. Guion

### 2.1 Vista de tripulación (semáforo, sin detalle)

Consola: semáforo de los 4. ast-02 y ast-03 en NEEDS SUPPORT, ast-01 y ast-04 en OK, todo marcado SIMULATED.

```powershell
(Invoke-RestMethod "$B/wellbeing/crew").members | Format-Table astronaut_id, display_name, level, trend, latest_origin
```

Mensaje: la tripulación ve sólo el semáforo y la tendencia. El detalle es de cada persona.

### 2.2 ast-02: necesita apoyo desde el día 14

Consola: detalle de ast-02 y línea de tiempo con el inicio marcado.

```powershell
$a = Invoke-RestMethod "$B/astronauts/ast-02/wellbeing"
$a | Format-List level, confidence, onset_date, sustained_days, sustained_sources
$a.support_notes
$a.indicators | Format-Table kind, status, z, deviant_since, latest_origin
(Invoke-RestMethod "$B/astronauts/ast-02/wellbeing/timeline?days=21").days | Format-Table day, level, origin
```

Mensaje: se compara contra su propia línea base. La alerta llega al **tercer** día seguido, no por un día aislado, y `onset_date` dice desde cuándo (lo que pidió la psicóloga). Coinciden 4 fuentes, por eso la confianza es alta. Los 6 indicadores tienen datos. `activation` sale en `attention` desde el día 14: en las cámaras de ambiente se mueve menos y pasa más tiempo quieto (movimiento simulado; aún no hay mediciones reales del modo ambiente).

### 2.3 ast-03: discrepancia

```powershell
$c = Invoke-RestMethod "$B/astronauts/ast-03/wellbeing"
$c | Format-List level, discrepancy, onset_date, sustained_sources
$c.support_notes
```

Mensaje: su checklist dice "estoy bien", pero las señales pasivas (cámara, fisiología, interacción social) caen desde el día 15. Eso se marca, y se plantea como invitación, no como acusación.

### 2.4 ast-01: bitácora EN VIVO

En la **Terminal 3**, frente a la cámara a ~50 cm, con buena luz. Con la cámara del teléfono:

```powershell
uv run wellbeing-vision bitacora --astronaut ast-01 --camera 1 --flip 1 --seconds 60
```

Con la cámara de la laptop, quita `--camera 1 --flip 1`.

Los primeros 3 s son el neutral del día: hay que mirar a la cámara sin hablar. `q` o `Esc` terminan antes.

Consola: métricas de visión de ast-01 marcadas LIVE; el día de hoy, MIXED.

```powershell
$w = Invoke-RestMethod "$B/astronauts/ast-01/wellbeing"
$w | Format-List level, latest_origin, live_days, simulated_days, mixed_days
($w.indicators | Where-Object kind -in "fatigue","stress").components | Where-Object source -eq "vision" | Format-Table component, latest_value, baseline_median, z, latest_origin
```

Mensaje: la bitácora de hoy se compara contra su línea base, con z cerca de 0 en reposo. Si actúas cansancio o tensión (ojos entrecerrados, ceño fruncido), suben PERCLOS y el pico de ceño. Un solo día **no** genera alerta.

### 2.5 Modo ambiente EN VIVO

En la **Terminal 3**, cada cámara es un módulo (cam 0 = `modulo-a`, cam 1 = `modulo-b`):

```powershell
uv run wellbeing-vision ambiente --cameras 0 1 --flip 1 --window 60
```

Déjalo correr al menos un minuto. Cada ventana de 60 s envía, por módulo, quién estuvo y con quién (co-presencia) y una sesión de movimiento por persona (con 10 s o más de pose). `q` termina; una ventana cortada se envía si duró 10 s o más. Si las dos cámaras ven la misma zona, agrega `--overlap`: si no, la misma persona sale en las dos como "seen from …" y aparecen traslados entre módulos.

Consola: actividad y vida social de ast-01 marcadas LIVE.

```powershell
$w = Invoke-RestMethod "$B/astronauts/ast-01/wellbeing"
($w.indicators | Where-Object kind -in "activation","social").components | Format-Table component, latest_value, latest_origin
```

Mensaje: las cámaras de ambiente no guardan video, sólo números: tiempo acompañado, distancia y movimiento. `social.accompanied_minutes` sale LIVE cuando dos astronautas reconocidos comparten módulo.

### 2.6 Envío al psicólogo en Tierra (consentimiento)

```powershell
$today = [System.TimeZoneInfo]::ConvertTimeBySystemTimeZoneId((Get-Date), "Pacific Standard Time").ToString("yyyy-MM-dd")
function Send-Package($who, $consent) {
  $body = @{ astronaut_id = "ast-02"; requested_by = $who; requested_by_name = "Demo"
    consent = @{ astronaut_confirmed = $consent; statement_version = "v1" }
    period_from = ([datetime]$today).AddDays(-20).ToString("yyyy-MM-dd"); period_to = $today
    include = @("assessment", "timeline", "checkins") } | ConvertTo-Json -Depth 3
  Invoke-RestMethod -Method Post "$B/wellbeing/ground-packages" -ContentType "application/json" -Body $body
}
# a) Sin consentimiento: se rechaza (422)
try { Send-Package "captain" $false } catch { "Sin consentimiento -> HTTP " + [int]$_.Exception.Response.StatusCode }
# b) El capitán lo inicia, con consentimiento de ast-02: queda en cola, nunca se envía solo
$p = Send-Package "captain" $true; $p | Format-List requested_by, status, id
# c) Lo que se enviaría (los comentarios privados no van)
$k = Invoke-RestMethod "$B/wellbeing/ground-packages/$($p.id)/content"; "Nivel {0}, inicio {1}" -f $k.assessment.level, $k.assessment.onset_date
# d) ast-02 retira su consentimiento: el contenido deja de estar accesible (409)
(Invoke-RestMethod -Method Post "$B/wellbeing/ground-packages/$($p.id)/withdraw").status
try { Invoke-RestMethod "$B/wellbeing/ground-packages/$($p.id)/content" } catch { "Tras retirar -> HTTP " + [int]$_.Exception.Response.StatusCode }
```

Si el equipo muestra el corte del enlace con Tierra ([`demo-outage.md`](demo-outage.md)), bienestar no se ve afectado: todo funciona a bordo.

Mensaje: **privacidad por diseño.** La telemetría de la nave nunca transporta datos de bienestar. Un paquete sólo sale con el consentimiento explícito del astronauta y por un canal dedicado, distinto de la telemetría, que es el siguiente paso del proyecto. Por eso el paquete se queda en cola a bordo (`queued`). Lo puede iniciar el propio astronauta, el capitán o un psicólogo al final de la misión, siempre con consentimiento, y el astronauta puede retirarlo.

**Frase para la demo:** "Los datos de bienestar nunca viajan en la telemetría de la nave: sólo salen con el consentimiento del astronauta, por un canal dedicado."
(En inglés: "Wellbeing data never rides on ship telemetry: it only leaves with the astronaut's consent, through a dedicated channel.")

## 3. Plan B

**La cámara no abre**
1. Cierra todo lo que use la cámara (Teams, Zoom, navegador) y revisa *Configuración → Privacidad → Cámara*.
2. Prueba otra cámara: `uv run wellbeing-vision bitacora --astronaut ast-01 --camera 1 --seconds 60`.
3. Si no hay cámara, manda la bitácora real de reposo grabada antes (S2) como la de hoy. **Dilo así en la demo:** es una bitácora real grabada antes, no en vivo.

Las métricas de la S2 van incluidas aquí, así que no depende de ningún archivo local:

```powershell
$now = (Get-Date).ToUniversalTime()
$s2 = @{ astronaut_id = "ast-01"; session_type = "bitacora"; module_id = "modulo-a"; source = "vision:replay"
  started_at = $now.AddSeconds(-60).ToString("o"); ended_at = $now.ToString("o"); quality = "good"
  valid_frame_ratio = 0.966; identity = @{ method = "manual"; match_score = $null }; neutral_ok = $true
  fatigue = @{ blink_rate_per_min = 23.2; perclos = 0.122; eye_openness_vs_neutral = 0.925; yawn_count = 0; nod_count = 0 }
  tension = @{ brow_lower_delta = 0.029; lip_press_delta = 0.09; brow_lower_peak_1s = 0.129; lip_press_peak_1s = 0.492 }
  motion = $null; provisional = $true }
Invoke-RestMethod -Method Post "$B/wellbeing/vision-sessions" -ContentType "application/json" -Body ($s2 | ConvertTo-Json -Depth 4)
```

**La API se cae o no responde**
1. Mira la Terminal 1. Ciérrala con `Ctrl+C` y vuelve a levantarla con los mismos comandos (incluida `$env:WELLBEING_MISSION_TZ`).
2. Si el puerto 8000 está ocupado (por ejemplo, porque se cerró la ventana en vez de usar `Ctrl+C`): `Get-NetTCPConnection -State Listen -LocalPort 8000 | Select-Object OwningProcess`, y luego `Stop-Process -Id <pid>`. Si `Stop-Process` dice que no encuentra el proceso, quedó vivo un proceso hijo de `fastapi dev` que conserva el puerto. Ciérralo así y vuelve a levantar la API:

   ```powershell
   $dead = (Get-NetTCPConnection -State Listen -LocalPort 8000).OwningProcess | Select-Object -First 1
   Get-CimInstance Win32_Process -Filter "ParentProcessId=$dead" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
   ```
3. Visión no pierde la bitácora: si la API estaba caída, la guarda en `outbox\pending.jsonl` y la reenvía en el siguiente envío.
4. Comprueba que la zona sea la correcta: `(Invoke-RestMethod "$B/wellbeing/parameters").mission_tz` debe decir `America/Tijuana`.

**`wellbeing.db` corrupta o datos raros**

Lo más rápido es reconstruir. Primero detén la API (`Ctrl+C` en la Terminal 1).

```powershell
cd services\onboard-api
Rename-Item data\wellbeing.db "wellbeing.corrupt-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Remove-Item data\wellbeing.db-wal, data\wellbeing.db-shm -ErrorAction SilentlyContinue
```

Levanta la API de nuevo y corre `uv run python scripts/demo_reset.py --tz America/Tijuana`.

Para recuperar un estado anterior exacto (por ejemplo, con una bitácora en vivo ya grabada), con la API detenida:

```powershell
Get-ChildItem data\backups | Sort-Object LastWriteTime -Descending | Select-Object -First 5 Name, LastWriteTime
Remove-Item data\wellbeing.db-wal, data\wellbeing.db-shm -ErrorAction SilentlyContinue
Copy-Item data\backups\wellbeing-<AAAAMMDD-HHMMSSZ>.db data\wellbeing.db -Force
```

Después levanta la API. `demo_reset.py` hace un respaldo cada vez que corre, así que el más reciente es el estado justo antes del último reset.

## 4. Checklist de 5 minutos antes

- [ ] Terminal 1 con la API arriba y `(Invoke-RestMethod "$B/wellbeing/parameters").mission_tz` = `America/Tijuana` (con Docker sale `UTC`, ver sección 1).
- [ ] `demo_reset.py --tz America/Tijuana` corrido hoy, y su tabla con los 4 casos como en la sección 1.
- [ ] Prueba de cámara sin enviar nada: `uv run wellbeing-vision bitacora --astronaut ast-01 --seconds 10 --dry-run`. Se abre la vista, la cara se detecta y pasa el neutral.
- [ ] Luz frontal, cámara a ~50 cm, fondo tranquilo, notificaciones de Windows apagadas, cargador conectado.
- [ ] Tripulación registrada con la cámara de la demo, e `identify` en cada cámara da el nombre correcto (sección 1).
- [ ] Prueba de ambiente sin enviar nada: `uv run wellbeing-vision ambiente --cameras 0 1 --flip 1 --seconds 30 --dry-run`. Al cerrar debe decir 10 FPS o más por cámara.
- [ ] Consola abierta y conectada a la API (o, si no está la pestaña, esta guía abierta en el paso 2.1).
- [ ] Plan B a mano: hay respaldos en `services\onboard-api\data\backups\` (los crea `demo_reset.py`) y esta guía abierta en la sección 3.
- [ ] Frase lista: "el historial es simulado; la bitácora de hoy es real; el sistema no diagnostica, apoya".
