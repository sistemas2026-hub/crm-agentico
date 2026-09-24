# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Si contradice a una conversación, gana este archivo.

**Un gate no está cerrado hasta que este archivo lo refleje.** Y se poda cuando
se actualiza: una sección que quedó vieja no es inocua — la siguiente sesión la
lee como verdad. La historia detallada vive en `auditorias/`, no acá.

Última actualización: **24/09/2026 ~16:30 Bogotá**. Esta versión es la
**FUSIÓN A MANO** de las dos copias que existían de este archivo — una en
`integrar-centro-mando` y otra en `feature/bandeja-relevo`, editadas las dos
el mismo día, divergidas 252 lineas. No se borró nada de ninguna: se importó
entera la sección `VALIDACIÓN DE PRODUCCION` que solo tenía bandeja-relevo, y
se remidió el mapa de ramas, que estaba mal en las dos.

**Desde hoy este archivo tiene un solo escritor.** La regla y su motivo están
al final, en `UN SOLO DUEÑO DEL ESTADO`. En una línea: dos sesiones arreglaron
el MISMO defecto el mismo día sin saberlo —`DECLARACION_NO_ALCANZA`, en
`6207b9a` y en `4ac7dfb`— y cada una lo anotó en su copia. Un documento de
autoridad con dos escritores no es autoridad: son dos borradores homónimos.

---

## DÓNDE VIVE CADA COSA

**REMEDIDO el 24/09/2026 ~16:30 Bogotá, por contenido y no por hash.**
Esta sección se equivocó dos veces hoy, en direcciones opuestas, y las dos
veces por medir mal. La primera versión decía que nada estaba desplegado
cuando el Centro de Mando ya estaba afuera. La corrección de la mañana dijo
que el upstream era la rama de despliegue y que el trabajo «ya estaba
afuera», y tampoco: el upstream es `origin/integrar-centro-mando`.

Lo que hay que medir es el **contenido**, no la ancestría. Otra sesión tomó
dos commits de esta rama y los puso en producción con otro hash, así que
`merge-base --is-ancestor` los contaba como ausentes estando presentes:

```
git log --format=%H origin/fix/integracion-wisphub..HEAD   -> 19 commits
   comparados por `git patch-id --stable` contra producción:
   2 YA ESTÁN afuera con otro hash   65c8f57 -> 790e185
                                     eb8f503 -> b7cfa90
   17 realmente fuera
git rev-list --left-right --count origin/fix/integracion-wisphub...HEAD -> 2  19
git rev-list --left-right --count origin/integrar-centro-mando...HEAD   -> 2  46
```

`origin/integrar-centro-mando` quedó **detrás** de la rama de despliegue: su
último push es del 23/09 (`5cd47e6`). Por eso los 46 «sin pushear» y los 19
«fuera de producción» no se contradicen — miden contra bases distintas.

**Lo que está REALMENTE fuera de producción son 17 commits**, y son el trabajo
de hoy: el sistema de trabajo con IA (CLAUDE.md, 9 agentes, 4 comandos,
`pre-commit`, CI), la plataforma multi-ISP entera (70 -> 14 archivos), el
entorno local aislado, y el arreglo de `DECLARACION_NO_ALCANZA` (`6207b9a`).

Además hay **2 commits en producción que no están acá** (`790e185`, `b7cfa90`)
— los mismos dos de arriba, rebasados por la otra sesión.

| Rama | Qué tiene | Estado medido |
|---|---|---|
| `integrar-centro-mando` | **Activa, es esta.** Centro de Mando, sistema de trabajo con IA, plataforma multi-ISP | 🔴 **17 commits fuera de producción**, 46 sin pushear a su propio remoto, 2 detrás |
| `feature/bandeja-relevo` | Bandeja Fase 1, batería de 41 flujos, validación de producción | 🟡 activa en `C:/tmp/dexter-bandeja`. **NO está congelada** pese a lo que dice la memoria: 3 commits hoy 16:12-16:14 |
| `feat/campo-diseno-stitch` | **Dexter Campo.** 101 archivos de prueba, 551 pruebas | 🟡 activa en `C:/wisphub/_wt_campo`. Una tercera sesión implementa ahí «refrescar ficha» (`test_refrescar_ficha.py`, sin commitear) |
| `fix/integracion-wisphub` | **Producción.** Push ahí ES deploy | Centro de Mando desde `ee4563f` (23/09 12:29) + los dos tableros de hoy |

