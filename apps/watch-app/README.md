# watch-app

App local de Apple Watch (watchOS 10+, SwiftUI). Sustituye a ARCHeR, el actígrafo de muñeca de NASA (Artemis II), que no tiene API pública ni datos en vivo. El reloj lee lo que ya mide `onboard-api`.

- **Lecturas**: `GET /astronauts/{id}/status` cada 5 s. Valor, hora y antigüedad, con el estado del servidor (`SIN DATOS`, `OBSOLETO`, `ALERTA`). Sin conexión conserva los últimos datos.
- **SOS**: mantener el botón 2 s (o la acción de VoiceOver "Enviar SOS"). Envía `POST /assistant/messages {"message":"SOS"}` y reintenta cada 5 s hasta 200. Un SOS pendiente sobrevive a reiniciar la app.
- **Alerta de otros relojes**: consulta `GET /incidents?status=open` cada 5 s. Un incidente nuevo de otro astronauta vibra y muestra un aviso rojo.
- **Ajustes**: URL de `onboard-api` y astronauta.

No se publica en la App Store. Se instala desde Xcode con un Apple ID personal.

## Instalar en un reloj real

1. Xcode → Settings → Accounts: añade tu Apple ID.
2. Abre `apps/watch-app/WatchApp.xcodeproj`. Target `WatchApp` → Signing & Capabilities: Team = tu Personal Team, y cambia el Bundle Identifier (`com.example.spaceapps.watch`) por uno único, por ejemplo `com.<tu-nombre>.spaceapps.watch`.
3. Activa el Modo desarrollador en el iPhone (Ajustes → Privacidad y seguridad → Modo desarrollador) y en el reloj (Ajustes → Privacidad y seguridad → Modo desarrollador). Ambos se reinician.
4. Mac, iPhone y reloj en la misma Wi-Fi.
5. En el Mac, arranca el servicio escuchando en la red y el simulador de sensores:

   ```sh
   cd services/onboard-api && uv run fastapi dev --host 0.0.0.0
   python3 firmware/simulator.py   # desde la raíz del repo, en otra terminal
   ```

6. En Xcode elige el reloj como destino y pulsa Run.
7. En el reloj, escribe `http://<IP del Mac>:8000`, pulsa "Cargar astronautas" y elige uno. La primera vez watchOS pide permiso de red local: acéptalo.

## Límites

- La firma con un Apple ID gratuito caduca a los 7 días: vuelve a pulsar Run para reinstalar.
- Las alertas en otros relojes solo llegan con la app abierta. Un push real necesitaría APNs y un servicio en la nube.
- HTTP sin cifrar, permitido solo en la red local (`NSAllowsLocalNetworking`).

## Comprobaciones

```sh
cd apps/watch-app
swiftc WatchApp/Api.swift Checks/main.swift -o /tmp/watch-checks && /tmp/watch-checks
xcodebuild -project WatchApp.xcodeproj -target WatchApp -sdk watchsimulator build
```

En el simulador se pueden fijar los ajustes sin teclear:

```sh
xcrun simctl spawn <dispositivo> defaults write com.example.spaceapps.watch baseURL http://127.0.0.1:8000
xcrun simctl spawn <dispositivo> defaults write com.example.spaceapps.watch astronautID ast-01
```
