# Agente de campo para el técnico instalando

**Estado:** encuadrado, **no se construyó nada** · **Anotado:** 02/11/2026

> **Por qué queda anotado y no se arrancó.** El usuario: *«dejalo anotado para
> después, que están haciendo un cambio que da otro punto de vista»*. Hay
> trabajo en curso de otra sesión que puede mover los supuestos de abajo.
> **Antes de retomar esto, releer lo que haya cambiado**, en especial la
> autonomía por agente y lo que se decida sobre acciones críticas.

## Qué pidió el usuario

> *«se crearía para que ayude al técnico al momento de realizar una
> instalación, a llenar los formularios y adjuntar los documentos, autorizar
> el equipo en SmartOLT y demás funciones que uno le indique. Este agente lo
> supervisa el agente Supervisor IA. El técnico empieza y gestiona la
> instalación desde la app — aún no está habilitado instalación.»*

Y confirmó después: **la misma app y el mismo técnico** hacen soporte,
instalación y cualquier otro trabajo. Una instalación es **un tipo de trabajo
más**, no un flujo aparte.

## El hallazgo que ordena todo

**Lo que falta no es un agente.** Falta (a) autorizar la ONU en SmartOLT, que
no existe ni como herramienta ni como endpoint verificado, y (b) el alta del
cliente en WispHub, verificada en la skill pero sin herramienta y sin un solo
llamador. El agente es la última capa; hoy no tendría nada que ofrecer.

## Lo que ya existe, y no hay que volver a construir

| Pieza | Estado |
|---|---|
| Labor `instalacion` + plantillas de partida `instalacion_fibra` y `traslado_servicio` | ✅ de fábrica. `instalacion_fibra`: 120 min, 5 campos (serial ONU, metros de fibra, potencia en roseta −28/−8 dBm, WiFi probada, cliente informado), 4 evidencias, 2 obligatorias |
| El ciclo completo de la orden, el checklist que bloquea el cierre, la cola offline de evidencias | ✅ y **no distinguen labor** |
| El clasificador que separa instalación de correctivo | ✅ por el cliente de instalaciones del ISP; 220 de 220 acertados (08/10/2026) |
| La IA mirando las fotos contra las instrucciones de la plantilla | ✅ desplegado el 31/10–01/11/2026 |
| El serial del equipo volviendo al ISP solo | ✅ `lazo_isp.py` |
| La revisión del cierre por el Supervisor | ✅ |
| El canal de aviso al técnico | ✅ salvo el proveedor de push |

**«No está habilitado instalación» no es código: es configuración.** Cuatro
cosas, todas desde pantallas: adoptar la plantilla y **publicar** su versión;
declararle **asuntos** (con dos plantillas de la misma labor y sin asuntos, el
caso **no se despacha**); una cuadrilla con labor habitual `instalacion`; y
`hora_de_corte` (sin eso el Supervisor no crea órdenes solo). **Medirlo es una
lectura, no un desarrollo.**

## Los huecos reales

1. **Autorizar la ONU: no existe y NO ESTÁ VERIFICADO.** La skill de SmartOLT
   (788 líneas) no tiene la operación; solo el campo de lectura
   `authorization_date`. Escrituras conocidas: `reboot` (ejecutada en vivo) y
   las cinco de CATV (documentadas, ninguna ejecutada). Nada sobre ONU sin
   autorizar ni cómo descubrirlas — el enum de estados medido no incluye un
   «sin autorizar». **Sondear con `GET` + id imposible MIENTE acá**: seis
   candidatos de CATV dieron 405 y existían. Lo que funciona es bajar la
   colección oficial. Es trabajo de `verificador-de-api`.
2. **Sería la SEXTA herramienta `irreversible`** del sistema. Es la única de
   su familia que **crea** algo en la OLT —ocupa puerto y compromete recursos—
   y el deshacer no lo midió nadie. Entra en M06-D como `INDETERMINADA` hasta
   que haya evidencia. Obliga a actualizar `CLAUDE.md §5`, `M06-D` y
   `tests/test_m06d_matriz_autonomia.py`. Y choca con
   `SPEC/objetivos/reemplazo-de-mano-de-obra.md`, donde las críticas *«se
   quedan como están»*.
3. **Alta del cliente en WispHub**: endpoint **sí verificado en vivo**
   (`POST /api/clientes/agregar-cliente/{id_zona}/?instalacion`, respuesta
   asíncrona con `task_id`), sin herramienta y sin llamador. Y exige un cruce
   **IP ↔ zona que no está modelado en ninguna parte** — la skill dice que no
   hay forma de saberlo sin conocer la topología. Ese mapa es **configuración
   de la empresa**, no una tabla en código.
4. **Adjuntar documentos HOY NO SE PUEDE.** El backend acepta
   `foto|documento|firma` y el storage acepta PDF, pero el editor guiado solo
   emite `foto` y **la app no tiene selector de archivos** (`image_picker` sí,
   `file_picker` no existe). Solo entra una foto del documento.
5. **Grieta de contrato en la firma**: la app escribe `campoClave:
   'firma_receptor'`, un campo que ninguna plantilla declara y que el backend
   no conoce. Síntoma anotado: orden cerrada en el teléfono y trabada en el
   servidor.

## Lo que mata al agente conversacional en campo, y hay que decirlo primero

**El técnico trabaja sin señal.** La app es offline-first con cola. Un turno
de conversación **no se puede encolar**: se ejecutaría cuando el técnico ya se
fue, midiendo un momento que a nadie le importa — el mismo criterio ya escrito
para `ProbarConexionView`.

Un agente conversacional en campo es, por construcción, **una capacidad que
existe solo con red**, y la app tiene que decirlo en la cara en vez de fallar
en silencio.

## La app no habla con el motor, y no hace falta que empiece

Las ~45 rutas de la app van todas a Django. El motor ya se consume **desde la
app por el backend**, dos veces y con el contrato de error ya diseñado
(`probar-conexion` → `ping_cliente`, `medir-senal` → `consultar_senal_ont`).
Un segundo camino significaría una segunda credencial de servicio en un
teléfono.

Y la ruta del motor que presta el modelo ya existe y es genérica en los
hechos: su docstring dice *«No sabe de qué está hablando»*. El bucle de
razonamiento también existe y acepta `tools` como parámetro.

> **⚠️ Filo que hay que cerrar ANTES de reusar ese bucle.** El ejecutor de
> herramientas del chat es **un dict global sin dueño** y no filtra por actor.
> Pasarle `tools` acotado solo cambia lo que el modelo *ve*: si nombra
> `delegar_tarea`, se ejecuta igual — y eso **enciende tareas autónomas del
> Supervisor**. Hoy lo contiene el permiso de la ruta (jefe de operaciones),
> no el catálogo. Un agente del técnico que herede eso sería un técnico en la
> calle encendiendo autonomía. **Se arregla en el ejecutor, no en el prompt.**

## «Lo supervisa el Supervisor IA»: qué significa con lo que hay

Supervisar **el trabajo** está construido. Supervisar **a un agente** no
existe. La forma que el proyecto ya eligió para medir una IA es el par
*(lo que dijo la IA, lo que dijo la persona)* como **filas separadas**, nunca
un `UPDATE` — ver `AnalisisDeEvidencia`.

Lectura propuesta: no es una capa nueva, es eso generalizado. El agente deja
su sugerencia como fila, el técnico decide, y la revisión del cierre gana **un
punto más que puede valer `True` o `None` y nunca `False`** — la decisión
congelada del 31/10/2026. Lo que **no** es extensión es que el Supervisor
*autorice* acciones: eso es la frontera del motor, y el Supervisor **no
ejecuta nada** por diseño.

## El plan, cuando se retome

**Prerrequisitos, antes de la etapa 1:**

- **P1** — medir qué falta de la configuración de instalación en la org real.
  Es una lectura.
- **P2** — `verificador-de-api` sobre SmartOLT: existe el endpoint, con qué
  parámetros, qué devuelve y **cómo se deshace**. Sin esto no puede entrar al
  catálogo.
- **P3** — la decisión del usuario, abajo.

**Etapa 1 · «Autorizar la ONU desde la app». Sin modelo.** Hoy el técnico
instala, escribe el serial y **se sale de la app** a autorizar en el panel de
SmartOLT. Ese salto es lo que de verdad cuesta, es determinista y **funciona
con mala señal**. Herramienta en el catálogo (config, patrón de
`actualizar_sn_onu` y `reiniciar_ont`), servicio en `campo/services/` espejo
de `lazo_isp.py`, endpoint en campo, botón en el detalle de la orden como
`probar-conexion`. **Sin señal se rechaza, nunca se encola.** Es alcance, no
autonomía: sigue habiendo aprobación humana atada antes del efecto.

**Etapa 2 · El alta del cliente en WispHub.** Antes hay que modelar el mapa
IP↔zona como configuración del tenant.

**Etapa 3 · Ahí sí el agente.** Rol en `tenant_config` editable desde
`/agentes`, catálogo propio **partido por rol** (ver el filo de arriba), bucle
en Django, modelo prestado por el motor. Y el conocimiento operativo de
instalación en `directivas/`: hoy el corpus del RAG es una sola guía de
atención al cliente, **no hay manual de instalación ingestado**. Un agente de
campo sin eso no tiene nada que saber que el formulario no diga ya.

## Qué NO hay que crear

Un cliente HTTP al motor en la app · una ruta de chat nueva en el motor · un
segundo bucle de razonamiento · una tabla de conversación nueva · un canal de
aviso al técnico · una tubería de visión · un registro de «equipo instalado en
el cliente X» (eso lo sabe WispHub, frontera ya fijada) · una plantilla de
instalación nueva · un catálogo de prompts por empresa.

Y un cuidado de catálogos con la misma forma que **no son el mismo**: la
`zona` de WispHub (la del alta, con el servidor en el nombre), la `zone` de
SmartOLT (medida como ignorada en un filtro), las `ZonaDeReparto` de campo, y
`localidad`/`ciudad` del cliente son **cuatro identificadores independientes**.
El alta los cruza todos, y es donde ya costó tiempo.

