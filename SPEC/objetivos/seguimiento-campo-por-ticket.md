# Objetivo · El seguimiento de campo vive en la orden, no en un chat

> **Objetivo: CERRADO — 30/09/2026.** Abierto el 29/09/2026.
> **Producción: DESPLEGADO, pendiente de confirmación de arranque** — ver la
> sección siguiente y su punto de no retorno.
>
> Fases A–D implementadas, medidas y con sus límites escritos. **No quedan
> funciones pendientes dentro de este objetivo.**
>
> Fuera de alcance, deliberadamente y con su motivo:
>
> - **el latido móvil** — no existe señal periódica de conectividad fiable en la
>   aplicación actual, así que «sin sincronización reciente» queda construido,
>   probado y **apagado**. Encenderlo cambia comportamiento móvil, consumo,
>   batería, trabajo en segundo plano y frecuencia de sincronización: es otro
>   objetivo, no un agregado de este;
> - **la publicación automática en Google Chat** — hasta resolver el tratamiento de
>   datos con terceros. La fase 1 (generar y copiar el texto) no tiene ese problema
>   porque la pega una persona.
>
> Las invariantes que salieron de acá quedaron congeladas en `CLAUDE.md` §12, y la
> regla de la prueba de cadena real en §6.

## Estado de producción

> **DESPLEGADO — pendiente de confirmación de arranque.** 30/09/2026.
>
> Commit desplegado: **`6332710`** en `fix/integracion-wisphub`
> (`fb8cb84..6332710`, fast-forward). Verificado **por contenido y no por hash** —
> `git hash-object` de cada archivo contra la rama remota— que la rama desplegada
> trae `salud_seguimiento.py`, `bloqueos.py`, `seguimiento_campo.py`,
> `materiales_de_orden.py` y la migración `0016_unir_inventario_y_catalogo_de_rol`.
>
> Las fases A–D están implementadas y verificadas contra Postgres real.

### El punto de no retorno

**Este objetivo pasa a `CERRADO EN PRODUCCIÓN` cuando, y solo cuando:**

1. `docker exec <backend> python manage.py showmigrations campo` muestre
   `[X] 0016_unir_inventario_y_catalogo_de_rol`;
2. el backend esté arrancado **sin traceback asociado al despliegue**.

El smoke funcional de Materiales y Seguimiento es confirmación adicional, no la
condición. Y la condición es esa por un motivo medido: las migraciones de `campo`
llegaron a tener **dos nodos hoja**, y Django se niega a arrancar con eso. Como el
entrypoint del backend corre `migrate`, ese fallo no aparece en una prueba: aparece
con el servicio abajo.

### Falta confirmar en producción

- [ ] backend iniciado sin errores;
- [ ] migración `0016` aplicada;
- [ ] ausencia de excepciones nuevas después del deploy;
- [ ] Materiales y Seguimiento cargan en una orden real.

Esta sesión **no puede** hacer ninguna de las cuatro: no tiene acceso al servidor
ni a la base de producción, y el repo prohíbe conectarse a producción y leer los
secretos donde estarían esas credenciales.

### Riesgo operativo separado, y NO es de este despliegue

`tenants/rapilink.config.yaml` cambió en la rama de despliegue —no en este
trabajo— agregando a `cerrar_caso_crm` las banderas `invocable_por_servicio: true`
y `argumentos_sobrescribibles: [id_caso]`. Viene de **M09-S** (el Supervisor
cerrando un caso cuando una persona acepta una propuesta).

**El código que las lee ya está desplegado**: `nucleo/canales/api.py:4218` hace
`if not herramienta.invocable_por_servicio` y responde **403**. Y la base manda
sobre el YAML, así que si esa configuración no está cargada, aceptar una propuesta
de caso desincronizado **falla con 403** — y el síntoma se lee como un problema de
integración o de red, no de configuración.

Se mide con `py -3.13 cli/diferencias_config.py rapilink`: la dirección que rompe
es «el repo lo declara y la base no». **No se carga desde esta sesión ni se mezcla
con este cierre**: es del dueño de M09-S.

### Pendientes ajenos a este objetivo

- **12 pruebas rojas** en `campo/tests/test_seguridad_seed_y_admin.py`,
  **preexistentes en producción** y verificadas byte a byte contra la rama de
  despliegue: la prueba le pasa `--org` a `seed_campo_demo`, que no declara ningún
  `add_argument`. Llegó así en `f74eaf0`; el arreglo es de quien la escribió.
