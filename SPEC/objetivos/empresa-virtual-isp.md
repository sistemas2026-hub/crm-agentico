# Objetivo · La operación de un ISP se mira como una empresa virtual

> Abierto el 29/10/2026. Estado: **abierto** — fase 0 sin arrancar.
> El **qué** y el **por qué** del multi-ISP viven en [PRD.md §8.13](../../PRD.md)
> y en [plataforma-multi-isp.md](plataforma-multi-isp.md); acá no se repiten.
> Si difieren, manda el PRD.

El Centro de Mando pasa de ser una pantalla que dibuja agentes a ser una
**empresa virtual isométrica configurable por empresa**: departamentos, puestos,
personajes y oficinas que cada ISP define sin tocar código.

---

## Qué significa terminado

Un ISP entra a la plataforma, ve su empresa dibujada con **sus** departamentos
—los que él configuró, no los de Rapilink—, y cada animación operativa que
ocurre en esa oficina puede rastrearse hasta el evento del motor que la causó.

---

## Lo que se midió antes de escribir esto

Todo lo de abajo está medido contra `origin/fix/integracion-wisphub` el
29/10/2026, no recordado. Cinco de estas cifras corrigen un diagnóstico previo
de esta misma sesión.

```
roles del tenant            9        (soporte, facturacion, administracion,
                                      cliente_final, facturacion_cliente,
                                      soporte_tecnico_cliente, ventas,
                                      configuracion_guiada, supervisor_noc)
herramientas del catalogo  84        con roles_permitidos y solo_lectura
areas en config.areas       5        administracion, cartera, operativo,
                                      soporte_tecnico, ventas
valores de rol.area         6        Administración, Atención al Cliente,
                                      Facturación, Operaciones, Soporte
                                      Técnico, Ventas
centro de mando            26 arch · ~3.900 lineas · SVG isometrico
frontend completo         938 arch · 115 pantallas
wisphub / smartolt / bottlecrm   151 / 67 / 36 archivos
odoo                        0 archivos   -- NO existe en este repositorio
sondeo del centro de mando 12 s      sin SSE ni WebSocket en el motor
motor                      gunicorn --workers 1
```

**La cifra de «41 roles» que circuló era falsa.** Salió de un `grep` que contaba
claves de todo el YAML en vez de la sección `roles:`. Son 9. Eso reduce el
tamaño del problema de personajes, y es la razón por la que el MVP cabe.

---

## Los tres defectos que hay que arreglar ANTES de migrar

Ninguno es nuevo trabajo inventado: los tres están vivos hoy y los tres
muerden exactamente donde este objetivo quiere construir.

### D-A · Una carga de config BORRA los departamentos

`TenantConfig.SINCRONIZADOS` (`nucleo/config/schema.py:3178`) contiene cinco
claves:

```
localidades · localidades_actualizado_en · parrilla_canales ·
precios_de_planes · precios_actualizado_en
```

**`areas` no está.** Y hay una segunda mitad, peor, que se midió el 29/10:

```
areas en TenantConfig.SINCRONIZADOS      NO  -> la carga no la restaura
areas en editor.SECCIONES_EDITABLES      NO  -> la guarda no la revisa
```

`cargar_config.py:374` restaura desde la base todo lo `SINCRONIZADO` antes de
escribir; `areas` no entra, así que el archivo la pisa. Y
`cargar_config.py:286` recorre `SECCIONES_QUE_EDITA_LA_INTERFAZ` para avisar
*«esto está en la base y no en el archivo: se BORRARÍA»*; `areas` tampoco entra,
**así que se pierde en silencio**. Existe una guarda diseñada justo para esto y
las áreas quedan fuera de su alcance. Por eso el 19/10/2026 nadie se enteró
hasta después, y hubo que bajarlas al YAML a mano desde un volcado de
`cli/diferencias_config.py --todo` contra la base v176.

**La decisión de diseño que esto abre** —y que es de la fase 0, no se improvisa:

| Opción | Qué implica |
|---|---|
| `areas` → `SINCRONIZADOS` | vive solo en la base, deja de versionarse en el YAML. Revierte lo que se hizo el 19/10 |
| `areas` → `SECCIONES_EDITABLES` **y** preservación propia | se versiona **y** se preserva. Es una tercera categoría que hoy no existe: *«lo escribe una persona desde la interfaz Y desde el archivo»* |

La segunda es la que el SaaS necesita —un cliente configura sus departamentos y
también quiere verlos en el repositorio— pero **cuesta una categoría nueva en
el cargador**, no una línea en una tupla.

Si la estructura organizacional del SaaS se construye encima de un mecanismo
que borra lo que el cliente configuró, el SaaS no existe. **Esto se arregla
primero, con prueba de conservación, o no se migra nada.**

### D-B · Dos vocabularios de departamento que no se cruzan

| | Valores | Dónde vive | Quién lo consume |
|---|---|---|---|
| `config.areas` | `administracion, cartera, operativo, soporte_tecnico, ventas` | base + YAML, editable en `/settings/areas`, con `agentes[]`, `icono`, `color` | tickets, equipo, conectores |
| `rol.area` | `Administración, Atención al Cliente, Facturación, Operaciones, Soporte Técnico, Ventas` | texto libre dentro de cada rol | **la planta del Centro de Mando** |

No son el mismo conjunto: `cartera` ≠ `Facturación`, `Atención al Cliente` no
existe en el primero, `operativo` ≠ `Operaciones`. **Hoy la oficina virtual
agrupa por un vocabulario distinto al que el CRM usa para organizar la empresa.**

> **No se asume que `cartera` y `Facturación` son lo mismo.** Es una decisión de
> negocio de Rapilink, no una equivalencia técnica, y se pregunta antes de
> fusionar nada. La migración conserva ambos lados hasta que alguien decida.

### D-C · El refresco del Centro de Mando no respeta la sesión

Medido: `PRIVATE_ASISTENTE_TENANT` queda en 5 archivos, y **dos son lectores
reales**, no el ayudante ni sus pruebas:

```
src/routes/api/centro-mando/+server.js     <- el refresco de ESTA pantalla
src/routes/api/agentes/+server.js
```

La primera pintada (`+page.server.js`) **sí** usa `tenantDeLaSesion`. El proxy
que la refresca cada 12 s **no**: toma el tenant de una variable de entorno del
despliegue. Con dos ISPs en la misma instalación, los refrescos servirían los
datos del tenant de la variable a cualquier sesión.

Su comentario explica la intención —que el navegador no pueda elegir la
empresa— y esa intención es correcta; lo que está mal es de dónde sale el dato.
Es el criterio **A1** de [plataforma-multi-isp.md](plataforma-multi-isp.md),
que sigue abierto (su ficha dice «hoy son 70»; hoy son 5, de los cuales 2
cuentan).

---

## Decisión de producto congelada

**SIMULACIÓN HÍBRIDA CON PROCEDENCIA EXPLÍCITA.** Aprobada el 29/10/2026.

| | Qué es | Respaldo | Cómo se ve |
|---|---|---|---|
| **Ambiental** | caminar, sentarse, descansar, moverse | ninguno | sin indicador; no aparece en el historial |
| **Operativa** | consultar, ejecutar herramienta, derivar, finalizar, pedir aprobación | **un evento real, con su uuid** | nombre de la actividad y estado visibles |

La regla que lo hace verificable: **cada instrucción de animación lleva un campo
de procedencia** — `evento:<uuid>` o `ambiente`. El historial solo puede mostrar
las que traen uuid. Así es imposible que un movimiento decorativo acabe contado
como trabajo.

*Un agente caminando no significa que esté trabajando.* Esa frase es el criterio
de aceptación, no una aspiración.

---

## Arquitectura

