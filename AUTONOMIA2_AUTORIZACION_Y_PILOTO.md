# AUTONOMÍA 2 — AUTORIZACIÓN GRANULAR + PRIMER PILOTO

Fecha: 2026-09-19

**Nada se activó.** El interruptor de etapa está apagado, ninguna tabla nueva
existe en producción, el kill switch sigue `detenido` y `DBUSER` sigue siendo
`postgres`. Sin commit, sin despliegue.

---

# 1. AUTORIZACIÓN IMPLEMENTADA

## 1.1 Tres tablas, no una bandera

`supabase/202609191430_autonomia2_autorizacion.sql` (**no aplicada a
producción**; aplicada y probada en el entorno aislado):

| Tabla | Qué contesta |
|---|---|
| `asistente.nivel_autonomia` | el **techo** de la empresa, 0–4 |
| `asistente.autorizacion_herramienta` | qué puede hacerse **de verdad**, herramienta por herramienta |
| `asistente.ejecucion_autonoma` | qué pasó — **bitácora, no agenda** (§3) |

Las tres son *append-only*, como el kill switch: cada fila es una transición y
la vigente es la más reciente. Revocar es escribir `estado='revocada'`, nunca
borrar — si se borrara, no quedaría quién autorizó qué ni cuándo.

`autorizacion_herramienta` cubre lo que pide el bloque 2: `organization_id`
(tenant), `herramienta`, `nivel_maximo`, `estado`, `vigente_desde`/
`vigente_hasta`, `autorizado_por`, `creado_en`, `motivo`, `limites` (jsonb) y
`estado_anterior`.

## 1.2 El techo acota; no habilita

```
nivel_efectivo = min(techo de la empresa, nivel de la autorización)
```

Medido: techo 1 + autorización de nivel 4 → **efectivo 1**, bloqueado. Así
bajar el techo desactiva todo sin borrar nada, y revocar una herramienta no
obliga a tocar las demás. Una empresa en nivel 4 **sin autorizaciones no
ejecuta nada**.

## 1.3 Es independiente de las dos cosas de las que debía serlo

- **De `tenant_config.requiere_confirmacion`**: ninguna de las dos se lee en la
  decisión. Esa bandera viaja en la config cacheada, y esa ruta ya se midió
  fallando ABIERTA por dos caminos (15/09/2026). Una autorización que se pierde
  con un caché vencido no es una autorización.
- **Del nivel global**: son tablas distintas y se exige que pasen las dos.

## 1.4 Dónde vive el control

Dentro de `frontera.autonoma()` — **no en los llamadores**. Es la misma razón
por la que existe la frontera: el paso 10.14 midió cinco caminos que escribían
afuera sin pasar por el gate, y ninguno era un descuido grande. Un llamador
nuevo que no sepa que esto existe queda cubierto igual.

`humana()` **no** pasa por aquí, a propósito: una persona identificada que
aprueba una acción concreta no es el sistema actuando solo, y exigirle
autorización de autonomía dejaría sin operar al panel el día que se revoque una
herramienta.

## 1.5 El flujo del bloque 1, y dónde está cada eslabón

```
M09  →  PropuestaSupervisor  →  autorización granular  →  guards
     →  tool autorizado  →  frontera de efecto  →  resultado  →  auditoría
```

| Eslabón | Dónde | Estado |
|---|---|---|
| PropuestaSupervisor | `operaciones/models.py` | existe, sin tocar |
| autorización granular | `nucleo/seguridad/autorizacion.py` | **nuevo** |
| etapa + prerequisito B-7 | `nucleo/seguridad/autonomia2.py` | **nuevo** |
| guards | `frontera.autonoma()` | **ampliado** |
| frontera de efecto | `http.py::frontera.exigir` | existe |
| auditoría | `asistente.ejecucion_autonoma` | **nuevo** |

**No se usó `acciones_propuestas` como autorización**, y las dos colas no se
fusionaron.

---

# 2. HERRAMIENTAS CANDIDATAS

De las 69 del catálogo, 27 escriben. M10-A las clasificó: R1(3), **R2(19)**,
R3(3), R4(2). R3 y R4 quedan fuera por el bloque 4.

Las 19 R2 se parten en dos, y eso decide casi todo:

| Destino | Cuántas | Cuáles |
|---|---|---|
| **WispHub** (`api.wisphub.io`) — tercero | **11** | `actualizar_estado_ticket`, `agendar_visita_internet`, `agendar_visita_tecnica`, `cerrar_ticket_operativo`, `completar_ticket_instalacion`, `crear_ticket`, `crear_ticket_caso`, `crear_ticket_instalacion`, `reasignar_ticket_instalacion`, `responder_ticket`, `responder_ticket_operativo` |
| **CRM propio** (`backend:8000`) | **8** | `cancelar_solicitud_servicio`, `cerrar_caso_crm`, `crear_caso_soporte`, `crear_tag_crm`, `importar_caso_externo`, `reconciliar_caso_externo`, `registrar_solicitud_servicio`, `sincronizar_respuestas_externas` |

Las 11 de WispHub quedan descartadas de entrada: el efecto ocurre en el sistema
de un tercero, no se puede probar en el entorno aislado sin llamarlo de verdad,
y llamarlo está prohibido.

De las 8 del CRM, contra los criterios del bloque 4:

| Herramienta | Efecto | Reversible | Impacto | Verificable |
|---|---|---|---|---|
| **`crear_tag_crm`** | crea una etiqueta | sí, borrándola | **mínimo: no toca a ningún cliente** | sí (`listar_tags_crm`) |
| `cerrar_caso_crm` | cierra un caso | sí, reabriendo | medio: SLA, CSAT, avisos | sí |
| `crear_caso_soporte` | crea un caso | sí | medio: dispara enrutamiento y escalado | sí |
| `registrar_solicitud_servicio` | alta comercial | parcial | medio | sí |
| `cancelar_solicitud_servicio` | cancela una solicitud | parcial | medio | sí |
| `importar_caso_externo` | importa | sí | medio | sí |
| `reconciliar_caso_externo` | reconcilia | parcial | medio | parcial |
| `sincronizar_respuestas_externas` | escribe respuestas | **no** | **alto: el cliente las ve** | parcial |

No se inventó ninguna herramienta nueva.

---

# 3. HERRAMIENTA SELECCIONADA

## **UNA: `crear_tag_crm`.**

El bloque 5 dice «idealmente 1, máximo 3». Es 1.

---

# 4. MOTIVO DE LA SELECCIÓN

| Criterio (§5) | `crear_tag_crm` |
|---|---|
| **efecto** | crea una etiqueta en el CRM propio. No sale de la plataforma, no llega a ningún cliente, no toca dinero ni equipos |
| **reversibilidad** | total: una etiqueta se borra y no deja rastro operativo |
| **riesgo** | el más bajo del catálogo: una etiqueta de más es ruido, no un incidente |
| **idempotencia** | usa `asistente.operaciones_externas`, el mecanismo existente. Medido: misma clave + mismos argumentos → **una sola llamada** |
| **auditabilidad** | queda en la bitácora con autorización, nivel, actor y clave |
| **dependencias** | ninguna externa. `BOTTLECRM_API_TOKEN` (PAT con scopes), **no `service_role`**, sin privilegios administrativos |
| **rollback** | borrar la etiqueta, o revocar la autorización — que la apaga sin desplegar nada |

Y una razón práctica que pesa: el CRM **corre en el entorno aislado**, así que
el piloto se puede ejercitar de punta a punta sin llamar a ningún tercero.
Las 11 de WispHub no admiten eso.

`cerrar_caso_crm` fue el segundo candidato y se descartó: cerrar un caso mueve
SLA, dispara CSAT y puede notificar al cliente. Es reversible, pero su efecto
sale de la plataforma — y para el **primer** piloto eso sobra.

---

# 5. GUARDS

Las nueve compuertas del bloque 7, en orden, leídas del código:

| # | Compuerta | Dónde |
|---|---|---|
| 1 | kill switch | `interruptor.veredicto` (en `frontera.autonoma`) |
| 2 | tenant válido | `frontera.autonoma` |
| 3 | nivel de autonomía | `autorizacion.veredicto` (cruza el techo) |
| 3b | etapa + prerequisito B-7 | `autonomia2.veredicto` |
| 4 | autorización granular | `autorizacion.veredicto` |
| 5 | aprobación previa | `motor.py:2005` → `es_accion_autonoma(aprobada_por_humano)` |
| 6 | previas | `motor.py:3190` → `_previas_no_cumplidas` |
| 7 | idempotencia | `idempotencia.ejecutar` |
| 8 | frontera de efecto | `http.py` → `frontera.exigir` |
| 9 | auditoría | `frontera._bitacora` → `asistente.ejecucion_autonoma` |