- **Rotar la credencial** que quedó expuesta en la transcripción de la sesión del
  30/09/2026. Pendiente operativo de mayor prioridad.

## Gate de cierre (30/09/2026)

Siete pasos, sin código nuevo salvo dos arreglos que el propio gate destapó.

| # | Qué | Resultado |
|---|---|---|
| 1 | `pytest campo/` (SQLite) | **486 pasan**, 7 skips |
| 2 | `pytest campo/` **entera contra Postgres real** | **493 pasan, cero rojos y cero skips.** Nunca se había corrido así, y encontró dos defectos (abajo) |
| 3 | `vitest` de la cadena del frontend | **42 pasan**. En la carpeta entera hay 32 rojos en 13 archivos **ajenos** (business-hours, leads, macros, routing, tags…), ninguno de este trabajo |
| 4 | `pnpm check` | **41 errores y 26 warnings en 29 archivos** — los mismos que antes de empezar; ninguno en archivos de campo ni de esta pantalla. Registrados acá para que no se lean como regresión |
| 5 | Migraciones **desde una base vacía** | Las 16 de `campo` aplican de cero, incluida la migración de datos `0011`; cero pendientes en todo el proyecto; `makemigrations --check` → «No changes detected» |
| 6 | Recorrido en el navegador | Materiales → INICIO → AVANCE → BLOQUEO NOC → resolución → CIERRE, entero y en orden |
| 7 | Enlaces | Este objetivo es **una sola ficha** con las cuatro fases dentro, así que no hay fichas A/B/C/D separadas que cruzar. El enlace desde `DEXTER_ESTADO_ACTUAL.md` lo escribe la sesión dueña de ese archivo: esta entrega el hash y la línea |

**Los dos defectos que destapó el paso 2**, los dos en pruebas ajenas y los dos
invisibles en SQLite:

1. `test_anonimizador.py` **mutaba** `settings.DATABASES["default"]` en vez de
   reasignar el atributo, así que `pytest-django` no lo revertía: después de esa
   prueba la configuración quedaba apuntando a `crm.empresa-de-verdad.co` y **toda
   conexión nueva posterior moría** con «failed to resolve host». Eso tiraba 7
   pruebas de concurrencia que pasan solas. Medido con el middleware de contacto
   desactivado para descartar que fuera de este trabajo: las mismas 10.
2. `test_inventario_fase2_api.py` comparaba decimales **por su texto**
   (`== "30"`), y Postgres serializa esa columna como `"30.000"`. Una prueba que
   afirma sobre el formato mide el motor de base, no el comportamiento.


## Qué significa terminado

Cualquiera que abra una orden de trabajo puede leer la intervención completa
—qué se hizo, cuándo, con qué material y quién lo afirmó— sin abrir Google Chat,
y el NOC puede ver de un vistazo cuáles trabajos abiertos no reportan.

Nace del comunicado de operaciones que exige reportar **INICIO, AVANCE, BLOQUEO y
CIERRE**, no dejar un trabajo abierto más de 30 minutos sin actualización —salvo
bloqueo esperando gestión del NOC— y cerrar con solución, medición final y
evidencias.

## Lo que YA estaba construido (medido el 29/09/2026)

Esto se mide antes de escribir el plan porque cambia el plan. La mitad del
trabajo propuesto ya existía:

| Lo que existía | Dónde | Consecuencia |
|---|---|---|
| Bitácora append-only por orden: `tipo`, `profile`, `datos` JSONB, `ordering = ["created_at"]` | `campo/models.py:466` `EventoTrabajo` | **No se crea tabla nueva.** Se emiten cuatro tipos más |
| Nueve tipos ya escribiéndose (`orden_creada`, `asignacion`, `datos_actualizados`, `evidencia_confirmada`, `correccion_requerida`, `consumo`, `contexto_refrescado`…) | `campo/services/transiciones.py:240` y `:314` | La línea de tiempo ya tiene con qué empezar |
| El cierre en dos pasos: `completada_campo` → validación del supervisor → `cerrada`, con `correccion_requerida` y contador de `vuelta` | `campo/models.py:176` y `:490` | **«No permitir cerrar el ticket directamente» ya está**, y con más dientes: una foto de la vuelta 1 no satisface un requisito devuelto en la vuelta 2 |
| Máquina de transiciones que **niega** un salto inválido (`TransicionInvalidaError`) | `campo/services/transiciones.py` | Un estado derivado de «el último evento» perdería esta garantía |
| `MovimientoDeMaterial.orden` — FK a la orden | `campo/models.py:861` | La pestaña Materiales es una consulta, no datos nuevos |
| `ReservaDeMaterial.orden` — material comprometido para ese trabajo | `campo/inventario_operacion.py:114` | Es lo único que significa «asignado a esta orden» |
| SLA del compromiso con el cliente, calculado en backend | `campo/models.py:325` `sla_vence_en` | Es **otro** reloj: mide la promesa al abonado, no el reporte del técnico |
| Una ficha de orden en el CRM, con `estado_operativo` | `(app)/supervisor-noc/programacion/+page.svelte:816` → `/api/supervisor-noc/ordenes/[id]` → `GET /campo/trabajos/<id>/` | La pestaña tiene dónde vivir; `leerOrden` ya descarta teléfono y GPS |

Y lo que **no** existía: estado `bloqueado`, cola «requiere NOC», reloj de los 30
minutos, formularios con mediciones, y cualquier integración con Google Chat.

## Decisiones cerradas

No se reinterpretan sin una medición nueva.

**1 · No hay tercer eje de estado.** `estado_operativo` sigue siendo la máquina de
estados y `estado_validacion` sigue siendo otra cosa. Los eventos cuentan la
historia; «hace 18 min» es metadata derivada, **no** un estado. Motivo: derivar el
estado del último evento tiraría la máquina de transiciones que hoy niega saltos
inválidos, y dejaría tres ejes contradiciéndose.

**2 · `EventoTrabajo` es la bitácora canónica.** Se agregan `inicio_campo`,
`avance_campo`, `bloqueo_campo` y `cierre_campo`. **No se crea otra tabla de
seguimiento en paralelo.**

**3 · Las evidencias conservan `requisito_id + vuelta`.** Si después se quiere
navegación cronológica, se agrega `evento` FK **nullable**; nunca se reemplaza el
vínculo existente. Motivo: el checklist del supervisor se apoya en el requisito, y
atar la evidencia al momento en su lugar lo rompe.

**4 · Las mediciones viven en `WorkTypeVersion`.** Nada de `nivel_1550`, `PLC` o
`puerto` en modelos ni en el frontend. El tipo de trabajo —versionado— declara qué
campos pide cada ISP. Motivo: otro ISP mide otra ventana y nombra distinto sus
elementos; con campos fijos, el segundo ISP necesita un commit para dar de alta un
tipo de trabajo (CLAUDE.md §3.3).

**5 · «Servicio validado» es una declaración humana**, guardada con quién la hizo y
cuándo. Nunca una conclusión de Dexter. Motivo: es el mismo caso que
`ACCION_CONFIRMADA` —que el equipo responda no dice que la casa tenga internet— y
un ticket que dice «validado» sin decir quién lo afirmó no vale nada en una
disputa.

**6 · Google Chat: solo fase 1** —generar y copiar el texto. La publicación
automática queda **bloqueada** hasta resolver tratamiento de datos con terceros:
la autorización que firma el cliente nombra al proveedor del modelo, y Chat no
está ahí (CLAUDE.md §5, mismo motivo por el que Sentry sigue apagado).

**8 · `bloqueada` y `requiere_noc` son dos conceptos distintos** (29/09/2026, al
construir la Fase C). El estado dice que el trabajo está detenido; el booleano dice
que hace falta una acción del NOC. Un trabajo esperando al cliente, al material o a
que pare de llover está bloqueado y **no** lo destraba el NOC: si fueran uno, esa
bandeja mostraría trabajos que nadie de esa mesa puede resolver y a la semana la
dejarían de mirar. `requiere_noc` es **estructural** y no se deduce de un campo del
esquema del ISP —otra empresa lo llamaría «Requerimiento a NOC»— así que un filtro
que dependa de ese nombre deja de funcionar con la segunda.

**7 · Los movimientos de material no se duplican.** Se consultan por
`MovimientoDeMaterial.orden`. La pestaña **no calcula una segunda contabilidad**:
solo presenta movimientos que ya existen.