### DESPLEGADO el 24/09/2026 17:0x Bogotá — y verificado en la pantalla

`790e185 .. 1a83886`. Salieron los 28 commits del día: la plataforma multi-ISP,
el sistema de trabajo con IA (CLAUDE.md, 9 agentes, 4 comandos, `pre-commit`,
CI), el entorno local aislado, `DECLARACION_NO_ALCANZA` clasificado en los tres
guardas, la medición de TR-069 y el extracto en la ficha del agente.

**La verificación que cierra la plataforma multi-ISP, y por qué vale:**

```
Centro de Mando en produccion, tras iniciar sesion:
  insignia            RAPILINK
  panorama            126 activas, 8 agentes, 110 conversaciones hoy,
                      528 herramientas, grafo completo
```

No es «se ve lindo». `(app)/centro-mando/+page.server.js` tiene **una sola
fuente** para el tenant —`tenantDeLaSesion(locals, fetch)`— y si devuelve
`null` la pantalla no pinta el panorama: devuelve `panorama: null` y el texto
«Asistente no configurado». No hay default y no hay camino alternativo. Que se
vea el grafo prueba que el motor contestó `/tenant-de-organizacion/<org>` con
`rapilink`, o sea que **la empresa ya no sale de una variable de entorno: sale
de quién inició sesión**. Es la propiedad entera de PRD §8.13, medida en la
pantalla y no en una prueba.

**El riesgo de orden de contenedores no se materializó.** Se esperaba una
ventana en que el frontend levantara antes que el motor y las pantallas
salieran vacías (falla cerrada, sin fuga). No pasó.

**CERRADO el 24/09/2026 por la noche: ya no queda ninguna.** Los últimos 9
archivos que leían `env.PRIVATE_ASISTENTE_TENANT` resuelven la empresa con
`tenantDeLaSesion`, y el puente `tenantDeLaInstalacion()` se borró — existía
con fecha de vencimiento escrita en su propio docstring.

```
ningun archivo de src/ lee env.PRIVATE_ASISTENTE_TENANT
    guarda: src/lib/server/v2/tenant.test.js, hermana de
            tests/test_nucleo_sin_tenants.py. Recorre src/ y FALLA NOMBRANDO
            el archivo culpable. Comprobada al reves antes de darla por
            buena: se metio una violacion a proposito y la cazo por su ruta.
pnpm vitest run   936 pasan. Los 63 rojos son los MISMOS 17 archivos que ya
                  fallaban en produccion --medido contra un worktree en
                  790e185--: cero regresiones.
pnpm check        40 errores en 29 archivos. La linea base eran 43 en 30.
```

Lo caro no fue reemplazar la lectura: fue que `locals` llegue a donde hace
falta. La acción `invite` de `team` no lo recibía, y `guardia()` de los tres
proxies era síncrono llamando a `cfg()`, así que los dos cambiaron de firma.
Por eso se hizo a mano archivo por archivo: una sustitución por regex ya
rompió ocho archivos antes, exactamente por esto.

**Esta versión NO está desplegada.** Producción sigue en `1a83886`.

⚠️ Ruido esperado y ya explicado, para que la próxima sesión no lo investigue
de nuevo: al reiniciar el frontend aparecen `Token refresh failed ... 401` en
su log. Es una cookie `jwt_refresh` ya gastada —`ROTATE_REFRESH_TOKENS` +
`BLACKLIST_AFTER_ROTATION`, o sea un solo uso por token— de una pestaña
abierta desde antes del despliegue. Ninguno de los 28 commits toca
autenticación, JWT ni `settings.py`; `hooks.server.js` no cambió una línea.
Solo preocupa si es continuo y para todos JUSTO DESPUÉS de iniciar sesión:
eso sería `SECRET_KEY` cambiada, que invalida todo lo emitido.

### Qué hay en producción, con fecha

Importado de la copia de `feature/bandeja-relevo`, que lo tenía y esta no.
Es la evidencia de los despliegues del 23/09 — no se pierde en la fusión.