**Si cualquiera falla, no ejecuta**, y todas fallan cerrado: «no se pudo
comprobar» bloquea. Medido: con la base caída al leer la autorización, el
veredicto es `AUTORIZACION_DESCONOCIDA` y **no sale ninguna llamada**.

## El sistema no puede elevarse solo (§6)

- Ni `autonomia2.py` ni `autorizacion.py` contienen un solo `insert`: **solo
  leen**. Comprobado por AST.
- Ningún módulo del núcleo inserta en `autorizacion_herramienta` ni en
  `nivel_autonomia`. El `GRANT` de la migración se lo da únicamente a
  `autonomia_operador`, la misma identidad administrativa que mueve el kill
  switch; `app_backend` (el runtime) solo tiene `SELECT`.
- `autonomia2.py` no menciona `interruptor.detener` ni `reactivar`: **no toca
  el kill switch**.
- Fuera de la lista blanca no se ejecuta: autorizar `crear_tag_crm` **no**
  autoriza `cerrar_caso_crm` — medido, con las dos en la misma corrida.

---

# 6. IDEMPOTENCIA

No se creó un segundo mecanismo. Se usa `asistente.operaciones_externas` a
través de `idempotencia.ejecutar`, sin tocarlo. Medido:

| Caso | Resultado |
|---|---|
| misma clave + mismos argumentos | **1 llamada** (la segunda devuelve lo guardado) |
| misma clave + argumentos distintos | **rechazada**, 1 llamada en total |
| **6 hilos** con la misma clave a la vez | **1 llamada** |
| la llamada externa falla | la operación queda `fallida`, no a medias, y el permiso no queda abierto |
| reintento | explícito (`reintentar_fallida`), no automático |

## `[HALLAZGO]` Un fail-open latente en `idempotencia.ejecutar`

El `if` que interpreta la decisión del reclamo cubre `repetida`, `en_curso`,
`rechazada` y `fallida`; **cualquier otro valor cae al final y ejecuta**. Hoy no
es alcanzable: el único productor (`db.py::reclamar_operacion_externa`) devuelve
exactamente esos cuatro más `ejecutar`.

Lo encontré porque me mordió: escribí un stub de prueba con nombres de decisión
inventados, y **el módulo ejecutó igual** — una prueba en verde que no probaba
nada. Eso es exactamente lo que pasaría si algún día se agrega una decisión
nueva y se olvida la rama.

**No lo parcheé**: está fuera de lo que este bloque autoriza a modificar. Queda
reportado.

---

# 7. AUDITORÍA

`asistente.ejecucion_autonoma` registra, por decisión: tenant, propuesta,
herramienta, autorización, nivel efectivo, clave de idempotencia, timestamp,
decisión, código, motivo, actor, evidencia, resultado y error.

Dos decisiones que importan:

- **Se registra lo PERMITIDO, no solo lo bloqueado.** Una bitácora que solo
  guarda rechazos no puede contestar «¿qué ejecutó el sistema solo la semana
  pasada?», que es para lo que existe.
- **No guarda secretos ni credenciales** — comprobado sobre la fila escrita.

Y **no es una segunda cola** (§3), comprobado de tres formas:

1. Ninguna clase `AssistantTask` / `AIAction` / `ExecutionQueue` /
   `AutonomyQueue` / `ApprovalQueue` existe — por AST, no por texto.
2. La base **rechaza** `decision='pendiente'` por restricción `check`.
3. No tiene columnas de agenda (`estado`, `reclamado_por`, `vence_en`,
   `intentos`, `proximo_intento`) ni `for update skip locked`.

La única cola de trabajo sigue siendo `PropuestaSupervisor`.

---

# 8. PRUEBAS

`tests/test_autonomia2.py` — **todo en verde**. Los 20 casos del bloque 12 más
cuatro guardas:

| # | Caso | Resultado |
|---|---|---|
| 1 | tool autorizado ejecuta | 1 llamada |
| 2 | tool no autorizado no ejecuta | 0 llamadas · y autorizar una no autoriza la de al lado |
| 3 | autonomía insuficiente | techo 0 y techo 1 bloquean; techo 1 + autorización 4 → efectivo **1** |
| 4 | autonomía OK pero B-7 NO-GO | bloquea con `B7_REQUERIDO`, **y sin ese secreto la misma llamada sí pasa** |
| 5 | kill switch detenido | bloquea, y **con su propio motivo**, no con el de Autonomía 2 |
| 6/7 | propuesta ≠ autorización | ningún módulo inserta autorizaciones; una propuesta con origen declarado no sustituye a la autorización |
| 8 | autorización ≠ ejecución | consultarla no ejecuta nada |
| 9 | idempotencia | ver §6 |
| 10 | concurrencia | 6 hilos → 1 llamada |
| 11 | tenant incorrecto | `ACCION_EXTERNA_TENANT_DISTINTO`; y sin tenant no autoriza nada |
| 12 | evidencia insuficiente | la puerta humana no abre sin actor ni sin evidencia |
| 13 | previas faltantes | `reiniciar_ont` sin historial reporta las dos que le faltan |
| 14 | autorización revocada | `AUTORIZACION_REVOCADA`, 0 llamadas |
| 15 | expirada / aún no vigente / **ilegible** | `EXPIRADA`, `AUN_NO_VIGENTE`, `DESCONOCIDA` — las tres bloquean |
| 16 | auditoría | registra permitido y bloqueado, con código, sin secretos |
| 17 | rollback | operación `fallida`, permiso cerrado |
| 18/19/20 | R3 y R4 | las 5 bloqueadas **con todo lo demás en verde y nivel 4** |
| G1 | no hay segunda cola | ver §7 |
| G2 | ≤ 3 herramientas | 1, y ninguna R3/R4 |
| G3 | no se eleva solo | ver §5 |
| G4 | etapa apagada por omisión | `''`, `'0'`, `'false'`, `'no'`, `'quizas'` **no** encienden |

**Se afirma el efecto, no el mecanismo**: casi todos los casos cuentan llamadas
al ejecutor HTTP. Y donde hay un cero, se demuestra que el instrumento dispara —
el caso 4 comprueba que sin el secreto de B-7 la misma llamada **sí** pasa, así
que el cero de arriba era B-7 y no otra cosa.

## Contra PostgreSQL real (entorno aislado)

Lo que las pruebas sin base no pueden cubrir. Migración aplicada en `pg-b7`,
**todo en verde**: las columnas existen; el «más reciente gana» funciona; una
revocación tapa sin borrar; `limites` vuelve como dict; la base rechaza una
vigencia invertida, un nivel fuera de 0–4 y una decisión `'pendiente'`.

---

# 9. REGRESIÓN

## Núcleo: **86 de 88 archivos**

Antes del cambio: 84 de 87. Después: 86 de 88 (el archivo nuevo incluido).

Los **2 que fallan son previos y ajenos**: `test_p2_inerte` (guarda del
scheduler: «nadie llama a `job_claim`…») y `test_reloj` (barridos sin datos de
conexión). Comprobado: **0 menciones** de Autonomía 2 en su salida, y ninguno
importa `frontera`, `autonomia2` ni `autorizacion`.

## `[IMPORTANTE]` Cinco archivos de prueba existentes cambiaron de expectativa

No los relajé: **el contrato cambió y hay que decirlo**.

| Archivo | Qué pasó |
|---|---|
| `test_activar_catv.py` | esperaban que, con el kill switch **activo**, una escritura autónoma se ejecutara. Ahora necesita además la etapa, el prerequisito de B-7 y una autorización granular |
| `test_adjuntar_archivo.py` | ídem |
| `test_idempotencia_externa.py` | ídem |
| `test_interruptor_autonomia.py` | ídem |
| `test_alta_tenant_autonomia.py` | ídem |

En los cinco se declara la **respuesta de la base**, igual que ya declaraban el
interruptor — nunca se desactiva el gate, y el camino del código sigue siendo el
real. En `test_interruptor_autonomia` el orden importa y está comprobado: con el
switch `detenido`, el motivo del bloqueo **sigue siendo el suyo**, no el de
Autonomía 2.

**La consecuencia que hay que entender:** volver a levantar el kill switch **ya
no re-habilita las escrituras autónomas**. Ahora hacen falta además la etapa y
una autorización por herramienta. Es lo que pide el bloque 6, y es un
endurecimiento — pero cambia el comportamiento del sistema entero, no solo el
del piloto.

