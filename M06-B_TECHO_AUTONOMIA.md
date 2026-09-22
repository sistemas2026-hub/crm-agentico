# M06-B — Techo de autonomía por niveles

Fecha: 21/09/2026 · Rama local: `fix/integracion-wisphub` · **Sin commit, push,
PR ni deploy. Sin migraciones aplicadas en ningún entorno persistente.**

## Resumen

El techo **ya existía**: `asistente.nivel_autonomia`, de Autonomía 2. Es un
techo por empresa, de solo agregar; el runtime lo puede leer pero no escribir,
y lo escribe una identidad separada, `autonomia_operador`. Este bloque **no creó
un segundo mecanismo**: lo convirtió en un control real.

**Lo que se construyó:**

1. Un paso propio en la frontera, justo después del kill switch. Antes el techo
   estaba escondido dentro de la autorización granular.
2. Una única lectura del techo, que **falla cerrado sin asumir un nivel**. Antes,
   "sin fila" se leía como 0.
3. RLS por empresa. La tabla no la tenía.
4. Un nivel por acción, con el mismo valor de siempre por defecto: **no se
   reasignó ninguna herramienta**.
5. Un tope de política global igual a 3.
6. Un único camino de cambio: la CLI de operador, con compare-and-set y cada
   intento auditado.

**Producción no cambia de comportamiento.** No se fijó ningún techo. La etapa
de Autonomía 2 sigue apagada, y aunque se encendiera contesta `B7_REQUERIDO`.
No se habilitó ni el nivel 2 ni el 3.

**Un hueco que se cerró de paso** (sección 4). `agregar_promesa_pago`, que es R4
y declara aprobación humana, podía salir por la puerta autónoma si alguien le
daba techo, etapa y autorización granular. Ahora no puede. Sin eso, la prueba 8
no se cumplía para esa herramienta.

---

## 1. Archivos modificados

| Archivo | Cambio |
|---|---|
| `nucleo/seguridad/techo.py` | **Nuevo.** Niveles, tope de política, lectura que falla cerrado, veredicto, `cambiar()` con sus rechazos |
| `nucleo/seguridad/frontera.py` | El paso del techo en `autonoma()` y `critica()`; nivel requerido; en `exigir()`, lo que declara aprobación humana no sale autónomo |
| `nucleo/seguridad/autorizacion.py` | `nivel_de` lee el techo de `techo.py`: una sola lectura, las dos capas no pueden discrepar |
| `nucleo/persistencia/db.py` | Lectura con la organización de la fila y la consultada; `registrar_cambio_techo` (operador, lock, compare-and-set, repetición); `registrar_intento_techo`; `historial_techo` |
| `nucleo/modelo/motor.py` | Pasa el nivel **de la herramienta** a la frontera (conversación, ruta de servicio, irreversible); 8 códigos de bloqueo |
| `nucleo/config/schema.py` | `Herramienta.nivel_autonomia` (opcional, 0..3; una escritura no puede declarar 0) |
| `nucleo/seguimiento/forzado.py` | Los 8 códigos, para que un bloqueo no fuerce una escalada |
| `cli/autonomia.py` | `--techo N --desde M`, único canal; la consulta muestra el techo |
| `supabase/202609211900_techo_autonomia.sql` | **Nueva, sin aplicar** (sección 12) |
| `django-crm/frontend/.../conversaciones/[id]/+page.svelte` | Los 8 motivos en palabras |
| `tests/test_m06b_techo_autonomia.py` | **Nuevo**: 93 comprobaciones sin base |
| `tests/test_m06b_techo_postgres.py` | **Nuevo**: 20 comprobaciones contra Postgres descartable |
| `tests/test_autonomia2.py` | La guarda "el runtime no se autoriza" pasa a AST: admite el INSERT del techo **solo** dentro de una función que abre la sesión como `autonomia_operador` |
| `tests/test_autonomia2_preactivacion.py` | Techo 4 → 3 en el punto 6: 4 ahora es inválido, y con 4 el punto habría pasado por el motivo equivocado |
| `tests/test_m06a_gate_critico.py` | Con techo 1, el bloqueo ahora lo da el paso del techo, antes que la autorización |
| `tests/test_timeout_interruptor.py`, `test_escalada_forzada.py` | La función nueva del gate y los códigos nuevos, por nombre |
| 7 archivos de prueba (`test_autonomia2*`, `test_interruptor_autonomia`, `test_idempotencia_externa`, `test_alta_tenant_autonomia`, `test_m06a_gate_critico`) | Solo la **simulación** de la lectura del techo: ahora devuelve la organización de la fila, como la función real. Ninguna aserción cambió |
| `PRD.md`, este informe | Documentación |