```
23/09/2026, push a fix/integracion-wisphub (= deploy):
  00407ac  el aviso del reencauzamiento no llegaba al modelo
  0b27263  el embudo de identidad se puede medir  (+ migracion 202609231445)
  969e7b9  privacidad de la observabilidad del frontend
  49d9318  la pestaña abierta antes del deploy se recupera sola
  055d1a2  franja horaria en el prompt, y motivo de escalada obligatorio
  ee4563f  Centro de Mando (12:29)

y en la base de producción ese mismo día:
  config v150 -> v154   descripcion de derivar_a_area, por el editor versionado
                        (nucleo/config/editor.py), UN CAMPO POR VEZ. Nunca con
                        --forzar: ese sube el documento completo.
  migracion             202609231445_identidad_eventos.sql aplicada. Ledger en
                        0 pendientes, 0 checksums distintos.

24/09/2026:
  b7cfa90  el tablero se mira de lejos y se lee de un vistazo   (11:55)
  790e185  el tablero no cabia donde de verdad se mira          (15:35)
                        ^ los dos son commits de `integrar-centro-mando`
                          rebaseados y pusheados por otra sesion.
```

⚠️ **Tres frentes activos a la vez, y hoy se cruzaron tres veces:**

1. Dos sesiones arreglaron **el mismo defecto** sin saberlo —
   `DECLARACION_NO_ALCANZA`, en `6207b9a` (esta rama) y en `4ac7dfb`
   (bandeja-relevo). Dos arreglos del mismo bug, en dos ramas.
2. Dos sesiones editaron **este archivo** el mismo día, y las dos copias
   divergieron 252 líneas. Esta versión es la fusión a mano de las dos.
3. Una sesión **rebaseó y pusheó** dos commits de esta rama sin avisar. El
   trabajo salió bien, pero el hash local ya no existe afuera, y eso es
   exactamente lo que hizo fallar la medición por ancestría.

Ninguno de los tres es un error de código. Los tres son el mismo error de
coordinación, y la regla del final existe para eso.

### Cómo se resuelve el cruce de `DECLARACION_NO_ALCANZA` al fusionar

Medido el 24/09 comparando las dos ramas archivo por archivo: **los dos
arreglos son semánticamente idénticos.** No hay que elegir cuál está bien;
hay que deshacer un conflicto de texto. Va escrito acá para que quien
fusione no lo decida a ojo:

```
nucleo/modelo/motor.py          ambos agregan "DECLARACION_NO_ALCANZA" al
                                MISMO frozenset (CODIGOS_DE_BLOQUEO), en la
                                misma posicion. Conflicta el COMENTARIO, no el
                                codigo. -> quedarse con uno, da igual cual.
nucleo/seguimiento/forzado.py   ambos lo agregan al MISMO set
                                (CODIGOS_MOTOR_GUARD). Verificado leyendo a
                                que set pertenece cada linea, no por cercania
                                visual. -> idem.
+page.svelte  (linea 138)       aca SI hay una decision: el texto que ve el
                                usuario es distinto.
                                  integrar-centro-mando:
                                    "lo que el cliente reporto no corresponde
                                     a esa accion"
                                  bandeja-relevo:
                                    "la accion no corresponde a lo que el
                                     cliente dijo que le pasaba"
                                Dicen lo mismo. -> elegir uno y borrar el otro;
                                dejar los dos duplica la clave del objeto.
tests/test_escalada_forzada.py  SOLO integrar-centro-mando. Agrega el codigo
                                al set GATES de la prueba. No conflicta, y es
                                el lado que hay que conservar: es la guarda.
```

La prueba de que el lado de esta rama queda verde:

```
py -3.13 tests/test_escalada_forzada.py     -> exit 0
   "Todo en orden: lo que obliga a escalar no depende del modelo."
```


## TRABAJO ACTIVO

**Tres frentes avanzaron el 24/09**, cada uno en su propio árbol. Ninguno está
bajo los pies de los otros.