## Una guarda mía me atrapó, y la satisfice declarando

`test_timeout_interruptor` afirma el **inventario exacto** de funciones que usan
el timeout corto del gate. Mis cuatro funciones nuevas lo usan, así que falló.
Las agregué a la lista **con su justificación**, sin relajar la comprobación:
sigue siendo un conjunto exacto, y una función nueva que se ponga ese timeout
sin pasar por ahí volverá a hacerla fallar.

## CRM (Django): M02 / M03 / M09 / M11

`django-crm/backend` **no importa nada de `nucleo/`** (grep completo: 0
coincidencias), así que este cambio no puede alcanzarlo. Verificado igual.

`test_m09f_gobernanza` — incluida la guarda
`test_no_existe_ninguna_ruta_de_ejecucion` — **pasa**. Los dos fallos de ese
archivo (`test_la_rls_de_la_tabla_esta_puesta_y_forzada` y
`test_dos_hilos_reales_compitiendo_dejan_una_sola_decision`) son de **entorno**:
uno consulta `pg_policies` y el otro necesita dos conexiones reales, y la suite
corre sobre SQLite.

---

# 10. B-7

**Es un prerequisito, y se MIDE — no se declara.**

`autonomia2.veredicto_b7()` pregunta a la base si el GUC
`app.settings.jwt_secret` sigue puesto. Si está, contesta `B7_REQUERIDO`:
mientras ese secreto exista, `crm_user` puede leerlo y firmar un token
`service_role` con `BYPASSRLS` sobre 129 de 135 tablas — o sea que el privilegio
que B-7 retira se recupera por otra vía.

No es una bandera `B7_GO` que alguien pueda poner en `true` de memoria. Es la
misma lección de todo el proyecto: **una prueba que afirma que un mecanismo
existe no prueba que funcione**; la ausencia del secreto sí es medible.

`[LÍMITE HONESTO]` Mide **un** vector — el que B-7 dejó abierto y documentado.
**No prueba que B-7 esté cerrado del todo**: eso incluye además rotar el secreto
y cambiar `DBUSER`, cosas que esta consulta no ve. Es un prerequisito
**necesario, no suficiente**.

Y no toca el kill switch: ni lo lee ni lo mueve, como pide el bloque 8.

---

# 11. PRODUCCIÓN

**Cero modificaciones.** Medido al cerrar, con `transaction_read_only = on`:

```
asistente.nivel_autonomia            existe=False  ok
asistente.autorizacion_herramienta   existe=False  ok
asistente.ejecucion_autonoma         existe=False  ok

kill switch: Rapilink | detenido | migracion | 2026-09-17   (sin tocar)

tablas en public         135    ok
roles                    41     ok
django_migrations        192    ok
tablas con FORCE RLS     66     ok
case                     213    ok
operaciones_propuesta    0      ok
DBUSER efectivo: postgres
```

No se ejecutaron efectos reales, no se llamó a WispHub ni a SmartOLT, no se tocó
Dokploy, no se modificó RLS, no se creó ningún `service_role`, no se modificó
M09 ni M11. Todo se probó en el entorno aislado.

---

# 12. QUÉ QUEDA LISTO PARA ACTIVAR

## El interruptor, apagado

Uno solo, declarado en `.env.example`:

```
AUTONOMIA_2_ACTIVA=
```

Apagado por omisión y **falla cerrado**: solo un sí explícito lo enciende. En el
`.env` de este equipo **no está**. `OFF → ON` sin tocar una línea de código.

## Pero encenderlo no alcanza — y es a propósito

Para que `crear_tag_crm` se ejecute sola hacen falta **cuatro** cosas, y ninguna
implica desplegar código:

1. **B-7 = GO** — en concreto, que el GUC `app.settings.jwt_secret` ya no esté.
   Hoy sigue ahí, así que la respuesta es `B7_REQUERIDO` aunque se encienda todo
   lo demás.
2. **Aplicar la migración** `supabase/202609191430_autonomia2_autorizacion.sql`.
3. **Fijar el techo y autorizar la herramienta**, con la identidad
   administrativa (`autonomia_operador`), nunca desde el runtime ni desde Django
   Admin:

```sql
INSERT INTO asistente.nivel_autonomia
  (organization_id, nivel, nivel_anterior, actor, motivo)
VALUES ('<org>', 2, 0, '<quien>', 'piloto Autonomía 2');

INSERT INTO asistente.autorizacion_herramienta
  (organization_id, herramienta, estado, nivel_maximo,
   autorizado_por, motivo, limites, vigente_hasta)
VALUES ('<org>', 'crear_tag_crm', 'autorizada', 2,
        '<quien>', 'piloto', '{"por_dia": 20}'::jsonb,
        now() + interval '30 days');
```

   La vigencia es una decisión suya: con `vigente_hasta` el piloto se apaga
   solo; sin él, hay que revocarlo a mano.

4. **Levantar el kill switch**, que hoy está `detenido`.

## Cómo se apaga

Cualquiera de las cuatro, en orden de menos a más brusco:

```sql
-- solo esta herramienta
INSERT INTO asistente.autorizacion_herramienta
  (organization_id, herramienta, estado, estado_anterior, nivel_maximo,
   autorizado_por, motivo)
VALUES ('<org>', 'crear_tag_crm', 'revocada', 'autorizada', 2,
        '<quien>', '<por qué>');

-- toda la empresa, sin borrar autorizaciones
INSERT INTO asistente.nivel_autonomia
  (organization_id, nivel, nivel_anterior, actor, motivo)
VALUES ('<org>', 0, 2, '<quien>', '<por qué>');
```

o `AUTONOMIA_2_ACTIVA=` vacío (toda la plataforma), o el kill switch (corte de
emergencia). **Ninguna requiere desplegar.**

## Lo que NO quedó hecho, dicho explícitamente

- **No hay CLI de autorización.** El kill switch tiene `cli/autonomia.py`; esto
  no. Autorizar hoy es un `INSERT` con la identidad administrativa. Es
  suficiente para un piloto de una herramienta y **no** es lo que quiere una
  operación real — si el piloto sigue, el siguiente paso natural es esa CLI.
- **Los `limites` se guardan pero no se aplican.** La columna existe y viaja en
  el veredicto; el código que haría cumplir `{"por_dia": 20}` **no está
  escrito**, y hay un código (`LIMITE_DE_AUTORIZACION_EXCEDIDO`) reservado sin
  usar. Lo digo en vez de dejar que el campo parezca un control.
- **`PropuestaSupervisor` sigue sin ejecutar nada.** Sigue en Shadow Mode y la
  guarda `test_no_existe_ninguna_ruta_de_ejecucion` sigue en verde. Cuando
  alguien conecte «propuesta aceptada → ejecutar», tendrá que pasar por
  `frontera.autonoma()`, que ya exige todo lo de arriba.

---

## RESUMEN

**La autorización granular existe y decide.** Tres tablas append-only, el techo
cruzado con el menor, lectura sin caché y fail-closed. El control vive dentro de
`frontera.autonoma()`, no en los llamadores, así que un camino nuevo queda
cubierto aunque no sepa que esto existe. Autorizar una herramienta no autoriza
la de al lado — medido con las dos en la misma corrida.

**El piloto es una sola herramienta: `crear_tag_crm`.** Escribe en el CRM
propio, no llega a ningún cliente, se revierte borrando una etiqueta, y es la
única clase de R2 que puede ejercitarse de punta a punta en el entorno aislado
sin llamar a un tercero.

**B-7 funciona como prerequisito porque se mide, no porque se declare.** El
motor pregunta a la base si el vector de escalamiento sigue abierto. Hoy lo
está, así que la respuesta es `B7_REQUERIDO` aunque se encienda todo lo demás.

**Dos cosas incómodas que prefiero decir.** Encontré un *fail-open* latente en
`idempotencia.ejecutar` —una decisión desconocida cae al final y ejecuta—, no
alcanzable hoy y sin parchear porque está fuera de lo autorizado; me mordió a
mí, con un stub de nombres inventados que puso una prueba en verde sin probar
nada. Y **cinco pruebas existentes cambiaron de expectativa**: levantar el kill
switch ya no basta para que una escritura autónoma salga. Es el endurecimiento
que pide el bloque 6, pero cambia el sistema entero, no solo el piloto.

**Nada está activado.** Interruptor apagado, tablas ausentes de producción, kill
switch `detenido`, `DBUSER` en `postgres`, producción sin una sola diferencia
contra su baseline.

---

**No se hizo commit. No se desplegó. No se activó autonomía productiva. No se
tocó M09, M11 ni el kill switch.**