## Decisiones pendientes, las dos del usuario

1. **¿Qué es este agente?** (a) un **asistente determinista** en la app:
   botones que ejecutan lo que hoy obliga a salirse, con validación en código
   y aprobación humana atada — sin modelo, anda con mala señal; o (b) un
   **agente conversacional**. No son excluyentes, pero **(b) sin (a) no tiene
   nada que ofrecer**. **Recomendación: (a) primero.**
2. **¿El agente de campo podría alguna vez autorizar una ONU solo?** Hoy la
   respuesta del repositorio es no. Si la intención es que sí, **se decide y
   se registra con fecha antes de la primera línea**, no se descubre al final
   — igual que se hizo el 31/10 con «el punto de IA nunca vale `False`».

## DECISIÓN DEL USUARIO, 13/11/2026: el técnico crea el contrato desde la app

> *«ahora el técnico crearía el contrato desde la app de dexter»*

Hoy el técnico, en la casa del cliente, entra a WispHub y llena **a mano**:
nombre, apellido, cédula, plan, dirección, coordenadas, el técnico que lo crea y
la fecha. Todo eso **ya está en la plataforma antes de llegar**:

| Lo que llena hoy en WispHub | De dónde sale |
|---|---|
| Nombre, apellido, cédula, plan, dirección | la solicitud que llenó el cliente (`solicitudes.SolicitudServicio`) |
| Coordenadas | ~~el GPS de «Llegué» en la app (el punto real de la casa); el de la solicitud como respaldo~~ **Cambiado por el usuario el 25/11/2026: mandan las del ticket.** Ver «El formato de instalación» |
| El técnico | la sesión de la app, emparejada con su usuario de `/api/staff/` de WispHub |
| La fecha | el momento de tocar «Crear el contrato» |

**Prototipo navegable:** `apps/tecnicos-mobile/lib/vista_previa/contrato_main.dart`
(commit `c9e25839`), instalado como «Contrato (prototipo)» en el teléfono de pruebas.
**Contrato de ejemplo** generado con WeasyPrint (el motor de `solicitudes/pdf.py`):
datos de la solicitud + red + instalación + autorizaciones + dos firmas + huella de
los datos firmados. Las cláusulas NO se inventaron: se cargan como texto de la empresa.

### El plan

| Fase | Qué | Depende de |
|---|---|---|
| 1 | La orden de instalación queda unida a su solicitud y la app muestra los datos del cliente; pantalla «Crear el contrato» con firma; el PDF del contrato al expediente | nada externo |
| 2 | El alta en WispHub (`agregar-cliente/{zona}`), por el motor, con idempotencia y aprobación atada; espera el `task_id` y guarda el servicio en la orden; cierra el ticket | **la respuesta de abajo** |
| 3 | Autorizar la ONU en SmartOLT | verificar su API (P2) |

**Sin señal no se crea, y nunca se manda solo después:** crear un cliente dos veces
es peor que esperar.

### Lo que falta del usuario

1. ~~**Zona/router, IP y usuario PPPoE.**~~ **RESPONDIDO el 14/11/2026: los
   elige el TÉCNICO, en la casa.** Ver abajo.
2. ~~**El contrato que firman hoy.**~~ Resuelto: las cláusulas y el NIT son
   configuración por empresa (`ConfiguracionDeContrato.texto_condiciones`), se
   cargan en Programación. Fase 1, `645cc8ef`.

### LA IP LA ELIGE EL TÉCNICO — decisión del usuario, 14/11/2026

Preguntado explícitamente entre cuatro opciones (la oficina antes de la visita,
el técnico en la casa, WispHub solo, sin definir), el usuario eligió **el
técnico, en la casa**.

**Esto CONTRADICE lo que la skill de WispHub daba por sentado**, y la skill se
corrigió el mismo día. Decía: «el alta de red (ip, usuario_rb, plan, zona)
sigue siendo de la oficina, que es la única que conoce la topología». Era una
suposición, no una medición, y la decisión del usuario gana (CLAUDE.md §1).

**Qué cambia del diseño de la Fase 2:**

- La IP **no puede viajar en la orden**, porque todavía no existe cuando la
  orden se crea. Se elige en la pantalla del contrato, con señal.
- La plataforma tiene que **guardar los rangos por zona** —configuración
  editable por empresa, CLAUDE.md §3.3, nunca un rango fijo en código— y
  ofrecerle al técnico las libres.
- **Ofrecer, no pedir que teclee.** Es el mismo motivo que trajo todo este
  trabajo: el usuario reportó que al digitar los datos «hay muchos errores,
  mala escritura del nombre, direcciones mal digitalizadas». Una IP mal
  tecleada no es un error de ortografía: es un cliente sin servicio, o dos
  clientes con la misma IP.
- La zona tiene que **corresponder a la red real de esa IP**. Ya está medido
  que no se puede adivinar: el catálogo de zonas trae el número de servidor en
  el NOMBRE (`CORTE 15 - SERVIDOR 1`) y hay que cruzarlo contra los segmentos
  IP, no deducirlo.

**CÓMO LO HACE HOY** (el usuario, 14/11/2026): en el panel de WispHub el
técnico **aprieta una lupa en el campo de IP y le salen las disponibles**, y
elige cualquiera — *«puede ser cualquiera»*. Eso dice tres cosas del diseño:

1. **WispHub ya sabe cuáles están libres**, pero ese listado NO está en su API
   pública: el índice del spec tiene 54 rutas y ninguna es de IP disponibles
   (`/clientes/{accion}/` es solo activar/desactivar). La lupa vive en el panel
   (`wisphub.io`), no en `api.wisphub.io`.
2. **No hace falta lógica para elegir.** Cualquiera libre sirve, así que la
   pantalla solo tiene que ofrecer y el técnico toca una.
3. **Depender del endpoint interno del panel sería peor que calcularlo**: no
   tiene contrato, puede cambiar sin aviso y probablemente pide la sesión del
   navegador y no la clave de API. Para un camino que CREA clientes, eso no.

**OJO con el fallo, que no es limpio.** Si se ofrece una IP que ya está tomada,
`agregar-cliente` no devuelve un `400`: devuelve **202 + `task_id`**, y la
skill ya tiene medido que *«una tarea asíncrona puede decir SUCCESS y traer un
error de texto como resultado»*. O sea que el diseño no puede apoyarse en «si
está ocupada, la API avisa»: hay que leer el resultado de la tarea.

**Lo que falta medir antes de construir** (y es una medición, no una decisión):
cuáles IPs están ocupadas hoy. El filtro `zona` de `/api/clientes/` **está
medido como IGNORADO**, así que no se puede pedir «las de esta zona» directo;
la respuesta de LISTA sí trae `ip` y `zona` por fila, y `router` sí filtra. Qué
camino sirve se decide con el método del valor imposible, no por analogía.

## LA FASE 2, CERRADA EN DISEÑO — 14/11/2026

Cuatro respuestas del usuario ese día, y una medición que corrigió a la
tercera. El flujo queda **igual al que el técnico ya usa en WispHub**, que es
también la forma que la API pide:

```
1. el técnico elige la ZONA            ← `agregar-cliente/{id_zona}` la pide primero
2. salen las IP disponibles de esa zona
3. toca una — «puede ser cualquiera»
4. se crea el cliente
```

### Lo que decidió el usuario, y lo que midió el repositorio

| | Lo que dijo | Lo que los datos agregaron |
|---|---|---|
| Quién elige la IP | **el técnico, en la casa** | contradecía a la skill, que la daba por de la oficina. Corregido |
| Cómo lo hace hoy | aprieta una lupa y sale la lista | ese listado **no está en la API**: 54 rutas, ninguna de IP libres |
| Cuánto del pool se usa | «las 254; solo fuera la primera y la última» | cierto para `.0` y `.255`. **El `.1` NO**: libre en 83 de 86 pools, incluido uno con 240/254 ocupadas. Es la puerta de enlace y no se ofrece |
| El orden | **primero la zona, después las IP** | encaja con `{id_zona}` en la URL del POST |

### El defecto que casi se construyó encima

El primer informe agrupaba por ZONA. Pero `172.16.9.0/24` tiene 42 clientes en
«CORTE 15 - SERVIDOR 1» y 211 en «CORTE 30 - SERVIDOR 1»: decía **«212 libres»
donde hay una**.

La evidencia de que es una sola red: en 16 prefijos la suma de las dos zonas
**nunca pasa de 254**, y nueve están al 98-99%. Si fueran redes distintas los
conteos serían independientes y alguno se pasaría. **«CORTE 15/30» es el día de
corte de la factura** —las dos zonas dicen *SERVIDOR 1*—, no la red.

Entonces: la zona dice **de qué prefijos** se puede sacar; lo ocupado se cuenta
**sobre todos los clientes**, sin importar su zona. Las dos cosas a la vez.

### Lo que se va a construir

| | |
|---|---|
| **Los prefijos de cada zona son configuración** | se siembran con los medidos y la empresa los corrige. Un prefijo con un cliente no es un pool: `169.254.x` es link-local y `192.168.x` es LAN privada, y los dos aparecían con «252 libres» |
| **Lo ocupado se lee de WispHub, no se guarda** | una copia envejece, y entre que se lee y se crea pasan minutos. Se pregunta al momento |
| **El `.1` queda fuera** | y los 3 pools donde un cliente lo tiene van a revisión aparte |
| **Se ofrece, no se teclea** | el motivo de todo esto: el usuario reportó que al digitar «hay muchos errores». Una IP mal tecleada no es un dedazo: es un cliente sin servicio, o dos con la misma |

### Lo que NO va a poder prometer, dicho antes de construirlo

**Que una IP libre sea usable.** Los equipos de red —antenas, switches, CTO— no
son clientes, así que no están en `/api/clientes/` y la resta no los ve. Si una
dirección la tiene una antena, la lista la va a ofrecer igual.

