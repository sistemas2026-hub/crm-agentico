# Objetivo · La operación de un ISP se mira como una empresa virtual

> Abierto el 29/10/2026. Estado: **abierto** — **FASE 0 CERRADA** el
> 29/10/2026, con A1 verificado contra PostgreSQL. La fase 1 (eventos) espera
> autorización. Los riesgos pendientes NO se podan al cerrar: siguen abajo.
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

### ~~D-C · El refresco del Centro de Mando no respeta la sesión~~ — FALSO POSITIVO

**No existía. Lo afirmé y era mío el error**, corregido el 29/10/2026 al abrir
el archivo en vez de confiar en un `grep`.

`routes/api/centro-mando/+server.js:24` **ya usa `tenantDeLaSesion(locals,
fetch)`**. Lo que mi búsqueda encontró era el **comentario** de la cabecera y
el texto de un mensaje de error, no código ejecutable. Medido después:

```
lecturas reales de env.PRIVATE_ASISTENTE_TENANT en src/   0
las 8 apariciones son: 3 comentarios + 5 en pruebas
```

Y hay más de lo que supuse: **ya existe una guarda de arquitectura** que lo
impide —`tenant.test.js:112`, «ningún archivo de src/ lee
PRIVATE_ASISTENTE_TENANT»— escrita para afirmar sobre el **efecto** y no sobre
que `tenantDeLaSesion` exista. El criterio **A1** de
[plataforma-multi-isp.md](plataforma-multi-isp.md) está cumplido en el código;
lo que queda son dos comentarios desactualizados que dicen lo contrario de lo
que hace el archivo, y que son justo los que me hicieron creer en el defecto.

**La lección vale más que el falso positivo**: un `grep` encuentra texto, no
comportamiento. Es la otra cara de lo que CLAUDE.md §6 llama *«no detectado por
chequeo estático ≠ no hay diferencias»*.

Lo que **sí** faltaba, y se construyó: una prueba que afirme el aislamiento
**en el endpoint**, no solo en el ayudante. Aquella puede estar perfecta y este
proxy pasarle otra cosa al motor — la falla del salto entre capas que §6
describe y que ya se cobró dos veces el 29/09/2026.

---

### D-D · La guarda no veía que se quitara UN elemento de una lista

Apareció al construir la prueba de conservación, y es el caso más probable de
todos: **nadie vacía la lista entera — se edita el archivo y se pierde uno.**

Medido el 29/10/2026, antes de tocar nada:

```
                       quitar uno      vaciar entera
areas                   0 avisos         1 aviso
planes_venta            0 avisos         1 aviso
servicios_ofrecidos     0 avisos         1 aviso
```

La comparación hoja por hoja saltaba las rutas que el archivo no trae —y con
razón, porque un campo ausente lo completa el esquema con su default— pero eso
metía en la misma bolsa dos cosas distintas: *falta el campo* (ruido) y *falta
el elemento entero* (pérdida). Se distinguen por el prefijo.

Es la **tercera** vez que esta guarda se queda corta; las dos anteriores están
documentadas en su propia prueba (23/08 y 24/08/2026).

**Lo que había que cuidar, y se midió**: que el arreglo no reintrodujera falsos
positivos, que es como esta guarda se rompió la segunda vez.

```
reordenar listas    original 68 avisos  ->  con el arreglo 68   (sin ruido nuevo)
quitar un area      original  0 avisos  ->  con el arreglo  1   (el defecto)
```

Y un hallazgo **preexistente que queda abierto**: esos 68 avisos al reordenar
son falsos positivos de `planes_venta` y `guias_tv`, cuyas listas se indexan
por POSICIÓN porque sus elementos no traen clave `nombre`. No es de este
objetivo y no se tocó; queda anotado porque es exactamente el ruido que enseña
a usar `--forzar` sin leer.

---

## Inventario de agentes ejecutables — medido el 29/10/2026

**Son 9 roles, y NO son 9 empleados virtuales.** El motor los invoca por
caminos distintos, y eso decide cuáles merecen personaje propio.

| Rol | Orientado a | Cómo se invoca | ¿Autónomo? | Herramientas | Personaje |
|---|---|---|---|---|---|
| `cliente_final` | cliente_final | webhook WhatsApp vía `rol_de_entrada` | **sí** | **1** | **Recepción** |
| `facturacion_cliente` | cliente_final | derivación desde recepción | **sí** | 7 | propio |
| `soporte_tecnico_cliente` | cliente_final | derivación | **sí** | 21 | propio |
| `ventas` | cliente_final | derivación | **sí** | 15 | propio |
| `supervisor_noc` | colaborador | `/interno/supervisor/chat` (puerta propia) | **sí** | 11 | propio |
| `configuracion_guiada` | colaborador | `/api/configuracion-guiada`, **rol fijo** | **sí** | 2 | propio |
| `soporte` | colaborador | asignado a una **persona** | no | 28 | **capacidad** |
| `facturacion` | colaborador | asignado a una **persona** | no | 11 | **capacidad** |
| `administracion` | colaborador | asignado a una **persona** | no | 9 | **capacidad** |