```
Centro de Mando        🟢 EN PRODUCCIÓN desde el 24/09 09:31 Bogotá (468f575).
                          El estado anterior decía ee4563f: ese commit es del
                          23/09 12:29 y producción avanzó 20 commits desde ahí.
                          Quedan dos entradas de menú que se pisan, y E2E-001
                          fuera por el choque en el serializer de campo
Dexter Campo           🟡 FASE 2 · PULIDO desde el 24/09/2026: datos reales,
                          los modulos ausentes del contrato §2, la deuda del §6,
                          diseño, y 2.E prioridad dual (decidida el 24/09, sin
                          implementar). Se permiten cambios de funcionalidad y
                          arquitectura; los seis invariantes del §3 NO se
                          relajan. Ficha: objetivos/campo-release-candidate.md
                          LÍNEA BASE de la Fase 1, medida el 23/09 sobre
                          cf4684e: 536 pruebas verdes en las dos compilaciones,
                          APK de release 53.2 MB. ⚠ esa rama avanzó 4 commits
                          desde entonces (evidencias con geolocalización, sello
                          de hora de fotos, filtro de localidad, siembra de
                          carga) y NO se remidió: el 536 es de antes, no de hoy
Batería de evaluación  🟡 viva en C:/tmp/dexter-bandeja (feature/bandeja-relevo),
                          5 commits fuera de producción. 20 conversaciones
                          completas que se juzgan solas, y la auditoría del
                          bloque: tres falencias arregladas, nueve anotadas.
                          Hallazgo propio: la batería daba verde con el sistema
                          caído — su garantía era falsa
Sistema de trabajo IA  ✅ CLAUDE.md como enrutador, 9 agentes, 4 comandos,
                          pre-commit activo y corregido (3 hallazgos). Falta CI
                          del lado del servidor (D1). ⚠ los agentes NO se
                          cargan en la sesión: los 9 están en disco
                          (.claude/agents/) y solo `verificador-de-api` queda
                          invocable — medido por TERCERA vez el 24/09
```

## TRABAJO SIN COMMITEAR — no se limpia sin preguntar

Alguien lo dejó ahí a propósito. Medido el 24/09.

**En `C:/wisphub/_wt_campo`** (Campo, el árbol vivo) — probablemente 2.E en curso:

```
M  apps/tecnicos-mobile/lib/features/trabajo/trabajo_vista.dart
M  apps/tecnicos-mobile/lib/features/trabajo/widgets/tarjeta_trabajo.dart
M  (3 registrants generados de macos/ y windows/)
?? compose.puerto-8001.yml
```

**En `C:/tmp/dexter-bandeja`** (la batería):

```
M  SPEC/CONTRATO_RELEVO_IA_HUMANO.md   arrastre ajeno sobre G9, sin destino propio
```

**En este árbol** (`integrar-centro-mando`): 43 archivos, **todos sin seguimiento**,
ninguno modificado ni en stage. 21 `.playwright-mcp/*.yml` y 7 PNG en la raíz
(`disco-*`, `radial-*`, `proto-radial`) son artefactos de sesión — justo lo que
el `pre-commit` bloquea; 10 en `documentos/command-center/` (avatares y
prototipo radial); 5 en `apps/tecnicos-mobile/`, las copias de B2.

⚠️ **Stage por rutas explícitas siempre, también para documentación**:
prohibidos `git add .`, `git add -A`, `commit -a` y **`git add SPEC/`**. El
último se coló en el cierre de 1.8 y metió un arrastre ajeno en el commit
documental. Un directorio entero es el mismo gesto que un `add .`: basta con que
alguien deje un archivo ajeno adentro. Verificar siempre con
`git diff --cached --name-only` antes de commitear.

⚠️ **Hay 21 worktrees registrados** (`git worktree list`), la mayoría de bloques
ya cerrados (`dexter-d17`, `dexter-d19d23`, `dexter-hotfix`, `dexter-ledger`…).
No se podan acá: es decisión de una persona, no de una sesión.

## VALIDACIÓN DE PRODUCCIÓN — abierta, y ahora se sabe en qué

Objetivo `SPEC/objetivos/endurecer-validacion-de-produccion.md`. **NO está
cerrado.** La versión anterior de esta sección decía «cerrado con una
salvedad»; estaba mal contada y se corrige acá.

Lo que quedó funcionando y medido el 24/09:

```
cli/bateria_flujos.py    41 conversaciones que entran por atender_turno y se
                         juzgan solas contra la traza. 36/38 en LOCAL; 3
                         necesitan el CRM (backend:8000, red del compose).
                         Cierra el hueco de que cli/evaluar.py llama a
                         motor.responder() directo.
casos dorados            el inestable partido en dos: 10/10 y 10/10.
                         'sin el serial cargado' dejó de afirmar sobre la
                         redacción: 10/10.
cli/evaluar.py           afirmaciones 'bloquea_con' / 'no_bloquea_con'.
diferencias_config       exit 0. Las 3 diferencias son las sincronizadas
                         (localidades, localidades_actualizado_en,
                         parrilla_canales).
test_bloqueos_en_traza   VERDE (7/7). Estaba rojo en la rama.
```

**Lo que se descubrió al medir, y es lo importante de esta sección:** la
batería comiteada **nunca se había corrido**. El commit `d9733df` está escrito
como un arreglo de una línea del cliente simulado y además agrega 20 casos —de
21 a 41—, entre ellos los de seguridad. El 19/19 que esta sección declaraba se
midió sobre `81677b4`, con 21 casos. O sea: la evidencia no describía el código
comiteado, que es el error cardinal de este proyecto.