Y el fallo no es limpio: `agregar-cliente` devuelve **202 + `task_id`**, no un
`400`, y ya está medido que *«una tarea asíncrona puede decir SUCCESS y traer
un error de texto como resultado»*. Hay que leer el resultado de la tarea.

### Un hallazgo que no es de la app, y vale aparte

**Los pools de SERVIDOR 1 están casi llenos**: nueve `/24` al 98-99%, y
Sabanagrande con `172.16.40.0/24` en **240 de 254**. Eso no lo arregla una
pantalla; son direcciones que se agotan. Queda anotado porque se vio midiendo,
no porque alguien lo pidiera.

## EL FORMATO DE INSTALACIÓN — decisiones del usuario, 25/11/2026

Planeado en conversación con el dueño del producto antes de probarlo en campo
con un técnico instalador. El pedido que lo ordena todo: *«que sea lo más fácil
para el técnico al momento de realizar una instalación»*.

### Una sola app, dos formatos

> *«tiene que ser una sola aplicación, pero con dos formatos distintos, un
> formato para soporte o preventivo y un formato para instalaciones
> independientes. No tienen por qué estar mezclados.»*

### El recorrido de una instalación

```
Voy en camino
Llegué al sitio
Validar puerto y acceso                (un solo paso)
   │
   ├── NO hay puerto ──► el técnico reporta los precintos que validó y el
   │                     número de caja (si la caja tiene la marca)
   │                     ──► la orden se cierra «en espera de puerto»
   │                     ──► una persona del NOC valida con esos datos
   │
   └── SÍ hay puerto ──► el técnico se va a tender la fibra
                         y MIENTRAS TANTO la app arma el contrato
                         ──► el técnico solo valida y confirma
                         ──► se crea en WispHub
                         ──► las 10 fotos obligatorias
                         ──► configuración del equipo
                         ──► cierre
```

**El contrato no se arma al asignar el ticket**: se arma cuando el técnico
confirma que hay puerto. Sin puerto no hay instalación, y un contrato de una
instalación que no se va a hacer es un cliente creado de más.

**Sin puerto decide una persona, y es a propósito.** El usuario: *«entra en
validación un humano porque él valida los puertos con los precintos que el
técnico le indica y número de caja si cuenta con la marca»*. Lo hace el NOC.

### Los datos del contrato: llegan escritos, el técnico solo confirma

Vienen del ticket (de la solicitud que lo creó). El técnico no teclea: revisa
contra la cédula que tiene delante y corrige lo que esté mal — *«si el nombre
viene mal usa la cédula para que lo corrija»*.

| Dato | Cómo queda |
|---|---|
| Nombre y apellido | en MAYÚSCULAS |
| Cédula | solo los números: sin puntos y sin «CC» |
| Teléfono | solo los 10 dígitos, sin indicativo |
| Correo | en minúsculas |
| Dirección | en MAYÚSCULAS, **con el barrio pegado al final** |
| Barrio | además, solo, en su propio campo |
| Coordenadas | las del ticket |

**Las coordenadas cambian de dueño respecto del 13/11.** Ese día se anotó «el
GPS de "Llegué"; el de la solicitud como respaldo». El 25/11 el usuario pidió
*«las coordenadas que tienen el ticket»*. Queda así: mandan las del ticket; las
del teléfono se usan solo si el ticket no trae, y **se guardan igual** en el
contrato (`gps_del_telefono`) para que no se pierda dónde se firmó. En el papel
son dos lugares distintos: las de la instalación van con los datos del
suscriptor, y el pie —el que dice «firmado en…»— lleva las del teléfono. Poner
ahí las del ticket sería afirmar que se firmó en un punto donde quizá nadie
estuvo.

**Qué es de cada empresa y qué no** (CLAUDE.md §3.3). Mayúsculas, barrio pegado
a la dirección y cuántos dígitos lleva el teléfono son costumbre de una
empresa: van en `ConfiguracionDeContrato` y se cambian en Programación → El
contrato de instalación. Que una cédula sean solo números y un correo vaya en
minúsculas no varía por empresa: se hace siempre.

### El plan, el corte y el servidor

- **El plan** sale del ticket y se compara con los planes que la empresa vende
  (`planes_venta` de su configuración, que es donde ya está qué plan va en qué
  zona). La comparación es tolerante porque el ticket no trae el nombre exacto
  del catálogo: *«Plan: FAMILIA 200MB - $89.900»* es `PLAN FAMILIA`. La hace el
  código, por las palabras que distinguen a cada plan; **si no reconoce uno
  solo, no adivina**: el técnico elige de la lista.
- **El corte** se lo pregunta el técnico al cliente y lo deja elegido en la app.
- **El servidor** sale de plan + corte. En WispHub el corte no es un campo: es
  la zona («CORTE 15 - SERVIDOR 1», «CORTE 30 - SERVIDOR 1»). Entonces la
  pantalla le muestra al técnico **solo los servidores del plan** — para los
  planes de corte, dos opciones; para los de Sabanagrande, una, ya elegida —
  y elegir el corte ES elegir el servidor.

Medido contra WispHub en solo lectura el 25/11/2026:

| Plan que se vende | Id en WispHub | Zonas donde va |
|---|---|---|
| PLAN HOGAR | 197388 | 20053 (corte 15) · 20049 (corte 30) |
| PLAN FAMILIA | 197389 | 20053 · 20049 |
| PLAN ULTRA | 197390 | 20053 · 20049 |
| PLAN ELITE | 197391 | 20053 · 20049 |
| PLAN FIBRA OPTICA 150MB_SB | 173066 | 32278 (Sabanagrande) |
| PLAN FIBRA OPTICA 200MB SV | 173679 | 32278 |

Existe además un `PLAN HOGAR PROMO` (211174) que no está entre los que se
venden: por eso la comparación se hace contra `planes_venta` y no contra el
catálogo técnico entero.

### La IP

El técnico toca una de la lista de libres (decisión del 14/11, sin cambios).
La lista la calcula la plataforma; **falta cargar los rangos de cada servidor**
para que ofrezca alguna.

### Lo que el alta va a necesitar y el técnico no escribe

| Campo de WispHub | Con qué se llena | Por qué |
|---|---|---|
| `usuario_rb` (el nombre del cliente en el router de red) | el nombre completo del cliente | medido en solo lectura: en **297 de los 300** clientes más recientes ese campo contiene el nombre del cliente (292 son solo letras, ninguno viene vacío). No puede ir vacío: la API lo exige |
| usuario del router wifi | `admin` | decisión del usuario |
| clave del router wifi | la misma para todos los equipos | **es un secreto de la empresa**: va cifrada en Configuración → Credenciales y se la nombra, nunca se escribe en un documento ni en un ticket |

Esto es de la fase 2 (el alta). Se anota acá para no volver a preguntarlo.

### Un contrato creado se puede anular y hacer otro

Pedido del usuario. En la plataforma: el contrato pasa a **anulado** con quién,
cuándo y por qué, y la orden queda libre para firmar uno nuevo. El anulado no
se borra — lo firmó un cliente — y su PDF sigue ahí.

**Mientras no exista el alta, anular no toca WispHub.** Cuando exista: lo único
que borra un cliente en WispHub es `DELETE /api/clientes/{id}/perfil/`
(asíncrono; medido en la skill). Borrar un cliente es una acción crítica (PRD
§2: borra datos y deja sin servicio), así que un contrato que ya está en el ISP
**no se anula desde la app**: se rechaza con un mensaje que lo dice, hasta que
esa baja exista y pase por la frontera.

### Las fotos: diez, todas obligatorias

Cédula por delante · cédula por detrás · recibo público de la dirección ·
fachada · dónde queda el equipo · la caja cerrada · cómo se acomodó la fibra ·
el precinto · la ONU instalada · la medición de potencia.

### La configuración del equipo

Lo que se configura: la WAN (IP y VLAN), el nombre y la clave del wifi —que
**los elige el cliente**—, el acceso remoto y su clave. Hoy se hace entrando
desde el navegador a la IP del router. La marca y el modelo se amarran al
serial cuando el equipo entra a inventario, y al escanear el serial la app los
trae.

**Por ahora el botón «Configurar» queda a la vista y no hace nada** (decisión
del usuario). Automatizarlo desde el teléfono es un trabajo aparte.

### Qué quedó construido el 25/11/2026 y qué no

| | Estado |
|---|---|
| Datos con formato (mayúsculas, cédula, teléfono, correo, barrio pegado), en el borrador **y** al firmar | **construido**, servidor |
| El plan reconocido contra los que se venden, y los servidores filtrados por plan | **construido**, servidor |
| Coordenadas del ticket primero | **construido**, servidor |
| Anular un contrato y firmar otro | **construido**, servidor |
| Las tres costumbres de la empresa en Programación | **construido**, plataforma web |
| Validar puerto, «en espera de puerto» y la validación del NOC | falta — app y servidor |
| Las 10 fotos en el formato de instalación | **hecho como plantilla** (ver «El formato como plantilla», abajo): se ve en la app instalada |
| El botón «Configurar» (visible, sin función) | falta — app |
| Quitar el «CC» que la app dibuja delante de la cédula; mostrar las coordenadas; botón de anular | falta — app |
| El alta en WispHub | **construida el mismo día, APAGADA de fábrica y sin probar contra WispHub de verdad** — ver «El alta en WispHub (fase 2)» |
| La baja en WispHub de un contrato ya creado | falta — por la frontera |
| Marca y modelo en inventario | falta |

**Todo lo que dice «app» necesita un APK nuevo**, y se compila en la máquina de
compilar: no sale de un cambio de servidor.

### Lo que el usuario todavía no respondió

1. Qué se pide después de las fotos además de la configuración (serial,
   valor de potencia, firma del cliente — el 13/11 quedó que firma en el teléfono).
2. La regla de la VLAN.
3. Si hacen falta las zonas de SERVIDOR 2 (20054 y 20050) para algún plan.

## EL ALTA EN WISPHUB (fase 2) — diseño del 25/11/2026

El usuario: *«sí, arranca con el alta»*. Es que la plataforma cree al cliente
en el ISP cuando el técnico confirma el contrato, en vez de que alguien lo
teclee después en el panel.

