---
name: wisphub-api
description: Integrar o ampliar la conexion con la API de WispHub (o la de cualquier otro ISP). Usar al agregar herramientas al catalogo de un tenant, al dar de alta un ISP nuevo, o al tocar filtros, agregaciones y endpoints. Contiene el metodo de verificacion obligatorio y los hallazgos ya confirmados en produccion.
---

# API de WispHub — integrar sin que te mienta

## Como leer TODA la documentacion sin un navegador

`wisphub.net/api-docs/` es una pagina renderizada con ReDoc: el HTML que se
descarga esta practicamente vacio (solo un titulo), y el contenido real lo
inyecta JavaScript en el navegador. Herramientas que solo piden el HTML (sin
ejecutar JS) ven la pagina vacia y concluyen —erroneamente— que no hay nada
que leer ahi.

**No hace falta un navegador ni Playwright.** ReDoc se inicializa apuntando a
un archivo YAML estatico que contiene TODA la especificacion, sin renderizar:

```python
# el HTML crudo de /api-docs/ contiene esta linea:
#   Redoc.init("/static/yaml/api/api-main.yaml", {...}, ...)
import requests, yaml
r = requests.get("https://wisphub.net/static/yaml/api/api-main.yaml")
spec = yaml.safe_load(r.text)          # OpenAPI 3.0 completo, 54 rutas
```

El archivo bajado queda en `reference/openapi.yaml` de esta skill. Aun asi,
sigue aplicando la regla de siempre: **el spec dice que existe, no que
funcione como dice.** El propio archivo trae un error verificado — su bloque
`servers:` apunta a `api.wisphub.net`, y la produccion real es `api.wisphub.io`.
Ni el dominio del spec se da por bueno sin comprobar.

## La regla, antes que nada

> **La documentacion de la API es una HIPOTESIS, no una fuente de verdad.
> Ningun parametro entra al catalogo sin haber sido verificado contra la API real.**

No es prudencia excesiva. Esta medido: la API **ignora filtros en silencio** y
devuelve el universo entero como si fuera la respuesta filtrada. No da error, no
avisa, no falla. Un total exacto respondiendo otra pregunta es peor que un error,
porque nadie lo detecta.

## El metodo del valor imposible

Se consulta con un valor que no puede existir y se compara contra el total sin
filtro. Si coinciden, la API esta ignorando el parametro.

```
total sin filtro                   = N
total con ?campo=999999999         = N   ->  IGNORADO    (inservible)
total con ?campo=999999999         = 0   ->  RESPETADO   (sirve)
```

Un tercer caso: `HTTP 400`. Significa que la API **conoce** el parametro y valida
su formato — hay que revisar como se envia, no descartarlo.

Y no basta con que el imposible de 0: hay que probar tambien con un **valor real**
tomado de la propia data. Un parametro que siempre devuelve 0 tampoco sirve.

```python
# Patron minimo
base  = contar(endpoint, {})                      # sin filtro
imp   = contar(endpoint, {campo: 999999999})      # valor imposible
real  = contar(endpoint, {campo: <valor de la data>})

sirve = (imp == 0) and (0 < real < base)
```

Para valores reales: traer unas filas del propio endpoint y leer el campo. Ojo con
los campos que vienen anidados (`{"id": 12, "nombre": "..."}`): se prueba con el id.

## Hallazgos verificados (Rapilink, julio-agosto 2026)

### Filtros que SIRVEN