```
  MOTOR (Python)          agentes, herramientas, frontera -- sin cambio de alcance
        │                 + registro de eventos consultable (nuevo)
        ▼
  ORGANIZACION (Django)   empresas · unidades · departamentos · roles ·
        │                 agentes · asignaciones · oficinas · puestos
        ▼
  PROYECCION (API)        traduce estado+eventos a instrucciones de escena,
        │                 con procedencia. Aqui se valida el permiso.
        ▼
  ESCENA (PixiJS + TS)    render, camara, pathfinding, animacion
```

**La escena no conoce el negocio.** Habla por una interfaz de cuatro funciones
—`montar(contenedor, estado)`, `aplicar(eventos)`, `seleccionar(id)`,
`destruir()`— y recibe instrucciones ya resueltas. No sabe qué es un ISP, ni una
herramienta, ni un ticket. Eso cumple el requisito de que el renderizador sea
independiente del motor empresarial: cambiar PixiJS por otra cosa, o rediseñar
el aspecto, no toca ningún proceso del ISP.

**El permiso se valida en la proyección, no en la escena.** El frontend nunca
recibe lo que no puede ver, así que ocultar algo en la interfaz nunca es la
defensa.

---

## Modelo organizacional

Reutiliza lo que Django ya tiene (`Org`, `Profile`, `Teams`, `BaseOrgModel` ya
resuelven empresa y persona humana). Lo nuevo, con las tres separaciones que el
objetivo exige:

```
Empresa (= Org, ya existe)
 └── UnidadOrganizacional     arbol: subdepartamentos y unidades transversales
      └── Departamento         nombre, color, icono, modulo de oficina
           ├── Puesto          coordenada dentro del modulo
           └── Asignacion      N:N con vigencia  <- un agente en varios deptos

RolEmpresarial    el cargo descrito: "Agente de Facturacion". NUNCA ejecuta.
AgenteIA          la instancia ejecutable: slug, orientado_a, capacidades.
PersonajeVirtual  la identidad visual: sprite, color, peinado. Estable.
Capacidad         herramienta permitida. Las 84 del catalogo YA son esto.
```

Las tres entidades de arriba son tres cosas distintas y hoy están fundidas en
una sola entrada de YAML. Un `RolEmpresarial` puede existir sin `AgenteIA`
(un cargo que ocupa una persona), y un `Departamento` puede existir sin ninguno
de los dos — **eso último ya funciona hoy**: `config.areas` tiene `agentes: []`
en `ventas` y `operativo`.

**Cuáles de los 9 roles son agentes ejecutables es una medición pendiente de la
fase 0**, no un supuesto. Tener entrada en `roles:` no prueba que el motor lo
invoque.

---

## Modelo de eventos

**El sustrato ya existe.** `asistente.tool_calls` tiene lo necesario:

```sql
id uuid primary key              -- identificador
creado_en timestamptz            -- marca temporal
organization_id uuid             -- aislamiento por empresa
herramienta, parametros jsonb    -- que se hizo (enmascarado)
rol_solicitante, exito, codigo_error, duracion_ms, es_escritura, confirmado_por
indice: (organization_id, creado_en desc)
```

Lo que falta:

1. **Cursor estable `(creado_en, id)`.** `creado_en` solo no basta: dos llamadas
   en el mismo milisegundo rompen la paginación. El índice debe incluir `id`.
   Esto resuelve duplicados y pérdidas a la vez.
2. **Endpoint incremental** `GET /eventos?desde=<cursor>&limite=N`, que devuelve
   eventos y el cursor siguiente, **acotado por `organization_id` de la sesión**.
   Reconexión: el cliente guarda su cursor. Si es más viejo que la retención, el
   servidor responde «salto» y el cliente recarga la foto entera — nunca
   inventa el hueco.
3. **El destino de la derivación.** Hoy vive en `tool_calls.parametros` y no
   sale en el payload. Es lo que convierte un pulso genérico en un personaje que
   camina de recepción a un departamento.

**NO se abre WebSocket ni SSE.** El `EventSource` de esta plataforma se revirtió
el 03/08/2026 por cuatro razones documentadas en `notifications.svelte.js`: era
el único código async del backend y **forzaba todo el despliegue a ASGI**; cada
petición en vuelo tomaba **su propia conexión de base sin techo**; entregaba
nada en silencio bajo un rol de base correcto; y su manejador de error era un
placeholder vacío. El motor sigue con `--workers 1`. Ninguna condición cambió.