### Tres mediciones de ese día que ordenan el diseño (solo lectura)

| Qué se midió | Resultado | Qué decide |
|---|---|---|
| `GET /api/clientes/?ip=<valor imposible>` y `?ip=<la de un cliente real>` | 0 filas / 1 fila, y es ese cliente (de 7.711) | **el filtro `ip` SIRVE.** Saber si una IP ya la tiene un cliente es UNA llamada, no recorrer 7.711 filas. Con eso se comprueba la IP en el último metro y se confirma el alta leyendo de vuelta |
| Lo mismo con `cedula` y `servicio` | filtran los dos | sirven para reconocer «este cliente ya es el nuestro» |
| Lo mismo con `usuario_rb` y `search` | devuelven los 7.711 | **ignorados**: no usarlos |
| Cuánto espera la app una respuesta (`api_client.dart`) | 20 s | **el alta no puede ir dentro de la firma**: corre después, en segundo plano |

### El camino

```
el técnico firma el contrato            (la app recibe su respuesta enseguida)
        │  si la empresa encendió «crear el cliente en el ISP» — apagado de fábrica
        ▼
una tarea en segundo plano  →  el motor, por una ruta propia y angosta
        ▼
   puerta HUMANA: quién (el técnico) y con qué evidencia (el contrato firmado)
   interruptor, leído sin caché justo antes de escribir
        ▼
   1. la IP está en los rangos de ESA zona          (configuración de la empresa)
   2. la IP no la tiene ningún cliente              (lectura viva, filtro `ip`)
   3. el plan existe en el catálogo del proveedor   (lectura viva → su id)
        ▼
   4. se crea — una sola vez por contrato (idempotencia)
        ▼
   5. se confirma LEYENDO al cliente por su IP, no creyéndole al mensaje
      de la tarea  →  el contrato queda «creado en el ISP» con su número
```

**Por qué ruta propia y puerta humana.** Igual que guardar la ubicación o
cerrar el ticket de una orden: la ruta genérica es la puerta autónoma, la del
sistema decidiendo solo. Aquí decidió una persona parada en la casa del
cliente, con un contrato firmado como evidencia. El esquema **rechaza** que la
herramienta del alta sea invocable por un servicio o esté en el catálogo de un
agente: no hay otro camino por donde pueda salir.

**Crear un cliente no es idempotente, así que hay dos defensas.** La clave de
idempotencia es por contrato: el mismo contrato no sale dos veces. Y si la
llamada salió y la respuesta se perdió —lo que ninguna clave resuelve
(CLAUDE.md §12)—, el siguiente intento empieza mirando la IP: si ya la tiene un
cliente con el mismo nombre en el router y el mismo documento, **es el
nuestro** y se adopta en vez de crear otro.

**La respuesta no es limpia.** `agregar-cliente` devuelve `202` + una tarea, y
una tarea puede decir `SUCCESS` con un error adentro. Por eso lo que confirma
es la lectura por IP.

### «No sé» no es «falló» — lo que cambió la auditoría de frontera

La primera versión, el mismo día, trataba como **fallo** dos cosas que no lo
son: que la llamada saliera y volviera con un error ambiguo (un corte, un 5xx),
y que después de pedir la IP quedara tomada por una ficha que no se reconocía.
Un contrato con el alta fallida se puede anular, y el mensaje llegaba a decir
*«anula el contrato y firma otro con una IP distinta»*. Quien seguía esa
instrucción, con el primer cliente quizá ya creado, creaba **dos**. Lo encontró
una revisión independiente antes de que saliera de esta máquina.

Ahora el alta distingue tres cosas, y no se mezclan:

| Estado | Qué significa | Qué se puede hacer |
|---|---|---|
| **fallida** | **No hay cliente.** El proveedor dijo que no (rechazó el pedido, o dio el trabajo por fallido con la IP libre), o nunca se le llegó a pedir | reintentar, o anular y firmar otro |
| **en curso** | Se pidió, o no se sabe si llegó, y el cliente todavía no aparece. Se sigue mirando sola, seis minutos | esperar |
| **por revisar** | **Nadie sabe.** No apareció en el tiempo que se pudo esperar, o la IP quedó tomada por una ficha que no se reconoce | **nada desde la app**: ni anular ni reintentar. Alguien de **gestión** mira en el proveedor y dice una de dos: «sí quedó, este es su número» o «no quedó» |

Reglas que salen de ahí:

- **Una IP «ocupada por otro» solo se cree cuando nunca se había pedido nada
  para ese contrato.** Si ya se había pedido, el que la tiene puede ser el
  nuestro: va a «por revisar».
- **Lo que falló no se vuelve a ejecutar.** No existe «reintentar»: que una
  persona insista es un pedido nuevo, con otro número, y solo se puede pedir
  desde «fallida». Queda escrito quién lo pidió.
- **Dos contratos no eligen la misma IP.** Se rechaza al firmar.
- **Queda escrito quién resolvió** un «por revisar», y cuándo.

**Lo que la auditoría señaló y queda abierto, dicho sin disimulo:**

- El número de pedido lo pone Django, no el motor: la garantía «un pedido nuevo
  solo cuando una persona lo decidió» es de ese lado. El motor garantiza que el
  mismo número no sale dos veces y que todo pedido empieza mirando la IP.
- Al cliente recién creado se lo reconoce por su IP y su nombre en el router.
  Si WispHub guarda ese nombre distinto de como llega, **toda** alta va a
  terminar «por revisar». No está medido: es lo primero que tiene que decir la
  prueba vigilada.
- Si la respuesta de una tarea de WispHub trae el estado en otro lugar que
  `status`, el alta nunca va a saber que el proveedor dijo que no: va a esperar
  los seis minutos y quedar «por revisar». Seguro, pero lento.
- La clase de riesgo quedó en R2 («registro externo») con dos asteriscos
  escritos en `tests/test_m10a_gobierno_frontera.py`. Si esa es la clase
  correcta para «crear un cliente» es una decisión del dueño del producto.

### Qué se manda y qué no

| Dato | De dónde |
|---|---|
| zona (va en la URL), IP, plan (su id) | el contrato firmado |
| nombre en el router (`usuario_rb`) | nombre completo — la regla está en la configuración de la herramienta, no en el código |
| nombre, apellidos, cédula, correo, teléfono, dirección, barrio, coordenadas | el contrato firmado |
| usuario del router wifi | `admin`, fijo en la configuración de la herramienta |
| clave del router wifi | el secreto `CLAVE_ROUTER_WIFI` de la empresa, **si está cargado**; si no, no se manda y el resultado lo dice |
| las otras cuatro contraseñas | **nunca**: no hay quién las decida |

No se manda `?instalacion`: Rapilink no usa ese módulo (medido el 12/11).

### Lo que esto NO puede prometer

- **Que la IP sea usable.** Libre significa «no la tiene un cliente»; una antena
  no es un cliente (ya anotado el 14/11).
- **Que funcione contra WispHub tal como está escrito.** El cuerpo del `POST`
  es la documentación más una creación de prueba de agosto; lo que devuelve la
  tarea al terminar no está medido. **La primera alta real tiene que ser una
  prueba vigilada, con autorización explícita del usuario** (crear un cliente
  de prueba y borrarlo), igual que se hizo en agosto. En el entorno local no
  sale: está puesto para leer afuera y no escribir afuera.

### Qué quedó construido, y dónde vive cada cosa

| Pieza | Dónde |
|---|---|
| La lógica del alta: las tres comprobaciones, la puerta humana, la idempotencia, confirmar leyendo | `nucleo/seguimiento/alta_de_cliente.py` |
| La ruta angosta por donde el backend la pide, y la que solo comprueba | `nucleo/canales/api.py` → `/interno/contrato/<id>/crear-cliente` y `/comprobar-cliente` |
| Cómo se declara un alta sin que el motor conozca al proveedor | `nucleo/config/schema.py` → `ParametrosDeAlta`, `ParametrosDeBusquedaPorIp`, `ParametrosDeTarea` y las marcas `crea_cliente`, `busca_cliente_por_ip`, `lee_tarea` |
| Las tres herramientas de Rapilink | `tenants/rapilink.config.yaml` → `crear_cliente_del_contrato`, `buscar_cliente_por_ip`, `leer_tarea_de_wisphub`. **No se aplican solas:** en cada entorno hay que cargarlas con `cli/cargar_config.py` |
| El interruptor de la empresa, apagado de fábrica | `ConfiguracionDeContrato.crear_en_el_isp`; se enciende en Programación → El contrato de instalación |
| Cómo va el alta de cada contrato (pedida, en curso, por revisar, fallida, con su porqué), si algo pudo haber salido, quién lo pidió y quién lo resolvió | `ContratoDeServicio.alta_*` |
| Pedirla, comprobarla y dejar escrito cómo terminó | `campo/services/alta_en_el_isp.py` |
| La tarea en segundo plano que insiste hasta saber, y a los seis minutos lo deja «por revisar» | `campo/tasks.py::crear_cliente_en_el_isp` |
| El botón de una persona para volver a pedirla (solo desde «fallida») | `POST /api/campo/contratos/<id>/crear-en-el-isp/` |
| Gestión dice si quedó creado (la única salida de «por revisar») | `POST /api/campo/contratos/<id>/resolver-alta/` |
| Dónde lo ve la oficina | la página Instalaciones: cada solicitud dice si el cliente quedó creado; si falló, por qué, con «Volver a intentar»; si nadie sabe, con los dos botones de gestión |

### Lo que falta para encenderla

1. ~~**Cargar los rangos de IP de cada servidor**~~ **Hecho el mismo día, con
   su pantalla**: ver «Los rangos de IP de cada servidor», abajo.
2. **La clave del router wifi** en Configuración → Credenciales, con el nombre
   `CLAVE_ROUTER_WIFI`. Sin ella el alta sale igual, sin ese campo, y lo avisa.
3. **Una prueba vigilada contra WispHub**, autorizada por el usuario: crear un
   cliente de prueba y borrarlo. Es lo único que dice si el cuerpo es el que
   WispHub espera y qué devuelve su tarea.
