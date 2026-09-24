# Objetivo · Dexter Campo — candidata y pulido

> Abierto el 23/09/2026. Estado: **abierto**, en **Fase 2 · pulido** (24/09/2026).
>
> **Fase 1 · candidata:** Parte A ✅ medida · Parte B 4 de 5. Sus números quedan
> como **línea base**, no como trabajo terminado.
> **Fase 2 · pulido:** decidida el 24/09/2026. Se permiten cambios de
> funcionalidad y de arquitectura — lo que la Fase 1 prohíbía.
> Primera ficha del sistema. Lo que encontró al estrenarse está en "Qué reveló
> esta ficha", al final — no se borra: es lo que hay que arreglar del sistema.

## Qué significa terminado

La aplicación de técnicos tiene un artefacto instalable que una empresa puede
usar mañana, y lo que se le promete está medido, no supuesto.

**Se parte en dos, porque son dos cosas distintas y solo una se puede
automatizar:**

| | Qué | Quién puede cerrarlo |
|---|---|---|
| **A** | La suite verde en la rama correcta, el APK de release compilado, y el contrato commiteado y al día | Una sesión con `/goal` |
| **B** | Las cinco verificaciones de campo del contrato §5 | **Una persona con un teléfono.** Ninguna IA |

`/goal` cierra **A**. **B** es una lista de control que firma una persona.
Escribir un objetivo que prometa cerrar las dos sería exactamente el error que
este repositorio llama *afirmar sobre el mecanismo en vez del efecto*.

## Criterios de aceptación

### Parte A — verificable por comando

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| A1 | El trabajo corre sobre la rama que tiene Campo | `git ls-files apps/tecnicos-mobile/test/ \| wc -l` → **101**, no 6. Salida pegada |
| A2 | La suite pasa entera | `flutter test` en `apps/tecnicos-mobile/` → exit 0 y el conteo pegado (referencia del contrato: **529**) |
| A3 | Pasa en las **dos** compilaciones | la suite verde con la bandera de demostración apagada **y** encendida. Una guarda que solo corre apagada no prueba nada |
| A4 | El APK de release existe | `flutter build apk --release` → exit 0, ruta y tamaño del artefacto pegados |
| A5 | El contrato está en el repositorio y al día | `CAMPO_RELEASE_CONTRACT.md` commiteado; sus cifras coinciden con lo que A2 midió recién, o se corrigen |
| A6 | Nada se coló | `git diff --cached --name-only` solo muestra rutas bajo `apps/tecnicos-mobile/` |

### Parte B — no se cierra con un comando

Del contrato §5. Cada una necesita un teléfono, una cuenta real, o tiempo.

- [x] **Instalar el APK limpio en un teléfono.** ✅ 23/09/2026, reportado por
      el usuario: instaló bien. Artefacto: `app-arm64-v8a-release.apk` (19.2 MB,
      22:46), cuyo `libapp.so` es byte a byte el mismo que el fat verificado
      (`4efb4a1d…`), o sea `cf4684e`. *(Las dos fallas anteriores solo aparecían
      en el artefacto final: un comentario XML con `--` que rompía
      `mergeReleaseResources`, y config declarada en el repo que producción no
      tenía. Ninguna volvió a aparecer.)*
      **Lo que esto NO dice todavía:** que la aplicación abra. Instalar y
      arrancar son dos cosas distintas.
- [x] **Entrar con una cuenta real y bajar una jornada de verdad.** ✅ 23/09/2026,
      reportado por el usuario. Es la casilla que cubre `cf4684e` (*el servidor se
      podía elegir y no cambiaba a dónde iban los pedidos*): sin ese arreglo,
      elegir el servidor correcto no servía de nada.
- [ ] Recorrer el día completo en el teléfono, sin red parte del tiempo.
- [x] **Reinstalar sobre una versión anterior.** ✅ 23/09/2026, reportado por el
      usuario. Ejercita las migraciones de la base local v12 con datos ya
      guardados — el camino por el que una actualización le borra la jornada a
      un técnico.