## 2. Modelo y configuración

| Nivel | Nombre | Qué permite |
|---|---|---|
| 0 | observar | ver, analizar, proponer; ningún efecto |
| 1 | recomendar | recomendar; toda ejecución la hace una persona |
| 2 | coordinar | coordinación de bajo riesgo, autorizada |
| 3 | ejecutar autorizado | acciones reversibles y previamente autorizadas |

- **Dónde vive el techo:** `asistente.nivel_autonomia`, una fila por cambio, y el
  vigente es el más reciente. Cada empresa tiene el suyo.
- **Tope de política global:** `techo.TECHO_MAXIMO_POLITICA = 3`, una constante
  **del núcleo**. Si viviera en la configuración de la empresa, la empresa
  podría subirlo. El 4 de la escala de M09-J ("crítico, siempre humano") no se
  puede fijar como techo: lo crítico lo gobierna el gate de irreversibles, no un
  número.
- **Nivel exigido por acción:** `Herramienta.nivel_autonomia`. Sale del catálogo,
  **nunca** de los argumentos de la llamada. Si no lo declara, una lectura exige
  0 y una escritura exige 2, que es lo mismo que la autorización granular pedía
  antes. Ninguna de las 69 herramientas lo declara. Las pruebas de niveles 1 y 3
  usan **copias en memoria** del piloto `crear_tag_crm`.

## 3. Flujo exacto del techo

```
acción autónoma (conversación · ruta de servicio · irreversible aprobada)
  nivel exigido = Herramienta.nivel_autonomia del CATÁLOGO (default: 2; nunca < 1 en escritura)
  │
  frontera.autonoma() / frontera.critica()
    1  tenant válido
    2  kill switch ─────────────── detenido → bloquea (el techo ni se consulta)
    2b TECHO ───────────────────── techo.veredicto(tenant, nivel exigido)
         leer(): sin fila → AUSENTE · fuera de 0..3 / no entero → INVALIDO
                 ilegible → NO_LEGIBLE · tabla ausente → NO_INSTALADO
                 fila de otra empresa → DE_OTRO_TENANT
         techo < exigido → INSUFICIENTE
    3  etapa Autonomía 2 (+B-7)
    4  autorización granular: min(techo, autorización) ≥ exigido, con el MISMO techo
   (5  aprobación atada: solo en critica)
    6  auditoría → 7 permiso → 8 idempotencia
    9  último metro (exigir): irreversible → solo permiso crítico;
                               declara aprobación humana → nunca permiso autónomo
   10  efecto
```

`humana()`, que es la aprobación de una persona para algo no irreversible, **no**
consulta el techo. El techo gobierna decisiones autónomas, igual que el kill
switch. La prueba lo comprueba por AST.

## 4. Integración con la frontera existente

- **No se quitó ni se reordenó ningún control.** El techo es un paso nuevo entre
  el kill switch y la etapa, en `autonoma()` y en `critica()`. El orden está
  verificado por AST en las dos puertas.