| Entidad | Filtro | Notas |
|---|---|---|
| clientes | `estado` | **NUMERICO**: 1 activo, 2 suspendido, 3 cancelado, 4 gratis |
| clientes | `plan_internet`, `ciudad`, `localidad` | |
| clientes | `router`, `tecnico` | Hallados en agosto. `router` es la via para agrupar por zona geografica: en una red WISP el router ES la zona fisica |
| clientes | `telefono__contains` | Verificado agosto 2026 (metodo del valor imposible: `telefono__contains=9999999999` -> 0). `telefono=<valor>` (sin `__contains`) NO sirve para buscar un numero individual: el campo guarda varios numeros separados por coma (`"3242124123,3002687147"`) y el match es EXACTO contra la cadena completa, asi que un solo numero da 0. `__contains` si matchea un numero suelto dentro de la cadena. Es la via para identificar a un cliente de WhatsApp por su numero (ver `Autenticacion.patron_extraccion` en `nucleo/config/schema.py`) — probar primero con `__contains`, nunca asumir que el filtro exacto alcanza. |
| facturas | `estado` | 1 pendiente, 2 pagada, 3 cancelada, 4 en revision, 5 transferida |
| facturas | `zona` | Las 5 zonas suman exacto el total |
| tickets | `estado` | 1 nuevo, 2 en progreso, 4 cerrado |

### Filtros que la API IGNORA — nunca intentarlos

| Entidad | Filtro ignorado | Alternativa |
|---|---|---|
| clientes | `zona` | Usar `router`. Las **facturas** si se pueden contar por zona |
| clientes | `estado_facturas` | Contar facturas en estado `pendiente` (cuenta facturas, no clientes) |
| clientes | `saldo` | — |
| clientes | fechas (cualquier forma) | No se pueden contar altas de un mes |
| facturas | `facturadas` | — |
| tickets | `departamento`, `tecnico`, `prioridad` | — |
| tickets | cliente (8 nombres probados) | Filtrar por estado y cruzar en codigo, solo sobre los abiertos |

## Descubrir endpoints: GET no basta, usar OPTIONS

Un sondeo por GET marca como inexistente todo endpoint de solo escritura. `OPTIONS`
devuelve la cabecera `Allow` y revela lo que de verdad se puede hacer:

```bash
OPTIONS /api/tickets/   ->  Allow: GET, POST, HEAD, OPTIONS
```

### Mapa de lectura/escritura (verificado, agosto 2026)

| Endpoint | Metodos | Nota |
|---|---|---|
| `/api/clientes/` | GET | La coleccion NO acepta POST — pero ver el endpoint de accion, abajo |
| `/api/clientes/agregar-cliente/{id_zona}/` | POST | **SI se pueden crear clientes.** No vive en la coleccion: hay que sondear tambien endpoints de accion, no solo colecciones y recursos |
| `/api/clientes/agregar-cliente/{id_zona}/?instalacion` | POST | Crea una INSTALACION en vez de un cliente. Habilita `costo_instalacion` y `estado_instalacion`, y fuerza `firewall=true` |
| `/api/clientes/{id}/` | GET, PUT, PATCH, DELETE (segun `OPTIONS`) | **`DELETE` aqui NO funciona** — da HTTP 500. Ver aviso abajo |
| `/api/clientes/{id}/perfil/` | DELETE | **El borrado real.** Verificado end-to-end contra produccion — ver aviso abajo |
| `/api/tickets/` | GET, POST | Se pueden crear tickets |
| `/api/tickets/{id}/` | GET, PUT, PATCH | Se pueden actualizar |
| `/api/facturas/` | GET, POST | |
| `/api/gastos/` | GET, POST | Vacio, pero **acepta escritura** |
| `/api/zonas/`, `/api/plan-internet/`, `/api/staff/` | GET | Catalogos de solo lectura |

> **AVISO — se puede borrar un cliente (por `/perfil/`, ver mas abajo).**
> La misma clave que usa el asistente para consultar puede borrar un cliente. La
> proteccion es que ninguna herramienta declare esa operacion: el catalogo del
> tenant es lista blanca y solo existe lo declarado. Ninguna herramienta debe
> exponer el borrado, y toda escritura exige `requiere_confirmacion: true` (el
> validador lo obliga).

> **`/api/gastos/` acepta POST.** Esta vacio hoy, y por eso el informe de
> materiales tuvo que salir del texto de los tickets. Pero es escribible: si en
> algun momento se decide poblarlo, el informe dejaria de depender de parsear
> formularios en HTML.