- [x] **Medir arranque y scroll con una jornada de veinte órdenes.** ✅
      23/09/2026, **medido en emulador** (`sdk_gphone64_x86_64`, Android 15,
      60 Hz), APK de **profile** contra el backend local del compose.

      **Arranque en frío**, nueve corridas con `am force-stop` entre cada una:
      la primera **6.024 ms**, el resto **1327–1666 ms** (media ~1.5 s). Las
      tres primeras dieron 6024, 2324 y 1408: **4× de diferencia**. Una sola
      corrida habría dado cualquiera de las tres como "el dato" — mismo error
      que el ping, que ya está en los contratos congelados.

      **Scroll**, 925 cuadros de ~18 s de scroll manual, vía
      `dumpsys SurfaceFlinger --timestats` (histograma `present2present`):

      | | |
      |---|---|
      | p50 / p90 / p95 / p99 | 17 / 30 / 34 / **48 ms** |
      | ≤ 16 ms (fluido a 60 Hz) | 44,3 % |
      | 17–33 ms (un cuadro perdido) | 48,5 % |
      | `droppedFrames` · `jankyFrames` · `appBufferStuffing` | **0 · 0 · 0** |
      | `averageFPS` | 37,9 |

      **Lo que esto sí prueba:** no hay patología. Cero cuadros descartados,
      cero acumulación de búfer, peor caso 48 ms (~3 refrescos) y ningún
      congelamiento. La lista con 20 órdenes no degrada ni crece con el
      recorrido.

      **Lo que NO prueba:** que en el teléfono de un técnico se vea así. Un
      emulador x86_64 sobre un portátil no alcanza 60 Hz ni con contenido
      trivial, y **no se midió una línea base en el mismo emulador**, así que
      el 44 % fluido no se puede repartir entre techo del emulador y trabajo de
      la app. Para eso hace falta repetirlo en un equipo real.

      Sirve como **referencia contra la cual comparar**: si un cambio futuro
      mueve el p95 de 34 ms hacia arriba en este mismo emulador, eso sí es la
      app.
      **Herramienta lista, sin ejecutar:** `manage.py seed_campo_carga
      --tecnico <correo> --ordenes 20`. Siembra órdenes asignadas a un técnico
      y sabe deshacerlas (`--borrar`). **No crea tipos de trabajo ni esquemas**:
      exige que `seed_campo_demo` ya los haya creado, porque un esquema de
      formulario declarado en dos lugares es el defecto que en esta aplicación
      apareció **cinco veces**.
      Obliga a confirmar el entorno (`--si-la-base-es <nombre>`): imprime base,
      host y usuario, y sin coincidencia exacta no escribe nada. El técnico
      pedido es `mario.vasquez.moreno@rapilinksas.co`, un correo del dominio
      real de la empresa — si esa base es producción, veinte órdenes de prueba
      caen donde trabajan los operadores, y el repositorio lo prohíbe
      (*no crear mocks productivos*). **Decisión del usuario, no de una sesión.**

## Restricciones

Las tres permanentes del repositorio:

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — parte la medición de razonamiento ON/OFF.
- **NO correr los 56 casos dorados** — son del motor, no de Campo.

Las propias de este objetivo, **relajadas el 24/09/2026** al entrar en pulido:

- ~~NO agregar funcionalidad~~ · ~~NO cambiar arquitectura~~ — **levantadas.**
  La Fase 2 existe para eso. Queda escrito que se levantaron a propósito y
  cuándo, no que nunca estuvieron.
- **NO integrar `feat/campo-diseno-stitch` a otra rama** sin decisión explícita:
  sigue siendo una decisión de entrega (ver B1).
- **NO tocar `nucleo/` ni `tenants/`** — ese es el motor, no la app. `django-crm/`
  sí se puede, porque varios módulos de la Fase 2 necesitan backend.

### Lo que NO se relaja, y por qué

Relajar no es quedarse sin límites. **Los seis invariantes del contrato §3
siguen en pie**, cada uno con su prueba, y romperlos no es "pulir":