- **La autorización granular sigue cruzando** `min(techo, autorización)`, pero
  ahora lee el techo de `techo.py` y recibe el mismo nivel exigido. Si alguien
  saca el paso del techo, la autorización todavía frena: la mutación A lo mostró
  (sección 10).
- **Las barreras de M06-A no cambiaron.** Siguen las mismas cuatro
  irreversibles con el mismo código de bloqueo, y la batería de M06-A pasa entera
  (prueba 20). El control nuevo de `exigir()` se evalúa **después** del de las
  irreversibles, así que su código no se pisa.
- **Control agregado:** una herramienta con `aprobacion_humana` que llegue al
  ejecutor con permiso autónomo no sale (`APROBACION_HUMANA_REQUERIDA`). Ningún
  camino legítimo lo necesitaba, porque ninguna herramienta con aprobación es
  invocable por servicio. Por su camino de aprobación sigue saliendo igual; está
  probado.

## 5. Fail-closed

Ningún caso se convierte en un número. Cada uno tiene su código y todos bloquean.

| Situación | Código |
|---|---|
| Sin fila | `TECHO_AUTONOMIA_AUSENTE` (antes se leía como 0) |
| Valor fuera de 0..3, no entero, bool, `None`, texto, lista, o un 4 heredado | `TECHO_AUTONOMIA_INVALIDO` |
| Error al leer (base caída, timeout) | `TECHO_AUTONOMIA_NO_LEGIBLE` |
| Tabla sin instalar (SQLSTATE 42P01) | `TECHO_AUTONOMIA_NO_INSTALADO` |
| Fila de otra empresa, o sin la organización | `TECHO_AUTONOMIA_DE_OTRO_TENANT` |
| La acción declara un nivel que no existe | `NIVEL_REQUERIDO_INVALIDO` |

Los 8 códigos, incluido `APROBACION_HUMANA_REQUERIDA`, están en las tres listas
que tienen que coincidir: motor, `forzado.py` y la pantalla. Así se cuentan como
bloqueo y no fuerzan una escalada con un motivo falso.

## 6. Aislamiento por tenant

Son tres capas, y cada una se probó por separado:

1. **La consulta** filtra por la organización resuelta para el tenant.
2. **RLS** (nueva) sobre `nivel_autonomia` y `techo_autonomia_intentos`, para
   `app_backend` y para `autonomia_operador`. Probada en Postgres: como runtime
   de la empresa B se leen **0** filas de A, aun pidiendo las de A
   explícitamente. El operador en la sesión de A **no** puede escribir el techo
   de B.
3. **El código** exige que la organización de la fila sea la consultada. Si no
   coinciden, o falta alguna de las dos, no ejecuta.

Además, un permiso abierto con el techo de una empresa no escribe en otra
(`TENANT_DISTINTO`).

## 7. Cómo se impide que el agente eleve su propio nivel

| Barrera | Qué impide | Probado |
|---|---|---|
| **Base**: `app_backend` sin INSERT/UPDATE/DELETE sobre el techo; la migración **falla** si alguien se lo concede | el runtime no puede escribirlo | Postgres: INSERT rechazado; migración con el permiso concedido: falla |
| **Base**: el runtime solo puede anotar intentos `rechazado` | que se fabrique un "aplicado" | Postgres: rechazado por RLS |
| `cambiar()` se niega con una acción en curso (permiso abierto) | una herramienta, una aprobación (crítica o humana) o un agente ejecutando no mueven el techo bajo el que corren | 3 casos |
| `cambiar()` exige origen `cli:` | turno, evento, `accion_aprobada:`, propuesta, servicio | 7 orígenes rechazados |
| `cambiar()` rechaza actores del sistema | motor, Supervisor NOC IA, sistema, agente, asistente, aprobación, reloj, vacío | 8 actores rechazados |
| El nivel exigido sale del **catálogo** | que el modelo pase `nivel_autonomia: 0` o `techo: 3` en argumentos | no cambia nada |
| **Estática** (AST en `nucleo/`, `cli/`, `django-crm/backend`) | solo `cli/autonomia.py` llama a `techo.cambiar` | ok |
| **Estática** | Django (Supervisor NOC IA) no referencia la tabla del techo | ok |
| **Estática + HTTP** | ninguna de las rutas del motor habla de techo o nivel; `POST` con `{nivel: 3}` a rutas plausibles → 404 y 0 cambios | ok |

