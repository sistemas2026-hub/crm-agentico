# Objetivo · El técnico ve en el teléfono la marca de agua que va a llevar su foto

> Abierto el 13/11/2026. Estado: **construido, sin desplegar** (rama
> `campo/marca-en-la-camara`, worktree `C:/tmp/dexter-marca-camara`).

## Qué significa terminado

Después de tomar la foto de una evidencia, el técnico ve **en la app** la foto con
la banda de su empresa, igual a la que el servidor le estampa al subirla, aunque
esté sin señal.

## El pedido

El 13/11/2026, el usuario. La marca de agua de las fotos de campo (`fd65d551`,
desplegada) se dibuja solo en el servidor, y la copia que queda en el teléfono sale
sin marca. Se le preguntó si quería ver la marca en el teléfono al tomar la foto
(trabajo de la app + APK) o solo prenderla en el servidor: *«sí, hazlo así»*. Y
pidió poder emularlo para ver cómo va quedando.

## La decisión: el servidor sigue siendo el único que estampa

La app **dibuja encima** de la foto con la misma configuración; no toca el archivo.

- Si la app también estampara, la foto saldría con **dos bandas**.
- Si el servidor aceptara «ya viene marcada», el teléfono tendría la forma de
  **apagar la marca que lo certifica**: es el mismo agujero que la revisión de PII
  cerró con el mime (H3).
- La configuración baja del servidor y se guarda por empresa
  (`<documentos>/marca_de_agua/<org_id>/`), así que la vista previa no depende de
  la cobertura.

**Lo que no se puede:** la cámara es la del sistema (`image_picker`), y su pantalla
de confirmación (✓ / ✗) no admite dibujar encima. La banda aparece en cuanto la
foto vuelve a la app: en la miniatura del requisito, y en grande al tocarla. Ponerla
sobre el visor en vivo exige reemplazar la cámara del sistema por una propia (plugin
`camera`), y eso es otro objetivo, con su propio riesgo en campo.

## Lo construido

| Lado | Qué |
|---|---|
| Servidor | `GET /api/campo/marca-de-agua/` (cualquier persona de campo): configuración, empresa, nombre del técnico y huella del logo. `GET /api/campo/marca-de-agua/logo/`: el logo de **su** empresa, 404 si no hay |
| Servidor | **Defecto en lo desplegado:** la marca pedía `perfil.nombre_completo`, que no existe, y caía a `str(user)`, que es **el correo** (`common/models.py`). Prendida, cada foto habría salido con el correo del técnico rumbo al ticket del ISP. Ahora es `nombre_para_la_marca()`: el nombre, o nada |
| Servidor | **«A la derecha» no hacía nada:** la pantalla ofrece cuatro esquinas y el dibujo solo miraba arriba/abajo. Ahora el logo y el texto se pasan al borde derecho (`a_la_derecha()`) |
| App | `lib/core/marca/marca_de_agua.dart`: las reglas del servidor en Dart (`lineasDe`, `seEstampa`, `aLaDerecha`, las medidas de `_dibujar`) y `FotoConMarca`, que arma foto y banda en píxeles reales y escala todo junto |
| App | `lib/core/marca/marca_de_agua_local.dart`: lee lo guardado, refresca con red y rebaja el logo solo cuando cambia su huella. Nunca lanza |
| App | La miniatura de cada evidencia en Ejecución muestra la foto **entera** (antes `cover` en 140 px recortaba justo el borde de la banda) con la marca; tocarla la abre a pantalla completa |
| Banco | `lib/vista_previa/marca_de_agua_main.dart`: punto de entrada aparte, sin servidor ni sesión. Toma la foto con la cámara (la del emulador sirve) y deja prender y apagar cada opción. No entra en el APK de los técnicos |

## Cómo se emula

```
emulator -avd mythic_pixel -camera-back virtualscene
cd apps/tecnicos-mobile
flutter run -d emulator-5554 -t lib/vista_previa/marca_de_agua_main.dart
```

## Evidencia (13/11/2026)

| Qué | Resultado |
|---|---|
| `pytest campo/tests/test_marca_de_agua*.py` contra Postgres 17, usuario `NOBYPASSRLS`, alias `db` | **60 passed** (49 de antes + 11 nuevas: el correo, la esquina derecha, las dos rutas de la app, el logo de otra empresa) |
| `flutter test test/marca_de_agua_test.dart` | **25 passed**: los casos de `test_marca_de_agua.py` repetidos en Dart, las medidas número por número, el widget y lo guardado por empresa |
| `flutter analyze` sobre lo nuevo | sin hallazgos (el aviso de `ejecucion_screen.dart:495` ya estaba) |
| Emulador `mythic_pixel`: foto con la cámara virtual → vista previa | banda con logo, empresa, técnico, 15:59 en hora de Bogotá y coordenadas |
| La **misma foto** pasada por `campo/services/marca_de_agua.py` | misma altura de banda, mismo logo, mismas cuatro líneas, en abajo-izquierda y arriba-derecha. Lo que difiere es la letra: DejaVu en el servidor y la de la app en el teléfono |

## El APK 1.0.16 (13/11/2026)

`Desktop\dexter-apk\dexter-campo-1.0.16-marca-de-agua.apk`: **universal**, versionCode
16, `BACKEND_URL=https://agent-api.rapilinksas.co`, instalado por cable con
`adb install -r` en el teléfono de pruebas (vivo V2436). Actualizó encima de la 1.0.15
(la fecha de primera instalación no cambió) y sincronizó: «Todo sincronizado · hoy 17:11».

**Dos trampas que casi cuestan datos de un técnico:**

- **La firma.** Los teléfonos traen la 1.0.15 firmada con la llave de depuración del
  OTRO PC (SHA-256 `441eee5d…`), no con la de este (`c6186f3e…`). Un APK con otra llave
  no actualiza, y la única salida es desinstalar, que borra lo que no se sincronizó. Se
  firmó con `apksigner` usando una copia de ese `debug.keystore`. Antes de instalar en
  un teléfono, comparar la huella de lo instalado (`adb shell pm path` + `apksigner
  verify --print-certs`) con la del APK.
- **El número.** `--split-per-abi` le suma 2000 al versionCode (arm64 = 2016). Si eso se
  instala, el próximo APK universal (17) queda «más viejo» y Android lo rechaza. Se
  compila universal, como el otro PC.

## Lo que falta

1. **Desplegar el servidor** (push) y **construir e instalar el APK** en los
   teléfonos: sin el APK nuevo, los técnicos no ven nada distinto, aunque la marca
   del servidor funciona igual.
2. **Prender la marca** en `/supervisor-noc/programacion` y subir el logo en
   `/settings/organization`, como ya estaba pendiente.
3. Las fotos del **reporte de seguimiento** (`_tomarFotoDelReporte`) no se muestran
   en ninguna miniatura, así que no tienen vista previa. Se marcan igual en el
   servidor.
4. **Riesgo latente, no nuevo:** si el almacenamiento pasa a S3/R2 con subida
   directa, los bytes ya no pasan por el servidor y la foto sale sin marca. El
   teléfono mostraría una banda que el archivo no lleva.

## Restricciones

- **NO push** sin pedido explícito: push a `fix/integracion-wisphub` es deploy.
- El servidor es el único que escribe la marca en el archivo.