**La frecuencia del sondeo NO está decidida.** El «2–3 s» de la propuesta
anterior era una estimación sin medir. Sale de la fase 1 con números: coste del
endpoint vacío, con N empresas abiertas a la vez, contra `--workers 1`.

---

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| **A1** | Una carga de config **no** borra departamentos creados desde la interfaz | Crear un área en `/settings/areas`, correr `cli/cargar_config.py`, volver a leerla. Debe seguir ahí. Hoy desaparece |
| **A2** | Los dos vocabularios quedan unificados **sin fusionar nada por decisión propia** | Un volcado antes y después muestra las mismas relaciones agente↔departamento. Las fusiones que haya están aprobadas por escrito |
| **A3** | Rol, agente ejecutable y personaje son tres entidades | Existe un `RolEmpresarial` sin `AgenteIA`, y un `Departamento` sin ninguno de los dos, y la oficina los dibuja |
| **A4** | Un agente puede estar en varios departamentos | Una `Asignacion` doble se dibuja en las dos oficinas |
| **A5** | El refresco respeta la sesión | `grep -rn "PRIVATE_ASISTENTE_TENANT" django-crm/frontend/src` no devuelve `routes/api/centro-mando/+server.js` |
| **A6** | Dos ISPs no se ven entre sí | Dos orgs, dos sesiones: cada una recibe sus eventos y **nunca** los de la otra. Medido, no inferido |
| **A7** | El cursor no pierde ni duplica | Reconectar con un cursor de hace 10 min: cero duplicados y cero pérdidas, **contados** |
| **A8** | La carga del sondeo está medida antes de fijarla | Número publicado: peticiones/s y conexiones de base con N empresas abiertas |
| **A9** | Toda animación operativa tiene procedencia | Ninguna instrucción con `tipo: operativa` carece de `evento:<uuid>`. Verificable leyendo el estado de la escena |
| **A10** | El Centro de Mando actual sigue vivo | `/centro-mando` responde y dibuja mientras `/centro-mando/v2` existe |
| **A11** | La escena no conoce el negocio | `grep` en `escena/` no encuentra `wisphub`, `ticket`, `herramienta` ni `isp` |
| **A12** | Añadir un departamento no toca el motor visual | Crear uno desde la interfaz lo dibuja, sin desplegar nada |

---

## Plan por fases

El orden cambia respecto de la propuesta inicial: **los eventos van antes que el
modelo organizacional**, porque son lo único que puede invalidar el resto. Si no
alcanzan para animar con honestidad, el proyecto es otro.

| Fase | Qué | Cierra con |
|---|---|---|
| **0** | Auditoría y decisiones. Arreglar D-A. Medir qué roles son ejecutables. Mapear los dos vocabularios **sin fusionar** | A1, y el mapeo aprobado |
| **1** | Eventos: cursor, endpoint incremental **con aislamiento por empresa**, destino de derivación. Medir la carga | A6, A7, A8 |
| **2** | Modelo organizacional canónico. Migración con respaldo | A2, A3, A4 |
| **3** | Prototipo PixiJS: escena aislada, cámara, **un** departamento (NOC), sin personajes | A11 |
| **4** | Personajes, movimiento, animaciones ambientales | — |
| **5** | Proyección: agentes reales ↔ personajes, con procedencia | A9 |
| **6** | Constructor de oficinas configurable | A12 |
| **7** | Procesos ISP | — |
| **8** | Endurecimiento: rendimiento, pruebas, SaaS | — |

**El aislamiento por empresa y la validación de permisos entran en la fase 1 y
se verifican en cada fase posterior.** No se dejan para la 8: A6 es criterio de
la fase 1, y cada módulo nuevo lo arrastra.