4. **Cargar la configuración en producción** después de desplegar
   (`cli/cargar_config.py`): el archivo de la empresa no se aplica solo.
   **El código primero y la configuración después**, nunca al revés: las tres
   herramientas usan campos que el código de hoy en producción no conoce.
5. **La app.** La que está instalada firma y el alta sale sola, pero no
   muestra si falló ni tiene botón para reintentar: eso está en la web
   (Instalaciones). Verlo en el teléfono pide un APK nuevo.

## Los rangos de IP de cada servidor — 25/11/2026

El usuario: *«dale continúa»*, sobre la recomendación de hacer la pantalla de
rangos, que era lo que destrababa el alta.

**Lo que se encontró al empezar, y era peor que «falta la pantalla».** La
lectura de qué direcciones están tomadas (`ocupacion_ip.py`, construida el
14/11) **no estaba conectada para Rapilink** —ninguna herramienta tenía la
marca `sincroniza_ocupacion_ip`— **y ninguna pantalla la disparaba**. Sin esa
lectura la ruta de IP libres contesta «la ocupación de IP no se ha sincronizado
nunca»: **la lista de IP de la app nunca pudo ofrecer ninguna**. Es el caso de
CLAUDE.md §6, *código construido no es código que corre*.

**Lo que quedó.** En Programación → configuración, debajo del contrato, «Los
rangos de IP de cada servidor»:

- un renglón por cada servidor del contrato, donde se escriben sus rangos /24
  (`172.16.9.`, varios separados por coma). Se guardan normalizados y se
  rechaza lo que no es un /24 o es de uso reservado;
- al lado de cada rango guardado, cuántas direcciones están tomadas y cuántas
  libres;
- **sugeridos**: los prefijos donde ya hay clientes de ESA zona (al menos 10),
  con un botón «Usar los sugeridos» que llena la casilla —no guarda—;
- un botón «Leer del proveedor qué IP están tomadas» (recorre los clientes, un
  minuto; solo lectura).

**Medido al usarla en el entorno local, solo lectura:** 7.711 clientes, 156
prefijos con direcciones tomadas. Sugeridos de red privada: 23 para CORTE 15,
25 para CORTE 30, 3 para Sabanagrande (`172.16.40.`–`.42.`). Guardados esos, la
app ofrece 20 IP libres por servidor (antes cero), y el alta en vivo: IP libre
de su servidor → pasa las tres comprobaciones y se detiene en el último paso
(el entorno no escribe afuera); IP de otro servidor → `ip_fuera_del_rango`; IP
del rango ya tomada → `ip_ocupada`.

**Las IP `168.x` y `100.x` NO son errores: son la IP que se les pone a los
clientes AL CANCELARLOS**, para liberar la verdadera (el usuario, 25/11/2026).

Cómo se llegó, porque el primer paso fue equivocado y vale dejarlo dicho:

1. El usuario dijo primero que estaban «mal escritas». Se midió que no se podía
   deducir la IP real (en 1.253 de 1.944 casos la `172.16.<mismo>.<mismo>` ya
   la tenía otro cliente) y se construyó una opción de la empresa,
   `contar_ip_mal_escritas`, que no ofrece la dirección del rango que termina
   en los mismos dos números. Se encendió: las libres bajaron de 951 / 1.398 /
   359 a 299 / 583 / 330.
2. Al sacar la lista para corregirlas (2.360 clientes con IP fuera de red
   privada), **2.356 estaban CANCELADOS**: 1 activo y 3 suspendidos. Se le
   preguntó al usuario y confirmó la costumbre.
3. **La opción quedó APAGADA** (las libres volvieron a 951 / 1.398 / 359). Se
   conserva, apagada de fábrica, para una empresa que sí tenga IP mal escritas.

Lo que queda de esto: **revisar los 4 clientes NO cancelados** con IP fuera de
red privada (las primeras filas de la lista). La lista se entregó al usuario
como archivo en su equipo, fuera del repositorio.

También hay `192.168.10.` con 16 clientes en CORTE 30: es red privada, así que
se sugirió y quedó guardado. Revisarlo.

**Detalles de diseño:**

- La validación de lo que se guarda va en el editor y **no en el esquema**: un
  validador nuevo en el esquema haría que el motor rechace la configuración
  entera de una empresa que ya tenga un rango mal escrito guardado.
- «Lo que no se ve no se borra»: la pantalla muestra los servidores del
  contrato; un rango guardado de otra zona se conserva al guardar.
- La lectura cuenta clientes por zona y prefijo (`ocupacion_ip_por_zona`), solo
  conteos; nada del cliente.

## El formato como plantilla — 25/11/2026

El usuario, al proponerle la prueba contra WispHub: *«pero el cliente se crea de
último, cuando en la app se vea como yo quiero»*. Crear el cliente en el
proveedor queda para el final; primero, que la app muestre la instalación como
se planeó.

**Lo que se descubrió y cambia el costo:** la pantalla de trabajo de la app se
dibuja con la PLANTILLA del tipo de trabajo (pasos, datos y fotos), que vive en
el servidor y se edita desde la web (Plantillas), sin APK. Así que la mayor
parte del formato se pudo dejar visible en el teléfono que ya está instalado.

**«Instalación de fibra», versión 2** (publicada en el entorno local por la
misma ruta que usa la pantalla de Plantillas):

| Paso | Datos (* obligatorio) | Fotos (todas obligatorias) |
|---|---|---|
| Puerto y acceso | *¿Hay puerto disponible en la caja? (Sí/No) · *¿Hay acceso para hacer la instalación? (Sí/No) · Precintos que validaste · Número de la caja | — |
| Contrato y documentos | *Contrato creado y firmado por el cliente | Cédula por delante · Cédula por detrás · Recibo público de la dirección · Fachada |
| Instalación | *Serial de la ONU (se lee con la cámara) · *Potencia en la roseta (-28 a -8 dBm) · Metros de fibra | Dónde queda el equipo · Caja cerrada · Cómo se acomodó la fibra · Precinto · ONU instalada · Medición de potencia |
| Configuración y entrega | *Equipo configurado: WAN, WiFi del cliente y acceso remoto · Nombre de la red WiFi que eligió el cliente · *Cliente informado de cómo pedir soporte | — |

**El camino «no hay puerto», con lo que ya existe:** el técnico marca «No»,
anota precintos y caja, y toca **Reportar bloqueo** con «necesito al NOC». La
orden queda detenida, en la bandeja del NOC, con la foto de la caja (la plantilla
la pide en ese reporte). El NOC la destraba cuando valida. Es «en espera de
puerto» sin construir nada nuevo.

**Lo que NO se pudo sin APK nuevo:**
- que al marcar «No hay puerto» la app esconda los otros pasos y lleve sola al
  reporte de bloqueo con el NOC marcado;
- el botón «Configurar» (visible, sin función);
- quitar el «CC» que la app dibuja delante de la cédula en el contrato, mostrar
  las coordenadas, y los botones de anular el contrato y de reintentar el alta.

**Lo que NO se guardó, a propósito:** la clave del WiFi del cliente y la del
acceso remoto. Lo que se anota en una orden viaja en la nota al ticket del ISP y
lo lee cualquiera con acceso; una contraseña no va ahí. Si hay que guardarlas,
es otra decisión.

**Los documentos del cliente: «solo en la plataforma, no al ticket»** (el
usuario, 25/11/2026, preguntado con la medición a la vista: al ticket viajan
como máximo 8 fotos por visita, `campo/fotos_al_ticket.py::MAX_POR_VUELTA`, en
el orden en que se subieron).

Quedó como una marca de la plantilla, **`solo_en_la_plataforma`**, que se elige
foto por foto en el editor de Plantillas («solo en la plataforma (no va al
ticket)»). No se reconoce por el nombre: otra empresa la llamará «documento de
identidad». Una foto marcada queda en la orden y **no se adjunta ni al ticket
del CRM ni al del proveedor**; se saca ANTES del tope de ocho, así que las seis
de la instalación viajan todas. Si no se puede leer la plantilla de la orden, no
viaja ninguna foto (`fotos_al_ticket.requisitos_que_no_salen`).

En la versión 3 de «Instalación de fibra» van marcadas la cédula por delante, la
cédula por detrás y el recibo público. La fachada sí viaja.

Lo que esto NO cambia: la foto la sigue mirando el revisor de fotos (DeepSeek,
ya autorizado para datos de cliente), porque la revisión del cierre cuenta con
que todas las fotos tengan su análisis. Lo que el revisor dice NO viaja al
ticket: la nota lleva solo qué se revisó y cómo salió.

**En producción la plantilla no llega sola:** es un dato, no código. Se publica
desde Plantillas, igual que acá.

## La prueba del usuario en el teléfono — 25/11/2026

El usuario hizo una instalación completa en el teléfono (la OT-12: diez fotos,
contrato firmado a las 21:29, orden cerrada) y mandó la lista de arreglos. Lo
que se pudo hacer desde el servidor, para que se vea **con la app que ya está
instalada**:

| Lo que pidió | Qué se hizo | Dónde |
|---|---|---|
| «En la cédula sale CC y los números» | La app dibujaba el tipo de documento dentro de la casilla del número. La pantalla lo recibe vacío y el tipo viaja aparte; al firmar, si el teléfono lo devuelve vacío, se toma el de la solicitud. **El contrato firmado sí lleva el tipo** | `contrato.para_la_pantalla` · `firmar` |
| «Debajo de barrio salen habeas data y centrales de riesgo; ya no es necesario» | No se mandan a la pantalla. **Siguen en el contrato**: son la prueba de que el cliente autorizó, y `firmar` las toma de la solicitud, nunca del teléfono | `para_la_pantalla` |
| «Mejor si el corte se asigna solo» | Si el ticket dice el corte y eso da UN servidor del plan, se manda solo ese: la app ya marca sola el único y pide las IP libres. Sin corte en el ticket, van todos los del plan | `para_la_pantalla` |
| «Si está escrita cll debe ser calle, kra es cra, y así» | Reglas por empresa en la configuración del contrato (Programación → «Cómo se escribe la dirección», un renglón por regla: `CLL, CL = CALLE`). Solo palabras enteras, sin importar mayúsculas, tildes ni el punto; el barrio pegado al final no se toca («La Carrera» no es una carrera) | `contrato_formato.abreviar` · `ConfiguracionDeContrato.abreviaturas_de_direccion` (migración 0056) |
| «No veo para colocar el precinto del usuario» | «Precinto del cliente», obligatorio y con lector de cámara, junto al serial en el paso Instalación: **versión 4** de la plantilla | Plantillas |
| «… ni el serial» | Ya estaba: «Serial de la ONU», paso 3 Instalación | — |
| «… ni las coordenadas» | Ya se guardan solas: las del ticket (las siete órdenes de prueba las traen) y el GPS del teléfono al firmar (la OT-12 quedó con las dos). Lo que falta es **mostrarlas**: APK | — |