### Crear cliente / instalacion — esquema confirmado (documentacion oficial, agosto 2026)

```
POST /api/clientes/agregar-cliente/{id_zona}/[?instalacion]
```

Requeridos — SOLO estos tres, confirmado por dos vias independientes: la
documentacion oficial Y un `POST` vacio, que devolvio el mismo trio como error
de validacion. Cuando dos fuentes independientes coinciden, sube la confianza
mucho mas que confiar en una sola:

| Campo | Tipo | Que es |
|---|---|---|
| `usuario_rb` | string | Nombre de usuario en el router. Equivalente a Simple Queue / Secret PPPoE / PCQ / User Hotspot **segun el tipo de cliente** — el formato varia; confirmar contra un cliente real antes de automatizar |
| `ip` | string | IP del cliente (Remote Address para PPPoE) |
| `plan_internet` | integer | ID del plan, consultado en `/api/plan-internet/` |

**La respuesta es asincrona**: devuelve un ID de tarea, no el cliente creado.
El proceso corre en segundo plano — mismo patron que `registrar_pago`, que
tambien devuelve `task_id`. Hay que consultar el resultado de la tarea aparte
para confirmar que se creo de verdad.

**Campos opcionales de escritura que NUNCA debe proponer el modelo**, aunque el
esquema los acepte: `password_servicio`, `password_cpe`, `password_router_wifi`,
`password_ssid_router_wifi`, `coordenadas`. Mismo criterio que en lectura —lista
blanca por rol— pero aplicado a lo que se ESCRIBE. Una herramienta de "crear
cliente" debe fijar estos campos en codigo (vacios o ausentes), nunca dejar que
el modelo los complete.

**Descuido de la documentacion de WispHub, no nuestro**: `mac_cpe` aparece
descrito como "Coordenadas" —copiado del campo `coordenadas`, al que si le
corresponde esa descripcion—. Otra razon para no confiar en las descripciones
de campo sin verificar contra datos reales.

Campos opcionales relevantes para operar: `nombre`, `apellidos`, `email`,
`direccion`, `telefono`, `cedula`, `sectorial`, `sn_onu`, `comentarios`,
`forma_contratacion` (1-7, enum), `tipo_persona` (1 moral, 2 fisica).
Exclusivos de instalacion: `costo_instalacion`, `estado_instalacion`
(1 nueva, 2 en progreso, 7 pendiente, 8 planificacion, 3 activada, 4 terminada).

### Verificado en produccion: crear un cliente de prueba (agosto 2026)

Se creo y se intento retirar un cliente de prueba real, con autorizacion
explicita, para validar el flujo completo. Hallazgos:

**El `usuario_rb` que se envia NO es el campo que se lee de vuelta.** Al leer el
cliente creado, el texto enviado aparece en `servicio`, no en `usuario_rb`.
Ademas WispHub genera solo un `usuario` interno con formato
`slug-del-texto@rapilink-sas`. Es la misma dualidad escritura/lectura que ya se
veia en otros campos — nunca asumir que el nombre de un campo de escritura es
el mismo al leer.

**La zona debe corresponder a la red real de la IP, o el alta puede fallar.**
No hay forma de saberlo de antemano sin conocer la topologia: el catalogo de
zonas trae el numero de servidor en el NOMBRE (`CORTE 15 - SERVIDOR 1`,
`CORTE 30 - SERVIDOR 1`, etc.), y hay que cruzarlo contra los segmentos IP
documentados en la guia de configuracion de ONT del cliente, no adivinar.

**`interfaz_lan` en blanco es NORMAL, no un dato faltante.** Verificado
comparando contra 15 clientes reales y activos: varios de los mas recientes lo
tienen vacio, y valores como `ether2` o `vlan300_clientes_S1` SI aparecen en
clientes reales — no son un relleno del serializador. El campo se completa en
un paso posterior (conexion/sincronizacion del router), no al crear el cliente
por API. Una herramienta de creacion NO necesita enviarlo.