| Invariante | Su prueba |
|---|---|
| El esquema del formulario se lee en **un solo lugar** (`campo_del_formulario.dart`) | `test/arquitectura_esquema_test.dart` |
| `lib/core/` no alcanza `lib/demo/`, ni directo ni por terceros | `test/arquitectura_demo_test.dart` |
| Fuera del modo demostración no se dibuja un valor de ejemplo (medido en **las dos** compilaciones) | `test/guarda_demo_test.dart` |
| Dos estados distintos no se dibujan igual | `test/matriz_de_estados_test.dart` |
| Tomar el cierre ≠ tener la jornada cerrada | `test/cierre_jornada_app_test.dart` |
| Nada cruza entre personas ni entre empresas: la identidad va en el `WHERE` | `test/isolation_cross_tenant_test.dart` |

El primero apareció **cinco veces** con síntomas distintos —el asterisco rojo
sin validación, el desplegable sin opciones, el botón que cerraba órdenes con
obligatorios vacíos— y ninguna lectura estaba mal escrita: *el problema era que
existieran varias*. Si el pulido necesita cambiar uno de estos seis, eso es una
decisión explícita con su motivo, no un efecto colateral.

## Qué NO hacer

- **No prometer la Parte B como hecha** porque la A esté verde. Sigue en pie:
  instalar, entrar, reinstalar y medir no dicen nada sobre un día sin señal.
- **No dejar un destino que lleve a "en construcción".** Dos secciones —Academia
  y Más— se quitaron de la barra de navegación por esto, y la regla sobrevive al
  pulido: un módulo entra a la navegación **cuando funciona**, no cuando empieza.
  *Un destino que lleva a "en construcción" es una promesa que no se cumple.*
- **No romper un invariante del contrato §3 de pasada.** Si el pulido necesita
  cambiar uno de los seis, se decide y se escribe el motivo. Ver arriba.

*Corregido el 24/09/2026:* esta sección decía «no construir lo que el contrato
§2 declara ausente» y «no normalizar el esquema de evidencias». Las dos eran
restricciones de la Fase 1 y **son exactamente el trabajo de la Fase 2** (2.B y
2.C). Dejarlas habría hecho que la ficha se contradijera a sí misma.

## Fase 2 · Pulido (24/09/2026)

Cuatro frentes, elegidos los cuatro. **Cada uno cierra por separado**: una ficha
con cuatro alcances y sin cierres propios deja de ser un contrato.

### 2.A · Datos y contenido reales

Que la app muestre lo que la empresa usa, no los ejemplos. Catálogos, textos,
tipos de trabajo, protocolos de atención, campos del formulario.

*Criterio de aceptación: **pendiente de definir contigo** — hace falta saber qué
datos son. Sin eso no hay comando ni salida esperada, y un criterio que no se
puede escribir así es un deseo.*

### 2.B · Lo que el contrato §2 declara ausente

Telemetría óptica (RX, CTO, puerto PON) · vehículo y preoperacional · academia ·
turno y cuadrilla · estado de jornada marcable sin señal · hora del último envío
bueno · escáner de códigos y medidor Bluetooth · mapa y ruta.

Son **51** datos inventariados en `campo_datos_pendientes.md`, y **ninguno es
solo interfaz**: cada uno arrastra su integración (el puente con SmartOLT,
`jornada.turno` en el backend, una cola propia de cambios, hardware). Se eligen
de a uno, no en bloque.

*Criterio por módulo: la pantalla lo muestra con dato real, su prueba existe, y
el dato viaja por la cola sin duplicarse.*

### 2.C · Deuda de arquitectura del contrato §6

- **El esquema de evidencias no tiene modelo normalizado.** Se lee en cuatro
  archivos, declarados a mano en la guarda. Tiene **el mismo riesgo que tuvo el
  de campos** — el que apareció cinco veces — y va a terminar igual si crece.
  Es el trabajo de mayor rendimiento de los cuatro frentes.
- `TrabajoScreen` y `MaterialesScreen` no reciben el estado de la cola: la señal
  se ve solo en la franja del armazón. Hoy es una decisión, no un hueco; si el
  pulido la cambia, que sea por un motivo escrito.