**Las reglas de Rapilink salieron de medir, no de adivinar** (solo lectura en
WispHub, solo la primera palabra de la dirección, contada): de 5.190 clientes
activos con dirección, empiezan con CALLE 1.672, CRA 1.560, CL 205, CR 200,
DIAGONAL 188, TRANSV 99, CARRERA 98, KR 92, KRA 87, TV 83, MANZANA 82,
TRANSVERSAL 72, CLL 67, y errores de dedo (CALLLE 21, CALL 12, CLLE 12, CALLA 5,
FIAGONAL 4, DIAHONAL 4…). Se cargaron cinco reglas: CALLE, CRA, DIAGONAL,
TRANSVERSAL y MANZANA. **Transversal es la única sin mayoría clara** (TRANSV 99
contra TRANSVERSAL 72): se eligió la palabra completa, como CALLE y DIAGONAL; se
cambia en Programación sin código.

**Lo que necesita APK nuevo** (la app no tiene un dato «ubicación» en las
plantillas ni lee `planes` todavía):
- el doble conteo de pasos: la línea de círculos y, debajo, la lista de los
  otros pasos con su resumen (`ejecucion_screen.dart::_selectorDePasos`) —
  quedarse con uno;
- el bloque de reportes (inicio, avance, bloqueo) arriba del formulario: en una
  instalación, abajo o fuera;
- el bloque «Cierre de trabajo» (`_checklistDeCierre`) → un botón «Ver el
  contrato» en su lugar;
- el plan como menú con los planes disponibles (el servidor ya manda `planes`
  con sus servidores);
- mostrar las coordenadas en el contrato.

**En producción**: la migración 0056, las reglas de dirección (se cargan desde
Programación) y la versión 4 de la plantilla (desde Plantillas) no llegan solas.

### La app 1.0.20 — lo que necesitaba APK (26/11/2026)

El usuario: «sí, hazlo». Los cinco cambios, en `apps/tecnicos-mobile`:

| Lo que pidió | Cómo quedó |
|---|---|
| Un solo conteo de pasos | Solo la línea de círculos (✓ en el paso completo). Se quitó la lista vertical de los otros pasos con su resumen (`_FilaDeOtroPaso`, del 14/11/2026) y la pastilla «Paso 1 de 4»; el número va en el título del bloque del paso («1. Puerto y acceso»). El encabezado de arriba («PASO 3 DE 5») no se tocó: cuenta las etapas de la orden, no los pasos del formato |
| Reportes abajo en instalación | En una instalación el bloque de reportes va al final. **No se quitó**: «no hay puerto» se reporta como bloqueo con el NOC, y sin él la instalación no tendría cómo pedirlo. En los demás trabajos sigue arriba |
| «Cierre de trabajo» → botón del contrato | En una instalación, «Ver el contrato» en su lugar (la franja de arriba se quitó: era el mismo botón dos veces). Lo que falta para cerrar sigue en `_loQueFalta`, arriba y fijo, con el mismo veredicto |
| El plan como menú | Si el servidor manda `planes`, el plan se elige de la lista; elegir uno deja SUS servidores y, si el servidor dice cuál es el del corte (`planes[].servidor_sugerido`, nuevo), solo ese y marcado. Un plan del ticket que no está en la lista queda sin elegir, con «En el ticket dice: …» al lado. Sin `planes` (un servidor viejo) el plan se escribe como antes |
| Ver las coordenadas | En el contrato, «Coordenadas: lat, lng» del ticket; sin ellas, que al crearlo se guarda la ubicación del teléfono. También en el contrato firmado |

Además la app deja de dibujar el «CC» y las casillas de autorizaciones aunque
un servidor viejo los mande.

`resumenDelPaso` (`pasos_del_trabajo.dart`) quedó sin uso en la pantalla; se
deja con sus pruebas por si vuelve el resumen en otra forma.

**El diseño (el usuario, 26/11/2026: «hazlo con diseño bien, que no se vea
genérico»).** Mirada con capturas de la pantalla real (las fuentes de la app,
390 px de ancho), no a ojo: el contrato usaba los controles de serie de Flutter
(bordes propios, radios, chips) y no se parecía al resto de la app. Quedó con
las piezas del diseño DEXTER CAMPO: secciones `DexterBloque` con ícono y
pastilla («De la solicitud»), nombre/apellido y documento/teléfono en dos
columnas, coordenadas y servidor asignado en `DexterBaldosaConIcono` (el dato
en la letra de la telemetría), los servidores como opciones marcadas con el
azul de acción (un punto de radio no se ve al sol), las IP como píldoras
monoespaciadas, la firma con su línea como en el papel, y el contrato firmado
como una ficha de datos. «Ver el contrato» es una tarjeta como las demás, toda
tocable. Las pruebas de la app: 1462 en verde, ninguna en rojo.

### La segunda prueba en el teléfono (1.0.20) y la 1.0.21 — 26/11/2026

Lo que pidió y lo que decidió, con las cuatro preguntas que se le hicieron (eligió
las cuatro recomendadas):

| Pidió | Quedó (1.0.21 + servidor) |
|---|---|
| «La pantalla de reporte, quita inicio» | En una instalación no sale «Inicio». Para cerrar no hace falta: el servidor da por iniciada la intervención en la que el técnico llegó al sitio (`seguimiento_campo`, `_llego_al_sitio`) |
| «En cada paso al último siempre sale ver contrato y reportar» | **Decidió: el contrato en el paso 2 y reportar en el paso 1.** Es una marca de la plantilla por paso (`pasos[].botones`: `contrato`/`reportar`), que cada empresa pone en el editor de Plantillas («Botones de cada paso»); sin marcas, como antes. «Instalación de fibra» v5 las trae |
| «Nombre arriba y apellido abajo, completo» | Uno debajo del otro, a todo el ancho |
| Coordenadas editables, con un mapa | El mapa satelital del ticket en el contrato, «Elegir en el mapa» (pin fijo, se mueve el mapa) y «Donde estoy» (GPS). Las corregidas viajan como `coordenadas` y GANAN sobre las del ticket (`datos.gps_origen`: tecnico/ticket/telefono). Unas inválidas no cuentan |
| «En la parte de corte no deja escoger» | Van todos los servidores del plan, el del corte del ticket primero y marcado; el técnico lo cambia tocando otro. El 25/11 se mandaba solo ese |
| «Que el sistema le indique la IP sin que tenga que elegir el técnico» | La asigna el servidor al firmar: la primera libre del servidor que no tenga otro contrato vigente (`contrato._ip_automatica`, `datos.ip_origen`). Sin motor o sin libres, se firma sin IP, como antes. Una app vieja que manda la suya, se respeta |
| «No se usa roseta, la fibra va de la caja directa a la ONU» | v5: «Potencia en la ONU», y la foto de la ONU sin roseta |
| «El campo nombre de la red WiFi debería quitarse» | Quitado en v5 |

### El material precargado, la IP para copiar y la fibra — 1.0.22, 26/11/2026

| Pidió | Quedó |
|---|---|
| «Material utilizado, que sea precargado» (2 conectores APC, 1 ONU, 2 tensores, 1 precinto, 2 chazos, 2 tornillos; grapas y fibra variadas). Decidió: vienen puestas y el técnico las ajusta | No es una tabla nueva: es `ReglaDeConsumo` (cuánto se suele usar, la misma cifra con la que la app ya avisaba), con tres campos nuevos: `precargar`, `orden_en_la_lista` y `cantidad_de_campo` (migración 0057). La empresa la arma en el editor de Plantillas («Material que se precarga»; `PUT /api/campo/plantillas/<id>/material-habitual/`). Viaja con la orden (`tipo.material_habitual`) y el teléfono la guarda (base local v30). En la app el bloque se llama «Material utilizado» y trae «Lo que se usa en este trabajo»: pasos − n +, «Tienes X» del kit, la ONU se elige entre las series que el técnico tiene a cargo (viene marcada la que escribió en un campo que se lee con la cámara) y «Registrar este material» encola un consumo por material, cada uno con su clave. Lo ya registrado de un material sale de la lista. Sacar un material de la lista NO borra su regla: pierde la marca y conserva su máximo |
| «En el paso 4 debe salir la IP que asignó el sistema, y que deje copiar pero no modificar» | Un botón más de la plantilla por paso, `ip`: un recuadro que lee el contrato firmado y muestra la IP como texto con «Copiar». Sin contrato, o sin señal, lo dice. «Instalación de fibra» v6 lo pone en «Configuración y entrega» |
| «Cuando se pone la fibra utilizada y la cantidad, que lo marque en material utilizado» | Una línea del material puede decir de qué campo de la plantilla sale su cantidad (por el TÍTULO del campo: la regla dura más que una versión). La de la fibra sale de «Metros de fibra usados»: se ve en «Material utilizado» y se corrige en su campo, no ahí |

En local: materiales nuevos PRECINTO, CHAZO y TORNILLO (los de producción son
los de la empresa) y la lista de la instalación cargada por la API.
**En producción no llega sola**: la migración 0057 y la lista, que la carga la
empresa desde Plantillas con sus propios códigos de material.