> **Borrar un cliente NO es `DELETE /api/clientes/{id}/` — es un sub-recurso.**
>
> El endpoint que documenta `OPTIONS` (`Allow: ..., DELETE`) sobre
> `/api/clientes/{id}/` **no funciona**: devuelve HTTP 500 (error interno,
> pagina HTML) y el cliente sigue existiendo. Es el mismo patron enganoso que
> `OPTIONS` mostro con otros campos: que un metodo aparezca permitido no
> significa que el endpoint lo implemente de verdad.
>
> El que SI funciona, verificado end-to-end contra produccion:
>
> ```
> DELETE /api/clientes/{id}/perfil/
> ```
>
> Sigue el mismo patron asincrono que crear: responde `202` con un `task_id`,
> y hay que consultar `/api/tasks/{task_id}/` para confirmar `SUCCESS`. Una
> vez creido eso, se verifico ADEMAS con un `GET /api/clientes/{id}/` aparte
> —no basta con el mensaje de la tarea— y dio `404`: confirmado, se elimino
> de verdad.
>
> **Leccion que vale para toda esta API**: no asumir el endpoint por analogia
> REST estandar (`DELETE` sobre el recurso). Las operaciones no estandar
> —crear, borrar— viven en sub-rutas de accion (`/agregar-cliente/{zona}/`,
> `/{id}/perfil/`), no en el CRUD obvio de la coleccion o el recurso.
>
> **Sobre `PATCH {"estado": 3}` para cancelar en vez de borrar**: sigue sin
> confirmarse que funcione — dio `200` con eco de exito pero la lectura
> posterior no reflejo el cambio (verificado con 3 reintentos espaciados).
> No descartado del todo: podria requerir otro formato de valor o un endpoint
> de accion propio, igual que borrar. Sin verificar todavia.

## Trampas que ya costaron tiempo

**Los filtros de estado son NUMERICOS.** `?estado=Nuevo` devuelve 0 resultados
sin error alguno. Parece "no hay tickets nuevos"; en realidad la consulta no
existe.

**El `next` del paginado viene en `http://`.** Seguirlo enviaria la clave del API
en texto plano. Se pagina con `offset` propio sobre HTTPS y no se sigue nunca esa
URL.

**Sin filtro de fecha, la API aplica un recorte propio.** No devuelve el
historico. Medido en tickets: sin filtro da 2.635, pero solo julio da 2.637 y
junio 3.341 — un subconjunto no puede superar al conjunto. Ese total no sirve
para comparar nada. En facturas el recorte son ~2 ultimos meses de emision.

**Los rangos de fecha tienen tope.** Facturas corta en 3 meses, tickets en 2.
Mas alla devuelve HTTP 400. Se valida ANTES de llamar, o el asesor ve un
"fallo al llamar a WispHub" sin saber por que.

**El campo `telefono` guarda varios numeros en uno.** El 55% de los clientes.
Leerlo como valor unico da 43% de cobertura; extrayendo todos los moviles
(`(?<!\d)3\d{9}(?!\d)`), 98.7%.

**El registro de cliente trae 54 campos**, incluidas **cuatro contrasenas**
(`password_cpe`, `password_servicio`, `password_router_wifi`,
`password_ssid_router_wifi`) y las **coordenadas GPS** del domicilio. Por eso la
lista de campos es BLANCA por rol y no negra: con lista negra, un campo nuevo
del proveedor queda expuesto por defecto.

**Un endpoint puede existir y estar vacio.** `/api/gastos/` responde 200 con 0
registros. "Existe" no significa "tiene datos".

## Hallazgos de otra integracion con la misma API

Provienen de `isp-reports-app`, otro desarrollo sobre WispHub. **No estan
verificados contra esta instancia** salvo donde se indica, pero son cicatrices
reales de produccion y conviene tenerlas presentes antes de tropezar con ellas.