*Criterio: el esquema de evidencias se lee en un solo lugar, con su prueba de
arquitectura — la misma forma que ya resolvió el de campos.*

### 2.D · Diseño e interacción

Jerarquía visual, espaciado, estados vacíos, transiciones, legibilidad bajo el
sol. El proyecto de diseño vigente es **`Dexter Campo App`** (Field Operations
Precision Engine, Inter) — hay **otro con nombre casi igual que NO es el
implementado**, y confundirlos es rehacer la pantalla equivocada.

*Criterio: `test/matriz_de_estados_test.dart` sigue verde —dos estados distintos
no se dibujan igual— y las capturas por pantalla se comparan contra las de hoy.*

### 2.E · Prioridad: dos escalas, dos pesos visuales

Decidido con el usuario el 24/09/2026. La tarjeta muestra **dos prioridades
distintas**, no una:

| | Quién la pone | Peso en la tarjeta |
|---|---|---|
| **Prioridad WispHub** | El operador que abrió el ticket, en el sistema del ISP | **Discreto** |
| **Prioridad Dexter** | Calculada por análisis, con sus motivos | **Prominente** |

**La trampa que hay que evitar, y que casi cometo.** Al despachar los cuatro
casos de prueba mapeé la prioridad de WispHub a la de la orden. Si la ranura
prominente mostrara eso, estaría presentando **una copia disfrazada de juicio**:
las dos ranuras dirían lo mismo y la grande afirmaría un análisis que no
ocurrió. Es exactamente contra lo que advierte el comentario del importador en
`nucleo/seguimiento/importacion_io.py`:

> *"La prioridad que le puso el proveedor va COMO TEXTO, no como prioridad del
> caso... Ponerlo a la vista evita que alguien lea ese 'Normal' como un juicio
> de Dexter — hoy no lo es. Cuando Dexter calcule prioridad de verdad, esta
> línea servirá además para comparar los dos criterios."*

Mientras Dexter no calcule, la ranura prominente dice **«sin evaluar»**. En las
cuatro órdenes de hoy.

#### Las escalas

WispHub usa cuatro niveles y los manda como entero:

```
1 Baja   ·   2 Normal   ·   3 Alta   ·   4 Muy Alta
```

La orden tiene tres (`alta`/`media`/`baja`). **Para que el contraste se lea, las
dos escalas tienen que coincidir**, así que falta un cuarto nivel: `muy_alta`.
Es barato — `choices` es validación, no esquema: la columna es
`CharField(max_length=10)` y `"muy_alta"` entra, así que la migración que Django
genera no toca la base.

#### Dónde se calcula

**En el motor, devuelto dentro del `contexto`.** Dos motivos, no uno:

1. Dos de los cuatro criterios viven ahí y en ningún otro lado — el estado de
   cuenta y la incidencia de red compartida los sabe el motor, no Django.
2. El `contexto` ya es *la ficha técnica congelada, con su hora*, que es
   exactamente lo que una prioridad calculada tiene que ser. Sin la hora al
   lado es una afirmación sobre el presente que nadie puede verificar.

**El código calcula, el modelo compone** (PRD §12.5). Esta prioridad la resuelve
Python leyendo señales. **Nunca se le pide al LLM.**

#### Los criterios, y cuáles se pueden hoy

| Criterio | ¿Hoy? | De dónde sale |
|---|---|---|
| **Visita reiterativa** | ✅ | `Case.name` == "Vista Reiterativa Post Soporte". Ya está en los datos reales: 10 de 100 |
| **Antigüedad y reaperturas** | ✅ | `Case.created_at`, `external_status_at` |
| Estado de la cuenta (mora) | ❌ | `contexto.cliente.estado` — necesita el motor corriendo |
| Incidencia de red compartida | ❌ | SmartOLT, vía el motor |

Dos de cuatro se calculan sin levantar nada. Más criterios entran después, o
cuando esté el agente supervisor.

#### Dos reglas que no se negocian

