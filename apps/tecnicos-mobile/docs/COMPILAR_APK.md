# Compilar y entregar la app de campo

Este documento es **la acción completa** para sacar una versión nueva de la
app. Quien lo ejecuta —una persona o una sesión de IA en la máquina de
compilar— no necesita más contexto que este archivo.

Se compila **la versión que dice `pubspec.yaml`**. El número no se elige al
compilar: se sube en el commit que hace falta publicar (ver §6).

---

## 1. Antes de empezar

| Qué | Cómo comprobarlo |
|---|---|
| Flutter **3.47.x**, Android SDK 37, NDK 28.2.13676358 | `flutter --version` y `flutter doctor` |
| La llave de firma de siempre — **ver «Dónde está la llave» acá abajo** | No se comprueba mirando el archivo: se comprueba en el paso 4 |
| El código al día | `git fetch origin` y `git status` sobre `fix/integracion-wisphub` |
| Unos 5 GB libres en disco y 4 GB de memoria libres | El 21/11/2026 la otra máquina se quedó con 0 MB de disco a mitad de las pruebas y tumbó Docker |

**Qué versión de Flutter.** La 1.0.18 se compiló con la 3.47.8 y las 1.0.16,
1.0.17 y 1.0.19 con la 3.47.2, en otra máquina, sin errores. Vale cualquiera
de la línea 3.47; otra línea no está probada.

### Dónde está la llave

**No dar por buena la de `~/.android/debug.keystore`: depende de la máquina.**
Flutter crea una llave nueva en esa ruta en cada instalación, así que el
archivo siempre existe y casi nunca es el correcto.

| Máquina | Dónde está la llave buena | Qué pasa con `~/.android/debug.keystore` |
|---|---|---|
| La de Docker (la primera) | En el volumen `dexter-adb-keys`, montado en `/root/.android` | Dentro del contenedor es la buena |
| La segunda (compiló la 1.0.16, 1.0.17 y 1.0.19) | Un archivo aparte que se le llevó a mano; el 21/11/2026 estaba en `Descargas\debug.keystore` | **Es otra llave** (su firma empieza `1FF3D3FA…`): con ella Android pediría desinstalar |
| La tercera (la PC con el entorno local; compiló la 1.0.20 el 26/11/2026) | `C:\Users\Usuario\.android\debug.keystore`, copiada a mano antes de compilar | Es la buena: se comprobó con `keytool` antes de compilar (SHA-1 `6E:D4:B6:00…79:CF`). Ojo: si no está cuando se compila, Gradle crea ahí una llave NUEVA y la compilación sale con otra firma |

En la segunda máquina hay que firmar con el archivo que se le llevó, no con
el que Flutter usa por omisión. *Cómo se le indicó esa llave a la
compilación no quedó escrito en el reporte del 21/11/2026: quien compile ahí
la próxima vez, que lo anote en este párrafo.*

La única prueba de que se usó la llave correcta es la del paso 4. Una llave
se reconoce por la firma que produce, no por dónde está guardada.

**Cómo se le dice a la compilación qué llave usar (la tercera máquina, 26/11/2026).**
La compilación de `release` firma con la llave de depuración, y Gradle la busca
en `%USERPROFILE%\.android\debug.keystore`. Basta con poner ahí el archivo
correcto ANTES de compilar por primera vez, y comprobarlo:

```
keytool -list -v -keystore %USERPROFILE%\.android\debug.keystore -storepass android
```

**Instalar el Android SDK sin Android Studio cambió.** Desde las
`commandlinetools` 16111833, `sdkmanager` está deprecado y delega en la
«Android CLI», que con varios paquetes juntos instaló solo el primero. Lo que
funcionó, sin mandar métricas a Google:

```
android --no-metrics --sdk=<ruta del SDK> sdk install platforms/android-37.0 build-tools/37.0.0 ndk/28.2.13676358
```

La plataforma 37 se llama ahora `android-37.0`, y **el AGP 9.1 del proyecto
busca `android-37`**: la compilación falla con «Failed to find target with
hash string 'android-37'». Las máquinas anteriores la instalaron cuando todavía
tenía ese nombre. En la tercera se resolvió SIN tocar el proyecto: una copia de
`platforms/android-37.0` llamada `platforms/android-37`, con `path` y
`api-level` cambiados a `37` en su `package.xml` y `ApiLevel=37` en
`source.properties` (el `android.jar` es el mismo byte a byte). Cambiar
`compileSdk` en el repo arreglaría esta máquina y rompería las otras. Apagar también la telemetría de
Flutter y Dart antes de cualquier otro comando: `flutter --disable-analytics` y
`dart --disable-analytics`.

`android/gradle.properties` le pide 8 GB a Gradle. En una máquina con menos,
**no editar ese archivo**: escribir `org.gradle.jvmargs=-Xmx1536m` en el
`gradle.properties` de la carpeta `.gradle` del usuario, que gana sobre el del
proyecto.

---

## 2. Traer el código y correr las pruebas

```
git fetch origin
git checkout fix/integracion-wisphub
git pull --ff-only
cd apps/tecnicos-mobile
flutter pub get
flutter test
```

**Hay una prueba que ya falla sola, de forma intermitente: `e2e_002`.** Medido
el 14/11/2026: sin ningún cambio falló 3 de 3; con cambios, 1 de 3. Si es la
única en rojo, se vuelve a correr y se sigue. Cualquier otra en rojo **frena
la compilación**: se reporta con su salida y no se entrega nada.

`flutter pub get` reescribe los archivos generados de `linux/`, `macos/` y
`windows/` cambiándoles solo los finales de línea. **No se commitean.** Para
dejarlos como estaban:

```
git checkout -- linux macos windows
```

---

## 3. Compilar