**El tecnico puede venir en `email_tecnico` y no en `tecnico`.** En ciertos
tickets —sobre todo instalaciones asignadas automaticamente— la API devuelve
`tecnico: null` mientras la asignacion real vive en `email_tecnico`
(ej. `instalaciones@rapilink-sas`). Quien lea solo el campo obvio concluye que
el ticket no tiene tecnico. El campo existe en la respuesta cruda (confirmado
aqui); lo no verificado es la frecuencia del caso.

**Desfase horario de +5 horas en fechas de cierre.** Un ticket cerrado a las
7 PM aparece con fecha del dia siguiente a las 00:00. Afecta cualquier metrica
diaria y hace "desaparecer" los cierres de la tarde.

**Formatos de fecha mezclados: MM/DD y DD/MM en la misma API.** Causo un bug de
"43.201 minutos" al interpretar `02/09/2026` como septiembre en vez de febrero.
Heuristica usada alla: si el primer numero es >12 es DD/MM; si el segundo es >12
es MM/DD; si ambos son <=12, asumir MM/DD.
**Para nosotros:** al FILTRAR enviamos ISO (`AAAA-MM-DD`), que es inequivoco. El
riesgo esta al PARSEAR respuestas — las fechas vienen como `08/04/2026 11:14:56`
y son ambiguas.

**Trailing slash inconsistente.** Unos endpoints exigen barra final y otros
fallan con ella. Conviene reintentar con la variante contraria ante un 404.
(Probado aqui sobre los endpoints ausentes: dan 404 en ambas formas.)

**`do_not_notify_client: true`** en `/api/tickets/comentarios/` permite dejar
notas internas sin enviar correo al cliente. Es un flag no documentado
oficialmente. Ese endpoint da 404 en esta instancia — puede ser diferencia de
version o de plan.

**El asunto se guarda como `"Asunto - Cliente"`**, y el catalogo de origen trae
errores de tipeo (`INSTATALACION NUEVA`). Al categorizar hay que cortar en
` - ` y contemplar los typos tal como vienen.

**La URL correcta es `api.wisphub.io`.** `www.wisphub.io` devuelve 403 en `/api/`
y `wisphub.net` es solo documentacion. Si la respuesta trae `<!DOCTYPE html>`,
la URL base esta mal.

## Como se traduce un hallazgo al catalogo

Todo va a `tenants/<slug>.config.yaml`, nunca al codigo del nucleo:

```yaml
  - nombre: contar_clientes
    tipo: agregado
    entidad: clientes
    endpoint: /api/clientes/
    auth_ref: WISPHUB_API_KEY          # el NOMBRE, jamas la clave
    filtros_verificados:
      estado:
        param: estado
        tipo: enum
        valores: {activo: 1, suspendido: 2, cancelado: 3, gratis: 4}
        verificado_el: 2026-07-29      # cuando se probo
      router: {param: router, tipo: id, verificado_el: 2026-08-04}
    filtros_ignorados_por_api:
      zona: >
        La API de clientes IGNORA el filtro por zona (devuelve los 7.272).
        Para agrupar clientes geograficamente usa 'router'.
    agrupar_por: [estado, router]      # SOLO campos verificados
```

Reglas que el validador (`nucleo/config/schema.py`) hace cumplir:

- Un filtro no puede estar en `filtros_verificados` y en `filtros_ignorados_por_api` a la vez
- `agrupar_por` solo admite campos verificados — agrupar cuesta **una llamada por valor**, y si el campo se ignora, cada llamada devuelve el universo y el desglose es basura con aspecto de dato
- Un filtro ignorado se **rechaza con su motivo**, no se intenta igual

## Al dar de alta un ISP nuevo

El catalogo **no se copia entre tenants**. Cada instalacion se comporta distinto:
en Rapilink `sectorial` y `asesor` vienen vacios; en otro ISP pueden estar
poblados, y su API puede ignorar cosas distintas.

El paso obligatorio del onboarding es correr el sondeo contra SU instancia y
generar su seccion `herramientas` con lo que sobreviva.

## Catalogos nuevos: verificados por lectura (agosto 2026)