Corrida ya la batería completa, los cinco casos de seguridad que nunca se
habían medido **pasan**: inyección de instrucciones, técnico falso, lista de
morosos, cédula de un tercero, amenaza de cancelar.

**Un hallazgo de conducta, determinista, fuera del objetivo:**

```
una falla de barrio     0/10. El agente dice "puede ser algo de la zona" y acto
no se diagnostica       seguido diagnostica una sola casa: consulta el incidente
como una casa           de red en el paso 9, DESPUÉS de haber propuesto el
                        reinicio en el 8. Arreglarlo es cambiar el orden del
                        diagnóstico, o sea conducta: se anota, no se toca.
                        El caso queda ADENTRO de la batería y en rojo.
```

**Lo que falta para cerrar el objetivo:**

```
docker exec <contenedor-motor> python cli/bateria_flujos.py rapilink --todos
```

Y no basta un contenedor local: los 3 casos de CRM llaman a
`http://backend:8000` con las credenciales de la config de producción. Un
`backend` levantado desde un worktree no las tiene y responde 403; en el
intento del 24/09 eso fue exactamente lo que pasó. El 41/41 literal solo sale
en la red de producción, y antes hay que desplegar `cli/bateria_flujos.py`.

**Lo que la auditoría dejó abierto** (`SPEC/auditorias/2026-09-23-bateria-de-flujos.md`):

```
AUTONOMIA_2_NO_ACTIVA  sigue sin clasificar como bloqueo. No se arregla con un
                       renglón en una lista: llega por el except genérico, así
                       que hay que hacer que ese camino preserve e.codigo.
                       (DECLARACION_NO_ALCANZA SÍ se arregló: commit 4ac7dfb.)
traza incompleta       la batería juzga contra la traza de la base y hubo dos
                       ConnectionTimeout al escribirla. Hoy nada distingue "la
                       herramienta no se llamó" de "la llamada no se pudo
                       escribir": un caso puede salir verde por el error.
franja horaria         REFUTADO el 23/09: medido dentro de la imagen,
                       ZoneInfo('America/Bogota') funciona.
```

## CERRADO

```
Fase 0 (componentización)     ✅
D29 · D30                     ✅
G9 recibo punta a punta       ✅ verde en producción 16/09/2026
Fase 1.1–1.4B (visual)        ✅
FASE 1.4C  backend + UI de T6 ✅
FASE 1.5   Case + Tools       ✅
FASE 1.6   Activity           ✅  el relevo se lee por primera vez
FASE 1.7   Customer           ✅  lo que sabe del cliente, y lo que no
FASE 1.8   Network            ✅  qué se le hizo al equipo, sin botones
FASE 1.9   cierre visual      ✅  utilidades de panel unificadas
FASE 1     Bandeja rediseñada ✅  COMPLETA
```

## ABIERTO al cerrar la Fase 1

```
G6 sobre messages poblada   🔒 gate de DESPLIEGUE. La migración aplica limpia
                               desde cero y el ledger la anota sola, pero no se
                               midió sobre una tabla con datos. No bloquea
                               desarrollo; sí bloquea cualquier push.
                               ✅ 24/09: el push de hoy NO lo violó, medido.
                               El deploy ee4563f..468f575 llevó UNA sola
                               migración, 202609231445_identidad_eventos.sql, y
                               es `create table if not exists` sobre una tabla
                               NUEVA + índices + RLS: no hay tabla poblada que
                               medir. Las tres migraciones que sí tocan
                               `messages` (202609071000, 202609072000,
                               202609161600) son del 07 y 16/09 y ya estaban
                               afuera desde antes. El gate NO se salteó:
                               no era el caso. Sigue vigente para el próximo
                               push que sí toque `messages`.
QA visual multi-viewport    🔴 NO EJECUTABLE con los medios disponibles, y no
                               por falta de intento: el dev server levanta pero
                               hooks.server.js:373 redirige a /login antes de
                               montar el layout, así que ni el estado de error
                               dentro de .mesa.bandeja se dibuja. Entrar exige
                               un JWT del backend de producción; una ruta de
                               prueba con datos falsos está prohibida.
                               NINGÚN píxel de 1.4C a 1.9 se vio renderizado.
D28                         ⏭ abierto para B4. La pantalla lo MUESTRA (1.5): el
                               dueño del CRM es informativo, el de Dexter manda.
                               No se reconcilian — no comparten identidad de
                               usuario, y por eso se comparan nombres.
hot path ③a/③c              ⏭ idempotencia del outbound automático del canal,
                               retirado y preservado en
                               auditorias/1.4C-hotpath-diferido.md
T7 endpoint                 ⏭ «devolver sin responder»: capacidad distinta, NO
                               el recovery de T6
semánticos ember/clay/      ⏭ resueltos en context/ (1.5); los consumidores de
rust/moss                      otras pantallas, en la fase de cada una
```