**9 · La salud del seguimiento se calcula, no se guarda** (30/09/2026, Fase D). No
hay `estado_seguimiento` en ninguna tabla: sería el tercer eje que la decisión 1
prohibió. Un veredicto guardado diría «al día» mientras el reloj sigue corriendo.
Hay una guarda que recorre los modelos de `campo` y falla si alguien agrega esa
columna.

**10 · «No reportó» y «no sé si tiene señal» no se juntan nunca.** Medido el
30/09/2026 en `apps/tecnicos-mobile`: la cola se drena por **eventos de la
interfaz** y no hay `Timer.periodic` ni escucha de conectividad. Sin latido, la
ausencia de contacto no distingue «sin señal» de «app cerrada en el bolsillo», así
que `minutos_contacto_reciente` viene **en nulo = no se evalúa** y el sistema no
afirma lo que no puede medir. Se enciende cuando la app tenga latido; la lógica ya
está construida y probada.

**11 · Dos umbrales, nunca un número compartido.** `minutos_para_reportar` sale del
procedimiento de la empresa; `minutos_contacto_reciente` sale de cómo funciona la
app. Los dos por empresa.

## El hallazgo que corrige la Fase A

`EntregaDeKit` **no tiene FK a la orden** (`campo/models.py:643`), y es correcto:
el despacho de la mañana es a la **custodia del técnico**, no a un trabajo. Con el
mismo kit hace cinco instalaciones.

Entonces un bloque titulado «Entregado al técnico» dentro de una orden se lee como
«entregado para este trabajo», y eso es falso: son 150 m de drop para el día, no
para esta casa. La pestaña muestra, con los nombres exactos de lo que cada dato
es:

| Bloque | De dónde sale | Qué significa |
|---|---|---|
| **Comprometido para esta orden** | `ReservaDeMaterial.orden` | Lo único que de verdad está asignado a este trabajo, con su desenlace (pendiente / consumida / liberada / vencida) |
| **Consumido en esta orden** | `MovimientoDeMaterial.orden`, `tipo=consumo` | Con serie cuando la hay |
| **Devuelto** | `tipo=devolucion`, misma orden | |
| **Otros movimientos de esta orden** | `ajuste`, `traslado`, `baja` | Con su estado (`aceptado`, `descuadre`, `conflicto`) |
| **En custodia del técnico hoy** | `EntregaDeKit` del día — *opcional, y rotulado como lo que es* | Contexto. **Dice explícitamente que no es de esta orden** |

`IncidenciaDeMaterial` queda fuera: no tiene FK a la orden, y llegar a ella por
material + técnico sería inventar un vínculo que nadie registró.

## Las cuatro fases, con puerta en cada una

### Fase A · Materiales en la orden

Solo lectura. No cambia el modelo, no toca transiciones, no introduce estados, no
toca offline, no toca permisos críticos.

### Fase B · La bitácora

Los cuatro tipos de evento y la línea de tiempo, mezclados con los nueve que ya
se escriben. Los formularios se generan desde `WorkTypeVersion`.

**Precisión de diseño:** cada evento guarda el **snapshot del esquema que lo
produjo** —su `schema_version` y las respuestas tal como se capturaron— más
`captured_at_device`. Motivo: versionar el tipo de trabajo mañana no puede cambiar
cómo se interpreta un AVANCE de hace tres años.

### Fase C · Bloqueos y NOC

`bloqueada` entra como `estado_operativo`, con transiciones **explícitas**.

**El estado de retorno no se adivina.** El evento de bloqueo guarda
`estado_operativo_anterior`, y resolver el bloqueo es una transición explícita a
un estado permitido — nunca un `bloqueada → en_sitio` fijo, porque puede haber un
bloqueo **antes** de llegar al sitio.

`Requiere NOC` se agrega como filtro/columna de la bandeja **que ya existe**. No
se crea pantalla nueva hasta comprobar que el volumen la necesita: dos lugares
donde el NOC mira trabajos es peor que uno incómodo.

### Fase D · El reloj

Última, y con el concepto cambiado. La app es offline-first, así que el servidor
**no sabe** si el teléfono tiene señal. Se guardan las dos horas y se muestran dos
datos separados:

```
Seguimiento de la intervencion   hora declarada por el dispositivo
Sincronizacion                   lo ultimo que el servidor vio de verdad
```

Y tres lecturas, no dos:

| Se ve | Qué dice |
|---|---|
| Al día | Último avance dentro de la ventana |
| **Seguimiento vencido** | Sincronizó hace 2 min y el último avance fue hace 38: **hay comunicación y no reportó** |
| Sin sincronización reciente | El dispositivo no aparece. **No acusa al técnico de nada** |

No se usa el texto «sin contacto»: Dexter no tiene heartbeat independiente que
pruebe conectividad, solo la sincronización de la app. Se llama por su nombre.

Un bloqueo abierto esperando NOC **pausa** la regla de los 30 minutos, que es la
excepción que el propio comunicado contempla.

## Criterios de aceptación

Comando y salida, no prosa.

| # | Fase | Evidencia | Cómo se comprueba |
|---|---|---|---|
| 1 | A | `pytest campo/tests/test_materiales_de_la_orden.py -q` pasa | salida pegada |
| 2 | A | Una orden con reserva, consumo y devolución devuelve los tres bloques separados, y el kit del día **no** aparece como «de esta orden» | prueba con las cuatro clases de movimiento |
| 3 | A | Un movimiento de OTRA orden no aparece — y un movimiento de otra **org** tampoco | la segunda mitad es el aislamiento, y se afirma con 0 filas |
| 4 | A | `pnpm check` sin errores nuevos en archivos de campo | comparar el total antes y después |
| 5 | B | Un `avance_campo` guardado hace tres versiones del tipo de trabajo se sigue leyendo igual | prueba que cambia `WorkTypeVersion` y vuelve a leer el evento viejo |
| 6 | C | `bloqueada → <estado anterior>` funciona desde `en_camino` **y** desde `en_sitio` | las dos, porque el retorno no es fijo |
| 7 | C | Una transición no declarada sigue levantando `TransicionInvalidaError` | el estado nuevo no abre la máquina |
| 8 | D | Con el dispositivo sincronizando y sin reportar: **seguimiento vencido**. Sin sincronizar: **sin sincronización reciente** | las dos, y que no se confundan |
| 9 | D | Un bloqueo abierto esperando NOC no marca vencido | |
| 10 | todas | `pytest campo/ -q` verde, y las `postgres_only` corridas contra Postgres real, sin skips | `TEST_DATABASE_URL` |