**MVP = fases 0–5**, con un solo departamento visual (NOC) y sus agentes reales.
El hito que demuestra el proyecto: *un agente ejecuta una tarea real y su
personaje en el NOC lo refleja, sin que el Centro de Mando actual se entere.*

**Posterior:** los otros siete departamentos, el constructor, Tiled, múltiples
pisos, procesos ISP completos, Odoo.

---

## Qué se reutiliza, qué se modifica, qué se reemplaza

**Se reutiliza tal cual** — es trabajo ya verificado, no se vuelve a hacer:

```
planta.js · planta-radial.js      geometria isometrica: matematica de
                                   proyeccion, independiente de SVG o Pixi
estados.js · actividad.js          estados de agente y reparto de eventos
telemetria.js · resumen.js
SistemasExternos.svelte            salud de WispHub/SmartOLT
AgentDetail.svelte                 la ficha lateral
EventTimeline.svelte               el historial
/centro-mando (endpoint)           como foto de respaldo del cursor
las 84 herramientas                ya SON el modelo de capacidades
```

**Se modifica:** `eventos.js` (cursor) · `api.py` (endpoint incremental, destino
de derivación) · `schema.py` (`SINCRONIZADOS`, entidades) ·
`routes/api/centro-mando/+server.js` (D-C).

**Se reemplaza, y solo dentro de `/v2`:** `PlantaRadial.svelte` ·
`PuestoAgente.svelte`.

**Nuevo:** `organizacion/` (Django) · `proyeccion/` (backend) · `escena/`
(TypeScript + Pixi) · `modulos-oficina/` (biblioteca).

---

## Riesgos

| Riesgo | Gravedad | Mitigación |
|---|---|---|
| El sondeo corto tumba `--workers 1` | **alta** | A8 lo mide antes de fijar la frecuencia. Si no da, el sondeo se queda largo y la oficina se refresca más lento — no se fuerza ASGI |
| La migración pierde departamentos | **alta** | D-A se arregla primero. Respaldo y prueba de conservación antes de tocar nada |
| Fusionar `cartera` con `Facturación` por comodidad | **alta** | Prohibido sin aprobación escrita. A2 lo verifica |
| El coste de arte se subestima | **alta** | 7 animaciones y los agentes del NOC en el MVP. Nada más |
| La simulación inventa actividad | **alta** | Procedencia obligatoria. A9 |
| No hay pruebas de interacción en este repo | media | Medido el 07/10/2026: jsdom **no arranca** acá — el worker de vitest muere a los 60 s con forks, threads y `--no-isolate`, y también con una sonda de tres líneas sin Svelte. Está escrito en `vitest.config.js`. Hay que resolverlo o aceptar validación manual, diciéndolo |
| Pixi dentro de Svelte con ciclo de vida mal cerrado | media | `destruir()` obligatorio en `onDestroy`; una fuga de canvas no se ve hasta que el navegador se arrastra |

---

## Restricciones

- **NO push** — es deploy a producción.
- **NO tocar `--workers 1`** en este objetivo. Es el otro techo de la plataforma
  y se levanta aparte ([plataforma-multi-isp.md](plataforma-multi-isp.md)).
- **NO abrir WebSocket ni SSE** sin resolver antes el techo de conexiones.
- **NO `pnpm check` en Windows con Docker arriba** — va por contenedor.
- **NO borrar el Centro de Mando actual** hasta que A10 y A9 estén en verde con
  datos reales. Ya se descartó un componente el mismo día de estrenar su
  reemplazo (07/10/2026); no se repite.
- **NO fusionar departamentos** sin decisión escrita del cliente.

## Qué NO hacer

- **No construir los ocho departamentos a la vez.** Uno (NOC), de punta a punta,
  antes de invertir en escenarios y animaciones.
- **No modelar Odoo.** No existe en el repositorio; es desarrollo posterior.
- **No mover la organización a Django «de paso».** Si `tenant_config` sigue
  siendo el hogar o se migra a tablas es una decisión de la fase 0, con su
  medición.
- **No usar métricas simuladas como si fueran reales**, ni en capturas ni en
  demostraciones.