**Límite, dicho:** actor y origen los declara quien llama. Lo que los vuelve
confiables no es la validación de texto sino dos cosas: que solo la CLI de
operador llega a `cambiar()`, y que solo `autonomia_operador` escribe en la
base. Si un proceso tiene las credenciales de `postgres` y puede hacer SET ROLE,
puede escribir. Es la misma frontera que ya tenía el interruptor (paso 10.12).

## 8. Auditoría de cambios

`asistente.techo_autonomia_intentos` (nueva, solo agregar) guarda **cada**
intento con estos campos: empresa, nivel anterior, nivel solicitado, quién,
cuándo, motivo, origen, resultado y código. Los resultados posibles son
`aplicado`, `repetido`, `conflicto` y `rechazado`.

- Un `aplicado` se escribe en la **misma transacción** que el techo.
- Un rechazo del código (por ejemplo, actor del sistema) también queda
  registrado.
- La transición en sí queda en `nivel_autonomia`, con `nivel_anterior`, `actor`,
  `motivo`, `origen` y fecha.

Verificado contra Postgres: un cambio real dejó todos los campos, y un intento
de "motor" quedó registrado como `rechazado` con su código.

## 9. Pruebas ejecutadas

**`tests/test_m06b_techo_autonomia.py`** (código real: frontera, ejecutor y
motor; base y red simuladas): **93 comprobaciones, 0 fallas.**

| # | Resultado |
|---|---|
| 1 | Techo 0 bloquea una acción de nivel 1 (`INSUFICIENTE`, 0 llamadas) |
| 2 | Techo 1 deja pasar el techo a una de nivel 1; la frena la barrera siguiente (sin autorización granular, o etapa apagada) |
| 3 | Techo 1 bloquea una de nivel 2 |
| 4 | Techo 2 con todo en regla: la de nivel 2 **sale** (1 escritura) |
| 5 | Techo 2 bloquea una de nivel 3 |
| 6 | Techo 3 deja pasar el techo a una de nivel 3; una autorización de nivel 2 la frena; con autorización de nivel 3, sale |
| 7 | Las 3 R3 con techo 3 y sin aprobación: bloqueadas por aprobación y en el último metro, 0 llamadas |
| 8 | R4 `registrar_pago`, igual. R4 `agregar_promesa_pago` con techo 3 y autorizada: bloqueada (`APROBACION_HUMANA_REQUERIDA`); aprobada por una persona, sale por su camino |
| 9 | Kill switch tirado con techo 3: bloquea en `autonoma` y en `critica`, **sin consultar el techo** (0 lecturas) |
| 10 | 8 valores inválidos, 2 errores de lectura, tabla ausente y nivel exigido inexistente: todos bloquean |
| 11 | Sin fila: `AUSENTE`; la autorización granular lee el mismo techo y también bloquea |
| 12 | Fila de otra empresa, o sin organización: `DE_OTRO_TENANT`; un permiso de una empresa no escribe en otra |
| 13–15 | Sección 7 |
| 16 | Aplicado: se registran empresa, nuevo, anterior, quién, motivo, origen; rechazado: queda con su código |
| 17 | 4, 5, 99, −1, "3", 3.0 y `True` rechazados; el catálogo rechaza nivel 4 y el nivel 0 en una escritura |
| 18 | Conflicto: no se aplica; repetición: `repetido` (la concurrencia real va en la prueba de Postgres) |
| 19 | 69 herramientas y 27 escrituras; R1=3, R2=19, R3=3, R4=2; ninguna declara nivel; exigencia efectiva 0 y 2, igual que antes |
| 20 | Las mismas 4 irreversibles, y la batería de M06-A pasa entera (**89** comprobaciones) |
| Especiales | Supervisor NOC IA, propuesta, herramienta, petición manipulada y tenant diferente: todos rechazados |