### Los puntos de TV — 1.0.23, 26/11/2026

La regla que eligió: 1 punto = 2 conectores coaxiales, sin spliter; desde 2,
**2 por punto + 2 de entrada** (2 = 6, 3 = 8, 4 = 10, 5 = 12) y el spliter más
chico que alcance **entre los que tiene el técnico**; el cable se pregunta (si
usó el de la empresa y cuántos metros); máximo 5.

- **Es de la empresa, por tipo de trabajo** (`PuntosDeTv`, migración 0058;
  `PUT /api/campo/plantillas/<id>/puntos-de-tv/`): el conector, cuántos por
  punto y de entrada, el máximo, el cable y los spliters con sus salidas. Se
  carga en el editor de Plantillas («Puntos de TV», que además muestra la cuenta
  de cada cantidad de puntos). Viaja con la orden (`tipo.puntos_de_tv`) y el
  teléfono lo guarda (base local v31).
- **La cuenta la hace la app, sin señal** (`lib/features/ejecucion/puntos_de_tv.dart`,
  probada sola): si el técnico no tiene un spliter que alcance, propone el más
  chico de la empresa y dice «No está en tu kit»; si ninguno de la empresa
  alcanza, no inventa uno y le pide elegir el que usó. Puede cambiar el
  propuesto. Registrar encola consumos comunes (conector, spliter, cable).
- **En local**: CONCOAX, SPL2, SPL3, SPL4 y RG6 en el catálogo; el técnico de la
  OT-15 tiene 20 conectores, spliters de 2 y de 4 (a propósito sin el de 3) y
  100 m de cable.
- **Un hueco que muestra la cuenta**: con los spliters cargados (2, 3 y 4
  salidas) 5 puntos no tienen spliter que alcance. Si la empresa usa uno de 6
  u 8, se agrega en el editor.

### «Activar ONU» en SmartOLT — 1.0.24, 26/11/2026

El usuario: «en el paso 3, cuando se ponga el serial, cómo se hace para que se
active la ONU en SmartOLT enseguida». Decidió: un botón después del serial,
construido APAGADO y probado una vez con su permiso; la VLAN sale del servidor
del contrato; la zona la sugiere el barrio y el técnico la confirma.

**Lo medido antes de construir** (solo GET, 20 llamadas; skill `smartolt-api` →
«Autorizar una ONU nueva»): la ONU nueva aparece esperando autorización con su
OLT, placa, puerto y tipo (`unconfigured_onus`, que filtra por serial); Rapilink
no usa presets; las 82 autorizaciones de la última semana llevan zona, VLAN (300
o 301 en la OLT principal según el servidor, 302 en Sabanagrande) y el nombre del
cliente en mayúsculas, y NUNCA caja, dirección ni ID externo.

**Cómo quedó:**

- **Motor** (`nucleo/seguimiento/activar_onu.py`, rutas `/interno/onu/buscar`,
  `/interno/orden/<id>/activar-onu`, `/interno/onu/comprobar`): cuatro
  herramientas por su marca (`busca_onu_sin_autorizar`, `autoriza_onu` con
  `parametros_de_onu`, `lee_onu`, `lista_zonas_de_red`). Solo escribe si el
  proveedor lista la ONU ESPERANDO, con el lugar sacado de esa fila; interruptor
  pegado a la escritura; puerta HUMANA; clave fija por pedido y sin reintentar lo
  que falló; confirma leyendo, y lo que no se ve a tiempo queda EN CURSO, no
  «falló». El ejecutor aprendió a mandar formulario (`form_urlencoded`) y un
  tiempo de espera propio (`timeout_segundos`, 90 s). Clase de riesgo: R2 con los
  asteriscos del alta (`tests/test_m10a_gobierno_frontera.py`) — **abierto para
  el dueño del producto**, igual que el alta.
- **Plataforma** (`campo/activacion_onu.py`, migración 0059): el interruptor
  `activar_onu` (apagado de fábrica) y la VLAN de cada servidor en Programación;
  el registro de cada pedido (`ActivacionDeOnu`) y la tarea que mira hasta saber
  y, si no, lo deja «por revisar».
- **App**: el botón de paso `onu` («Activar la ONU», v7 de la plantilla en
  Instalación). Busca con cada valor escrito en los campos del paso que se leen
  con la cámara, hasta que la red reconozca uno (el paso tiene dos: serial y
  precinto, y no se adivina por el nombre); muestra OLT, placa y puerto, la zona
  sugerida y la VLAN; pide y espera el resultado.

**Verificado en vivo, sin escribir** (con `SIN_EFECTOS_EXTERNOS`): un serial
inventado → «no espera»; la ONU real que esperaba → OLT 3, placa 3, puerto 6, la
VLAN 300 del servidor del contrato y las 60 zonas; y el pedido por la cadena
entera (app → servidor → tarea → motor) llegó al último paso y la guarda lo
frenó: «no salió». La ONU siguió esperando.

**Lo que falta para encenderlo de verdad:**
1. La prueba vigilada, con permiso explícito del usuario: activar UNA ONU real
   de una instalación real, fuera de este entorno (o levantando la guarda solo
   para esa llamada), y mirarla después en SmartOLT.
2. En producción: las migraciones 0057–0059, las cuatro herramientas en la
   configuración de la empresa (por el editor, sin pisar lo que solo tiene la
   base), la VLAN de cada servidor y el interruptor en Programación.
3. Una zona sugerida necesita que el barrio del contrato se parezca a una zona
   de SmartOLT; con barrios de prueba no sugiere y el técnico elige.

### La ONU de «Material utilizado» sale del serial — 1.0.25, 26/11/2026

El usuario: «en material utilizado, donde dice ONU GPON, debe llenarse solo al
momento que el técnico escanea, para no volver a escribir». La línea de la ONU
en la lista de material dice de qué campo sale (`campo: "Serial de la ONU"`, el
mismo marcador que ya llevaba los metros de fibra): en un material común es la
cantidad; en un equipo con serie, **la serie**. La app la muestra tal cual se
escaneó (sin espacios, en mayúsculas), sin lista para elegir ni casilla para
escribir; si todavía no se escaneó, dice dónde hacerlo y no deja registrar. Una
serie que no está en el kit del técnico se avisa y se registra igual: el equipo
ya está instalado, y la diferencia la cuadra la bodega. En el editor de
Plantillas, «O sale del campo» ofrece ahora también los campos de texto.
Pruebas: `material_precargado_test.dart`, 3 nuevas (11).

### El contrato a nombre de otra persona — 1.0.26, 26/11/2026

El usuario: «cuando el técnico llegue y el contrato se hace a nombre de otra
persona, pero los otros datos siguen igual: solo cambiarían el nombre, el
apellido y la cédula». En el bloque «El cliente» del contrato, un botón **«A
nombre de otra persona»**: vacía nombre, apellido y documento, pide el tipo de
documento y muestra las dos autorizaciones para que esa persona las acepte ahí
mismo (habeas data obligatoria). Lo demás sigue igual, y «Volver a los datos de
la solicitud» deshace. El PDF dice que no es quien hizo la solicitud y que
aceptó al firmar; Instalaciones muestra a nombre de quién quedó; el alta en
WispHub sale con la persona nueva. Una cédula cambiada sin el botón se firma
como antes, la app lo advierte y queda `documento_cambiado`. Detalle: PRD §8.35.

### La prueba vigilada: la primera ONU activada de verdad — 26/11/2026

Con el permiso explícito del usuario («Sí, solo esa ONU»; la borra él después
en SmartOLT). Lo que pasó, en orden (horas de Bogotá):

1. 15:38 — «no la encontró», y 23 s después sí: SmartOLT tardó en ver la ONU
   recién conectada. **Arreglado en la app (1.0.27):** si no aparece, vuelve a
   buscar sola cada 8 s, hasta 8 veces, y lo dice («sigo buscando»).
2. 15:39 y 15:41 — «no salió»: la guarda `SIN_EFECTOS_EXTERNOS`, como debía.
   Para no apagar el entorno entero (WhatsApp incluido) se agregó una lista
   angosta, `EFECTOS_EXTERNOS_PERMITIDOS` (por nombre exacto, vacía por
   defecto, `nucleo/seguridad/entorno.py`, con su prueba), y se abrió SOLO
   para `autorizar_onu_en_smartolt`.
3. 16:04 y 16:05 — «la red rechazó la activación»: 400, sin decir por qué.
   **Arreglado:** el motivo del proveedor queda en el pedido y se ve en la app
   (`activar_onu.motivo_del_rechazo`: solo el texto del error, corto, nunca la
   respuesta entera ni al log).
4. 16:10 y 16:11 — el motivo: `onu_mode` es obligatorio. Medido: las 112 ONU
   que Rapilink autorizó en dos semanas están en `Routing`. Quedó como dato fijo
   de la herramienta en la configuración (`argumentos_fijos: {onu_mode:
   Routing}`), en el YAML y en la base local (versión 11).
5. 16:14 — **«ONU activada en la red»**, confirmada leyendo. El permiso se
   cerró enseguida. Después la ONU apareció otra vez esperando en 3/3/15: la
   borró el usuario, como se acordó.

**En producción, además de lo de antes:** `argumentos_fijos: {onu_mode:
Routing}` en `autorizar_onu_en_smartolt` (por el editor, sin pisar lo que solo
tiene la base). `EFECTOS_EXTERNOS_PERMITIDOS` no existe en producción ni hace
falta: allá no hay `SIN_EFECTOS_EXTERNOS`.

### El dinero que recibe el técnico — 1.0.28, 26/11/2026

El usuario: «falta aún registrar el dinero que recibe el técnico». Eligió:
instalación y equipos o material extra, solo efectivo, el técnico escribe
cuánto, y queda en Dexter para que la oficina lo reciba (no WispHub).

- **En la plantilla**: un dato de número con la casilla «Es dinero que recibe el
  técnico». En local, «Instalación de fibra» **v8** lo trae en «Configuración y
  entrega»: «Valor de la instalación» (obligatorio; «si no cobraste, escribe
  0»), «Equipos o material extra» y «Qué equipos o material cobraste» (texto).
  La OT-20 (la única abierta) pasó a v8.