## B4 — CERRADO EN CÓDIGO. Falta encenderlo (G7)

```
migración    202609201000_sincronizaciones_externas.sql   aplica limpia
T20          nucleo/relevo/reconciliador.py               la regla de reintento
worker       nucleo/relevo/worker_reconciliador.py        proceso propio, 5 min
ejecutor     nucleo/relevo/efectos_externos.py            crear_caso real
panel        «Sincronización externa», read-only, sin botón de reintentar
commits      b5bfb84 · 62487db
```

**G7 es ahora sólo activar**, y en este orden: declarar `busca_caso` en el
catálogo del tenant → comprobar que funciona → recién entonces
`RECONCILIADOR_HABILITADO=1` y desplegar el servicio. El mecanismo existe entero. El reloj general sigue en ~60 min y **no
se tocó**: el worker tiene interruptor propio, para que encender uno no encienda
el otro por descuido.

Lo que sigue sin conectar, y es deliberado:

```
crear_ticket sin ejecutor      y no lo tendrá mientras Q2 siga rojo. Uno que
                               llegue hoy a la cola termina en
                               fallida_definitiva con 'sin_ejecutor', visible
sólo crear_caso se encola      los otros tres tipos existen en esquema y panel,
                               sin productor
falta declarar `busca_caso`    ningún tenant declara la herramienta de búsqueda.
en el catálogo                 Sin ella todo reintento intentaría crear — no es
                               inseguro (el 400 se maneja) pero conviene tenerla
                               antes de encender el worker
```

## B4 — lo que Q2 ya decidió

```
Q2                    🔴 ROJO, cerrado el 20/09/2026 (auditorias/B4-Q2-WISPHUB.md)
crear_ticket WispHub  NO es reintentable automáticamente: la API no acepta
                      clave de idempotencia, no hay filtro para buscar el
                      ticket, WispHub reescribe el asunto y el histórico se
                      recorta sin rango de fecha (tope 2 meses)
fallo incierto        → estado 'desconocida'. NUNCA se crea otro ticket
                      automáticamente: un ticket pendiente de revisión es
                      preferible a dos visitas técnicas al mismo cliente
crear_caso (CRM)      SÍ reintentable: el nombre incluye el conversation_id y
                      es único por organización; un repetido da 400 y se adopta
```

**La cola de B4 no puede diseñarse homogénea.** Los dos tipos de efecto tienen
estrategias distintas, y `desconocida` deja de ser un caso teórico del esquema
para ser el camino normal de la mitad de la cola. Eso arrastra dos cosas a
decidir antes de escribir la migración: dónde se muestra un pendiente de
revisión en la conversación, y que el reintento automático de `crear_ticket`
**no se escribe**, ni detrás de una bandera.

## G3 — VERDE. El camino de ejecución está cerrado

```
36 acciones de legado en 'pendiente' (34 create_ticket · 2 promise_payment),
sin conversation_id. SIGUEN pendientes: cancelarlas es trabajo de una persona
con la pantalla delante, y ese es el punto.
```

Cerrado en `5055c20` (motor) y `e67875b` (pantalla). Detalle en
`auditorias/G3-CIERRE.md`.

```
1. aprobar responde 409 y no llega al ejecutor. La guarda corre ANTES del
   chequeo de estado y de leer la config.
2. 'cancelada' es estado declarado, con motivo obligatorio y evento durable
   en la misma transacción (I12). Tabla nueva acciones_eventos: el
   conversation_id de relevo_eventos es NOT NULL y estas 36 no tienen.
3. /acciones-legado lista las pendientes. Sin botón de aprobar —ausente, no
   deshabilitado— y sin 'argumentos' (valores reales sin enmascarar).
```

El criterio de legado es **la falta de `conversation_id`**, nunca la edad ni el
tipo. Cuando B5 traiga la columna, la misma función deja pasar las que la
tengan sin tocarla.