## Restricciones

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`**.
- **NO tocar `SPEC/DEXTER_ESTADO_ACTUAL.md`** — tiene un solo escritor, la sesión
  de `integrar-centro-mando`. Esta sesión entrega hash y una línea.
- No tocar `nucleo/`: esto es trabajo del CRM (`campo/`). El motor es genérico y
  no conoce órdenes de trabajo de un ISP.
- No reabrir el cierre en dos pasos ni el contador de `vuelta`.

## Qué NO hacer

- **No crear una tabla de seguimiento** al lado de `EventoTrabajo`. Motivo:
  decisión 2, y dos bitácoras se contradicen el día que una falle.
- **No derivar el estado del último evento.** Motivo: decisión 1.
- **No hardcodear campos de Rapilink** (dBm, PLC, puerto). Motivo: decisión 4.
- **No publicar automáticamente en Google Chat.** Motivo: decisión 6; es un
  bloqueo legal, no técnico.
- **No calcular saldos en la pestaña Materiales.** La existencia sale del libro
  (`existencia(ubicacion, material)`), nunca de una columna ni de una segunda
  suma. Motivo: decisión 7 y el invariante de una sola verdad.
- **No mostrar el kit del día como material de la orden.** Motivo: el hallazgo de
  arriba.

## Agentes involucrados

Lo devuelve el `orquestador`. Pendiente de correr.

| Agente | Para qué | Estado |
|---|---|---|
| `orquestador` | clasificar cada fase | pendiente |
| `arquitecto-dexter` | la pregunta «¿ya existe?» se respondió en la medición de arriba: la mitad existía | respondida por medición (29/09) |
| `revisor-de-pii` | Fase A: qué dato del cliente llega a la pestaña; `leerOrden` ya descarta teléfono y GPS | pendiente |
| `verificador-de-api` | se saltea: ninguna fase llama a una API externa | se saltea |
| `auditor-de-frontera` | Fase C: `bloqueada` no produce efecto externo, pero abre transiciones | pendiente en C |
| `auditor-independiente` | al cerrar cada fase | pendiente |

## Bloqueos

| Qué | Bloquea | Quién decide |
|---|---|---|
| Tratamiento de datos con Google como tercero | la fase 2 de Chat, **no** la fase 1 | el cliente / legal |
| ¿La cola «requiere NOC» es filtro de la bandeja o pantalla propia? | Fase C | producto, con el volumen medido |

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 29/09/2026 | Medido qué existía ya (8 hallazgos con archivo:línea), cerradas las 7 decisiones, corregida la Fase A por el hallazgo de `EntregaDeKit` sin FK a la orden | Fase A | — |
| 29/09/2026 | **Fase A cerrada.** Servicio, vista solo-lectura, proxy y los cuatro bloques en la ficha de la orden. 16 pruebas nuevas (401 en `campo/`), 24 contra Postgres real, y la del kit **verificada en negativo**: al colarlo, tres fallan y una nombra el 150. En el navegador, con datos reales: custodia 300 m, orden 37,5 m | Fases B, C y D | `2e24c3b` |
| 29/09/2026 | **Fase B cerrada.** Los cuatro tipos de evento, el formulario derivado de `WorkTypeVersion` y la línea de tiempo única. 25 pruebas nuevas (426 en `campo/`), 49 contra Postgres real. **En negativo**: leer con el esquema vigente en vez del snapshot hace fallar la prueba. Ciclo completo verificado en el navegador | Fases C y D | `98367ef` |
| 29/09/2026 | **Decisión nueva, medida en la pantalla:** un AVANCE antes del INICIO **se acepta** —un reporte perdido es peor que uno desordenado— pero la ficha avisa que falta la condición inicial, y la línea de tiempo **no se reordena** para que parezca prolija | — | `98367ef` |
| 29/09/2026 | **Fase C cerrada.** `bloqueada` como estado operativo con su mapa (`SE_PUEDE_BLOQUEAR_DESDE`), `BloqueoDeTrabajo` como hecho con apertura y cierre, `bloqueo_resuelto` con quién/qué/minutos, y los dos filtros en la bandeja existente. 31 pruebas + 4 de la cadena del frontend; 457 en `campo/`; 80 contra Postgres real. **En negativo**: deducir `requiere_noc` del formulario hace fallar la prueba | Fase D | `6ea7dd2` |
| 29/09/2026 | **Tres defectos que solo se vieron probando la pantalla:** la cadena del CRM no reenviaba `requiere_noc` (el backend lo respetaba y tenía prueba; la bandeja del NOC quedaba vacía para siempre), la vista de resolver devolvía un `orden` en memoria ya viejo, y la fila de la tabla no se refrescaba sin `invalidateAll`. Se agregaron 4 pruebas de la capa servidor del frontend, que es donde se perdía el dato | — | `6ea7dd2` |
| 29/09/2026 | **Defecto de la Fase B, hallado leyendo el código:** la línea de tiempo leía `estado_nuevo` y `transiciones.py` escribe `nuevo_estado`, así que las transiciones salían mudas. La prueba estaba en verde porque **fabricaba** el evento con la clave equivocada en vez de ejecutar una transición real | — | `6ea7dd2` |
| 30/09/2026 | **Fase D cerrada.** `salud_seguimiento.calcular` con el orden de prioridad, los dos umbrales por empresa, `ContactoDeDispositivo` con freno, la columna y los dos filtros, y el bloque en la ficha. 29 pruebas (486 en `campo/`), 87 contra Postgres real, 42 en vitest. **En negativo**: invertir el orden de las preguntas, y evaluar la sincronización con el umbral apagado | — | `affadd9` |
| 30/09/2026 | **Medición que cambió el diseño:** la app **no tiene latido** (la cola se drena por eventos de la interfaz). Sin él la ausencia de contacto no prueba nada, así que la cuarta situación queda construida, probada y **apagada**. Lo único que falta para encenderla es un `Timer.periodic` en Flutter, que quedó fuera a propósito: es otra superficie y no se midió | el latido en la app | `affadd9` |
| 30/09/2026 | **El recorrido completo, medido:** al día (12 min) → vencido (38) → sin contacto (dispositivo hace 40) → vencido otra vez (dispositivo hace 2) → pausado (2 h) → al día. **El mismo atraso de 38 minutos da dos veredictos distintos según si el teléfono apareció** | — | `affadd9` |