### Las tres categorías, y cómo se distinguen en el código

**1 · Agentes autónomos del canal público (4).** Atienden solos a quien
escribe por WhatsApp. `cliente_final` es la puerta —y **un ROUTER sin
herramientas propias**: tiene **1 sola**, la de derivar—; los otros tres
reciben el caso derivado. El mapa está en la herramienta con `deriva_rol: true`:

```
roles_permitidos: [cliente_final, facturacion_cliente, soporte_tecnico_cliente, ventas]
areas_destino:    [facturacion_cliente, soporte_tecnico_cliente, ventas]
```

`cliente_final` **no** está entre los destinos, y el comentario explica por qué:
*«sería un callejón sin salida — el cliente quedaría con un agente que no puede
resolverle nada»*. Un especialista que se equivocó de área pasa **directo** al
otro, no vuelve a pasar por recepción. **Eso es una ruta de personaje, y está
medida: cuatro personajes y las derivaciones entre ellos.**

**2 · Agentes con puerta propia (2).** `supervisor_noc` y
`configuracion_guiada` se invocan desde una pantalla del CRM con rol fijo o
resuelto por Django. Son ejecutables y tienen personaje, pero **no reciben
clientes**: su trabajo lo dispara un colaborador.

**3 · Capacidades de una persona (3).** `soporte`, `facturacion` y
`administracion` **no son empleados virtuales**. `/api/asistente` dejó de mandar
rol fijo: manda **quién pregunta**, y el motor resuelve
`agentes_de_colaborador(tenant, profile_id)` —`{profile_id: [agente, ...]}`—
**fusionándolos si son varios**. Son una capacidad que se le asigna a una
persona real del CRM, no alguien sentado en un escritorio.

> **Consecuencia para la oficina**: dibujar nueve personajes sería inventar
> tres empleados que no existen como procesos. Los tres de la categoría 3
> deberían aparecer **sobre la persona que los tiene asignados** —un distintivo
> en su puesto, no un escritorio propio—. Es la decisión que queda para ti.

Y un matiz que afecta al diseño: la **bandeja** (`conversaciones/[id]`) invoca
`rol_efectivo || 'cliente_final'`, así que una persona puede responder *con* el
rol de un agente. El personaje y quien lo opera no siempre son lo mismo.

---

## Mapeo organizacional — propuesto el 29/10/2026, sin ejecutar

Según la decisión aprobada: **«Finanzas y cartera» como departamento principal,
Facturación y Cartera como funciones independientes dentro.**

| `config.areas` | `rol.area` | Propuesta | Confianza |
|---|---|---|---|
| `cartera` | — | **Finanzas y cartera** › Cartera | aprobado |
| — | `Facturación` | **Finanzas y cartera** › Facturación | aprobado |
| `soporte_tecnico` | `Soporte Técnico` | Soporte Técnico | directa |
| `administracion` | `Administración` | Administración | directa |
| `ventas` | `Ventas` | Comercial › Ventas | directa |
| `operativo` | `Operaciones` | **¿el mismo?** | **ambigua** |
| — | `Atención al Cliente` | **falta como área** | **ambigua** |

### Las dos ambigüedades, RESUELTAS el 29/10/2026

**1 · `operativo` NO se fusiona con el NOC.** Se crea una agrupación
**Dirección de Operaciones** con **dos departamentos independientes**:

```
Direccion de Operaciones          (agrupacion, no departamento)
  ├── NOC y Redes                 supervision de red, alarmas, diagnostico
  └── Operaciones de Campo        instalaciones, correctivos, cuadrillas
```

`supervisor_noc` se mapea a **NOC y Redes**, conservando sus permisos y
registros históricos. **`operativo` queda como identificador legado pendiente
de mapeo** — no se fusiona automáticamente con ninguno de los dos.

El motivo lo dio el usuario y es de diseño, no de comodidad: *«mañana una
empresa tendrá que separar el NOC de las cuadrillas y habría que rehacer su
estructura»*. Un ISP pequeño las tiene juntas; uno grande, no. Por eso la
agrupación existe desde el principio aunque hoy sobre.

**2 · `Atención al Cliente` se crea como departamento independiente.** Los tres
roles que hoy declaran esa área (`soporte`, `cliente_final`,
`soporte_tecnico_cliente`) se mapean a ella **documentando la asignación y sin
cambiar permisos ni rutas de ejecución**.

Debe poder derivar hacia NOC, Operaciones de Campo o Finanzas **según las
capacidades realmente implementadas** — hoy la derivación solo alcanza a
`facturacion_cliente`, `soporte_tecnico_cliente` y `ventas`, y eso no se
inventa en la pantalla.

---

## Personajes virtuales — decidido el 29/10/2026