**Lo que este gate NO hizo, a propósito:** tocar las 36 filas. El contrato pide
revisión humana una por una, no un `UPDATE` en lote. Las 2 de promesa de pago
quedan para revisión: si el cliente pagó no se puede saber sin consultar
producción, y no se consultó.

Migración `202609201400_acciones_legado.sql` **sin aplicar en producción** — ver
la nota de abajo sobre *estar en el repo ≠ estar aplicada*.

B5 queda desbloqueado.

## B5 — CERRADO EN CÓDIGO. Falta la config del tenant (Q3)

Commits `1bad6f3` (motor), `f779d07` (pantalla) y `155bb15` (barrido T20).
Detalle en
`auditorias/B5-ACCIONES.md`.

```
aprobar = reservar -> revalidar -> ejecutar -> resolver  (§9.3)
          los dos del medio FUERA de transaccion (X23)
```

La revalidacion tiene **tres** desenlaces y no dos: «no se pudo comprobar» no
ejecuta y devuelve la accion a `pendiente`. Tratarlo como «cumple» ejecutaria a
ciegas con la API externa caida; como «no cumple» mataria una accion valida.

Dos aprobaciones concurrentes producen **un** efecto: probado con dos peticiones
reales compitiendo.

**Lo que falta, y no es codigo:** la config de Rapilink no declara
`vigencia_minutos` ni `revalidar`, y no puede hacerlo hasta que cierre la
medicion ON vs OFF (Q3). Hasta entonces las acciones nacen sin plazo y se
aprueban sin revalidar, con las guardas que no dependen de config. El validador
esta en modo **advertencia** a proposito.

Las cuatro revalidaciones de §3.7 tampoco estan escritas: el contrato exige
confirmarlas con la skill `wisphub-api` contra la API real antes de escribirlas.

T20 cierra lo que queda a medias: `ejecutando` vieja -> `desconocida` a los
10 min (§14.1 Q4), `pendiente` pasada de plazo -> `vencida`. Nunca reejecuta
(X21). Una de legado `pendiente` no se vence jamas, por construccion.

Migracion `202609201800_acciones_b5.sql` **sin aplicar en produccion**.
Verificado sobre base limpia (`b5_limpia`): 51 archivos, 0 checksum distinto.

## ESTAR EN EL REPO ≠ ESTAR APLICADA

Distinción que el 24/09 casi se pierde al medir. Son dos hechos distintos y solo
uno se puede comprobar desde una sesión:

```
en el repositorio   se mide con git, desde acá        ✅ medido el 24/09
aplicada en la base  se mide con el ledger, contra    ❌ NO se midió: consultar
                     producción                          producción desde una
                                                         sesión está prohibido
```

Medido el 24/09 con git: las **64** migraciones `.sql` de `supabase/` son
**idénticas** entre este árbol y la rama de despliegue — las tres de B4, G3 y B5
incluidas. Eso significa que sus archivos **sí viajaron a producción**, y no
dice nada sobre si el ledger las aplicó. Los «sin aplicar» de arriba siguen
vigentes tal como se escribieron; nadie los remidió.

Lo mismo vale para Campo: producción tiene **3** migraciones de `campo` en el
repo y `feat/campo-diseno-stitch` tiene **6**, mientras la anotación anterior
hablaba de **2 aplicadas** en la base. No es una contradicción: son dos cuentas
distintas, y confundirlas es el error que esta sección existe para frenar.

```
py -3.13 cli/migrar_asistente.py --estado    # lo único que responde la pregunta
```

## SIGUIENTE GATE DE LA BANDEJA *(en pausa — pero su rama NO está congelada)*

```
Branding   pantalla de ajustes, FUERA de la Fase 1
```

No es la Bandeja: es «Settings · Appearance & Branding», con subida de archivo,
almacenamiento de assets y alcance por organización. Hoy existe `Marca.logo_url`
en el esquema del tenant **sin ningún consumidor**, y nada más. Necesita su
propio scope.

Entrada: `SPEC/FASE_1_CHECKPOINT.md`.

**No es lo que sigue hoy**, y el motivo cambió. Hasta el 23/09 este gate estaba
en pausa *porque su rama estaba congelada*. Medido el 24/09, eso ya no es cierto:
`feature/bandeja-relevo` recibió 5 commits el 23–24/09 en el worktree
`C:/tmp/dexter-bandeja`, sobre la batería de evaluación y la auditoría del
bloque — no sobre la Bandeja.