```
flutter build apk --release --dart-define=BACKEND_URL=https://agent-api.rapilinksas.co
```

Tarda entre 5 y 9 minutos según la máquina. Sale en
`build/app/outputs/flutter-apk/app-release.apk`, de unos 75 MB.

**`--dart-define=BACKEND_URL` no es opcional.** Sin él la app apunta a
`127.0.0.1`, que dentro del teléfono es el teléfono mismo. En una
actualización no se nota —el servidor elegido queda guardado en el aparato—,
pero una instalación limpia quedaría sin servidor. La dirección es la del
despliegue; está en `DESPLIEGUE.md`.

Si la compilación se hace con Docker (así se hacía en la máquina anterior):

```
docker run --rm -v "<ruta>/apps/tecnicos-mobile:/app" -w /app \
  -v "dexter-adb-keys:/root/.android" \
  -v "campo_gradle_home:/root/.gradle" \
  -v "campo_build:/app/build" \
  dexter/flutter-apk:3.47.8 \
  flutter build apk --release --dart-define=BACKEND_URL=https://agent-api.rapilinksas.co
```

Ojo con esa variante: `build/` es un **volumen**, así que el archivo recién
compilado **no** está en la carpeta `build/` del disco. El 14/11/2026 casi se
entrega el APK del día anterior por mirar ahí. Se copia desde el volumen.

---

## 4. Comprobar la firma — obligatorio, antes de instalar en ningún lado

```
apksigner verify --print-certs build/app/outputs/flutter-apk/app-release.apk
```

(`apksigner` está en `build-tools/37.0.0` del Android SDK.)

La línea `certificate SHA-1 digest` tiene que decir **exactamente**:

```
6ed4b600a44b4d17f2adbbc5ea6d640887a579cf
```

Es la firma de todas las versiones que están en los teléfonos (verificada al
compilar la 1.0.18, el 14/11/2026).

**Si dice otra cosa, se frena acá y no se instala.** Android no deja
actualizar una app firmada con otra llave: pide desinstalar, y desinstalar
**borra lo que el técnico tenga sin sincronizar** —órdenes, fotos y
movimientos de material en cola—. Una firma distinta significa que la máquina
no tiene la llave correcta; se reporta y no se sigue.

Por qué la llave es una `debug.keystore`: `android/app/build.gradle.kts` firma
la compilación de `release` con la configuración de depuración. Es deuda
conocida, y es la razón de que la llave viva en la máquina y no en el
repositorio.

---

## 5. Entregar

1. Copiar el archivo con su versión en el nombre: `dexter-campo-<versión>.apk`
   (por ejemplo `dexter-campo-1.0.19.apk`).
2. Instalarlo **encima** de la app que ya está, primero en **un solo
   teléfono**, con todo sincronizado antes. Nunca desinstalar para instalar.
3. Si Android dice «app no instalada»: el número de versión es menor que el
   instalado, o la firma es otra. Volver al paso 4; no desinstalar.
4. Abrir la app, entrar, y comprobar que la versión que muestra es la nueva.
5. Recién entonces repartirla al resto.

Reportar al terminar: versión compilada, resultado de las pruebas, la línea
de la firma, y en qué teléfono se probó.

---

## 6. La regla de la versión

La versión vive en `pubspec.yaml` (`version: 1.0.19+19`) y se sube **en el
commit que hace falta publicar**, nunca al compilar. El número después del
`+` es el que Android compara: tiene que ser **mayor** que el instalado.

Estuvo en `1.0.0+1` mientras en los teléfonos ya andaba la 1.0.13, porque el
número se ponía a mano en cada compilación. Desde el 06/11/2026 la versión
que dice el repositorio es la que corre en la calle.

---

## 7. Qué trae la 1.0.19 y qué hay que medir con ella

**Qué trae.** Al elegir una imagen de la galería, la app lee de dónde salió y
de cuándo es —su tamaño, si el nombre del archivo dice «captura», la fecha
del nombre, y la fecha y la cámara que trae adentro— y lo manda con la
evidencia. El servidor ya lo sabe leer (desplegado el 21/11/2026, `5168edf4`):
en la revisión del cierre sale un renglón al lado de cada imagen de galería.
Decisión y motivos: `PRD.md` §8.30.

**Estado al 21/11/2026:** compilada y firmada (`…a579cf`, 1453 pruebas en
verde, ninguna en rojo), **sin instalar en ningún teléfono todavía**.

**Qué hay que medir, porque no se pudo medir sin un teléfono.** En el
teléfono de prueba, con una orden de prueba (cliente MARIO SABANAGRANDE,
servicio 5832 — no usar clientes reales):

1. Hacer una captura de pantalla en ese teléfono y adjuntarla como evidencia
   desde la galería.
2. Mandar el reporte y abrir la orden en Programación, en «Por revisar».
3. Al lado de esa imagen tiene que decir **«Captura de pantalla de este
   teléfono · del <día y hora>, el mismo día en que se adjuntó»**.

Si en cambio dice **«No es una captura de este teléfono ni una foto de su
cámara»**, el renglón trae dos medidas (*la imagen mide A×B y la pantalla
C×D*): esas dos medidas son el dato que hace falta. Significa que el tamaño
que la app lee de la pantalla no coincide con el de sus capturas en ese
modelo, y se corrige en `lib/features/ejecucion/origen_de_la_imagen.dart` y
`campo/origen_de_la_imagen.py`.

Si dice **«el archivo no dice de cuándo es»**, el nombre con que ese teléfono
guarda sus capturas no trae la fecha en una forma conocida. No es un error
que frene nada —no levanta una duda—, pero conviene anotar la marca y el
modelo del teléfono.

Lo que **no** cambia con esta versión: una imagen de galería nunca devuelve
la orden sola por su origen o su fecha. Queda para que la mire una persona.