**`tests/test_m06b_techo_postgres.py`**: el código real contra una base
**creada y borrada** dentro del contenedor local `pg-b7`, corrida en la imagen
del motor con el `.env` real tapado por uno vacío. La prueba **se niega** a
correr contra cualquier host que no sea `pg-b7` (probado: devuelve 2), y sin la
variable se reporta **omitida**, no en verde. Resultado: **20 comprobaciones, 0
fallas.**

- Migración: aplica con un 4 heredado, es idempotente, y falla si el runtime
  tuviera INSERT.
- `AUSENTE` real, e `INVALIDO` para el 4 heredado.
- El runtime no escribe el techo (`InsufficientPrivilege`).
- Un cambio de operador queda auditado con todos los campos.
- RLS: B ve 0 filas de A y 0 intentos, y el operador de A no escribe en B.
- Un 4 escrito directo en la tabla se rechaza (`CheckViolation`).
- El runtime no puede fabricar un `aplicado`, y un agente que intenta subir el
  techo queda rechazado y auditado.
- **Diez operadores a la vez**: exactamente 1 aplicado y 9 en conflicto, con
  historial `[(2, None), (3, 2)]`.
- Reenviar el pedido ganador da `repetido`, sin fila nueva.
- La base descartable quedó borrada (verificado: 0).

## 10. Resultado de pruebas y desarme

Cada control se rompió a propósito, uno por vez, y la prueba lo detectó. Después
de cada mutación el archivo volvió byte a byte a su estado original (sha256).

| Control desarmado | Fallas | Qué se vio |
|---|---|---|
| A. `autonoma` consulta el techo | 6 | La autorización granular todavía frena: es defensa en profundidad, pero el paso propio desapareció y la prueba lo nota |
| B. Sin fila → 0 (lo de antes) | 2 | `AUSENTE` pasa a `INSUFICIENTE` |
| C. Comprobar la empresa de la fila | 3 | La fila de otra empresa **pasa** |
| D. Tope en la lectura | 6 | El techo 4 o 99 **pasa** |
| E. No cambiar desde una acción | 3 | Se podía cambiar desde las 3 puertas |
| F. Origen de operador | 7 | Turno, evento y aprobación podían moverlo |
| G. Aprobación humana no sale autónoma | 1 | `agregar_promesa_pago` **sale**: 1 llamada |
| H. Nivel desde la herramienta | 5 | Se ignora el nivel declarado |
| Guarda de `test_autonomia2` (INSERT del techo como runtime) | 1 | Nombra `db.py::registrar_cambio_techo` |

En la mutación G la etiqueta decía "0 llamadas" con la prueba en rojo. Era otra
vez un número escrito a mano; se corrigió y ahora muestra "1 llamadas".

## 11. Regresión completa

**Motor (`tests/`, 94 archivos, uno por uno con su exit code): 92 de 94 en
verde.**

- La corrida final dio 91. El que faltaba era `test_adjuntar_archivo`: su
  simulación del techo no traía la organización de la fila y el techo nuevo la
  bloqueaba, que es el fail-closed funcionando. Se le agregó el dato, igual que
  a las demás, y quedó en verde, verificado por separado después.
- `test_m06b_techo_postgres` figura en verde porque en el host se **omite**, y
  lo dice. Su resultado real (20 de 20) es el de la corrida en contenedor.
- Las dos fallas que quedan son **preexistentes y demostradas** en M06-A:
  - `test_p2_inerte` señala archivos del 17/09 que este bloque no tocó;
  - `test_reloj` espera 4 herramientas de importación y hay 5; la quinta ya está
    en `HEAD`.