| Rol ejecutable | Representación | Presencia |
|---|---|---|
| `cliente_final` | recepcionista digital | permanente, **solo origen** |
| `facturacion_cliente` | agente de facturación | permanente |
| `soporte_tecnico_cliente` | agente de soporte | permanente |
| `ventas` | agente comercial | permanente |
| `supervisor_noc` | supervisor virtual del NOC | permanente |
| `configuracion_guiada` | asistente administrativo | **aparece al ser invocado** |
| `soporte` · `facturacion` · `administracion` | — | **capacidades de una persona**, sin personaje |

**`cliente_final` nunca se dibuja como destino de derivación.** No es una
preferencia estética: el motor no permite esa operación —no está en
`areas_destino`— y pintarla sería mostrar una ruta que no existe.

**Los personajes distinguen existir de estar trabajando.** Un agente
configurado y en reposo se ve distinto de uno ejecutando una tarea, y la
diferencia la marca la procedencia del evento, no la animación.

### El número de personajes NO es seis

Seis es lo que tiene Rapilink hoy, **no un límite del sistema**. Otra empresa
tendrá un solo agente para varias funciones, o cuatro especializados en
soporte, redes, cartera y ventas.

> **La escena se dimensiona por los agentes EJECUTABLES que el motor reporta,
> nunca por los roles declarados en un archivo.** Son dos números distintos y
> hoy difieren: 9 roles, 6 ejecutables, 5 con escritorio permanente.

Esto es lo mismo que ya gobierna la planta actual —la geometría se deriva del
número de agentes y del lienzo, sin una sola constante de posición— y se
conserva al cambiar de motor gráfico.

**No se fusionan datos, permisos ni registros históricos.** El mapeo es una
tabla de equivalencias a aplicar en la fase 2, no una migración.

---

## Defecto independiente · 68 falsos positivos al reordenar listas

**Registrado el 29/10/2026. No corregido a propósito: no es de este objetivo.**

`planes_venta` y `guias_tv` se indexan por POSICIÓN en `_hojas`, porque sus
elementos no traen clave `nombre` (usan `nombre_wisphub` y `marca`). Reordenar
el YAML produce **68 avisos** que no son pérdidas:

```
planes_venta[0].nombre_wisphub: la base dice 'PLAN ELITE' y el archivo
'PLAN FIBRA OPTICA 150MB_SB' -- se PISARIA
```

**Impacto, y por qué importa para el SaaS:** la guarda bloquea con `SystemExit`
y ofrece `--forzar` como salida. Un operador que ve 68 avisos falsos aprende a
correr `--forzar` sin leer — y entonces la guarda deja de proteger, incluida la
de departamentos que se acaba de arreglar. Es el mismo mecanismo que ya rompió
esta guarda el 24/08/2026 (15 falsos de 31).

**No bloquea el trabajo visual.** Sí debería resolverse **antes** de convertir
la importación de YAML en una función para clientes del SaaS: ahí el que
corre `--forzar` no sería quien escribió el archivo.

**Arreglo probable**: que `_hojas` acepte más claves identificadoras que
`nombre`. Toca la comparación entera, así que pide su propia medición.

---

## Decisiones de producto congeladas

### Facturación y Cartera — aprobado el 29/10/2026

**Son funciones distintas que pueden compartir departamento.** Inicialmente
ambas bajo «Finanzas y cartera». La arquitectura debe permitir que cada ISP las
mantenga juntas o las separe en departamentos independientes.

**No se fusionan datos históricos, roles ni permisos automáticamente.** El
mapeo se documenta antes de cualquier migración. Esto es lo que convierte
`UnidadOrganizacional` en un árbol y no en una lista plana: el departamento
principal agrupa, las funciones viven dentro.

### La base manda; el YAML es plantilla — aprobado el 29/10/2026

| | Papel |
|---|---|
| **Base de datos** | fuente de verdad **operativa** de cada empresa |
| **YAML** | plantillas, importación y configuración versionada |

Una importación **no puede** eliminar ni sobrescribir departamentos creados
desde la interfaz sin mostrar las diferencias, advertir y obtener autorización
explícita.

**Ese mecanismo ya existía y no había que diseñarlo desde cero**:
`cargar_config.py:457` calcula lo que se perdería, **corta con `SystemExit`**
—no solo avisa—, lista las diferencias una por una, explica cómo exportar
primero, y deja `--forzar` como la autorización explícita. Las tres condiciones
estaban cubiertas. Lo que faltaba era que `areas` entrara en su alcance (D-A) y
que detectara elementos quitados (D-D).

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

## Verificaciones previas a la fase 1 — 29/10/2026

### V1 ✅ El destino de la derivación SOBREVIVE al enmascarado

El enmascarado de `tool_calls.parametros` tiene una excepción declarada el
20/10/2026: **lo que sale de un enum no se enmascara**, y el ejemplo que da su
propio comentario es *«nombres de area»*. Medido ejecutando el esquema real:

```
herramienta  derivar_a_area
  area        INTACTO       'facturacion_cliente'   <- enum
  confianza   INTACTO       'alta'                  <- enum
  servicio    INTACTO       'internet'              <- enum
  motivo      enmascarado   '...ubre'
  cedula      enmascarado   '...6789'
```

**El parámetro se llama `area`, no `area_destino`** — ese nombre lo inventé yo
al leer `areas_destino`, que es la lista del catálogo y no el argumento.

Se expone **solo las claves que `_valores_cerrados()` declara exentas**, nunca
el `jsonb` entero: así el destino viaja y el motivo y la cédula no. Y es
fail-closed: si el esquema no se puede leer, no se exime a nadie.

**Cuando no hay destino** —una derivación sin `area`, o una herramienta sin
enum— no se inventa ninguno: el evento se proyecta como actividad genérica.

### V2 ❌ El cursor `(creado_en, id)` PIERDE EVENTOS — demostrado

No es una hipótesis. Reproducido contra PostgreSQL 16:

```
A) cursor (creado_en, id)                  insertados 2  entregados 1  PERDIDA
B) cursor (tx, id) + frontera de snapshot  insertados 2  entregados 2  SIN PERDIDAS
```

**La causa**: `creado_en default now()` es el instante de **inicio de la
transacción**, no el del commit. Una transacción que empieza a las 10:00:00 y
commitea a las 10:00:05 inserta una fila con sello 10:00:00. Si el cliente ya
avanzó su cursor a 10:00:03, esa fila queda **detrás** y no se entrega
**nunca**. El `id` desempata sellos iguales; no corrige sellos anteriores.

**La solución, verificada**: ordenar por identificador de transacción y no
entregar nada que todavía pueda tener transacciones por delante.

```sql
-- columna nueva:  tx xid8 not null default pg_current_xact_id()
where tx < pg_snapshot_xmin(pg_current_snapshot())   -- ya no hay nada en vuelo
  and (tx, id) > (:cursor_tx, :cursor_id)
order by tx, id
```

`xid8` es de 64 bits y **no da la vuelta**, a diferencia de `xid`. La condición
del snapshot es la garantía: cuando se entrega hasta `tx = X`, ninguna
transacción con `tx <= X` puede commitear después.

**Consecuencia de alcance**: esto ya no es «un índice sobre `tool_calls`». Pide
una **columna nueva**, y las filas anteriores no la tendrán. Es trabajo de fase
1, no un ajuste.

### V3 ⚠️ Un evento NO es un estado — hay que separar cuatro cosas

Una llamada registrada hace diez segundos **no prueba** que el agente siga
trabajando. `tool_calls` se escribe cuando la llamada **termina**, con su
duración: no existe la fila «en vuelo». Ya está documentado en `api.py`, que
por eso **no emite el estado `waiting_tool`**: *«una herramienta lenta y una
recién terminada se ven igual»*.

| Capa | Qué es | De dónde sale |
|---|---|---|
| **Evento** | algo que ocurrió | `tool_calls`, inmutable |
| **Ejecución activa** | trabajo en curso | **hoy NO existe** |
| **Estado proyectado** | qué se cree que hace | derivado, con caducidad |
| **Ambiental** | relleno visual | nada |

**Regla**: un evento produce una animación **breve y acotada por su
`duracion_ms`**, no un estado permanente. Pasado ese tiempo el personaje vuelve
a reposo. **No se afirma que sigue trabajando.** Y cuando el sistema no sabe, la
pantalla lo dice — igual que `offline` no se emite hoy porque *«confundir sin
datos con caído hace que la pantalla avise de una avería que no existe»*.

### V4 ✅ La derivación se representa como EXPEDIENTE, no como caminata

Decidido el 29/10/2026. Un paquete digital viaja al departamento destino; el
personaje no abandona su escritorio. La transferencia sigue siendo real y
verificable: la respalda el evento con su `area`.

Caminar se reserva para lo que de verdad implica moverse.

### V5 ⚠️ El parámetro `tenant` no es una autorización

Medido: el motor hace `request.args.get("tenant")` y con eso llama a
`_config_de(tenant)`, **sin comprobar que el llamante corresponda a esa
empresa**. Lo único que lo protege es `X-Servicio-Token`, que es **de la
instalación, no de la empresa**.

El modelo de confianza real es: *el frontend resuelve la empresa desde la sesión
(probado) y el motor confía en el token de servicio*. Funciona mientras el
frontend sea el único llamante.

**Para el endpoint nuevo**: el `tenant` **no viaja desde el navegador**; lo pone
el proxy del servidor desde `tenantDeLaSesion`, igual que hoy. **Queda como
riesgo anotado** que el token no distingue empresas — cerrarlo exige que el
motor conozca sesiones del CRM, que es otro objetivo.