- **La prioridad de Dexter viaja con sus motivos.** Un técnico que lee «Alta» no
  aprende nada; uno que lee *«Alta — tercera visita por lo mismo · cliente
  suspendido»* sabe qué va a encontrar. Sin motivos, la ranura grande es un
  adorno.
- **Los umbrales van a `tenant_config`**, no al código: cuántos días es «viejo»,
  cuánto pesa una reapertura. La próxima empresa va a querer otros números, y
  esa es la regla de §3.3.

#### Deuda que esto destapa

`Case` no guarda la prioridad del proveedor en un campo: vive como texto dentro
de `description` (*"Prioridad en wisphub: Alta."*). Hoy se lee parseando esa
frase, que es **frágil** — depende del formato de un texto que escribe el propio
importador, y si cambia se rompe en silencio. El arreglo correcto es un campo en
el importador (`nucleo/`), y **los 100 casos ya importados no se arreglan
solos**.

---

### Cierre de la Fase 2

Cualquiera sea el frente, al cerrar se **vuelve a correr la Parte A completa**
contra la línea base de la Fase 1:

| | Línea base (23/09/2026) |
|---|---|
| `flutter test`, las dos compilaciones | 536 + |
| APK de release | 53.2 MB |
| Arranque en régimen | 1327–1666 ms (media ~1,5 s) |
| Scroll, p95 | 34 ms · 0 cuadros descartados |

Sin esa comparación no se sabe qué costó el pulido, y ese es el único motivo por
el que la Fase 1 no se cerró como abandonada.

---

## Agentes involucrados

| Agente | Para qué | Estado |
|---|---|---|
| `auditor-independiente` | La pasada adversarial antes de entregar. Es el único agnóstico del stack: sus cinco huecos (mecanismo que nunca corre, prueba que afirma existencia, repo que declara lo que el artefacto no tiene, condición de éxito ruidosa, garantía sobre algo inestable) aplican igual a Flutter | pendiente |
| `arquitecto-dexter` | Solo su pregunta 1 y 3 (¿ya existe? ¿dónde vive?). Su contenido está escrito para el motor | parcial |
| `guardia-de-release` | Su **espíritu** aplica —¿estamos listos para salir?— pero su checklist es ledger, `tenant_config` y variables del motor. No sirve tal cual | **no aplica sin reescribir** |
| `verificador-de-api` · `revisor-de-pii` · `auditor-de-frontera` · `corredor-de-evaluacion` · `guardia-de-config` | **Se saltean.** Ninguno toca este trabajo: no hay API externa nueva, ni listas blancas del motor, ni frontera de autorización, ni casos dorados, ni config de tenant | se saltean |

## Bloqueos

**B1 · El código no está bajo tus pies, y es una decisión, no una tarea.**
Medido el 23/09/2026: 6 archivos de prueba en `integrar-centro-mando` contra
101 en `feat/campo-diseno-stitch`. Hay que elegir:

| Camino | Implica |
|---|---|
| Worktree aparte sobre `feat/campo-diseno-stitch` | Cero riesgo para el Centro de Mando. Dos árboles que mantener |
| Integrar Campo a `integrar-centro-mando` primero | Un solo árbol. Mezcla dos trabajos que hoy avanzan por separado |

Sin resolver esto, A1 no se puede cumplir y el objetivo no arranca.

**B2 · Los archivos sueltos no tienen dueño declarado.** `e2e_002/003/004`,
`test/apoyo/` y `docs/CAMPO_RELEASE_CONTRACT.md` están sin commitear en esta
rama, que no es la de Campo. Hay que decidir si son arrastre de la otra rama o
trabajo nuevo que va a alguna parte. **No se tocan hasta que eso se decida.**

