# Dexter Campo — contrato de versión candidata

Qué está terminado, qué todavía no existe, y qué no se puede romper.

Este documento no describe el futuro. Describe **lo que hoy se puede prometer**
a una empresa que use la aplicación mañana, y lo que hay que revisar antes de
tocar cada cosa. Si algo de acá deja de ser cierto, se actualiza acá primero y
después se cambia el código.

Medido el 23/09/2026 contra `feat/campo-diseno-stitch`.

| | |
|---|---|
| Versión de la aplicación | `1.0.0+1` |
| Versión de la base local | 14 |
| Esquema de formulario soportado | 1 (una orden que pida más se bloquea) |
| Migraciones de `campo` en el backend | 6 |
| Pruebas | 546, verdes con la bandera de demostración apagada y encendida |
| Archivos de prueba | 46 |

---

## 1. Lo que está terminado

Terminado quiere decir: tiene dominio, tiene interfaz, tiene pruebas, y el
recorrido completo está cubierto por un escenario dorado.

### Jornada y órdenes

- Inicio decide **un** próximo trabajo con un criterio explícito: empezado →
  en camino → vence antes → prioridad. La hora prometida le gana a la
  prioridad de la oficina.
- Un trabajo terminado y sin subir cuenta como hecho. Una devuelta para
  corregir sigue siendo trabajo del día.
- El detalle muestra lo que la orden trae: cliente, acceso, plan, ticket de
  origen, franja prometida, requisitos de seguridad, caja de distribución y
  serial del equipo. Lo que la orden no trae, no se dibuja.

### Ejecución

- El formulario se arma con la plantilla del tipo de trabajo. Un solo lugar
  interpreta ese esquema (`CampoDelFormulario`) y de él dependen el dibujo, el
  checklist y la validación de cierre.
- Se entienden los dos vocabularios: el del servidor (`id`, `reglas.required`,
  `reglas.options`) y el viejo (`clave`, `obligatorio`, `opciones`), porque
  hay órdenes ya guardadas en teléfonos con el segundo.
- Lo que se escribe se guarda al instante, sin botón de guardar.
- El botón de finalizar pregunta al **mismo** veredicto que muestra el
  checklist. No hay dos opiniones sobre si una orden se puede cerrar.

### Materiales y jornada

- El saldo se calcula, nunca se guarda: lo del servidor más lo que sigue en la
  cola. Un consumo aceptado pasa al kit al confirmarse, así que el número no
  rebota al sincronizar.
- Los movimientos son append-only: nunca se editan.
- Un descuadre y un conflicto de identidad son problemas distintos, se ven
  distintos y dicen caminos distintos.
- El cierre de jornada distingue **tomar** el cierre de **tener** la jornada
  cerrada. Lo segundo lo dice el servidor cuando congela el acta.

### Trabajo sin señal

- Todo se registra sin red y se ve reflejado en el acto.
- La idempotencia está en dos niveles: `Idempotency-Key` en el envío y la
  clave del hecho en la restricción de la base.
- Un fallo de envío no descarta nada. Un reintento no duplica.
- Se puede cerrar la jornada con cosas sin subir: esperar señal para poder
  irse a casa no es una opción.

### Seguridad de los datos locales

- Todo lo guardado cuelga de `(org_id, profile_id)`, incluidas las rutas de
  los archivos de evidencia.
- Cerrar sesión con trabajo sin subir **pregunta** antes de borrar, y ofrece
  conservarlo aislado por identidad.
- El tráfico en claro está apagado por variante de compilación.

---

## 2. Lo que todavía no existe

Nada de esto se dibuja en producción. Los identificadores `CAMPO-DATA-XXX`
llevan al fixture y al lugar donde iría; el inventario completo está en
[`campo_datos_pendientes.md`](campo_datos_pendientes.md). Son **51**.

| Falta | Qué haría falta |
|---|---|
| Telemetría óptica (RX, CTO, puerto PON) | El puente con SmartOLT |
| Vehículo y preoperacional | Un módulo que hoy no está |
| Academia | Un módulo que hoy no está |
| Turno y cuadrilla | `jornada.turno` en el backend de Campo |
| Estado de jornada marcable sin señal | Su propia cola de cambios |
| Hora del último envío bueno | La cola no la guarda |
| Escáner de códigos y medidor Bluetooth | Integración con el hardware |
| Mapa y ruta | Decidir la dependencia |