### V6 🚫 BLOQUEANTE · `CREATE INDEX CONCURRENTLY` no es viable hoy

```
el ledger envuelve cada migracion en   with con.transaction()  (migrar_asistente.py:589)
CONCURRENTLY dentro de una transaccion  ->  PostgreSQL lo RECHAZA
veces que se uso CONCURRENTLY en el repo ->  0
politica de retencion de tool_calls      ->  NO EXISTE (el PRD lo registra)
tamaño de tool_calls en produccion       ->  NO MEDIDO (no se toca produccion)
```

Un índice normal **bloquea escrituras** mientras se construye, y la tabla crece
sin purga desde agosto de 2026. **No se puede estimar el impacto sin conocer su
tamaño, y no se mide desde acá.**

Salidas, en orden de preferencia: (a) que alguien con acceso mida
`pg_total_relation_size('asistente.tool_calls')` y el conteo de filas; (b)
permitir al ledger migraciones fuera de transacción, declarándolo — es cambio
de infraestructura; (c) crear el índice a mano, que **§8 prohíbe**.

### V7 ⚠️ `api.py` y `db.py` están muy transitados

```
commits sobre ellos en 7 dias                        8
ramas con cambios NO integrados sobre ellos:
   origin/campo/al-dia              5 commit(s)
   origin/feat/campo-diseno-stitch  2 commit(s)
```

Son los dos monolitos de §2 (9.091 y 4.625 líneas). **No se integra ni se pisa
trabajo ajeno**: antes de tocarlos hay que volver a medir y, si esas ramas
siguen vivas, coordinar.

---

## E1 · Registro de eventos — validación exhaustiva, 29/10/2026

Todo lo de abajo está **ejecutado contra PostgreSQL 17.11**, que es la versión
que corre producción (Supabase nuevo; el `docker-compose` local usa pg16 y por
eso no servía para decidir).

### El banco de garantía: ocho escenarios

```
                                           A (creado_en,id)   B (tx,id)+snapshot
1  commit tardio                           PIERDE 1 de 2      2 de 2
2  rollback de una transaccion                   --           2 de 2, sin la abortada
3  cinco eventos de UNA transaccion              --           5 de 5, sin repetir
4  paginacion: 25 eventos en paginas de 4        --           25 de 25, 25 distintos
5  reconexion con el cursor guardado             --           7 de 7, sin repetir
6  retroceso del reloj                      2 de 2            2 de 2
7  filas historicas sin tx                       --           NO se entregan
8  transaccion abierta en vuelo                  --           retiene a las posteriores
```

**El cursor B es el que se adopta.** Resuelve el único caso donde A pierde, y no
rompe ninguno de los demás.

### Dos hallazgos del banco que cambian el diseño

**[7] Las filas históricas no se entregan, y está bien.** Una fila con `tx NULL`
queda fuera del cursor. **El backfill de lo ya existente es trabajo aparte** —el
cursor no lo resuelve y no debe fingir que sí—. Para la oficina virtual no
importa: lo que se anima es lo que pasa *ahora*, y la foto inicial sigue
viniendo de `/centro-mando`.

**[8] La garantía tiene un coste, y es de orden.** Con una transacción abierta,
el cursor **no avanza**: en el banco, 4 eventos insertados y 0 entregados hasta
que la transacción cerró. Después salieron los 4 de golpe.

Eso sería inaceptable sin techo. **Pero el techo existe y está medido en este
proyecto**: producción tiene `idle_in_transaction_session_timeout = 60s` en
`postgres`, `crm_user` y `motor_user` (CONTRATO_RELEVO_IA_HUMANO P-A, PRD §16),
más la restricción transversal de que **ninguna transacción queda abierta
esperando una operación externa**.

> **El retraso máximo del cursor es de 60 segundos, y no es una estimación:
> es el timeout configurado en producción.** Con un sondeo de pocos segundos,
> el caso normal es inmediato y el peor caso está acotado.

### V6 DESBLOQUEADO · la migración no necesita `CONCURRENTLY`

El bloqueante era que el ledger envuelve cada migración en una transacción y
PostgreSQL rechaza ahí `CREATE INDEX CONCURRENTLY`. **Se resuelve sin
necesitarlo**, en tres pasos que son todos de metadata:

```sql
alter table asistente.tool_calls add column tx xid8;          -- sin default
alter table asistente.tool_calls
  alter column tx set default pg_current_xact_id();           -- solo filas nuevas
create index tool_calls_cursor_idx
  on asistente.tool_calls (organization_id, tx, id)
  where tx is not null;                                       -- indice PARCIAL
```

**Por qué funciona, medido sobre 400.000 filas / 46 MB simuladas:**

```
indice parcial recien creado   8192 bytes   (nace VACIO: ninguna fila vieja tiene tx)
una fila nueva recibe tx       si
los tres pasos, cronometrados  0,050 s
```

