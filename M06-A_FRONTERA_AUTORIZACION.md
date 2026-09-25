# M06-A — Frontera de acciones técnicas y autorización

Fecha: 21/09/2026 · Rama local: `fix/integracion-wisphub` · **Sin commit, push, PR ni deploy.**
Producción: **no se tocó.** Ninguna prueba ejecutó una acción sobre un cliente
real ni llamó a WispHub o SmartOLT: toda la red de las pruebas es simulada.

Este informe tiene dos partes:

- **Parte A** (la vigente): la corrección del gate de R3/R4, con los 12 puntos
  de entrega pedidos.
- **Parte B**: los 15 puntos del bloque original, actualizados al estado
  actual. Lo que la corrección volvió falso está corregido, no tachado.

---

# PARTE A — Corrección del gate R3/R4

## A.0 Lo primero que hay que saber

**Con la cadena completa que se pidió, hoy ninguna de las cuatro acciones puede
producir efecto, ni siquiera aprobada.** Las cuatro pasan por la etapa de
Autonomía 2, que está **apagada**. Aunque se encienda, contesta
**`B7_REQUERIDO`** mientras B-7 siga PARCIAL. Además cada una necesita una
autorización granular con nivel ≥ 2, que hoy no existe. Es exactamente lo que
pide el requisito 7 ("solo puede producir efecto si todas las demás barreras
también lo permiten"), pero tiene una consecuencia operativa directa. Cuando
esto se despliegue:

- un cliente que pida por WhatsApp reiniciar su ONT dejará una **propuesta** en
  la cola, y aprobarla **no la ejecutará** hasta que se cumplan las tres
  condiciones de arriba;
- lo mismo con `registrar_pago`: facturación ya no registra pagos desde el
  asistente.

Hay dos hallazgos más que agravan lo anterior:

1. **No hay pantalla que apruebe acciones.** Ningún archivo del frontend ni del
   backend de este repo llama a `/acciones/propuestas/<id>/aprobar`, y
   `operaciones/models.py` registra que esa cola ya acumuló **36 pendientes sin
   revisar** en producción.
2. **En este árbol local la conversación ya estaba bloqueada.** Un reinicio
   pedido en la conversación entra por `frontera.autonoma()`, que exige la
   etapa. Como la etapa está apagada, ese camino ya no ejecutaba nada **antes**
   de este bloque. Lo que hace que el reinicio funcione hoy en producción es
   que producción corre código anterior: `frontera.py` ni siquiera está
   versionado todavía.

Si se quiere que una aprobación humana alcance para estas cuatro sin la etapa
ni la autorización granular, eso es aflojar la cadena y es una decisión tuya.
No lo hice.

## A.1 Por qué había que modificar el mecanismo de aprobación

Sobre la frase del informe anterior (*"con la aprobación, el pago queda en la
cola y no sale ninguna llamada; sin ella, la misma corrida sí sale"*): la
prueba comparaba **la config con el gate declarado** contra **una copia con el
gate borrado**, y en ninguna de las dos corridas había una aprobación. "Sin
ella" quería decir "si alguien borra el gate de la config", que era el control
de que el instrumento distingue. El comportamiento era correcto, pero la frase
era ambigua, y la prueba no cubría el camino con aprobación. Ahora ese camino
está cubierto por las secciones B/F/H/J de `tests/test_m06a_gate_critico.py`.

Lo que el mecanismo anterior no podía garantizar, medido en el código:

| Defecto | Dónde | Consecuencia |
|---|---|---|
| "Aprobada" se escribía **después** de ejecutar, en el mismo UPDATE que el resultado | `api.py`, endpoint de aprobar | Durante el efecto no existía ningún registro de aprobación que la frontera pudiera comprobar |
| La aprobación no estaba atada a nada: `frontera.humana()` pedía solo un actor y una evidencia en texto | `frontera.py` | Con cualquier actor se podía ejecutar cualquier escritura |
| Las condiciones previas no se volvían a medir al aprobar | `ejecutar_accion_aprobada` | Un reinicio aprobado horas después se ejecutaba con la señal y el ping de antes |
| La aprobación no creaba la verificación posterior | ídem | Se perdía la comprobación de `ACCION_CONFIRMADA` |
| **Defecto nuevo:** una propuesta dejaba registrada una verificación pendiente | `motor.py`, al armar la traza | En el turno siguiente se mediría un reinicio que no ocurrió, saldría NO_CONFIRMADA y se escalaría "acción sin efecto" |
| `humana()` no consulta el kill switch | `frontera.py` | Una irreversible aprobada salía con el interruptor tirado (requisito M) |
| El camino de aprobación común convertía un bloqueo en un texto de error | `ejecutar_accion_aprobada` | Un bloqueo se contaba como falla de un tercero |

## A.2 Qué se modificó

**`Herramienta.irreversible`** (`nucleo/config/schema.py`) es el criterio R3/R4
de M10-A, llevado a la config de cada empresa porque ahora hay código que lo
aplica. El validador rechaza al cargar tres cosas: una irreversible sin
`aprobacion_humana`, una de solo lectura y una invocable por servicio. Lo
declaran exactamente las cuatro de la decisión.

**`nucleo/seguridad/aprobacion.py`** (nuevo) toma la fila **leída de la base** y
contesta si autoriza *esta* herramienta con *estos* argumentos en *este*
tenant. Tiene un código de bloqueo por cada atadura: ausente, no vigente, otro
tenant, otra herramienta, sin aprobador, sin momento, sin origen, sin huella,
otros argumentos.

**`frontera.critica()`** (nuevo) es la única puerta de las irreversibles. Recorre
la cadena entera (A.5) y abre un permiso atado a la herramienta y a la huella
de los argumentos.

**`frontera.exigir()`**, el último metro, ahora recibe los argumentos que están
por salir. Una irreversible con un permiso que no sea `critica` no sale, venga
del camino que venga. Un permiso crítico usado para otra herramienta, o con
otros argumentos, tampoco.

**`motor.py`** cambia en cuatro puntos:

- la propuesta de una irreversible guarda huella, origen y el contexto mínimo
  para volver a medir (identificadores técnicos y los argumentos de cada
  previa);
- `ejecutar_accion_irreversible()` (nuevo) pasa por la puerta crítica, comprueba
  la coherencia, **vuelve a medir las previas**, toma la medición previa de la
  verificación y ejecuta con idempotencia;
- se arregló el defecto de la verificación en las propuestas;
- `ejecutar_accion_aprobada` devuelve el código de bloqueo en vez de un texto.

**`api.py`**: para una irreversible, aprobar exige `revisado_por`. La
aprobación se **persiste antes del efecto** con compare-and-set, la fila se
relee y se ejecuta por `ejecutar_accion_irreversible`. El resultado se guarda
aparte, sin reescribir la aprobación. La verificación se anota contra la
conversación de origen; si la acción se verifica y no tiene conversación, **no
se aprueba**. Además, cada propuesta se ata a su conversación al terminar el
turno.

**Migración `supabase/202609211800_aprobacion_vinculante.sql`** (sin aplicar):
agrega `hash_argumentos`, `origen`, `contexto` y `conversation_id`, más un
trigger que vuelve inmutable la identidad de la propuesta. Para las
irreversibles también fija la aprobación: una vez `aprobada` o `rechazada`, no
se reescribe.

**Config** (`tenants/rapilink.config.yaml`, solo la semilla): las cuatro llevan
`irreversible: true` y `aprobacion_humana: true`, con una plantilla de resumen.
Las descripciones de las tres R3 y el texto `sugerir_cuando_disponible` de
`reiniciar_ont` decían **"SIN paso de aprobación humana"** y "cuéntale que ya la
reiniciaste". Se reescribieron: ahora dicen que queda solicitado y que un
colaborador lo aprueba, nunca que ya se hizo.

**Coherencia y trazas**: los 4 códigos nuevos están en `CODIGOS_DE_BLOQUEO`
(motor), en `CODIGOS_MOTOR_GUARD` (`forzado.py`) y en `MOTIVO_BLOQUEO` (pantalla
de conversaciones). Sin eso, un bloqueo se contaría como falla y forzaría una
escalada con un motivo falso. Lo exigía `test_bloqueos_en_traza`.

**Corredor de casos dorados** (`cli/evaluar.py`): una propuesta ya no cuenta
como "ejecutada". `no_usa` falla también si se *propuso*, porque una propuesta
indebida puede terminar aprobada. Se agregan `propone` y `propone_una_sola_vez`,
y tres casos pasan a afirmar la cola. Esos casos ya no reinician el equipo de
laboratorio.

## A.3 Cómo queda protegido R3 (`reiniciar_ont`, `activar_catv`, `cambiar_tipo_onu`)

1. **En la conversación no se ejecuta, se propone.** El motor las manda a la
   cola porque tienen `aprobacion_humana`. Las previas se exigen igual antes de
   proponer, y el límite por conversación cuenta la propuesta.
2. **La propuesta queda atada** a la huella de los argumentos (la ONU exacta),
   al origen (el mensaje que la pidió), a la conversación y al contexto para
   volver a medir.
3. **Al aprobar**, la cadena completa (A.5). Después, con el permiso abierto:
   - **coherencia**: la ONU de la acción es la misma con la que se van a medir
     las previas; si no, `CONTEXTO_DE_APROBACION_INCOHERENTE` y no se mide ni se
     manda nada;
   - **previas medidas de nuevo**: señal y ping (reinicio), plan con TV y CATV
     `Disabled` (activar), CATV `Not supported` (cambiar tipo). Una previa que
     no se cumple, o que no se puede medir, da `PREVIAS_NO_VIGENTES_AL_APROBAR`
     y no hay efecto;
   - **verificación**: la medición previa se toma pegada al efecto y la
     verificación se anota contra la conversación. El siguiente mensaje del
     cliente la resuelve como siempre (`ACCION_CONFIRMADA` / NO_CONFIRMADA /
     escalada).
4. **Ningún otro camino llega al equipo**: conversación, panel, ruta de
   servicio, ejecutor directo y `autonoma()` con todo en regla. Los cinco caminos
   están probados, con el caso de control que demuestra que el mismo ejecutor
   **sí** sale por la puerta crítica.

## A.4 Cómo queda protegido R4 (`registrar_pago`)

Pasa por los mismos pasos 1, 2 y 3: propuesta atada, cadena completa, huella
comparada en el último metro. No tiene previas ni verificación. La huella ata la
**factura** y la **acción**: una aprobación de la factura 999001 no paga la
999002, ni reutilizando la fila ni reutilizando el permiso. `fecha_pago` se fija
al proponer, y con `accion = 1` la reactivación del servicio también espera la
aprobación.

`agregar_promesa_pago` (también R4) **no** está en la decisión: conserva su
aprobación anterior, no atada. Queda como decisión pendiente (B.15).

## A.5 Flujo exacto de autorización de una irreversible

```
conversación ──► motor: previas (historial) ─► límite ─► PROPUESTA
                 (huella + origen + contexto; 0 efecto externo)
                            │
                  api._aprobar_irreversible
                  ├─ revisado_por obligatorio
                  ├─ si se verifica: exige conversación de origen
                  ├─ UPDATE … estado 'pendiente' → 'aprobada'  (compare-and-set)
                  └─ relee la fila de la base
                            │
motor.ejecutar_accion_irreversible
  frontera.critica:
    1 tenant → 2 kill switch → 3 etapa Autonomía 2 (+B-7)
    → 4 autorización granular (+nivel) → 5 APROBACIÓN VINCULANTE
    → 6 auditoría (bitácora 'permitida', con el aprobador) → 7 permiso crítico
  con el permiso abierto:
    coherencia de contexto → previas re-medidas → medición previa de la verificación
    → 8 idempotencia (origen = accion_aprobada:<id>)
    → 9 ejecutor HTTP → frontera.exigir: ¿crítico? ¿misma herramienta? ¿misma huella?
    → 10 efecto externo
  api: resultado aparte · verificación contra la conversación
```

El orden de los pasos 1 a 7 está verificado dos veces:

- **Por AST** sobre el código de `critica()`.
- **Por conducta**: el primer control que dice que no gana, y los siguientes ni
  se consultan. Con el kill switch tirado, la autorización granular se consulta
  **0 veces**.

## A.6 y A.7 Pruebas ejecutadas y resultado

**`tests/test_m06a_gate_critico.py`** (nuevo): **97 aserciones, 0 fallas.**

Toda la red es simulada, pero un nivel **por debajo** del ejecutor real, así
que `frontera.exigir` corre de verdad en cada prueba. `test_autonomia2`
reemplaza el ejecutor entero y con eso se salta justo ese control. Los datos son
inventados (ONU `PRUEBA000001`, factura `999001`, dominio `.invalid`).

| Req. | Qué | Resultado |
|---|---|---|
| A, E, G, I | Sin aprobación (pendiente, o sin fila) con **todo lo demás en regla** | Bloqueado · 0 llamadas · 0 lecturas, en las 4 |
| B, F, H, J | Aprobación válida con todo en regla | El efecto sale **una vez**, al endpoint correcto; la auditoría registra el aprobador; en R3 las previas se volvieron a medir; en el reinicio queda la verificación con su medición previa |
| — | Aprobación válida pero una barrera **posterior** dice que no | Señal degradada, plan sin TV, previa imposible de medir, ONU incoherente, techo de nivel en 1: bloqueado, 0 escrituras. **La aprobación no es un pase libre** |
| C | Argumentos modificados en la fila después de aprobar | `APROBACION_DE_OTROS_ARGUMENTOS`, 0 llamadas (factura y ONU) |
| D | Aprobación de la factura 999001 usada para la 999002 | Bloqueado |
| K | Aprobación de `reiniciar_ont` usada para `cambiar_tipo_onu`; permiso de reinicio usado para `activar_catv` | Bloqueado en la aprobación **y** en el último metro |
| L | Permiso del pago de 999001 usado para pagar 999002, o para un `crear_ticket` | Bloqueado en el último metro; el permiso no sobrevive a su bloque |
| — | Sin aprobador, sin momento, sin origen, sin huella, rechazada, de otra empresa | Un código propio para cada caso, 0 llamadas |
| M | Kill switch tirado + aprobación válida | Bloqueado en las 4 · 0 llamadas · 0 lecturas |
| N | La misma aprobación ejecutada dos veces | **1** escritura externa; la repetición no anota una segunda verificación |
| 5 | Orden de los controles | AST + conducta (arriba) |
| 4 | Bypass: `_ejecutar_tool`, `humana()`+ejecutor, `ejecutar_accion_aprobada`, ejecutor directo (sync y async), ruta de servicio, `autonoma()` con todo en regla | Bloqueado en las 4 × 6 · 0 llamadas; el control positivo por `critica()` sí sale |
| 4b | Estática: ningún módulo de `nucleo/` hace una escritura HTTP directa ni conoce un endpoint R3/R4 | 0 hallazgos |
| — | Conversación real (`motor.responder`, modelo de guion) pide `reiniciar_ont` | 0 llamadas; 1 propuesta con huella, origen del mensaje y contexto; **sin verificación pendiente** |
| O | R1/R2 sin este gate | `crear_ticket` aprobada sale por `humana()` como siempre, aun con el kill switch tirado y la etapa apagada; `crear_tag_crm` sale por `autonoma()` sin aprobación; las otras 23 escrituras no son irreversibles |

**Desarme: cada control se rompió a propósito y la prueba lo detectó.** Después
de cada mutación el archivo se restauró y se comprobó que su sha256 fuera
idéntico al original.

| Control desarmado | Fallas que produjo |
|---|---|
| `exigir`: irreversible exige permiso crítico | 16 (todos los bypass) |
| `critica`: consulta la aprobación | 18 (sin aprobación sale el efecto) |
| `exigir`: compara la huella | 1 (L) |
| `critica`: kill switch | 5 (M: 1 llamada y lecturas con el interruptor tirado) |
| Previas medidas de nuevo | 6 |
| La propuesta no deja verificación | 1 |

En la mutación del kill switch el primer informe decía "0 llamadas" con la
prueba en rojo. La etiqueta tenía el número **escrito a mano**: la aserción
estaba bien, pero el mensaje mentía justo cuando falla. Todas las etiquetas
pasaron a mostrar el conteo medido.

**Trigger de la migración, probado contra Postgres**, en una base descartable
creada y **borrada** dentro del contenedor local `pg-b7`, no en producción. La
migración aplica, y aplica dos veces sin error. Las 12 conductas dan lo
esperado:

- se puede vincular la conversación una vez, pero no mudarla;
- no se pueden cambiar argumentos, ni argumentos y huella juntos, ni la
  herramienta ni el origen;
- aprobar y registrar el resultado se permite;
- una aprobada no pasa a rechazada, y no se reescribe quién aprobó;
- R2 sin cambio de conducta.

La segunda aprobación de la misma fila da `UPDATE 0`.

**Otras pruebas del motor que se actualizaron** porque afirmaban la conducta
anterior. Cada una sigue afirmando el efecto, no la presencia del mecanismo:

- `test_m06a_frontera_autorizacion`: la matriz exige que las cuatro vayan por
  la puerta crítica. 73 aserciones.
- `test_activar_catv`: pedida en la conversación queda propuesta con 0
  escrituras, y la segunda vez no se vuelve a proponer.
- `test_escalada_forzada`: `registrar_pago` con aprobación.
- `test_autonomia2_preactivacion`:
  - la guarda "dos puertas" pasa a "tres puertas", con el motivo escrito;
  - la guarda del último metro buscaba un **texto** exacto y se pasó a AST
    (que el ejecutor *llame* a `frontera.exigir`).
- `test_bloqueos_en_traza`: los 4 códigos nuevos en las tres listas.

## A.8 Regresión completa

**Motor (`tests/`, 92 archivos, uno por uno con su exit code):** **90 de 92 en
verde.** La corrida final dio 89. La prueba que faltaba era
`test_escalada_forzada`: exigía exactamente 17 códigos de bloqueo, se le
agregaron los 4 nuevos **por nombre** y quedó en verde, verificada por separado
después. Quedan dos fallas, **preexistentes y demostradas**:

- `test_p2_inerte`: señala `despliegue/respaldo/verificar_restauracion.py` y
  `supabase/202609151705_scheduler_funciones_reconciliado.sql`. Ninguno de los
  dos lo tocó este bloque: los dos son del 17/09 y ya estaban sin versionar.
- `test_reloj`: espera 4 herramientas con `IMPORTACION_API_TOKEN` y hay 5. La
  quinta, `sincronizar_respuestas_externas`, ya está en el YAML de `HEAD`
  (601a001). Además, la clave `respuestas` del resultado la agregó
  `nucleo/reloj.py` (del 19/09, ya modificado al inicio de la sesión; `HEAD` no
  la tiene). La prueba es del 15/09 y quedó atrás de esos dos cambios.

`test_ledger_checksum`, que falló en la primera corrida, pasa con Docker
levantado: esa falla era del entorno (Docker Desktop estaba apagado).

**Django (backend completo, base descartable local `pg-b7`):**
`2 failed, 4585 passed, 43 skipped` en 19:50. Es idéntico a M05-B y a la
primera entrega de M06-A, y **no hay fallos nuevos**. Los 2 son los mismos ya
demostrados:

- `test_docs_environment_variables`: falla igual contra `origin @ 73bb30c`.
- `test_portal_rls`: corre como `admin`, que tiene `BYPASSRLS`.

## A.9 Migraciones

- **Motor:** `supabase/202609211800_aprobacion_vinculante.sql`, nueva y **sin
  aplicar** en ningún entorno persistente. Se probó solo en la base descartable
  de arriba, que ya no existe. El código funciona sin ella para lo común; para
  las irreversibles **falla cerrado**: el insert de la propuesta no pasa, o la
  aprobación llega sin huella y se bloquea.
- **Django:** ninguna nueva. Siguen generadas y sin aplicar las de M04/M05:
  `operaciones/0006`, `0007`, `0008` y `common/0041`.

## A.10 Archivos modificados en esta corrección

| Archivo | Tipo |
|---|---|
| `nucleo/seguridad/aprobacion.py` | **nuevo** |
| `nucleo/seguridad/frontera.py` | puerta `critica`, `exigir` con argumentos, desenlace de la clase crítica |
| `nucleo/herramientas/http.py` | pasa los argumentos al último metro |
| `nucleo/config/schema.py` | campo `irreversible` + 3 validaciones |
| `nucleo/modelo/motor.py` | propuesta atada, `ejecutar_accion_irreversible`, defecto de la verificación, códigos |
| `nucleo/persistencia/db.py` | insert atado, `select *`, `aprobar_accion_propuesta` (compare-and-set), resultado aparte, vínculo a la conversación |
| `nucleo/canales/api.py` | `_aprobar_irreversible`, vínculo propuesta↔conversación |
| `nucleo/seguimiento/forzado.py` | 4 códigos de bloqueo |
| `supabase/202609211800_aprobacion_vinculante.sql` | **nuevo** |
| `tenants/rapilink.config.yaml` | 4 herramientas: `irreversible`, aprobación, resumen, textos al modelo |
| `django-crm/frontend/src/routes/(app)/conversaciones/[id]/+page.svelte` | 4 motivos de bloqueo en palabras |
| `cli/evaluar.py` | propuestas ≠ ejecutadas; `propone`, `propone_una_sola_vez` |
| `evaluacion/rapilink.casos.yaml` | 3 casos afirman la cola |
| `tests/test_m06a_gate_critico.py` | **nuevo** |
| `tests/test_m06a_frontera_autorizacion.py`, `test_activar_catv.py`, `test_escalada_forzada.py`, `test_autonomia2_preactivacion.py` | actualizadas (A.6) |
| `PRD.md` §8.6, este informe | documentación |

## A.11 Producción no fue tocada

- No hubo deploy, push, commit, PR ni migración.
- No se leyó ni escribió `asistente.tenant_config` de producción: el cambio de
  config es **solo la semilla YAML**.
- Hasta que se aplique, `cli/diferencias_config.py rapilink` marcará "el repo lo
  declara y la base no", y es lo esperado.
- Los contenedores que se usaron (`pg-b7`, `redis-b7`, `runner-b7` y el de la
  regresión) son locales.

## A.12 Sin acciones sobre clientes

- Ninguna prueba salió a la red: `requests` está reemplazado en el ejecutor y
  cada llamada queda anotada y contada.
- Las credenciales también están reemplazadas por `clave-de-prueba`.
- No se usó ningún identificador de cliente real en las pruebas nuevas.
- No se corrieron los casos dorados, que leen WispHub de producción.
- No se aprobó ni ejecutó ninguna acción real.

## Pendiente de esta corrección

1. **Decidir si la cadena completa aplica tal cual a acciones aprobadas por una
   persona** (A.0). Hoy bloquea las cuatro hasta que se encienda la etapa, se
   cierre B-7 y se autorice cada herramienta.
2. **Pantalla de aprobación.** Sin ella, la cola sigue sin revisión.
3. **Aviso al cliente cuando se aprueba** su reinicio o su TV. Hoy se entera en
   su siguiente mensaje. No reduce ninguna garantía, pero es producto.
4. **`agregar_promesa_pago`**: ¿entra al gate atado?
5. **Rechazar una irreversible ya aprobada**: el trigger lo impide, y el
   endpoint de rechazo contestaría 500 en vez de un mensaje claro. No es un
   bypass, es un mensaje de error mejorable.
6. `cli/prueba_reinicio_con_ping.py` reinicia por `requests` directo la ONU de
   laboratorio (`CDTC505AE4AB`). Es un script manual de uso único, fuera del
   asistente, equivalente a un `curl` con la API key. No se tocó; la guarda 4b
   cubre `nucleo/`, no `cli/`. Borrarlo o dejarlo es decisión tuya.
7. **Casos dorados** sin correr (prohibido en este bloque). Hay que correrlos con
   `--base` después de aplicar config y migración.

---

# PARTE B — Los 15 puntos del bloque original (estado actual)

## B.1 Archivos

Ver A.10. La clasificación R0–R4 **se importa** de
`tests/test_m10a_gobierno_frontera.py` en lugar de copiarla: hay una sola
fuente.

## B.2 Herramientas revisadas

69 herramientas: 42 de lectura (R0) y 27 de escritura. Se revisaron las 27
escrituras con sus atributos `tipo`, `aprobacion_humana`, `irreversible`,
`invocable_por_servicio`, `requiere_confirmacion` y `exige_previas`.

## B.3 Matriz completa (27 escrituras)

| Clase | Herramienta | Tipo | Aprobación humana | Irreversible (puerta crítica) | Invocable por servicio | Previas |
|---|---|---|---|---|---|---|
| R1 | proponer_herramienta | interno | – | – | – | – |
| R1 | registrar_pedido_wifi | interno | – | – | – | – |
| R1 | reportar_comprobante_pago | interno | – | – | – | – |
| R2 | actualizar_estado_ticket | http | **SÍ** | – | – | – |
| R2 | agendar_visita_internet | http | – | – | – | – |
| R2 | agendar_visita_tecnica | http | – | – | – | – |
| R2 | cancelar_solicitud_servicio | http | – | – | – | – |
| R2 | cerrar_caso_crm | http | – | – | – | – |
| R2 | cerrar_ticket_operativo | http | – | – | **SÍ** | – |
| R2 | completar_ticket_instalacion | http | – | – | **SÍ** | – |
| R2 | crear_caso_soporte | http | – | – | – | – |
| R2 | crear_tag_crm | http | – | – | – | – |
| R2 | crear_ticket | http | **SÍ** | – | – | – |
| R2 | crear_ticket_caso | http | – | – | – | – |
| R2 | crear_ticket_instalacion | http | – | – | **SÍ** | – |
| R2 | importar_caso_externo | http | – | – | – | – |
| R2 | reasignar_ticket_instalacion | http | – | – | **SÍ** | – |
| R2 | reconciliar_caso_externo | http | – | – | – | – |
| R2 | registrar_solicitud_servicio | http | – | – | – | – |
| R2 | responder_ticket | http | **SÍ** | – | – | – |
| R2 | responder_ticket_operativo | http | – | – | – | – |
| R2 | sincronizar_respuestas_externas | http | – | – | – | – |
| R3 | activar_catv | http | **SÍ** | **SÍ** | – | plan con TV + CATV `Disabled` (se re-miden) |
| R3 | cambiar_tipo_onu | http | **SÍ** | **SÍ** | – | CATV `Not supported` (se re-mide) |
| R3 | reiniciar_ont | http | **SÍ** | **SÍ** | – | señal `aceptable` + ping (se re-miden) |
| R4 | agregar_promesa_pago | http | **SÍ** | – (pendiente) | – | – |
| R4 | registrar_pago | http | **SÍ** | **SÍ** | – | – |

`requiere_confirmacion` lo declaran las 27 y **no es una barrera**. La barrera
es `aprobacion_humana`, que tienen 8 de 27; la aprobación **atada** la tienen
las 4 irreversibles.

## B.4 Acciones que requieren aprobación humana

Con aprobación atada, por la puerta crítica: `registrar_pago`, `reiniciar_ont`,
`activar_catv` y `cambiar_tipo_onu`. Con la aprobación común, por
`frontera.humana()`: `actualizar_estado_ticket`, `crear_ticket`,
`responder_ticket` y `agregar_promesa_pago`.

## B.5 Candidatas a autonomía

Solo las R2 que ya entran por la ruta de servicio (`cerrar_ticket_operativo`,
`completar_ticket_instalacion`, `crear_ticket_instalacion`,
`reasignar_ticket_instalacion`) y las R1. Ninguna irreversible: el validador
prohíbe que sean invocables por servicio, y `exigir()` no las deja salir por
`autonoma()`.

## B.6 Acciones bloqueadas para la ruta autónoma

Las cinco R3/R4. Las cuatro irreversibles, **estructuralmente**: sin permiso
crítico no salen. `agregar_promesa_pago`, por su aprobación común y porque no es
invocable por servicio.

## B.7 Flujo final de autorización

| Estado | Dónde vive |
|---|---|
| Observada | Detectores M04/M05 → `PropuestaSupervisor` (CRM) |
| Recomendada | `PropuestaSupervisor`. El motor no la conoce: son dos colas separadas |
| Pendiente de aprobación | `acciones_propuestas` (`pendiente`), con huella, origen y contexto si es irreversible |
| Autorizada | Irreversible: fila `aprobada`, persistida **antes** del efecto, con quién y cuándo. Común: aprobada por una persona. Autónoma: autorización granular vigente |
| Ejecutable | Solo dentro del `yield` de `autonoma()`, `humana()` o `critica()`. Una irreversible, **solo** en `critica()` |
| Ejecutada | `operaciones_externas` (idempotencia) + bitácora de desenlace (autónoma y crítica) + resultado en la fila |
| Rechazada o bloqueada | `AccionExternaNoAutorizada` con su código. Los de la aprobación atada están en A.2 |

Puertas:

- `autonoma`: tenant → kill switch → etapa → autorización granular → bitácora
  → permiso.
- `humana`: actor + evidencia. **No** mira el kill switch, y solo sirve para lo
  no irreversible.
- `critica`: A.5.

## B.8 Frontera real de ejecución

`frontera.exigir()`, llamado por el ejecutor HTTP antes de cualquier escritura.
Para una irreversible exige además la clase crítica, la misma herramienta y la
misma huella. M09 no tiene con qué producir un efecto: verificado por AST en
`supervisor.py`, `asistentes.py`, `incidencias.py`, `novedades.py` y `sla.py`.

## B.9 Kill switch

- Lo leen `autonoma()` y ahora también `critica()`, sin caché y fallando
  cerrado.
- **Cambio de conducta:** una irreversible aprobada **sí** se frena con el
  interruptor tirado (requisito M). `humana()` sigue igual para lo demás, y la
  decisión está escrita en el código.
- Sigue siendo **binario** (brecha 4 de M10-A).

## B.10 Idempotencia

Clave `origen|herramienta|hash16(argumentos resueltos)`, exclusión por clave
primaria. En las irreversibles el origen es `accion_aprobada:<id>`, estable por
construcción: dos ejecuciones de la misma aprobación producen **un** efecto
(N). El compare-and-set de la aprobación impide además que dos aprobaciones
simultáneas lleguen a ejecutar.

## B.11 Pruebas

Ver A.6/A.7. Suites de seguridad: todas en verde (ver A.8).

## B.12 Regresión

Ver A.8.

## B.13 Migraciones

Ver A.9.

## B.14 Riesgos

1. **Operativo (A.0):** con la cadena completa, las cuatro irreversibles no
   producen efecto hasta que se encienda la etapa, se cierre B-7 y se autorice
   cada herramienta, y no hay pantalla de aprobación.
2. **Kill switch binario:** no permite apagar solo R3 o solo R4.
3. `aprobador` es quien el llamador dice que aprobó: el motor no autentica
   personas. Lo que se garantiza es que sin un aprobador con nombre, sin momento
   y sin estado persistidos no sale nada.
4. El reintento de identificador de SmartOLT (`gpon_hex`) ocurre **dentro** del
   ejecutor, después de `exigir()`. Es la misma ONU en otra notación, no otra
   acción.
5. La idempotencia depende del origen: sin un origen estable, la garantía no
   pasa del turno. En las irreversibles aprobadas el origen es estable.
6. `MOTOR_SERVICE_TOKEN` no está configurado en local; no se verificó el valor
   en producción.

## B.15 Decisiones pendientes

Las siete de "Pendiente de esta corrección", más:

- ¿Interruptor por niveles (R2/R3/R4)?
- ¿Cuándo se enciende Autonomía 2? B-7 sigue **PARCIAL**.
- **Clientes para pruebas funcionales:** ninguno autorizado y ninguno asumido.
  Antes de cualquier prueba con efecto hay que nombrarlos expresamente.