Lo que sigue en pausa es **Branding**, no la rama. Quien lo retome ya no tiene
que descongelar nada: tiene que decidir que Branding es lo que toca. Lo que
sigue hoy está en TRABAJO ACTIVO, arriba, y en las fichas abiertas de
[objetivos/](objetivos/).

## CONTRATOS CONGELADOS DE ESTA RAMA

No se reauditan sin evidencia nueva.

```
T6 · control = ia     sólo con wamid + estado_entrega='enviado' durables
T6 · sin optimismo    el control cambia sólo con devuelto_al_asistente === true
rechazado             ≠ incierto / sin_id / aceptado_sin_registro
unknown               conserva el control humano y NO ofrece reintentar
clave idempotente     una por intento; viaja con la burbuja junto a la intención
T7                    no es el recovery de T6
D28                   dueño del ticket CRM ≠ dueño durable de Dexter;
                      nombres iguales NO prueban identidad
ficha del cliente     Dexter guarda identidad + equipo y nada más (RNF-01);
                      no se consulta el ISP en vivo desde la Bandeja
acciones sobre el     no se ejecutan desde la Bandeja: reiniciar corta el
equipo                servicio y pasa por la cola con confirmación (PRD §7.4)
ACCION_CONFIRMADA     el equipo hizo lo pedido ≠ el cliente tiene internet
NO_VERIFICABLE        «no se pudo medir» ≠ «se midió y el efecto no está»
el ping               no es veredicto: medido, un equipo sano da 1/3, 2/3 y 3/3
bloqueo               ≠ error: el código frenando la acción es la protección
                      funcionando, y no ensucia la tasa de error
```


---

## UN SOLO DUEÑO DEL ESTADO

*Regla nueva del 24/09/2026. No nace de una preferencia: nace de que hoy tres
sesiones se cruzaron tres veces en un día.*

### La regla

**Este archivo lo escribe la sesión que trabaja en `integrar-centro-mando`.**
Las demás sesiones **no lo editan**. Si tienen algo que anotar, lo entregan en
su respuesta —hash del commit y una línea de qué cerró— y la sesión dueña lo
escribe acá.

Es la misma forma que ya funciona para producción (ver la memoria «Un solo
dueño de producción»: solo la IA de Plataforma pushea, las demás entregan
hashes). Se extiende al estado por el mismo motivo y con la misma evidencia.

### Por qué, y lo que costó

Un documento de autoridad con dos escritores **deja de ser autoridad**: pasa a
ser dos borradores con el mismo nombre. Lo que pasó hoy, medido:

- Las dos copias divergieron **252 líneas** en un solo día. Ninguna era «la
  buena»: cada una tenía secciones que la otra no.
- El mismo defecto se arregló **dos veces** (`DECLARACION_NO_ALCANZA` en
  `6207b9a` y en `4ac7dfb`) porque cada sesión leía su propia copia del estado,
  y en ninguna de las dos figuraba que la otra ya lo estaba mirando.
- La sección del mapa de ramas afirmó **lo contrario de la realidad dos veces
  el mismo día** —una en cada dirección— y la segunda corrección también estaba
  mal, porque medir por ancestría no ve un commit rebaseado.

El costo no es el desorden. Es que este archivo existe para que una sesión nueva
no tenga que reconstruir el estado, y un archivo que miente cuesta **más** que
no tenerlo: la sesión que lo lee no sospecha.

### Las tres cosas que se hacen distinto desde hoy

1. **Se mide por contenido, no por hash.** Para saber si algo está en
   producción: `git patch-id --stable`, no `merge-base --is-ancestor`. Un
   commit rebaseado por otra sesión es invisible para el segundo.

2. **Antes de arreglar un defecto, se mira si otra rama ya lo está
   arreglando.** `git log --all --oneline --since=<ayer> -- <archivo>` cuesta
   dos segundos y hoy habría ahorrado un arreglo duplicado.

3. **Nadie rebasea ni pushea commits de una rama ajena sin decirlo.** Si pasa,
   se anota acá cuál fue el hash viejo y cuál el nuevo — como quedó anotado
   arriba con `65c8f57 -> 790e185` y `eb8f503 -> b7cfa90`.

### Lo que esta regla NO dice

No dice que las otras sesiones trabajen menos ni que pidan permiso para
codificar. Cada rama sigue siendo dueña de su trabajo y de sus commits. Lo
único centralizado es **el relato de qué está hecho** — porque de eso hay uno
solo por definición, y hoy había tres.