- `ADD COLUMN` **sin default** no reescribe la tabla: es solo metadata. Con un
  default **volátil** como `pg_current_xact_id()` sí la reescribiría entera y
  tomaría un bloqueo largo — por eso va en dos pasos y no en uno.
- El índice es **parcial**: al crearse no hay ninguna fila con `tx`, así que
  nace vacío y crece desde cero.

A 0,05 s cabe de sobra dentro de la transacción del ledger. **No hay que tocar
el mecanismo de migraciones.**

### Lo que sigue sin medir: el tamaño real

No tengo acceso a producción y **no voy a leer `.env`**, que es donde están las
credenciales. Las consultas, para ejecutar a mano:

```sql
select version();
select pg_size_pretty(pg_total_relation_size('asistente.tool_calls')) as total,
       pg_size_pretty(pg_table_size('asistente.tool_calls'))          as tabla,
       pg_size_pretty(pg_indexes_size('asistente.tool_calls'))        as indices;
select reltuples::bigint as filas_estimadas
  from pg_class where oid = 'asistente.tool_calls'::regclass;
select min(creado_en), max(creado_en) from asistente.tool_calls;
```

Son todas de lectura y ninguna toma bloqueos. **El número ya no bloquea E1** —la
migración es instantánea sea cual sea el tamaño— pero sí hace falta para decidir
la política de retención, que el PRD registra como pendiente.

### Ramas concurrentes sobre los monolitos

```
origin/campo/al-dia              5 semanas sin actividad   api.py +31/-6   db.py +8/-1
origin/feat/campo-diseno-stitch  5 semanas sin actividad   api.py +120/-0  db.py +139/-0
```

Las dos están **paradas hace cinco semanas** y sus cambios son **aditivos** —la
segunda no borra una sola línea—. El riesgo de conflicto es bajo, pero existe.
**No se integran ni se tocan**: si reviven, se coordina antes.

---

## E2 · Contrato de instrucciones visuales — 29/10/2026

La capa que convierte eventos del motor en algo que una escena puede dibujar.
**No sabe qué es PixiJS**, ni un sprite, ni un píxel: por eso se puede cambiar
el motor gráfico sin tocarla.

### El contrato

```js
{
  id:           "<uuid del evento>",      // identidad, rastreable
  procedencia:  "evento:<uuid>",          // o 'ambiente'
  agente:       "soporte_tecnico_cliente",
  tipo:         "consulta" | "accion" | "falla" | "expediente" | "escalada",
  en:           "2026-10-29T17:00:00Z",   // cuando PASO
  duracion_ms:  900,                      // cuanto se muestra
  caduca_en:    1730221200900,            // y cuando deja de mostrarse
  etiqueta:     "consultar_olt",          // del catalogo, nunca del cliente
  destino:      "facturacion_cliente"     // solo en 'expediente'
}
```

Y el reposo, que **no es una instrucción operativa**:

```js
{ agente: "ventas", tipo: "reposo", etiqueta: null, procedencia: "ambiente" }
```

### Las reglas que lo gobiernan

**Una llamada terminada no prueba que el agente siga trabajando.**
`tool_calls` se escribe cuando la llamada **termina**: no existe la fila «en
vuelo», y por eso el motor ya se niega a emitir `waiting_tool`. Un evento
produce una animación **breve y acotada** que cuenta *algo que pasó*, nunca un
estado que afirme *algo que sigue pasando*.

**Todo caduca.** `caduca_en` es obligatorio y el techo son 2.500 ms. Una
herramienta que tardó 40 s **no** deja al personaje 40 s moviéndose: la
animación cuenta QUE pasó, no cuánto duró.

**Lo desconocido no se dibuja.** Un tipo que esta versión no conoce, un agente
que no es instancia ejecutable, un área que la empresa no configuró: nada de
eso produce instrucción. Se cuentan en `descartados` para que la pantalla
pueda decirlo. *Pintar algo genérico ante lo desconocido es cómo una pantalla
empieza a afirmar cosas que nadie midió.*

**Los duplicados se descartan, no se animan dos veces.** El flujo puede
entregar el mismo evento repetido —es el precio de no perder ninguno en la
transición foto→cursor— y animarlo dos veces contaría una actividad que
ocurrió una.

**La derivación es un expediente, no una caminata.** El personaje no abandona
su escritorio; lo que viaja es el paquete, con el `area` real del evento.

**Los departamentos y los agentes entran por parámetro**, nunca fijos en el
código: otra empresa tendrá otras áreas y otros agentes. Probado con una
empresa inventada cuyo departamento es `cobranzas`.

### Resultados — 22 pruebas

```
A9 · procedencia verificable         toda instruccion lleva evento:<uuid>
     sin id -> no se proyecta        y el reposo lleva 'ambiente'
duplicados y fuera de orden          el mismo evento 2 veces -> 1 instruccion
identidad del agente                 'soporte' (capacidad) NO se dibuja
derivacion                           area valida -> expediente; invalida -> nada
pasado vs activo                     todo caduca; 40 s -> 2,5 s como maximo
tipos desconocidos                   no se dibujan, y se cuentan
datos sensibles                      ni 'motivo' ni 'cedula' en ninguna etiqueta
independencia del motor grafico      sin sprite/pixi/canvas/x/y en la salida
```