- **En la app (1.0.28)**: el dato sale con «$», solo dígitos y «efectivo».
- **En la web**: Campo → **Dinero de técnicos** (solo gestión): cuánto tiene
  cada uno por entregar, de qué órdenes y conceptos, y «Recibí $X de …».
- **En producción**: la migración 0060 y marcar los datos en la plantilla de la
  empresa (desde Plantillas).

**Una falla que no es de esto:** `test_la_accion_relee_la_asignacion` (b y b2)
falla en el entorno local con o sin estos cambios («database table is
locked»): son carreras entre dos transacciones y las pruebas corren sobre
SQLite. CLAUDE.md §6 pide Postgres para eso.

## Bitácora

| Fecha | Qué | Evidencia | Hash |
|---|---|---|---|
| 02/11/2026 | **Encuadrado y aparcado a pedido del usuario.** Barrido completo: `apps/tecnicos-mobile/lib/` entero (91 `.dart`), `campo/` (57 módulos), la skill de SmartOLT (788 líneas), la de WispHub, `M06-D`, el catálogo (91 herramientas, 9 roles). Nada construido, ninguna API llamada, producción no leída | informe del arquitecto | — |
| 25/11/2026 | **El formato de instalación, planeado con el usuario, y la parte de servidor del contrato construida.** Los datos llegan con el formato de la empresa (tres costumbres configurables en Programación), el plan se reconoce contra `planes_venta`, el servidor se elige entre los del plan, mandan las coordenadas del ticket, y un contrato se anula para firmar otro. **No construido:** nada de la app (pide APK nuevo), ni el alta ni la baja en WispHub | Backend: `test_contrato_formato_y_plan.py` + `test_contrato_de_servicio.py` + `test_ips_libres.py`, **167 pasan**; `makemigrations --check`: sin cambios. Web: `contrato.test.js` + `programacion/page-server.test.js`, **46 pasan**. Seis mutaciones (formato al firmar, filtro de servidor por plan, anular uno que ya está en el ISP, cuál GPS manda, anulado contando como vigente, plan fuera del catálogo) dejaron **10 pruebas en rojo**; restauradas. En vivo, en el entorno local: el contrato de OT-11 y OT-12 pedido por HTTP con el catálogo real del motor; firmar → reintento → anular → firmar otro sobre OT-20 (borrado después); el formulario de Programación abierto y guardado en un navegador. **No se corrió** la suite completa del backend ni nada en un teléfono | commit del 26/11/2026 |
| 25/11/2026 | **El alta en WispHub, construida y APAGADA de fábrica; nunca probada contra WispHub de verdad.** Motor (`alta_de_cliente.py`, dos rutas, marcas nuevas en el esquema, tres herramientas en la config), backend (servicio, tarea, interruptor de la empresa, estado del alta en el contrato) y web (interruptor en Programación; Instalaciones muestra el resultado). **Dos revisiones independientes antes de darlo por hecho** — frontera y PII —: la de frontera encontró que lo incierto se informaba como fallo y podía terminar en un cliente duplicado; se rehízo con el estado «por revisar», sin «reintentar», con la herramienta fuera de la ruta genérica y con reserva de IP entre contratos. **Abierto:** la prueba vigilada contra WispHub, los rangos de IP (y su pantalla), la clase de riesgo (R2 con asteriscos), la app | Mediciones en solo lectura: los filtros `ip`, `cedula` y `servicio` de `/api/clientes/` sirven, `usuario_rb` y `search` no; 0 de 300 clientes recientes sin cédula; los 6 planes de venta resuelven a su id en vivo. Motor: `tests/test_alta_de_cliente.py` **196**, `tests/test_alta_ruta.py` **52**, `test_m10a_gobierno_frontera`, `test_nucleo_sin_tenants`, `test_coordenada_del_cliente`, `test_editor_config`, `test_ocupacion_ip`, `test_entorno_sin_efectos` en verde; `test_frontera_externa` sigue con sus 15 sin clasificar de antes, ninguna nueva. **17 mutaciones del motor, las 17 detectadas** (una pidió una prueba más). Backend: contrato + alta + IP libres + solicitudes, **232 pasan**. Web: **53 pasan**. En vivo en local, con `SIN_EFECTOS_EXTERNOS`: el alta llega al último metro con lecturas reales y sale «bloqueado», 0 clientes creados en WispHub; la cadena firmar → tarea → motor → Instalaciones → reintentar → anular corre. **No verificado:** ninguna escritura real en WispHub; la pantalla de Instalaciones en un navegador con un caso «por revisar»; la suite completa del backend | commit del 26/11/2026 |
| 25/11/2026 | **El formato de instalación como plantilla (v2 y v3 en local) y los documentos «solo en la plataforma».** Las órdenes de prueba OT-12..20 pasaron a v3 (OT-11 quedó en v1: ya estaba en sitio) | El teléfono de Dilan recibe los 4 pasos y las 10 fotos (leído por la ruta de la app). `test_fotos_solo_en_la_plataforma.py` **7**, y quitar el filtro de cualquiera de los dos caminos las pone en rojo (2 y 1). `test_fotos_al_ticket`, `test_las_fotos_van_al_isp`, `test_plantillas_editables` en verde. El editor web abre v3 con la casilla marcada en las 3 fotos de documentos y desmarcada en las otras 7 | commit del 26/11/2026 |
| 25/11/2026 | **La pantalla de rangos de IP, y la lectura de ocupación conectada por primera vez.** La app no podía ofrecer ninguna IP libre: la lectura no estaba declarada para Rapilink ni la disparaba ninguna pantalla. **Abierto:** qué son los 51 prefijos `168.x` | Motor: `tests/test_rangos_de_ip.py` **49**, `test_ocupacion_ip` 59, `test_alta_de_cliente` y `test_nucleo_sin_tenants` en verde. Web: `rangos-de-ip.test.js` + Programación + contrato + Instalaciones, **63 pasan**. En vivo en un navegador: leer la ocupación (7.711 clientes, completa), usar los sugeridos, guardar, volver a abrir; 0 errores de página. Después: 20 IP libres por servidor en la app y las tres respuestas del alta descritas arriba | commit del 26/11/2026 |
| 26/11/2026 | **La instalación, entera desde la app (1.0.20 a 1.0.25).** Contrato rediseñado, botones por paso en la plantilla, IP que pone el servidor, coordenadas en un mapa, material precargado (la fibra y la serie de la ONU salen de sus campos), puntos de TV, la IP para copiar y «Activar ONU» en SmartOLT construido APAGADO. **No probado contra SmartOLT ni WispHub de verdad**; PRD §8.34 | Backend 319, motor 8 archivos en verde, web 71, app 1.491; en vivo sin escribir: la ONU real encontrada en OLT 3 · placa 3 · puerto 6 y el pedido frenado por la guarda en el último paso | commit del 26/11/2026 |
| 26/11/2026 | **El contrato a nombre de otra persona (1.0.26).** Modo explícito en la pantalla del contrato; la persona nueva acepta sus autorizaciones al firmar, el PDF y la oficina lo dicen, el alta sale con ella. PRD §8.35 | Backend 247 (16 nuevas), web 19, app 1.496 | sin commit |
| 26/11/2026 | **La primera ONU activada de verdad, en prueba vigilada (1.0.27).** SmartOLT exige `onu_mode` (Routing, 112 de 112 medidas); el motivo de un rechazo queda a la vista; la app busca sola la ONU recién conectada; permiso angosto `EFECTOS_EXTERNOS_PERMITIDOS`, abierto y cerrado. PRD §8.36 | La ONU de prueba (3/3/15) quedó «activada» confirmada leyendo y el usuario la borró; `test_activar_onu`, `test_entorno_sin_efectos` y la guarda de arquitectura en verde; app `activar_onu_test` 6 | sin commit |
| 26/11/2026 | **El dinero que recibe el técnico (1.0.28).** Marca `dinero` en los datos de número de la plantilla; la oficina lo recibe en «Dinero de técnicos» con la cifra que vio. PRD §8.37 | Backend 20 nuevas (119 con plantillas y formulario), web 18, app 1.498; la página abre en local | sin commit |
| 26/11/2026 | **El alta en WispHub, probada de verdad (prueba vigilada).** Primer intento frenado por «IP ocupada» (foto de ocupación vieja) → la IP se pregunta en vivo al firmar; segundo intento: cliente creado (servicio 8039) y confirmado leyendo; lo borra el usuario. Al pasar, un guardado en Programación borró la config local del contrato: restaurada (825 bytes, igual que el último guardado bueno) y arreglado el formulario. PRD §8.38 | Motor en verde, backend 133, web 47, navegador real | sin commit |
| 26/11/2026 | **La instalación que valida una persona (1.0.29).** Al finalizar se crea como instalación (costo y ONU); se aprueba en Instalaciones → «Por activar», que la activa; al técnico le llega «valida y entrega»; al confirmar se cierra el ticket. Supervisor automático excluido. Falta: la lectura de cédula y recibo con IA, y la prueba vigilada de «activar». PRD §8.39 | Motor en verde; backend 24 + 271; web 13; app 1.501 | sin commit |
| 26/11/2026 | **El motor entra al panel web de WispHub (paso 1 del contrato de WispHub).** Tipo de herramienta `web` genérico: entra, abre, reenvía un formulario tal como viene y lee un dato; mismo último metro que la API; sesión reusada por el 429 medido a la quinta entrada. Tres herramientas de Rapilink (preparar el contrato, enlace, firma). Guardado vigilado del contrato 4928: rechazado dos veces por archivos de menos de 1 KB (texto intacto) y guardado al tercero; los archivos van por el bloque «Archivo + Título», que es «Subir Archivos». Falta: varias filas en un guardado, y los pasos 2–4. PRD §8.40 | `test_panel_web` 75 + 6 mutaciones; guardas y vecinas en verde; lecturas reales con una sola entrada | sin commit |
