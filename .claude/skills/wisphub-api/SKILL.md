---
name: wisphub-api
description: Integrar o ampliar la conexion con la API de WispHub (o la de cualquier otro ISP). Usar al agregar herramientas al catalogo de un tenant, al dar de alta un ISP nuevo, o al tocar filtros, agregaciones y endpoints. Contiene el metodo de verificacion obligatorio y los hallazgos ya confirmados en produccion.
---

# API de WispHub — integrar sin que te mienta

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

## Endpoints aun sin explorar

```
/api/clientes/{id}/saldo/     /api/zonas/        /api/plan-internet/
/api/staff/                   /api/gastos/  (verificado: existe, vacio)
```

Mas las operaciones de escritura: crear tickets, actualizar clientes. La unica
escritura verificada hasta hoy es `POST /api/facturas/{id}/registrar-pago/`.

## Antes de dar por buena una integracion

- [ ] Cada filtro del catalogo tiene `verificado_el`
- [ ] Los ignorados estan listados con su motivo, en lenguaje que un asesor entienda
- [ ] Los agrupables son todos verificados
- [ ] Los rangos de fecha se validan antes de llamar
- [ ] Ningun campo de contrasena o coordenada entra a una lista blanca
- [ ] El total de un desglose **cuadra** con el total sin agrupar