**Django (backend completo, base descartable `pg-b7`):**
`2 failed, 4585 passed, 43 skipped` en 19:46. Es idéntico a M05-B, M06-A y la
corrección de M06-A: **0 fallos nuevos**. Los dos son los mismos ya
demostrados:

- `test_docs_environment_variables`: falla igual contra `origin @ 73bb30c`.
- `test_portal_rls`: corre como `admin`, que tiene `BYPASSRLS`.

**Nota sobre fines de línea:** los scripts de edición de este bloque dejaron
algunos archivos del árbol local en CRLF. El repo tiene `core.autocrlf=true`, así
que git normaliza a LF al hacer commit. Se verificó con `git diff --numstat`:
solo aparecen las líneas cambiadas, no archivos enteros. Los scripts que corren
en contenedores están protegidos por `.gitattributes`.

## 12. Migraciones

`supabase/202609211900_techo_autonomia.sql` es **nueva, está revisada y se
probó en Postgres descartable. No se aplicó en ningún entorno persistente.**

Qué hace:

- Agrega `origen`.
- Agrega el tope `nivel between 0 and 3` como NOT VALID: una fila vieja con 4 no
  rompe la migración, y el código la lee como inválida.
- Activa RLS y la fuerza, con políticas para `app_backend` (solo lectura) y para
  `autonomia_operador`.
- Crea la tabla de intentos, con su RLS: el runtime solo inserta `rechazado`.
- Comprueba al final que el runtime no tenga escritura sobre el techo.

**Orden de despliegue** (cuando se autorice): esta migración va después de
`202609191430_autonomia2_autorizacion.sql`, que tampoco consta como aplicada en
este repo. Sin ellas el código falla cerrado: sin tabla, `NO_INSTALADO`; sin la
columna `origen`, el cambio de techo falla y el operador lo ve.

Django: ninguna migración nueva. Siguen generadas y sin aplicar las de M04/M05.

## 13. Producción no fue tocada

- Sin deploy, push, commit ni PR.
- El entorno local no tiene credenciales de base cargadas: la CLI lo confirmó
  ("No hay datos de conexión").
- Toda prueba con base corrió contra `pg-b7`, local, en una base creada y borrada
  por la propia prueba.
- **No se fijó ningún techo en ningún lado. No se habilitó ni el nivel 2 ni el
  3.**

## 14. Acciones sobre clientes

Ninguna. Toda la red de las pruebas es simulada y cada llamada queda contada.
Los datos son inventados (`PRUEBA000001`, factura `999001`, dominio
`.invalid`).

## 15. WispHub y SmartOLT

No hubo llamadas reales. Las credenciales están reemplazadas por
`clave-de-prueba` y el módulo `requests` del ejecutor por uno que solo anota. No
se corrieron los casos dorados.

---

## Pendientes y decisiones

1. **Asignar niveles a las herramientas**: por ejemplo, R1→1, R2 de coordinación→2
   y reversibles→3. El mecanismo está listo; asignar niveles es una decisión que
   este bloque prohíbe tomar.
2. **Hallazgo de antes de este bloque, no introducido por él:** en este árbol,
   las escrituras internas R1 (`reportar_comprobante_pago`,
   `registrar_pedido_wifi`, `proponer_herramienta`) entran por la puerta
   autónoma. Con la etapa apagada, quedan bloqueadas.
3. `autorizacion_herramienta` y `ejecucion_autonoma` tampoco tienen RLS, igual
   que tenía el techo. No se tocaron porque están fuera del alcance.
4. `agregar_promesa_pago` ya no puede salir sola, pero su aprobación sigue sin
   estar **atada** a la acción (pendiente de M06-A).
5. Antes de habilitar el nivel 2 o el 3 en producción: aplicar las dos
   migraciones, cerrar B-7, encender la etapa y fijar el techo con la CLI.
   Cada uno es un paso con su propia autorización.