Descubiertos en `reference/openapi.yaml` (ver arriba como conseguirlo) y
confirmados contra produccion `.io` con un `GET` real:

| Endpoint | Registros | Nota |
|---|---|---|
| `/api/router/` | 5 | **Singular**, no `routers`. Traduce ID de router a nombre — ver aviso critico abajo |
| `/api/sectorial/` | 1 | **Singular**, no `sectoriales` |
| `/api/proveedores/` | 5 | |
| `/api/modelo-antena/` | 72 | |
| `/api/formas-de-pago/` | 4 | |
| `/api/categorias-gastos/` | 40 | Relevante si algun dia se puebla `/api/gastos/` |
| `/api/planes-adicionales/` | 1 | |
| `/api/servicios-adicionales/` | 3704 | |
| `/api/instalaciones/` | 1 | Trae un registro con forma de cliente completo (nombre, cedula, direccion, email). Parece ser instalaciones PENDIENTES actuales, no historico — sin confirmar del todo |
| `/api/fichas/` | 0 | Sistema de fichas/hotspot; Rapilink no lo usa |
| `/api/tarjeta-cobranza/` | 0 | Sin uso en esta instancia |
| `/api/tickets/asuntos-tickets/` | — | Catalogo completo de ~140 asuntos. Confirma el hallazgo de otro proyecto: `"Instalacion Nueva"` y `"Instatalacion Nueva"` (typo) conviven como valores DISTINTOS del catalogo de origen |
| `/api/promesa-pago/` | — | `GET` con `limit=1` da `405`. Probablemente solo `POST`, o exige otros parametros — sin confirmar |

> **CRITICO — `zona` y `router` son catalogos con IDs INDEPENDIENTES, aunque
> compartan nombre.**
>
> ```
> ZONAS (/api/zonas/)              ROUTER (/api/router/)
> 32278  SABANAGRANDE              32229  SABANAGRANDE
> 20053  CORTE 15 - SERVIDOR 1     20044  CORTE 15 - SERVIDOR 1
> ```
>
> El mismo nombre, IDs distintos. Usar un `id_zona` donde se espera un
> `id_router` (o al reves) es un entero valido que la API aceptaria sin
> quejarse, apuntando a algo que no es. **Nunca asumir que el ID de una zona
> sirve para el filtro `router`, ni viceversa** — son dos catalogos que hay
> que consultar por separado.

## Endpoints de escritura/accion sin verificar — no probar sin autorizacion explicita

```
/api/clientes/eliminar-clientes/        posible borrado MASIVO
/api/facturas/eliminar-facturas/        posible borrado masivo
/api/gastos/eliminar/{folio}/           /api/gastos/editar/{folio}/
/api/fichas/eliminar/
/api/clientes/{accion}/                 patron generico de accion, sin mapear
/api/servicio-adicional/{accion}/       idem
/api/agregar-servicio-telefonia/        /api/agregar-servicio-television/
/api/solicitar-instalacion/             distinto de /api/instalaciones/ y de
                                         ?instalacion en agregar-cliente
/api/facturas/reportar-pago/{id}/       distinto de .../registrar-pago/,
                                         sin diferenciar aun
```

Los que llevan "eliminar" en el nombre son candidatos a **borrado masivo**, no
de un solo registro. Con el antecedente de esta sesion —un `DELETE` en el
recurso obvio que fallaba con 500 mientras la via real era un sub-recurso
distinto— cualquiera de estos puede comportarse distinto a lo que el nombre
sugiere. Ninguno se prueba sin plan concreto y autorizacion explicita.

## Antes de dar por buena una integracion

- [ ] Cada filtro del catalogo tiene `verificado_el`
- [ ] Los ignorados estan listados con su motivo, en lenguaje que un asesor entienda
- [ ] Los agrupables son todos verificados
- [ ] Los rangos de fecha se validan antes de llamar
- [ ] Ningun campo de contrasena o coordenada entra a una lista blanca
- [ ] El total de un desglose **cuadra** con el total sin agrupar