**B3 · La Parte B necesita un teléfono y una cuenta real.** Y "entrar con una
cuenta real" toca producción. Eso lo hace una persona, y conviene decidir
quién y cuándo antes de dar la candidata por lista.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 23/09/2026 | Ficha abierta. Medido dónde vive Campo (B1) y qué falta del contrato §5 | Resolver B1 | — |
| 23/09/2026 | Bloque cerrado. Pasada adversarial sobre el hook: 3 hallazgos, los 3 corregidos y reverificados (10/10) | B1 y el día sin red | — |
| 23/09/2026 | Casilla 5: arranque ~1,5 s y scroll p95 34 ms, medidos en emulador con 20 órdenes | Solo el día sin red | — |
| 23/09/2026 | Casillas 2 y 4 de la Parte B: cuenta real con jornada bajada, y reinstalación sobre versión anterior (reportadas) | Solo el rendimiento con 20 órdenes | — |
| 23/09/2026 | Primera casilla de la Parte B: el APK instala limpio en un teléfono real (reportado) | Que abra, cuenta real, día sin red, reinstalación, rendimiento | — |
| 23/09/2026 | **Parte A cerrada entera** en el worktree `C:/wisphub/_wt_campo`. A1–A6 verdes, medidos. B2 resuelto: los sueltos son copias | Solo la Parte B, que necesita un teléfono | ffa1761 |

---

## Entorno de prueba local

Montado el 23/09/2026 para medir la Parte B. **No toca producción.**

```
worktree   C:/wisphub/_wt_campo   (feat/campo-diseno-stitch)
levantar   OPENAI_API_KEY=no-se-usa docker compose              -f docker-compose.yml -f compose.puerto-8001.yml up -d db redis backend
puente     adb reverse tcp:8000 tcp:8001
app        servidor http://127.0.0.1:8000
           mario.vasquez.moreno@rapilinksas.co / campo12345
```

**El 8001 es el contenedor; el 8000 es el `runserver` nativo de Windows.** Los
dos escuchan en el host y eso ya costó media hora de diagnóstico: el teléfono
le hablaba al nativo, que apunta a otra base, y las credenciales sembradas acá
eran invisibles para él. La prueba que lo cerró fue crear un usuario marcador
en una base y pedirlo por la otra.

⚠️ **A qué base apunta ese proceso nativo está SIN VERIFICAR, y conviene
saberlo.** Arrancó el 22/09/2026 a las 09:17 desde
`C:\wisphub\dexter\django-crmackend\.venv`, o sea el worktree principal,
y en esta máquina **el `.env` de la raíz es el que decide la base**:
DESPLIEGUE.md documenta que con `DBHOST=crm.rapilinksas.co` el CRM se conecta
al Supabase **real** — *"esto no es una copia, es la base de producción"*. No
se comprobó (no se lee el `.env` ni se consulta producción desde una sesión).

**CONFIRMADO el 24/09/2026 por el usuario: `DBHOST=crm.rapilinksas.co`.** Ese
proceso sirve la base de producción.

Consecuencia buena: el teléfono habló con **producción** durante las primeras
casillas de la Parte B, así que «entrar con una cuenta real y bajar una jornada
de verdad» y «reinstalar sobre una versión anterior» valen **más** de lo que
decía su anotación: fueron contra datos reales, no contra un entorno de prueba.

*Corregido el 24/09/2026:* esta nota decía que ese proceso venía corriendo
`migrate --noinput` en cada arranque contra producción. **Es falso.** Ese
`migrate` vive en `docker/backend/entrypoint.sh`, o sea en el arranque del
contenedor; un `manage.py runserver` nativo **no migra** — solo avisa que hay
migraciones sin aplicar. Producción no recibió ningún cambio de esquema por ese
camino, y de hecho sigue con 2 de las 6 migraciones de `campo`.

**Los datos sobreviven a `docker compose down`.** El volumen es
`django-crm_postgres_data`, declarado `external: true`: Compose no lo crea ni
lo borra, tampoco con `down -v`. Es el **mismo** volumen que usa el compose de
`django-crm`, así que las 20 órdenes sembradas aparecen también al levantar el
stack desde la carpeta principal. No es contaminación —base local, datos de
desarrollo— pero conviene no sorprenderse.

Sembrar y deshacer:

```
docker exec wt_campo-backend-1 python manage.py seed_campo_carga     --tecnico mario.vasquez.moreno@rapilinksas.co --ordenes 20 --si-la-base-es crm_db
docker exec wt_campo-backend-1 python manage.py seed_campo_carga     --tecnico mario.vasquez.moreno@rapilinksas.co --si-la-base-es crm_db --borrar
```

**El `adb reverse` no sobrevive** a reiniciar el emulador ni al `adb kill-server`:
si vuelve el *Connection refused*, es eso. Se rearma con una línea.

**Automatizar toques sobre la interfaz ejecuta acciones de verdad.** Unos
barridos con `input swipe` abrieron la OT #1845 y le marcaron *en camino* y
*llegada*. Para medir, scrollear a mano.

---

## Qué reveló esta ficha sobre el propio sistema

Se estrenó y encontró tres cosas. Se dejan escritas acá porque son trabajo
pendiente del sistema de trabajo, no de Campo:

1. **Los agentes no estaban cargados en la sesión.** El comando `/objetivo`
   manda invocar al `orquestador` y no existía como tipo de agente: de los
   nueve, la sesión solo había registrado `verificador-de-api`. Están
   commiteados y en disco. Su plan se aplicó a mano.
2. **Seis de los nueve agentes no sirven para un trabajo de Flutter.** Están
   escritos para el motor. Ya estaba anotado como hueco conocido en CLAUDE.md
   §11.1 (`especialista-mobile`, sin crear); este objetivo lo confirma con un
   caso real, que era la condición para crearlo.
3. **Un objetivo puede tener una mitad que ninguna IA cierra.** La plantilla no
   preveía eso y empujaba a escribir todo como comando + salida. La partición
   A/B de arriba es la respuesta; conviene subirla a `PLANTILLA.md`.

---

## Resultado de la Parte A — medido el 23/09/2026

Ejecutado en el worktree `C:/wisphub/_wt_campo` (`feat/campo-diseno-stitch`),
sin tocar `integrar-centro-mando` ni integrar nada.

| # | Criterio | Resultado |
|---|---|---|
| A1 | La rama tiene Campo | ✅ **101** archivos bajo `test/`, app `1.0.0+1` |
| A2 | La suite pasa | ✅ `flutter test` → **536 +, 1 omitida, All tests passed!** |
| A3 | Pasa en las dos compilaciones | ✅ `flutter test -j 1 --dart-define=DEXTER_DEMO=true` → **536 +, All tests passed!** |
| A4 | El APK de release existe | ✅ `flutter build apk --release` → `build\app\outputs\flutter-apk\app-release.apk`, **53.2 MB**, Gradle 47,5 s |
| A5 | El contrato está al día | ✅ Ya lo estaba **en su rama**: declara 536 pruebas y 43 archivos, exacto contra lo medido |
| A6 | Nada se coló | ✅ El worktree de Campo quedó limpio; el commit de esta ficha solo tocó `SPEC/` |

**B2 queda resuelto, y no como se esperaba.** Los archivos sueltos en el árbol
de `integrar-centro-mando` no son trabajo nuevo: `e2e_002`, `e2e_003` y
`e2e_004` son **idénticos** byte a byte a los ya versionados en
`feat/campo-diseno-stitch`, y `test/apoyo/` también está allá. El único que
difiere es `CAMPO_RELEASE_CONTRACT.md`, y **la copia suelta es la vieja**
(decía 529 pruebas y 42 archivos; la versionada dice 536 y 43).

Son arrastre de la otra rama. Borrarlos no pierde nada — pero es una decisión
del usuario, no de una sesión.

**B1 sigue abierto y no lo cierra la Parte A.** Se ejecutó en un worktree, que
era el camino sin riesgo; si Campo se entrega desde `integrar-centro-mando`
hay que integrarlo, y eso sigue siendo una decisión de entrega.

**Lo que esta corrida NO prueba:** nada de la Parte B. El APK se construyó, no
se instaló. Nadie entró con una cuenta real, nadie recorrió un día sin red,
nadie reinstaló sobre una versión anterior, nadie midió el arranque con veinte
órdenes. *Que compile no es que ande* — y en este proyecto eso ya pasó dos
veces con este mismo artefacto.