**Y las cuatro garantías críticas mueren al mutarlas:**

```
quitar la caducidad            -> 1 falla
quitar la lista de agentes     -> 3 fallas
aceptar areas invalidas        -> 1 falla
no descartar duplicados        -> 1 falla
```

### Lo que E2 NO resuelve, y hay que decirlo

- **No hay ejecuciones activas.** El backend no las registra: `tool_calls` solo
  tiene llamadas terminadas. Mientras eso no cambie, la oficina puede mostrar
  lo que *pasó*, no lo que *está pasando*.
- **La ubicación no está en el contrato.** `agente` y `destino` son nombres,
  no coordenadas: dónde se dibuja cada uno lo decide la escena, con la
  configuración de departamentos.
- **El reposo no distingue «sin trabajo» de «sin datos».** Hoy son lo mismo
  visualmente; separarlos exige que el motor diga cuándo no sabe.

---

## Fases 3A y 3B — diseño, 29/10/2026 · sin implementar

### El hallazgo que ordena las dos fases

**3B puede romper E1 si se hace mal, y por un camino que no es obvio.**

Para registrar «ejecución en curso» hay que escribir ANTES de llamar a la
herramienta. Si esa escritura deja una transacción abierta mientras se espera
a WispHub o SmartOLT, pasan dos cosas: se viola la decisión congelada
*«ninguna transacción de base abierta mientras se espera una operación
externa»* (§12), y **el cursor de eventos se queda clavado** — es el escenario
[8] del banco, donde una transacción en vuelo retiene a todas las posteriores.

Una llamada HTTP lenta a un ISP congelaría el flujo de la oficina entera.

El patrón obligatorio, que ya existe en el repositorio (CONTRATO_RELEVO P-A):

```
transaccion corta -> marcar INICIO -> COMMIT
                     ejecutar la herramienta (fuera de toda transaccion)
transaccion corta -> marcar FIN     -> COMMIT
```

### A9 NO valida identificadores — confirmado

Medido el 29/10/2026. El proyector solo comprueba que `ev.id` sea *truthy*:

```
"ambiente"   -> procedencia "evento:ambiente"
"e1"         -> procedencia "evento:e1"
"../../etc"  -> procedencia "evento:../../etc"
```

En producción el dato real **sí** es un UUID (`tool_calls.id uuid primary
key`), así que hoy no hay falsos. **Pero la garantía no lo impide**, y eso deja
de ser teórico en cuanto 3A introduzca eventos simulados: una instrucción
marcada `evento:simulado-1` entraría al historial como operativa.

Peor: `"ambiente"` —la palabra reservada para lo NO operativo— pasa como si
fuera un evento.

**Arreglo (fase 3A, primera tarea):** validar formato UUID en `proyectar()`, y
que los eventos simulados lleven `procedencia: 'simulado'` como tercera
categoría, nunca un uuid inventado.

### 3A · Prototipo visual del NOC

Ruta **nueva e independiente**: `/centro-mando/laboratorio`. `/centro-mando` no
se toca.

```
  +page.svelte            monta la escena y el panel
  escena/montar.ts        la unica puerta: montar/aplicar/seleccionar/destruir
  escena/oficina.ts       suelo, paredes, mobiliario, monitores
  escena/personaje.ts     sprite, estados, animacion
  escena/camara.ts        zoom y desplazamiento
  escena/adaptador.ts     instrucciones E2 -> animaciones  <- LA FRONTERA
```

**`adaptador.ts` es la pieza que importa.** Traduce el contrato E2 a lo que la
escena entiende. Todo lo que sabe de negocio vive ahí; `oficina.ts` y
`personaje.ts` no conocen la palabra «herramienta» ni «ISP». Cambiar PixiJS por
otra cosa es reescribir `escena/`, no `adaptador.ts`.

**Tres indicadores distintos, que hoy son dos:**

| Estado | Qué significa | De dónde sale |
|---|---|---|
| **actividad** | hay un evento vigente | instrucción E2 |
| **reposo** | no hay eventos, y el flujo está al día | `retraso_s` bajo |
| **sin información** | el flujo está retrasado o caído | `retraso_s` alto o error |

El tercero **no existe todavía** y es la petición directa: *un agente no debería
aparecer como disponible cuando en realidad perdió conexión*. El dato ya viaja
—`retraso_s` del endpoint de E1— pero nadie lo lee.

### 3B · Ciclo de vida de las ejecuciones

**Una llamada de herramienta no es una ejecución.** Un turno del agente puede
llamar a varias herramientas; la ejecución es el turno, no cada llamada. Hoy
`tool_calls` registra llamadas terminadas y nada más.

