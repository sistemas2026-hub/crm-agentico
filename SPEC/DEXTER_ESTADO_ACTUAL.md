# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Si contradice a una conversación, gana este archivo.

**Un gate no está cerrado hasta que este archivo lo refleje.** Y se poda cuando
se actualiza: una sección que quedó vieja no es inocua — la siguiente sesión la
lee como verdad. La historia detallada vive en `auditorias/`, no acá.

Última actualización: **24/09/2026 ~10:40 Bogotá**, por `/inicio-sesion`, que
midió git con `fetch` y encontró que este archivo afirmaba lo contrario de lo
desplegado. La anterior era del 23/09, al cerrar Campo RC parte A+B4/5 y el
sistema de trabajo con IA.

**Lo que se corrigió, y por qué importa:** decía *"ninguna rama está pusheada a
la rama de despliegue"* cuando el Centro de Mando **está en producción desde hoy
09:31**, y declaraba `feature/bandeja-relevo` congelada cuando recibió 5 commits
entre ayer y hoy. Las dos afirmaciones llevaban a decisiones equivocadas: la
primera invita a pushear algo "por primera vez" que ya está afuera; la segunda,
a ignorar trabajo vivo. **No se borró nada de lo cerrado** — se corrigió dónde
vive cada cosa y se agregó lo que faltaba.

---

## DÓNDE VIVE CADA COSA

Medido el 24/09/2026 con `git fetch` + `merge-base --is-ancestor` contra
`origin/fix/integracion-wisphub`. **Producción está en `468f575`** (24/09 09:31
Bogotá).

| Rama | Qué tiene | Respecto de PRODUCCIÓN |
|---|---|---|
| `integrar-centro-mando` | **Activa acá.** Centro de Mando, sistema de trabajo con IA (CLAUDE.md, 9 agentes, 4 comandos, `pre-commit`), plan semanal | 🟢 **desplegada.** Solo 2 commits por delante, y los dos tocan **un único archivo de documentación** (`SPEC/objetivos/campo-release-candidate.md`). Todo su código está afuera |
| `feature/bandeja-relevo` | Bandeja Fase 1 + batería de evaluación + auditoría del bloque | 🟡 **5 commits fuera** (23–24/09). Su remota `origin/feature/bandeja-relevo` sí está contenida en producción; el trabajo nuevo vive en el worktree `C:/tmp/dexter-bandeja` |
| `feat/campo-diseno-stitch` | **Dexter Campo.** 101 archivos bajo `test/` | 🔴 **46 commits fuera, 246 detrás.** Muy divergente. La copia viva es el worktree `C:/wisphub/_wt_campo`, 4 commits por delante de su propia remota |

⚠️ **El upstream de `integrar-centro-mando` es la rama de DESPLIEGUE**, no su
propia remota:

```
git rev-parse --abbrev-ref @{u}   →   origin/fix/integracion-wisphub
```

Con `push.default` sin fijar (= `simple`) un `git push` pelado se rechaza porque
los nombres difieren — pero **`git push origin HEAD` despliega a producción**, y
`git pull` trae desde ahí. `origin/integrar-centro-mando` quedó 27 commits atrás
y ya no representa el trabajo.

⚠️ **Campo no está en `integrar-centro-mando`.** Remedido el 24/09: **6**
archivos de prueba acá contra **101** allá. Los E2E 002/003/004, `test/apoyo/` y
`docs/CAMPO_RELEASE_CONTRACT.md` sueltos en este árbol son copias byte a byte de
la otra rama (B2, resuelto el 23/09), **no** la suite.

⚠️ **Choque de migraciones de Django, hallazgo nuevo del 24/09.** Las dos ramas
tienen **un `0003` distinto cada una**:

```
producción (repo)          feat/campo-diseno-stitch (repo)
0001_initial               0001_initial
0002_remove_ordentrabajo…  0002_remove_ordentrabajo…
0003_alter_asignaciontra…  0003_campos_de_despacho        ← divergen acá
                           0004_entregadekit_materialcat…
                           0005_movimientodematerial_mot…
                           0006_actadedevolucion_inciden…
```

Integrar Campo no es solo traer cuatro migraciones: exige resolver dos `0003`
con el mismo número. Eso no estaba escrito y es parte de B1.

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