Dos secciones —Academia y Más— **se quitaron de la barra de navegación**. Un
destino que lleva a "en construcción" es una promesa que no se cumple.

---

## 3. Lo que no se puede romper

Cada punto tiene una prueba que falla si alguien lo rompe. La prueba es la
frontera real; esta lista dice **por qué** existe.

### El esquema del formulario se lee en un solo lugar

`campo_del_formulario.dart`. Nadie más toca `reglas`, `options`, `opciones` ni
`required`.

Esto apareció **cinco veces** con síntomas distintos: el formulario pintaba el
asterisco rojo y el checklist no exigía el campo; un campo de selección salía
sin opciones para elegir; el botón de finalizar cerraba órdenes con los
obligatorios vacíos. Ninguna lectura estaba mal escrita. El problema era que
existieran varias.

→ `test/arquitectura_esquema_test.dart`

### El núcleo no conoce la demostración

`lib/core/` no puede alcanzar `lib/demo/`, ni directamente ni a través de otro
archivo. Un dato de ejemplo dentro de un widget compartido viaja a toda
pantalla que lo use, y quien la escribe no se entera.

→ `test/arquitectura_demo_test.dart`

### Fuera del modo demostración no se dibuja un solo valor de ejemplo

Se mide en las **dos** compilaciones, afirmando lo contrario en cada una. Una
guarda que sólo corre apagada no prueba nada: si el bloque no se dibujaba por
otro motivo, la prueba pasa sin haber mirado.

→ `test/guarda_demo_test.dart`

### Dos estados distintos no se dibujan igual

Se comparan las capturas byte a byte dentro de cada pantalla. Así se encontró
que Materiales no mostraba los movimientos esperando señal: alguien podía
registrar consumo sin red toda la mañana y la pantalla se veía idéntica a
tenerlo todo enviado.

→ `test/matriz_de_estados_test.dart`

### Tomar el cierre no es tener la jornada cerrada

Confundirlos hace que alguien se vaya a su casa creyendo que entregó.

→ `test/cierre_jornada_app_test.dart`, `test/e2e_jornada_completa_test.dart`

### El servidor se elige desde el teléfono, y lo elegido manda

El campo existía desde el principio, pero sólo en depuración y —lo que
importa— **sin efecto**: `ApiEndpoints` arma rutas absolutas sobre una
variable que arrancaba con el valor de compilación y no la tocaba nadie, así
que una ruta absoluta le ganaba al `baseUrl` del pedido. La URL se guardaba
prolijamente y los pedidos seguían saliendo al servidor de siempre.

Eso se veía como un "error de conexión" sin causa visible: un APK compilado
sin `--dart-define=BACKEND_URL` apunta a `127.0.0.1`, que dentro del teléfono
es el teléfono mismo, y no había forma de corregirlo desde el aparato.

La guarda no afirma que el campo exista: afirma que cambiarlo cambia a dónde
sale el pedido. Y con esto vienen dos obligaciones que la prueba también
sostiene: el destino se ve **siempre**, aunque el campo esté plegado —nadie
escribe una contraseña sin saber a dónde va— y una dirección a medias se
rechaza en vez de recortarse, porque recortarla en silencio produce un
dominio que parece bueno y no resuelve.

→ `test/servidor_configurable_test.dart`

### Una evidencia dice cuándo se capturó

No sólo cuándo llegó. El backend espera `capturada_en_cliente` desde el
principio y la aplicación no la mandaba nunca: la columna existía del otro
lado y quedaba vacía en todas las filas.

Una foto sin hora prueba que *alguien subió una foto*. Con hora prueba que se
tomó antes de subirla — que es lo que se discute cuando alguien la revisa
meses después. El caso que le da sentido es el día sin señal: la foto se toma
en un sótano y sube al día siguiente; si la hora se calculara al subir, la
evidencia diría que el técnico estuvo ahí un día después.

La guarda no afirma que el campo exista: afirma que el valor que llega a la
fila es el que se pidió, y que encolar y capturar son dos hechos distintos.

→ `test/hora_de_captura_test.dart`

### Y dónde — pero la ubicación nunca cuesta una evidencia

Las fotos llevan coordenadas, precisión y equipo (`metadatos_captura`). Lo que
esta guarda protege no es que el GPS funcione —eso lo prueba el teléfono— sino
que **una evidencia nunca se pierda ni se demore porque el GPS no fije**.

