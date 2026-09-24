# Objetivo · La plataforma atiende a varios ISPs

> Abierto el 24/09/2026. Estado: **abierto**.
> El **qué** y el **por qué** viven en [PRD.md §8.13](../../PRD.md) y no se
> repiten acá: esta ficha es el contrato de ejecución. Si difieren, manda el PRD.

## Qué significa terminado

Ningún lugar del frontend decide de qué empresa son los datos leyendo una
variable de entorno. El tenant sale de **quién inició sesión**, siempre, y por
un solo camino.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| A1 | Ningún lugar lee la variable salvo el ayudante | `grep -rn "PRIVATE_ASISTENTE_TENANT" django-crm/frontend/src` devuelve **1** archivo (el ayudante) + su prueba. Hoy son 70 |
| A2 | El ayudante existe y se lee en un solo lugar | Una prueba de arquitectura que falla si aparece un segundo lector — misma forma que `arquitectura_esquema_test.dart` resolvió en Campo |
| A3 | Dos organizaciones distintas ven datos distintos | Prueba con dos orgs: cada sesión recibe su tenant y **nunca** el del otro. Sin esto, A1 es cosmético |
| A4 | Sin sesión no hay tenant | Falla **cerrado**: sin organización no se sirve un tenant por defecto. Es la misma regla que `app_backend` sin tenant → 0 filas |
| A5 | El frontend sigue andando | `docker exec <frontend> pnpm check` limpio, y las pantallas del asistente cargan |
| A6 | Nada se coló | `git diff --cached --name-only` solo muestra rutas del frontend y el motor |

## Restricciones

- **NO push** — es deploy a producción.
- **NO `pnpm check` en Windows con Docker arriba** — rompe el frontend por
  truncamiento de rutas. Va por `docker exec`.
- **NO abrir un segundo camino a la base.** El frontend entra por Django como
  `crm_user`, que no tiene privilegios sobre el esquema `asistente`. La
  resolución se le pide al motor, por el mismo principio que ya gobierna el
  contexto técnico.
- **NO servir un tenant por defecto** cuando falta la sesión. Un default acá es
  servirle a una empresa los datos de otra.

## Qué NO hacer

- **No mudar el dominio del webhook en este objetivo.** Hay que hacerlo (PRD
  §8.13) pero obliga a reconfigurar Meta y es su propia entrega.
- **No tocar `--workers 1`.** Es el otro techo de la plataforma y se levanta
  moviendo el historial caliente a la base, que es otro trabajo.
- **No dar de alta el segundo ISP.** Esto habilita; el alta es después.

## Lo medido, que define el tamaño

```
70 archivos · 80 apariciones · 0 derivan de la sesión
73 de las 80 son la MISMA linea:  const tenant = env.PRIVATE_ASISTENTE_TENANT;
routes/api 46  ·  routes/(app) 13  ·  lib/server 11  ·  1 prueba
```

Y el supuesto del diseño, **comprobado contra el esquema**:
`asistente.tenant_config` tiene `organization_id` como clave primaria y `slug`
con UNIQUE. Es una biyección, así que la inversa es una función.

## Bloqueos

**B1 · RESUELTO el 24/09/2026.** El motor expone
`GET /tenant-de-organizacion/<organization_id>`: 404 sin default cuando esa
empresa no tiene asistente. Del lado del frontend, `lib/server/v2/tenant.js`
es el único lugar que decide de qué empresa son los datos.

**B2 · RESUELTO el 24/09/2026.** Se levantó el contenedor del frontend y se
verificó con `docker exec ... pnpm check`. Dos mediciones que hacían falta y
que no son obvias:

- **La línea base de `svelte-check` ya estaba en rojo**: 71 diagnósticos (47
  errores, 27 advertencias) antes de tocar nada. El criterio no podía ser «que
  pase» sino **que no empeore**, y eso solo se sabe midiendo antes.
- **La línea base de `pnpm test` también**: 17 archivos y 63 pruebas en rojo,
  idénticas antes y después. Medirla se me pasó primero, que es el mismo error
  que cometí ese día con las 536 pruebas de Campo.

La sustitución se hizo con un script que exige tres condiciones por archivo, y
aun así **8 archivos quedaron rotos**: la heurística «el archivo contiene la
palabra locals» no prueba que la *función* que tiene esa línea la reciba, y no
comprobaba `async` en absoluto. Se revirtieron esos 8 y quedaron 44. Sin la
medición contra la línea base, esos 15 errores nuevos se habrían commiteado.

*(El bloqueo original, por si hay que revisar la decisión:)*

**La sustitución de los lugares no se podía verificar.** Su
comprobación es `pnpm check`, y en Windows con Docker arriba eso reescribe
`.svelte-kit/generated/` con rutas truncadas que después el contenedor no
resuelve — la aplicación entera pasa a devolver 500 con un síntoma que no
apunta a la causa. La salida es `docker exec <frontend> pnpm check`, y **no hay
contenedor de frontend levantado**. Hacer 73 ediciones sin poder comprobarlas
es exactamente cómo se rompe una pantalla sin enterarse.

*(Detalle del bloqueo original, que queda por si hay que revisar la decisión:)*

**De dónde salía la inversa `organización → tenant`.** El motor resuelve
`slug → organization_id`; falta el camino contrario. Tres opciones, y la
tercera es la que encaja con la arquitectura:

| Camino | Problema |
|---|---|
| Que el frontend consulte la tabla | No puede: `crm_user` sin privilegios sobre `asistente`, y la tabla tiene RLS |
| Que el JWT lo traiga | Lo emite BottleCRM, que no conoce el esquema del asistente |
| **Que el motor lo exponga** | Ninguno. Es el mismo principio de `contexto_del_caso` |

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 24/09/2026 | Decisión de producto registrada (PRD §8.13), forma medida, supuesto comprobado | Ejecutar | a416063 |
| 24/09/2026 | **44 de 70 archivos migrados.** Acoplamiento: 70→28 archivos, 80→37 apariciones. `svelte-check` sin un solo diagnóstico nuevo (71 antes, 71 después) | Los 26 restantes: 11 de `lib/server` sin `locals`, 8 con `async`/alcance, 6 `+page.server.js` | — |
| 24/09/2026 | **B1 resuelto.** El motor expone la inversa (`/tenant-de-organizacion/<id>`), con su guarda. El frontend tiene su ayudante único (`tenantDeLaSesion`), 8 pruebas verdes | La sustitución de los 73 lugares | 5f5b88f |