Tabla nueva, no columnas en `tool_calls` —esa es de auditoría y no debe mutar:

```
asistente.ejecuciones
  id uuid, organization_id uuid, agente text,
  estado text         iniciada | terminada | fallida | cancelada | desconocida
  iniciada_en, actualizada_en, terminada_en timestamptz
  tx xid8 default pg_current_xact_id()      <- mismo cursor que E1
  herramienta_actual text, latido timestamptz
```

**`desconocida` es un estado de primera clase.** Un proceso que muere a mitad
deja la fila en `iniciada` para siempre; un barrido la pasa a `desconocida`
pasado un umbral. La pantalla entonces dice «no sé», que es la verdad — el
mismo criterio por el que el motor hoy **no** emite `offline`.

### Dependencias

```
3A  necesita  el contrato E2 (ya existe) + el arreglo de A9
3B  necesita  el patron de transaccion corta, o rompe E1
3A + 3B       la integracion final: el personaje muestra "trabajando AHORA"
```

**3A no depende de 3B.** Puede construirse con eventos terminados y simulados,
y gana el estado «sin información» desde el primer día con `retraso_s`.

### Recursos gráficos

```
suelo y paredes isometricos          tiles, 2-3 variantes
mobiliario NOC                       escritorio, silla, rack, pantalla mural
personaje: 7 animaciones             reposo, caminar, sentarse, teclear,
                                     alerta, esperando, levantarse
expediente                           el paquete que viaja entre departamentos
```

**El arte es el coste real, no la librería.** PixiJS son ~500 KB; producir y
mantener estas animaciones no lo abarata ningún framework. Para el prototipo
basta **un** personaje (el supervisor) y **una** oficina.

### Riesgos

| Riesgo | Gravedad | Mitigación |
|---|---|---|
| 3B deja transacciones abiertas y congela el cursor | **alta** | transacción corta obligatoria; prueba que lo verifique |
| Una escritura más por llamada, con `--workers 1` | **alta** | medir antes; si no da, solo turnos y no cada herramienta |
| No hay pruebas de interacción (jsdom no arranca) | **media** | la escena se valida con navegador, diciéndolo |
| Fuga de memoria del canvas | media | `destruir()` obligatorio en `onDestroy` |
| Eventos simulados contados como reales | **alta** | procedencia `simulado`, separada de `evento:` |

### Orden recomendado

```
1  arreglar A9 (validar uuid + procedencia 'simulado')     pequeño, desbloquea 3A
2  el indicador "sin informacion" leyendo retraso_s        sin PixiJS todavia
3  3A: escena, camara, un personaje, adaptador
4  3B: diseño de ejecuciones + medicion de la escritura extra
5  integracion
```

Los pasos 1 y 2 **no necesitan PixiJS** y hacen que el prototipo nazca sin dos
defectos conocidos.

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
| **A1** | Una carga de config **no** borra departamentos creados desde la interfaz | ✅ **CERRADO 29/10/2026 contra PostgreSQL real**: `tests/test_conservacion_departamentos_con_base.py`. `cargar()` corta, nombra `areas`, dice BORRARIA, la base queda intacta y la versión no sube. Verificada por mutación: quitar el arreglo da **3 fallas**, entre ellas «los departamentos se habrían perdido». Más la unitaria del bloque [8] |
| **A2** | Los dos vocabularios quedan unificados **sin fusionar nada por decisión propia** | Un volcado antes y después muestra las mismas relaciones agente↔departamento. Las fusiones que haya están aprobadas por escrito |
| **A3** | Rol, agente ejecutable y personaje son tres entidades | Existe un `RolEmpresarial` sin `AgenteIA`, y un `Departamento` sin ninguno de los dos, y la oficina los dibuja. **Inventario medido el 29/10**: de 9 roles, 6 son ejecutables y 3 son capacidades de una persona |
| **A4** | Un agente puede estar en varios departamentos | Una `Asignacion` doble se dibuja en las dos oficinas |
| **A5** | El refresco respeta la sesión | ✅ **29/10/2026**: ya se cumplía (D-C era falso positivo) y lo guarda `tenant.test.js:112`, que afirma sobre el efecto |
| **A6** | Dos ISPs no se ven entre sí | ✅ **29/10/2026** *para el panorama*: `routes/api/centro-mando/server.test.js`, 7 pruebas. Verificada por mutación: devolver el endpoint a la variable de entorno **mata 5 de 7**. Queda pendiente para los EVENTOS de la fase 1 |
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
| **0** ✅ | ~~Auditoría y decisiones~~ **CERRADA 29/10/2026**: D-A y D-D corregidos, A1 verificado contra PostgreSQL, inventario de ejecutables medido, mapeo propuesto y las tres decisiones de negocio tomadas | A1 ✅ · A3 medido · A5 ✅ · A6 ✅ (panorama) |
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