El trabajo de campo ocurre en sótanos y cajas de distribución, que es justo
donde no hay señal: "no se pudo ubicar" no es el borde raro, es la mitad de los
días. Plazo de 5 segundos, todo dentro de un `try`, y si falla se guarda la
foto igual con el motivo escrito.

Por eso se distinguen tres cosas que un campo vacío confundía: **nulo** = no se
intentó · **`ubicacion_motivo`** = se intentó y no se pudo · **coordenadas** =
se supo.

→ `test/ubicacion_de_captura_test.dart`

### Nada cruza entre personas ni entre empresas

Toda escritura lleva la identidad en el `WHERE`. Una consulta sin ella no es
un descuido: es material de otra persona en el kit propio.

→ `test/isolation_cross_tenant_test.dart`, `test/ciclo_de_vida_local_test.dart`

---

## 4. Escenarios dorados

Corren en la suite normal, **sin etiqueta**. Uno que haya que acordarse de
invocar deja de correr en tres semanas.

| | Qué cubre |
|---|---|
| **E2E-001** | La jornada completa con consumo, de abrir la aplicación al acta |
| **E2E-002** | Un trabajo que no gasta material: no puede quedar trabado por eso |
| **E2E-003** | Un día sin señal y la vuelta: nada se duplica, nada se pierde |
| **E2E-004** | Conflicto de material: descuadre e identidad son cosas distintas |

Montan las pantallas **sin inyectarles nada**, como las construye la
aplicación: leen su identidad por el canal del almacenamiento seguro y sus
datos de la base real.

### Cómo se escribe uno nuevo

Bajo una prueba de widget todo corre con un reloj falso, y eso tiene tres
consecuencias que no son evidentes:

1. `pumpAndSettle` espera cuadros, no futuros. Una pantalla esperando a SQLite
   no tiene cuadros pendientes: tiene un futuro que necesita tiempo real. Se
   resuelve con `runAsync`.
2. El `setUp` de un `testWidgets` **también** corre bajo ese reloj. Un `await`
   a la base ahí cuelga la prueba antes de dibujar nada. La preparación va
   adentro del caso, envuelta en `runAsync`.
3. Las animaciones son lo contrario: avanzan con el reloj falso y no con
   tiempo real. Abrir una hoja modal necesita `pump` con duración.

Por eso hay tres ayudantes separados en `test/apoyo/sesion_en_el_telefono.dart`
—`montarConBaseReal`, `esperarLaBase`, `esperarLaAnimacion`— en vez de uno que
haga las tres cosas y se cuelgue la mitad de las veces.

---

## 5. Lo que falta antes de entregar

No son funciones. Son verificaciones que no se pueden hacer con pruebas.

- [x] **Compilar el APK de release e instalarlo limpio.** Hecho el
      23/09/2026 sobre el emulador (`x86_64`, instalación limpia tras
      `uninstall`): la pantalla de ingreso dibuja bien, el servidor elegido
      sobrevive a reinstalar, y el servidor real contesta *"Correo o
      contraseña incorrectos"* a credenciales falsas — o sea que el camino
      llega. Falta hacerlo en un teléfono de verdad (`arm64`, 19.2 MB).
      Ya hubo dos errores que sólo aparecen en el artefacto final: un
      comentario XML con `--` que rompía `mergeReleaseResources`, y
      configuración declarada en el repo que producción no tenía.
- [ ] **Entrar con una cuenta real** y bajar una jornada de verdad.
- [ ] **Recorrer el día completo en un teléfono**, sin red parte del tiempo.
- [ ] **Reinstalar sobre una versión anterior** para ejercitar las migraciones
      de la base local con datos ya guardados.
- [ ] **Medir el arranque y el scroll** con una jornada de veinte órdenes.

---

## 6. Deuda anotada

Cosas sabidas, no urgentes, que conviene no redescubrir:

- El **esquema de evidencias** no tiene modelo normalizado. Se lee en cuatro
  archivos, declarados a mano en la guarda. Tiene el mismo riesgo que tuvo el
  de campos y va a terminar igual si crece.
- `TrabajoScreen` y `MaterialesScreen` no reciben el estado de la cola: la
  señal se ve en la franja del armazón. Es una decisión, no un hueco.
- El proyecto de diseño vigente es **`Dexter Campo App`** (Field Operations
  Precision Engine, Inter). Hay otro con nombre casi igual que **no** es el
  implementado.
- Trece constantes de `lib/demo/` quedaron sin uso al limpiar Inicio. Se
  conservan como inventario de lo que falta construir.
