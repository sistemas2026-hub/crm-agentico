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

## Pasos 1 y 2 — hechos el 30/10/2026

### Paso 1 · A9 ya exige un identificador REAL

El proyector comprobaba que `ev.id` fuera *truthy*. Ahora exige **formato
UUID**, que es lo que de verdad tiene `tool_calls.id`.

```
rechazados ahora:  "ambiente" · "simulado" · "e1" · "inventado" · "../../etc"
                   "1" · "true" · "" · "   " · "no-es-un-uuid"
                   "00000000-0000-0000-0000"  (truncado)
                   "zzzzzzzz-0000-4000-8000-000000000000"  (no hexadecimal)
```

El peor de todos era `"ambiente"`: la palabra reservada para lo **no**
operativo entraba como `evento:ambiente`.

**Tres procedencias que no se mezclan:**

| | Qué es | ¿Al historial? |
|---|---|---|
| `evento:<uuid>` | actividad real, rastreable hasta su fila | **sí** |
| `simulado` | generada para probar o demostrar | **no** |
| `ambiente` | decorativo: caminar, estirarse | **no** |

**El lote se marca entero, no evento por evento.** Si dependiera de cada fila,
bastaría olvidarse de una para que un movimiento de prueba entrara como
trabajo real. Y un simulado **con uuid válido** sigue saliendo como `simulado`:
lo que decide no es la forma del id, es de qué lote viene.

### Paso 2 · «Sin información» como tercer estado

Hasta ahora un agente sin eventos se veía igual que uno cuyo backend murió:
los dos quietos. Eso convierte la quietud en una afirmación falsa — *«este
agente no tiene trabajo»* cuando lo cierto es *«no sé qué hace este agente»*.

**`retraso_s` no alcanza, y esa fue la corrección que lo ordenó todo.** Lo
calcula el backend y viaja **con** la respuesta: si el backend deja de
responder no llega un retraso alto, no llega **nada**. Un indicador que solo
mirara ese campo se quedaría mostrando el último valor bueno justo cuando más
importa que avise.

Cuatro señales, **tres de ellas del cliente**, que es quien puede notar un
silencio:

```
1  hace cuanto fue la ultima respuesta correcta    silencio   <- del cliente
2  si el ultimo intento fallo                      error      <- del cliente
3  si nunca hubo una respuesta                     arranque   <- del cliente
4  el retraso que el backend declara               retraso    <- del backend
```

**Umbrales, declarados en un solo sitio y configurables por empresa:**

| | Valor | Por qué |
|---|---|---|
| `silencio_s` | **40 s** | ~3 sondeos de 12 s. Uno perdido es ruido; tres son un silencio. Avisar al primero haría que el aviso saliera a diario y se aprendiera a ignorarlo |
| `retraso_s` | **30 s** | el peor caso **no** está acotado: `idle_in_transaction_session_timeout` solo corta sesiones OCIOSAS, no una que sigue ejecutando o esperando un lock |

**Dos reglas que gobiernan el indicador:**

- **«Sin información» prevalece sobre todo.** Una actividad vigente no tapa un
  backend caído. Mostrar actividad vieja como si fuera actual es peor que no
  mostrar nada: lo segundo se nota, lo primero no.
- **Reposo NO es «disponible».** Significa «no hay actividad vigente y los
  datos están al día». Si el agente puede atender algo es otra pregunta, y
  esta pantalla no la responde.

Un error viejo **no** condena para siempre: si después hubo una respuesta
buena, se recupera. Si no, la pantalla se quedaría en rojo tras un parpadeo.

### Verificado

```
40 pruebas del proyector   +18 sobre A9 y las procedencias
17 pruebas de frescura     arranque, silencio, error, retraso, recuperacion
159 verdes en total        cero regresiones en el Centro de Mando
```

**Las seis garantías críticas mueren al mutarlas:**

```
no validar el uuid                  -> 12 fallas
marcar lo simulado como real        ->  4 fallas
que sin_informacion deje de ganar   ->  3 fallas
no detectar el silencio             ->  5 fallas
tratar el arranque como reposo      ->  1 falla
ignorar el retraso del backend      ->  1 falla
```

### Lo que queda pendiente

**Nadie consume `frescura.js` todavía.** El módulo existe y está probado, pero
conectarlo a la pantalla es trabajo de 3A: ahí es donde el indicador se ve.
Hasta entonces el Centro de Mando sigue sin distinguir reposo de desconexión.

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

---

## Fase 3A — el NOC isométrico, hecho el 30/10/2026

Ruta nueva `/centro-mando/v2`. El centro de mando de producción **no se tocó**:
comparte `proyeccion.js` y `frescura.js` y nada más.

### Lo que se construyó

```
src/lib/centro-mando/escena/
  isometria.ts    la proyeccion y su inversa          PURO · 12 pruebas
  camara.ts       zoom, arrastre, clic vs arrastre    PURO · 19 pruebas
  pose.ts         las cinco poses y su mezcla         PURO · 14 pruebas
  adaptador.ts    LA FRONTERA: instruccion -> pose    PURO · 17 pruebas
  paleta.ts       colores derivados de «Fibra»        PURO
  texturas.ts     halo, sombra, haz, trama            PixiJS
  oficina.ts      suelo, muros, mural, mobiliario     PixiJS
  personaje.ts    la figura articulada                PixiJS
  montar.ts       la unica puerta                     PixiJS
src/lib/centro-mando/
  flujo.js        cursor + las cuatro señales         18 pruebas
  bitacora.js     dos historiales separados           11 pruebas
  demo.js         guion de demostracion               12 pruebas
  noc.js          los puestos y quien los ocupa       15 pruebas
src/lib/components/centro-mando/FichaDePuesto.svelte  19 pruebas
src/routes/(app)/centro-mando/v2/                     pantalla y su `load`
```

**Dependencia nueva: `pixi.js@8.22.0`** (publicada el 01/10/2026), en
`dependencies`. Instalada con pnpm 12.16.1 **dentro del contenedor**: el
`node_modules` de este árbol se creó ahí (`storeDir: /app/node_modules/
.pnpm-store`), y el pnpm del host quiere purgarlo antes de tocar nada.

### Las tres cosas que este prototipo fija, y valen más que la sala

1. **El corte entre datos y dibujo.** `adaptador.ts` es el único archivo que
   conoce los dos lados. Hay una guarda que lo mide
   (`escena/guardas.test.js`): ninguna fuente de `escena/` contiene
   `wisphub`, `ticket`, `isp`, `factura`… buscadas **con límites de palabra**,
   porque `isp` a secas marca «disponible» y una guarda que se pone roja por
   nada se apaga.
2. **Las transiciones no se programan.** Cinco estados dan veinte transiciones;
   escribirlas a mano garantiza que falten cuatro, y las que faltan no fallan:
   saltan. Cada estado declara una pose de números y la transición es
   interpolar. Hay una prueba que recorre **las veinte parejas** y afirma que
   ningún canal salta.
3. **Lo simulado vive en otro arreglo.** No es una bandera: `bitacora.js` tiene
   `real` y `simulado` separados y una sola puerta de escritura que mira la
   procedencia. Para que un dato de demostración entre al historial real hay que
   cambiar esa función, no olvidarse de un `if`.

### Lo medido en el navegador, y lo que NO se pudo medir

Banco en `node:22` + Vite, fuera del repositorio, con los mismos módulos.
Navegador real con GPU: `ANGLE (Intel UHD Graphics, Direct3D11)`.

| Qué | Resultado |
|---|---|
| La sala se dibuja | sí · WebGL · **244 objetos** |
| Coste de dibujar un fotograma (`gl.finish()`) | **0,22–0,42 ms** con antialias · 0,12–0,18 ms sin él |
| Los cuatro puestos se pueden seleccionar | sí, con regiones separadas y sin solapes |
| Arrastrar NO selecciona | sí |
| La rueda hace zoom | 1,09 → 2,05 |
| «Sin información» al caer el flujo | a los **40 s exactos**, el umbral configurado |
| La recuperación vuelve a «Actualizado» | sí |
| Lo simulado no entra en el historial real | `historialReal = 0` durante toda la demostración |

**Los cuadros por segundo NO se pudieron medir.** El navegador del banco
estrangula `requestAnimationFrame`: un contador propio dio **1 por segundo**
mientras la escena creía ir a 10. Cualquier cifra de fps sacada de ahí habla
del navegador, no del dibujo — por eso se añadió `medirDibujo()`, que dibuja N
veces seguidas sin esperar al refresco. El tiempo de la tarjeta en una máquina
de usuario real sigue **sin medir**, y es lo primero que hay que hacer en un
equipo de los que usa el cliente.

### Tres defectos que solo se vieron mirando (o midiendo píxeles)

Los tres estaban con todas las pruebas en verde. Es el recordatorio de para qué
sirve el navegador en una fase visual.

1. **`Container.tint` no existe en PixiJS 8.** El apagado del personaje se
   aplicaba al grupo que contiene tronco, cabeza y brazos. No falla, no avisa y
   no hace nada: en «no sé» el personaje seguía con su color, o sea que la
   pantalla volvía a decir que todo estaba normal — exactamente la mentira que
   ese estado existe para romper. **Y a simple vista la captura era creíble**;
   se encontró comparando los píxeles del lienzo entre los dos estados (1,33 %
   distintos contra 0,16 % de dos fotos del mismo estado).
2. **La zona sensible era un polígono que se cruzaba a sí mismo.** Seis puntos
   mezclando alturas sin el orden de la silueta: el recuento de cruces deja
   agujeros y pulsar en medio del puesto no seleccionaba nada. La silueta de un
   prisma isométrico es un hexágono convexo.
3. **El signo de interrogación caía detrás de la placa del puesto.** Estaba
   dibujado y visible, justo debajo del rótulo con el nombre.

### Lo que queda fuera, dicho

- **No es arte definitivo.** Todo está dibujado con geometría. Lo que se fija
  acá es la composición, la escala, la profundidad, el reparto de archivos y el
  coste; el día que haya ilustración se reemplaza el cuerpo de las funciones de
  `oficina.ts` y `personaje.ts` y nada más.
- **Cinco animaciones, no siete.** `caminar`, `levantarse`, `sentarse` y
  `esperando` son de un personaje que recorre la oficina, y eso no tiene todavía
  un hecho medido detrás. Siete a medias se ven peor que cinco terminadas.
- **Las tres estaciones están vacías a propósito.** Hoy hay un solo agente
  ejecutable con puesto en esta área. Dibujar tres ocupantes más haría una
  escena más vistosa y una pantalla que miente sobre la plantilla.
- **La geometría de la sala sigue en código.** El agente que la ocupa ya llega
  como dato desde el inventario del motor; las coordenadas no. Cuando haya un
  segundo departamento esto se convierte en una plantilla por empresa y
  `noc.js` desaparece. Está escrito dentro del archivo.
- **La ruta `/centro-mando/v2` no se abrió en la aplicación real.** Está detrás
  de la sesión y no hay backend local; lo verificado es la escena y sus módulos,
  en el banco. Abrirla con sesión es trabajo de quien despliegue.
- **El panel no se pudo montar en el banco**: `mount` desde fuera de la
  aplicación carga una segunda copia del runtime de Svelte y revienta — la misma
  avería que `svelte.config.js` documenta. Se verifica con `render()` de
  'svelte/server', 19 pruebas.

### Una señal nueva en `frescura.js`

`pausado`. El sondeo se detiene con la pestaña oculta —es la regla del
transporte— y el silencio crecía solo: la pantalla acusaba al motor de algo que
había hecho ella. **No cambia el veredicto** (seguimos sin saber, y con razón);
cambia el motivo, porque «la pestaña estuvo oculta» se arregla volviendo y «el
motor no responde» no.

---

## Fase 3B — el ciclo de vida de las ejecuciones, hecho el 30/10/2026

Lo que compra: el personaje puede mostrar **«trabajando AHORA»** y no solo «pasó
algo hace un momento». Hasta acá `tool_calls` se escribe cuando la llamada
TERMINA, así que una llamada lenta y una recién terminada se ven igual — y por
eso el motor se niega, con razón, a emitir `waiting_tool`.

### La medición que cambió el diseño, y estaba en el propio código

El diseño original escribía la fila `iniciada` al empezar el turno. **Un viaje a
la base de producción cuesta 1.054 ms de mediana** (medido el 07/09/2026; es la
razón por la que la traza del turno ya se movió a un hilo aparte).

O sea que la versión obvia le agrega **un segundo a cada respuesta del cliente**
para que una pantalla que quizá nadie mira pueda animar un personaje. Es
exactamente el costo que la traza dejó de cobrarle al cliente, y volver a
pagarlo sería deshacerlo.

```
apertura   en un hilo, fuera del camino crítico
cierre     plegado DENTRO del viaje que la traza ya hace
total      +1 viaje por turno, no +2
```

### Lo que eso obliga, y es la parte que importa

Apertura y cierre son **dos escrituras concurrentes sobre la misma fila sin
orden garantizado**. Si el orden importara, el caso malo sería silencioso: la
fila quedaría `iniciada` para siempre y la oficina mostraría a alguien
tecleando desde hace horas.

Por eso las dos son idempotentes sobre la clave primaria:

```
abrir    insert ... on conflict (id) DO NOTHING
cerrar   insert ... on conflict (id) DO UPDATE  (al estado terminal)
```

Una apertura tardía no puede revivir una ejecución cerrada; un cierre temprano
crea la fila ya cerrada. **El orden deja de importar**, que es la única forma de
que esto sea correcto sin coordinar dos hilos. El identificador se genera en
Python y no en la base, porque el cierre lo necesita enseguida y esperar el
`returning` volvería a poner el viaje en el camino crítico.

### `desconocida` se deriva, no se guarda — contra lo que decía el diseño

El diseño listaba `desconocida` como un quinto estado que escribiría un barrido.
No se hace así, por dos razones con cicatriz en este repositorio:

- un veredicto guardado miente mientras el reloj corre (es la misma razón por la
  que la salud del seguimiento de campo se **calcula**);
- un barrido es un proceso que **tiene que estar corriendo**, y acá ya pasó que
  el reloj de tareas colgara de un bloque `__main__` que gunicorn nunca ejecuta.
  Si el barrido no corre, las filas se quedan `iniciada` para siempre.

Derivado en la lectura no puede fallar así: una ejecución más vieja que el
umbral **es** desconocida, la calcule quien la calcule, sin que nadie haya
corrido nada. Umbral: 600 s, holgado a propósito — no está para cortar trabajo
lento, está para que un proceso muerto no deje a un personaje tecleando para
siempre.

### El orden de precedencia, que es donde una pantalla empieza a mentir

```
1  no saber gana siempre                      (el veredicto de frescura)
2  una ejecución vieja ES no saber            (creible: false -> incognito)
3  un acontecimiento gana al trabajo de fondo (falla, derivación, escalada)
4  una ejecución viva sostiene el tecleo      (y NO caduca sola)
5  lo demás, como antes
```

El 3 merece su línea: teclear es el fondo y el fondo no puede tapar un
acontecimiento. El 4 también: con la ejecución abierta la animación deja de ser
un destello que cuenta algo que pasó y pasa a sostenerse mientras pasa. Y sin
rótulo —el turno está en curso y todavía no se sabe con qué terminó; poner el
nombre de lo último sería contar como presente algo que ya pasó.

### Una cuarta procedencia

`ejecucion:<uuid>`, junto a `evento:`, `simulado` y `ambiente`. No se parece a
las otras tres: las demás describen algo que ya pasó y caducan solas. Esta
describe algo que sigue pasando. **No entra en el historial** —un trabajo en
curso todavía no es un hecho que contar— y cuando cierre producirá sus
`tool_calls`, que sí entran.

### Medido

Contra **PostgreSQL 17** de laboratorio, 16 comprobaciones en verde
(`tests/test_ejecuciones_con_base.py`):

| | |
|---|---|
| Una apertura tardía no revive una ejecución cerrada | ✓ |
| Un cierre temprano crea la fila ya cerrada | ✓ |
| `iniciada_en` no se pisa: la ejecución dura 1,10 s y no cero | ✓ |
| El cierre completa la conversación, y un cierre sin ella no la borra | ✓ |
| `desconocida` se deriva de la edad, sin barrido | ✓ |
| Sin empresa fijada se ven **0 filas**, no todas | ✓ |
| **La escritura no retiene el cursor de E1**: la frontera avanzó 776 → 781 | ✓ |

Las dos mutaciones centrales mueren:

```
la apertura deja de ser idempotente y pisa el estado  -> 1 comprobación en rojo
el cierre pisa el instante de apertura                -> 2 comprobaciones en rojo
```

En el navegador, con el banco:

```
reposo                        reposo       · ambiente
turno en curso                teclear      · ejecucion:<uuid>
el mismo, 9 segundos después  teclear      ← un destello habría caducado a los 0,9 s
turno sin noticias            incognito    · apagado 0,82
al cerrarlo                   reposo
```

**359 pruebas verdes** en el centro de mando (eran 338). La guarda de
arquitectura del motor, en verde. Y la guarda de la escena **cazó una violación
mía**: escribí la palabra «herramienta» en un comentario de `adaptador.ts` y la
prueba se puso roja.

### Lo que queda fuera, dicho

- **La migración NO está aplicada en ninguna parte.** `supabase/202610302200_ejecuciones.sql`
  existe y está probada en laboratorio; aplicarla a producción va por el ledger
  (`cli/migrar_asistente.py --aplicar`), con la credencial `DBUSER`, y es parte
  del despliegue, no de esta fase.
- **Sin la migración, el endpoint degrada en silencio y a propósito**:
  `ejecuciones_activas` devuelve `[]` ante un fallo y lo registra, así que la
  oficina sigue mostrando lo que pasó, como antes de que esto existiera.
- **El costo con `--workers 1` está acotado por diseño pero no medido en
  producción**: es un viaje más por turno, en un hilo. Cuántos turnos por día
  hay allá sigue sin medirse — hace falta acceso de lectura que esta sesión no
  tiene.
- **Un turno que revienta deja la fila `iniciada`.** No se cierra como
  `fallida` porque el camino de excepción no pasa por donde se cierra. El efecto
  es el correcto —pasado el umbral se deriva «no sé»— pero el estado `fallida`
  del esquema hoy no lo escribe nadie.

---

## Fase 4 — la planta deja de ser código, y entra el segundo departamento (30/10/2026)

### Lo que de verdad cambió

La geometría de la oficina estaba escrita dentro de `escena/oficina.ts`: un
mundo de 14 × 10, un pasillo en una franja fija y una lista de muebles con sus
coordenadas. Servía para UNA sala.

Ahora la escena **recibe la planta como dato**, sabe dibujar TIPOS de mueble y
no sabe qué departamento está construyendo:

```ts
Planta = { mundo, pasillo, cartel, mural, mobiliario[], puestos[] }
```

**La prueba de que eso valía la pena es que el segundo departamento no toca una
sola línea de `escena/`.** Es un archivo de datos y nada más. Hay una prueba que
lo fija: todo tipo de mueble que una planta pide tiene que existir en el
registro de la escena, y un tipo desconocido se cuenta en vez de dibujarse
«parecido».

`noc.js` desapareció, como decía dentro de sí mismo que iba a pasar.

### El segundo departamento no es el primero con otro rótulo

Atención al Cliente tiene **otro mundo** (13 × 9), **dos** pantallas de muro en
vez de tres, una espera con bancos junto al paso —lo que una sala de atención
tiene y un centro de operaciones no— y **ni armarios de equipos ni panel de
empalmes**. Si las dos salas se vieran iguales, la oficina virtual no estaría
representando a la empresa: estaría repitiendo un fondo.

Identificador `soporte_tecnico`, rótulo «Atención al Cliente». Mismo criterio
que `operativo` → «NOC y Redes»: el identificador es el que ya existe en la
configuración y en los datos; renombrarlo daría un rótulo bonito y perdería la
continuidad de todo lo registrado con el nombre viejo.

### Dos defectos que solo aparecieron al haber una segunda sala

**1. La escena seguía respondiendo después de `destruir()`.** Cambiar de sala
desmonta una escena y monta otra en el mismo gesto, y el bucle de quien la usa
puede tener un fotograma en vuelo. `metricas()` entraba a un `app.stage` que ya
era `null` y reventaba — y no reventaba sola: **se llevaba por delante el bucle
entero**, así que la sala nueva se quedaba quieta sin un solo mensaje que lo
explicara. Ninguna prueba podía verlo: hasta ese día nunca se había desmontado
una escena con otra arrancando detrás. Arreglado con una bandera de vida en los
ocho métodos, y `destruir()` idempotente.

**2. Las placas de dos puestos se tapaban.** En isometría dos puestos caen en la
misma columna de pantalla cuando `gx - gy` coincide, por lejos que estén en la
sala; el de delante se dibuja después y su placa corta el nombre del de atrás a
media palabra. Resolverlo moviendo muebles hasta que encajen no es resolverlo
—la siguiente planta vuelve a chocar y el síntoma no señala a la geometría—,
así que se separan en ALTURA: lo que está más lejos se rotula más arriba.
Funciona para cualquier reparto.

### Medido

```
NOC y Redes          279 objetos
Atención al Cliente  248 objetos
las dos              144 fps
ida y vuelta entre salas, dos veces: sin errores de consola
371 pruebas verdes del centro de mando (eran 364)
la guarda de arquitectura del motor, en verde
```

Y la guarda de la escena **volvió a cazarme**: escribí «ISP» en un comentario de
`oficina.ts`. La escena no puede saber en qué industria está.

### Lo que queda fuera, dicho

- **La planta sigue siendo código.** Vive en `departamentos.js`, no en
  `tenant_config`. Lo que SÍ está resuelto es la forma: una planta ya es un
  documento de datos que se puede guardar y editar, así que moverlo es cambiar
  de dónde se lee, no rediseñarlo. Mientras tanto es semilla, igual que
  `tenants/<slug>.config.yaml` lo es de la configuración.
- **Faltan seis departamentos.** Dos no prueban que el séptimo sea gratis, pero
  sí prueban que el segundo no costó lo que costó el primero.
- **No hay editor de plantas.** Mover un escritorio hoy es editar una fila en un
  archivo del repositorio, no una pantalla.

---

## Fase 5 — las seis salas, y el defecto que habrían tenido todas (30/10/2026)

### Seis, no ocho, y por qué

Los departamentos salen de las **áreas que los roles declaran de verdad** en la
configuración del tenant, leídas del YAML y no de memoria:

```
Operaciones         1 rol    → NOC y Redes
Atención al Cliente 2 roles  → Atención al Cliente
Soporte Técnico     1 rol    → Soporte Técnico
Facturación         2 roles  → Facturación y Cartera
Ventas              1 rol    → Ventas
Administración      2 roles  → Administración
```

Nueve roles, seis áreas, seis salas. **No son ocho**: ocho era mi estimación, y
el dato dice seis. Hay una prueba que lo fija por los dos lados — cada área real
cae en alguna sala, y ninguna cae en dos (el mismo agente en dos salas sería el
mismo trabajo contado dos veces).

### El defecto que ya estaba entregado

`config.areas` declara `operativo`; el rol `supervisor_noc` declara área
**`Operaciones`**. Los dos vocabularios no solo se escriben distinto: **tienen
miembros distintos** — «Atención al Cliente» existe en los roles y no tiene
entrada en `config.areas`, y `operativo.agentes` está vacío.

Con el identificador y el rótulo como únicas etiquetas, **la sala del NOC salía
vacía en producción**. Se vio leyendo el YAML del tenant, no deduciéndolo.

El arreglo: cada departamento **declara** las etiquetas que acepta, como dato.
Se escriben; no se adivinan. Y la prueba que decía «no adivina sinónimos» pasó a
comprobar las dos mitades: acepta lo declarado, rechaza lo que no.

### Tres tipos de mueble nuevos, y lo que distinguen

```
mostrador     solo Ventas          es el departamento al que alguien LLEGA
mesa          solo Administración  donde se reúne gente hay menos escritorios
estanteria    Cartera, Soporte,    la sala del papel
              Administración
```

Y una ausencia deliberada: **Facturación y Administración no tienen mural**. Un
mural es una sala que mira algo en vivo; ahí lo que se mira son cuentas y
decisiones. Colgarles pantallas habría sido repetir el NOC con otro color.

### Los acentos se eligieron midiendo

La configuración del tenant declara un color por área. **La escena no los usa
tal cual**: el naranja de Ventas (`#d97706`) quedaba a **143** de distancia del
rojo de alarma y la guarda lo rechazó — una sala tranquila se habría leído como
una sala en alarma.

```
distancia al rojo de alarma   NOC 351 · Atención 340 · Admin 370
                              Soporte 278 · Cartera 265 · Ventas 178
distancia mínima entre salas  77
```

Es una divergencia deliberada con la configuración de la empresa, no un
descuido: el color de un área en una lista y el color de una sala entera
iluminada no se eligen con el mismo criterio.

### Un defecto estructural que solo aparece con seis salas

**Una luminaria de techo tapaba el rótulo de un puesto del fondo.** La luminaria
está más cerca de la cámara que un escritorio lejano, así que se dibuja después
y su carcasa cubría media placa: en la captura se leía «ministración» y parecía
que la placa era demasiado estrecha. **No lo era** —tenía 18 px de margen a cada
lado, medido en el navegador—; era oclusión.

Los rótulos pasaron a una **capa propia por encima de todo el mobiliario**. Un
rótulo no compite por profundidad con los muebles: es información sobre la sala,
no un objeto dentro de ella. La capa va con `eventMode: 'none'`, o se comería
los clics.

### Medido

```
NOC y Redes            279 objetos
Atención al Cliente    248
Soporte Técnico        169
Facturación y Cartera  203
Ventas                 228
Administración         166
las seis               142-144 fps
recorrido completo de las seis, ida y vuelta: sin errores de consola
selección comprobada con la capa de rótulos encima
412 pruebas verdes · guarda de arquitectura del motor en verde
```

### Lo que queda fuera, dicho

- **Las seis salas siguen siendo rectángulos con dos muros.** Es el límite que
  queda sin tocar: no hay L, ni columnas, ni tabiques interiores. Se va a notar
  antes con seis que con dos.
- **La planta sigue en `departamentos.js`**, no en `tenant_config`.
- **Los nueve roles no son nueve empleados.** Tres son capacidades asignadas a
  personas, no agentes ejecutables con puerta propia. La oficina los dibuja
  igual porque el inventario del motor los sirve igual; distinguirlos pide un
  dato que hoy no viaja.

---

## Fase 6 — la empresa entera, las seis salas a la vez (30/10/2026)

Hasta acá la oficina virtual se miraba **de una sala en una**. Juntas son otra
cosa: se ve la empresa, no un departamento — y es lo que le da sentido al
nombre.

### Lo que costó, que es el punto

**Una sala no sabe que hay otras.** Cada planta gana un `origen` en celdas y la
escena la construye exactamente igual, en sus propias coordenadas, dentro de un
contenedor desplazado. Montar las seis **no obligó a tocar nada de
`oficina.ts`**: es la segunda vez que ese corte se paga solo.

El orden entre salas lo da la profundidad de su origen; dentro de cada una
sigue siendo el suyo. Es una simplificación honesta **y tiene un límite
declarado**: si dos salas se solaparan en la rejilla habría que intercalar sus
objetos uno a uno, y eso no se hace. Hay una prueba que comprueba que no se
solapan.

### El hueco se mide contra la ALTURA, no contra el suelo

Con tres celdas de separación los muros de una sala se metían dentro de la
vecina. En isometría un muro de cuatro unidades se proyecta más de cien píxeles
hacia arriba, así que invade la sala de atrás **aunque en planta no se toquen**.
Cinco celdas, y una prueba que exige que el hueco cubra la altura máxima.

### Medido en el navegador

```
1.289 objetos · 132-144 fps · escala 0,41
21 de 21 puestos seleccionables, de las SEIS salas
los nueve agentes del inventario, sentados y visibles a la vez
```

El barrido de selección es lo que más dice: recorrió el lienzo entero pulsando
cada 18 px y encontró los 21 puestos, repartidos en las seis salas. La cámara y
la selección funcionan igual con seis recintos que con uno.

### Una decisión sobre el color

Con las seis a la vez, **los colores de estado toman el acento de la primera
sala**, no el de cada una. Si cada sala tiñera su propio «trabajando», el mismo
estado se vería de seis colores distintos en la misma pantalla y el color
dejaría de decir nada. Los de alarma siguen sin cambiar nunca.

### Lo que queda fuera, dicho

- **Los rótulos están por encima del mobiliario de SU sala, no del de las
  vecinas.** Con las seis a la vez, un mueble de una sala cercana puede tapar el
  rótulo de una lejana. Se arregla subiendo la capa de rótulos al edificio;
  hoy vive en cada recinto.
- **No hay nada entre las salas.** El hueco es suelo vacío: ni pasillos que las
  unan, ni puertas, ni un vestíbulo. Son seis oficinas cerca, no un edificio.
- **Las seis siguen siendo rectángulos con dos muros.**

---

## Decisiones de producto congeladas — 31/10/2026

Tomadas por el cliente tras una auditoría externa, y registradas acá porque en
este proyecto **una decisión sin escribir se reabre sola cada sesión**.

### D1 · Ocho departamentos para la empresa piloto, ninguna cantidad fija

```
1 NOC y redes                5 Finanzas y cartera
2 Operaciones de campo       6 Administración
3 Atención al cliente        7 Recursos humanos
4 Comercial y marketing      8 Auditoría y cumplimiento
```

**Los departamentos vienen de la configuración organizacional de cada empresa,
no se deducen de los agentes.** Un departamento existe aunque no tenga a nadie:
Recursos Humanos y Auditoría son ejemplos. Eso representa una estructura
configurada, no inventa empleados.

Las áreas históricas de los roles **se mapean** a esa estructura; no se crean
departamentos duplicados.

Lo que esto corrige de lo que yo había construido: medí seis departamentos
leyendo las áreas de los roles y los di por el organigrama. **Eran los grupos
de los agentes, no la organización.** Son dos cosas distintas y las confundí.

### D2 · Edificio de tres niveles para la empresa piloto

Sección arquitectónica separada: niveles desplazados en vertical, unidos por un
núcleo visible, cada uno aislable.

```
Piso 3  NOC y redes · Dirección · sala de reuniones
Piso 2  Operaciones de campo · Atención al cliente · Comercial y marketing
Piso 1  Finanzas y cartera · Administración · Recursos humanos ·
        Auditoría y cumplimiento · recepción
```

**Tres pisos es la configuración del piloto, no un límite del producto.** El
motor debe admitir uno, dos, tres o más.

Antes de esta decisión, la ficha listaba «múltiples pisos» como *posterior* y el
MVP como *un solo departamento visual*. Queda elevado a requisito.

### D3 · Personas humanas, en una fase posterior

La plataforma representará **agentes IA y empleados humanos**, distinguiendo
identidad, capacidades, permisos y **procedencia de sus estados**.

La regla que lo gobierna: **no atribuir actividad laboral a una persona sin
evidencia real.** Haber iniciado sesión hace horas no es trabajar. Sin
información de actividad, el personaje se queda en reposo ambiental.

Los técnicos de campo **no se dibujan en la oficina**: se representarán con
unidades móviles o un mapa operativo. Fingir que están en un escritorio sería
afirmar algo falso sobre dónde está una persona.

Se implementa **después** de estabilizar el modelo de agentes IA.

### D4 · Entorno local autorizado

Autorizado levantar un entorno local aislado del CRM y SvelteKit para validar
la oficina. Condiciones: sin producción ni sus credenciales, sin tocar
contenedores ajenos, base de prueba aislada con datos inventados,
autenticación local, sin push ni deploy, y **sin fusionar automáticamente** los
24 commits pendientes de producción.

---

## P0.1 · Quién se sienta se DECLARA — hecho el 31/10/2026

### La corrección, y es de un diagnóstico mío equivocado

Dije: *«el dato que distingue a un agente ejecutable viaja desde el motor, y mi
capa servidor lo descarta»*. Lo verifiqué y **era falso en su conclusión**.

`orientado_a` sí viaja. Pero su valor por defecto en el esquema es
`colaborador`, así que los tres roles que no lo declaran salen **idénticos** a
los dos que sí lo declaran y sí tienen puerta propia:

```
cliente_final  4 roles   cliente_final, facturacion_cliente,
                         soporte_tecnico_cliente, ventas
colaborador    5 roles   configuracion_guiada, supervisor_noc   (declarado)
                         soporte, facturacion, administracion   (POR DEFECTO)
```

Separa 4 de 5. **No distingue un agente ejecutable de una capacidad asignada a
una persona.** Deducir la ocupación de ahí habría cambiado una invención por
otra.

### Lo que se hizo

**La ocupación es una declaración, no una deducción.** Cada puesto dice qué
agente lo ocupa, o ninguno. Antes `plantaDe` sentaba a *todos* los agentes del
área en orden hasta llenar los puestos — y así dibujaba nueve empleados donde
hay seis.

Y se **valida contra el inventario**: un agente declarado que el motor no sirve
deja el puesto vacío **y dice por qué**. Dibujarlo igual volvería a inventar un
empleado; callarlo sería un hueco que nadie puede explicar. La ficha distingue
«sin agente asignado» de «la configuración lo declara y el inventario no lo
trae», que no son lo mismo.

Las tres capacidades **no desaparecen**: cada departamento las declara y la
ficha las muestra como lo que son, sin escritorio. No basta con no dibujarlas;
ocultarlas sería otra forma de mentir.

`orientado_a` se reenvía igual, pero como **información** para la ficha —a
quién atiende el agente— y nunca como criterio de ocupación.

### Medido

```
Atención al Cliente   sentaba 2 agentes  →  ahora 1 (soporte es capacidad)
en total              9 personajes       →  6, y 3 declaradas como capacidad
una prueba que afirmaba «los nueve se sientan» se puso ROJA: era la mentira
```

---

## P0.2 · El primer estado terminal manda — hecho el 31/10/2026

### Lo que NO era cierto

La auditoría dijo que un estado antiguo puede sobrescribir uno más reciente. En
el **esquema**, sí. En el **cableado**, no: hay exactamente un cerrador por
turno, se llama una vez y siempre escribe `terminada`. `fallida` y `cancelada`
**no las escribe nadie**. Decir que estaba roto habría sido fabricarlo.

La puerta estaba abierta y no entraba nadie. Cerrarla ahora es barato, y el día
que exista un segundo escritor —una cancelación externa, un barrido, un corte—
deja de ser teórico.

### La regla

El primer estado terminal **gana**; el segundo levanta `cierre_en_conflicto`.
No se descarta en silencio: una contradicción es un hecho que alguien tiene que
poder ver, y el motor la registra.

Dos efectos del mismo cambio, que no estaban y hacían falta:

- `hubo_fallo` ahora es un **or**: un fallo visto una vez no lo borra un cierre
  posterior que no lo vio.
- `n_llamadas` toma el **mayor**, y `terminada_en` conserva el primero.

### Medido contra PostgreSQL 17

```
[OK] el primer cierre no es un conflicto
[OK] el primer terminal se conserva (quedó 'terminada')
[OK] el segundo se REPORTA como contradictorio
[OK] y queda anotado en la fila
[OK] no pierde el recuento de llamadas del primero
[OK] reintentar el mismo cierre no levanta la bandera
[OK] un cierre posterior que no lo vio NO borra el fallo
```

La migración se modificó **en el sitio** en vez de agregar una segunda: nunca
se aplicó en ninguna base. Si se hubiera aplicado, esto estaría prohibido — el
ledger valida por checksum.

---

## P0.3 · Ejecución y acontecimiento son dos dimensiones — hecho el 31/10/2026

### Lo que yo tenía, y la objeción que acepté

Un fallo **ganaba** sobre el trabajo de fondo y reemplazaba la animación.
Corrijo un matiz de la auditoría: no hacía que el agente *se detuviera* —duraba
1,6 s y el personaje volvía a teclear solo, porque la ejecución seguía
abierta—. Pero durante ese segundo y medio **lo parecía**, y una pantalla no
debería dar a entender algo falso ni por un segundo.

Un fallo de una llamada no significa que el turno haya terminado: el agente
puede estar recuperándose, llamando a otra cosa o redactando.

### Las dos dimensiones

```
ejecución        en_curso · sin_noticias · null      ← el cuerpo
acontecimiento   consulta · acción · falla ·         ← el aviso al lado
                 derivación · escalada
```

Conviven. Con el turno abierto, el cuerpo **sigue trabajando** y el
acontecimiento viaja aparte, se dibuja como un aviso junto a la placa y aparece
en la ficha etiquetado como lo que es: *lo último que pasó, mientras el turno
sigue abierto*.

Sin turno abierto, el acontecimiento **sí** manda el cuerpo: es lo único que
hay.

Y el aviso **caduca aunque el turno siga**. Un aviso perpetuo contaría un fallo
de hace media hora como si acabara de ocurrir.

El aviso va en la capa de rótulos, no en el puesto: un acontecimiento tampoco
puede quedar tapado por un mueble cercano.

### Medido en el navegador

Con un turno en curso y el guion de demostración corriendo a la vez:

```
cuerpo    supervisor_noc:teclear    (constante)
ejecución supervisor_noc:en_curso   (constante)
aviso     consulta → acción → derivación → escalada
```

Antes, cada uno de esos cuatro habría reemplazado la animación del cuerpo.

---

## P0.4 · La oficina dentro del CRM real — 31/10/2026

### El entorno, y por qué no se pudo usar el del repositorio

`docker-compose.yml` **no sirve para esto**, por tres razones medidas antes de
escribir nada:

1. El servicio `motor` hace `env_file: .env` — el de la **raíz**, que está en
   `.gitignore` y tiene credenciales de producción. Levantarlo arrancaría un
   contenedor apuntando a la base productiva.
2. El volumen `postgres_data` está declarado `external: true`: lo comparte con
   otros proyectos de esta máquina.
3. Publica 5432, 6379, 5173 y 5000, y hay servicios de otras sesiones corriendo.

Laboratorio propio en `oficinalab`: volúmenes propios, puertos 55500/55600/
55700/55800, variables inventadas, **sin leer el `.env` de la raíz**.

```
db (pgvector:pg16) · redis · backend Django · motor Flask · frontend SvelteKit
2 organizaciones ficticias, sembradas por `seed_data` (dominios reservados IANA)
30 migraciones del motor aplicadas POR EL LEDGER
configuración del tenant cargada: los 9 roles
autenticación local real, por el formulario de login
```

### La comprobación del ledger que pidió la auditoría

```
archivo   202610302200_ejecuciones.sql
sha256    d8d64e376b9d34fad5246cce522af80f9043852ad74aa9139d309380a3cf2e1a
          (algoritmo sha256-utf8-lf-v1)
```

En el laboratorio figuraba **pendiente** antes de aplicarla y quedó anotada con
ese checksum: no había una versión distinta registrada.

Para los entornos que esta sesión no alcanza, la comprobación es una consulta:

```sql
select archivo, sha256 from asistente.migraciones_aplicadas
 where archivo = '202610302200_ejecuciones.sql';
```

Cero filas = nunca aplicada. Ese sha256 = es esta versión. **Otro sha256** = se
aplicó una distinta y modificarla en el sitio fue un error que hay que revertir.
No se consultó producción ni bases de otras sesiones, y no se intentó.

### DEFECTO 1 — E1 nunca había funcionado

`/eventos` devolvía **HTTP 500** la primera vez que el motor lo sirvió de
verdad.

`sesion()` abre la conexión con `row_factory=dict_row`, así que una fila es un
diccionario. `eventos_desde` estaba escrita **por índice** de principio a fin:
`cur.fetchone()[0]` para la frontera, `for (a, b, c, ...) in filas` para
desempaquetar, `filas[-1][0]` para el cursor siguiente. Todo `KeyError`.

**La función entera nunca se había ejecutado.**

Y había un segundo fallo escondido detrás del primero: `_retraso_del_flujo`
hacía `fila[0]` dentro de un `try/except Exception: return None` puesto para el
caso sin permiso sobre `pg_stat_activity`. El `KeyError` caía ahí, así que la
función devolvía `None` **siempre** y la pantalla leía «no se pudo medir el
retraso» sin que nada fallara. Un fallo silencioso escondido detrás de un fallo
silencioso previsto.

**Por qué ninguna prueba lo vio, y lo dice su propio comentario:**

> «Se copia aquí en vez de importar db.py porque ese módulo abre su propia
> sesión contra la base de verdad; lo que se prueba es la GARANTÍA de la
> consulta.»

La prueba de E1 verificaba el SQL, no el código que lo usa. Es
`PARSEA ≠ IMPORTA ≠ FUNCIONA` en el único sitio donde faltaba.

Arreglado leyendo por nombre, y el `except` ahora **registra** en vez de callar.
Prueba nueva, `tests/test_eventos_desde_integracion.py`, que **llama a la
función**: 18 comprobaciones en verde.

### DEFECTO 2 — configuración del laboratorio, mío

El frontend pedía `/api/api/auth/login/` y la pantalla decía «Correo o
contraseña incorrectos» — **que era falso**: las credenciales estaban bien y la
ruta no existía. Un 404 disfrazado de credenciales malas. `PUBLIC_DJANGO_API_URL`
no lleva `/api`: lo agrega el cliente.

### Las cinco validaciones

**1 · Integración.** `/centro-mando/v2` carga dentro del CRM, con la barra
lateral, la organización de la sesión y las siete vistas. **293 objetos a 144
fps** en el NOC; **1.292 a 144 fps** con la empresa entera. Sin sesión,
redirige **307**.

**2 · Seguridad multiempresa.** Con la sesión en la segunda organización
—que no tiene tenant configurado— la oficina muestra **la sala vacía**, los
puestos dicen «agente no encontrado» y `/api/eventos` devuelve **500 sin un
solo dato**. No cae a un tenant por defecto: **falla cerrado**. Y en el motor,
el evento sembrado en la organización 2 **no sale** en el flujo de la 1.

**3 · Funcionamiento visual.** Las seis salas y la vista de empresa renderizan;
la selección abre la ficha; la rueda hace zoom; las animaciones corren.

**4 · Estados operativos.** Con `supervisor_noc` sentado desde el inventario
real y una ejecución abierta en la base, la ficha dice **«Un turno en curso»**
y el diagnóstico muestra consultas, turnos en curso y el cursor de E1
avanzando. Al **detener el motor**, el indicador pasa a «Sin información · la
última lectura falló» en 5 s —una lectura fallida es evidencia inmediata, no
hace falta esperar el silencio de 40 s—, el motivo escala a «el motor no
responde» al cruzarlo, y **las seis salas se apagan a la vez**. Al levantarlo,
vuelve a «Actualizado» en un sondeo.

**5 · Ciclo de vida.** Navegar fuera y volver remonta la escena con **los
mismos 293 objetos**: sin fuga. Recorrer las siete vistas no deja errores.

**Resoluciones.** 1625×600 (escritorio) y 1366×768 (portátil): el lienzo se
ajusta al contenedor, no hay desbordamiento horizontal, 144 fps en las dos.

### Lo que NO se validó, y hay que decirlo

- **Rendimiento de la aplicación entera.** Los 144 fps son del dibujo. El coste
  de la escritura de ejecuciones con `--workers 1` sigue sin medirse en carga.
- **La consola muestra un 500 cada 12 s** con una organización sin asistente
  configurado: el flujo reintenta indefinidamente una ruta que nunca va a
  funcionar para esa empresa. No rompe nada y es ruido; dejarlo de reintentar
  ante «no configurado» es trabajo pendiente.
- **El historial de eventos sale vacío al entrar**, y es por diseño: el flujo
  arranca en la frontera actual y no entrega histórico. La foto que lo
  completaría es `/api/centro-mando`, que esta pantalla todavía no pide.
- **Playwright como suite** no se montó: las comprobaciones de navegador se
  hicieron conduciendo la página, no con pruebas que alguien pueda volver a
  correr. Montarlas es trabajo aparte.
- **Los 62 rojos preexistentes** siguen como estaban; no se tocaron.
- **Las dos pruebas con base del laboratorio no pueden compartir instancia**:
  cada una borra `public.organization` al preparar, y la otra tiene filas que la
  referencian. Se corren en contenedores separados.

---

## P1.1 · La organización es configuración — 31/10/2026

### El error que esto corrige, y no es el que parecía

La oficina dibujaba **seis departamentos** y los seis estaban escritos en el
frontend. Lo que importa es de dónde habían salido: de **agrupar el campo `area`
de los roles configurados**. O sea que la pantalla no mostraba la organización de
la empresa — mostraba **los grupos de sus agentes**, que es otra cosa.

Tres consecuencias lo prueban:

- **Un departamento sin ningún agente no existía.** Recursos Humanos y
  Auditoría son departamentos reales de un ISP y no hay un agente que los
  represente. Deducidos de los agentes, desaparecen. Una empresa que mira su
  propia oficina y no ve a Recursos Humanos no está viendo su empresa.
- **Dos etiquetas de rol que son un departamento salían como dos salas.**
  «Soporte Técnico» y «Atención al Cliente» son dos áreas en el vocabulario de
  los roles y **una sola puerta de servicio** en la empresa.
- **La siguiente empresa necesitaba una sesión de código.**

### El corte: qué declara la empresa y qué sabe el producto

```
CONFIGURACIÓN (TenantConfig.organizacion, por empresa, editable)
   pisos           nivel + rótulo
   departamentos   id · rótulo · dirección · piso · plantilla · areas[] ·
                   capacidades[] · ocupaciones[] · acento
   espacios        id · rótulo · piso · plantilla · acento   (sin areas ni agentes)

PRODUCTO (plantillas.js, catálogo genérico que conoce la pantalla)
   operaciones · atencion · tecnica · expedientes · comercial · reuniones
   + generica (la de reserva)
```

**La geometría no es configuración, y el corte está puesto ahí a propósito.**
Describir una sala isométrica son cuarenta números y equivocarse en uno **no da
error**: los muebles se dibujan uno dentro del otro y el síntoma se describe
como «parpadea». Lo que una empresa quiere decidir es *«esta sala es un centro
de operaciones»*, no dónde va cada luminaria. Mismo reparto que
`AreaDeTrabajo.icono`, que ya nombra un dibujo de un catálogo que el motor no
tiene — y por eso el motor **no valida que la plantilla exista**: lo que valida
es todo lo que, mal escrito, haría que la pantalla afirmara algo falso.

### Por qué hay una estructura por defecto, y por qué no es el mismo error

Una organización vacía significa **no declarada**. El motor sirve entonces la
estructura genérica del producto **y lo dice**, en el mismo documento:

```
origen: "declarada"    la empresa la escribió. Es su organigrama.
origen: "por_defecto"  no la escribió. Es la del producto, y la pantalla lo
                       muestra: «estructura por defecto del producto».
```

Sin ese campo las dos se ven igual y una empresa creería que configuró algo que
no configuró — el día que reorganice de verdad no entendería por qué «ya estaba
bien». Un defecto **silencioso** sí sería el error anterior por la puerta de
atrás.

Lo que **no** se hace es caer a una estructura inventada cuando el motor no
responde: ahí no se dibuja edificio y el pie lo explica. Dibujarlo sería afirmar
cómo es una empresa que no se pudo consultar.

### La estructura del piloto, servida por el motor

| Piso | Salas |
|---|---|
| 3 · Tecnología y dirección | NOC y Redes · *Dirección* · *Sala de Reuniones* |
| 2 · Operación y clientes | Operaciones de Campo · Atención al Cliente · Comercial y Marketing |
| 1 · Administración | Finanzas y Cartera · Administración · Recursos Humanos · Auditoría y Cumplimiento · *Recepción* |

En cursiva, los **espacios complementarios**: existen como tipo aparte y no como
un departamento más, porque no agrupan áreas ni agentes. Meterlos en la misma
lista obligaría a que todos los campos de un departamento fueran opcionales, y
entonces un departamento mal cargado —sin áreas y sin puestos— pasaría la
validación haciéndose pasar por un espacio.

**Los acentos de las once salas se midieron, no se eligieron a ojo**: los once a
más de 160 del rojo de alarma y a más de 70 entre sí, par más cercano **77**. La
guarda de la pantalla ahora recorre las salas que llegan de la configuración, no
una lista escrita — así que el día que una empresa elija un acento rojizo desde
su formulario, esto lo encuentra.

### Lo que la validación RECHAZA

Cada una existe porque su ausencia haría mentir a la pantalla:

| Rechaza | Qué pasaría si no |
|---|---|
| dos salas con el mismo id | seleccionar una selecciona la otra |
| un espacio con el id de un departamento | lo mismo, entre tipos distintos |
| una sala en un piso no declarado | un departamento fuera del edificio |
| dos pisos con el mismo nivel | dos plantas que son una |
| un área reclamada por **dos** departamentos | el mismo trabajo contado dos veces |
| el mismo agente sentado en **dos** puestos | la misma actividad animando dos personajes |
| un agente que es capacidad **y** ocupa un puesto | una cosa dice que tiene escritorio y la otra que no |
| un id con mayúsculas o espacios | dos identificadores para la misma sala |
| un acento que no es `#rrggbb` | la configuración escribiendo estilos en la interfaz de todos |

### Medido

```
tests/test_organizacion_config.py          41 comprobaciones, todas en verde
  · los ocho departamentos aprobados, en orden, reparto 3/3/5
  · tres departamentos existen SIN agente: campo, recursos_humanos, auditoria
  · seis agentes sentados, tres capacidades declaradas sin escritorio
  · 12 invariantes RECHAZAN (el efecto, no la presencia del validador)
  · 4 / 15 / 12 → cuatro departamentos en una planta, quince en cinco, doce pisos
  · rapilink.config.yaml SIGUE CARGANDO con el campo nuevo

departamentos.test.js                      90 pruebas
tests/test_nucleo_sin_tenants.py           112 archivos, el núcleo no conoce clientes
tests/test_editor_config.py                en verde
```

**Las dos mutaciones que lo hacen creíble:**

```
quitar el prefijo de sala del id de puesto   →  3 pruebas en rojo
salasDe() ignora la configuración y devuelve
la estructura fija del fixture               → 12 pruebas en rojo
```

La segunda es la que importa: es exactamente la regresión que devolvería la
estructura al frontend, y se ve.

### El fixture del frontend se GENERA, no se copia

`vitest` no puede importar Python, así que la prueba de la pantalla necesita el
documento como JSON. Copiarlo a mano es **el error que dejó a E1 sin probar**:
su prueba copiaba la consulta en vez de importar el módulo, y la función no
funcionaba con la prueba en verde.

```
cli/exportar_organizacion.py                 lo genera desde el motor
tests/test_organizacion_config.py [6]        comprueba que siga coincidiendo
```

Si alguien cambia la estructura por defecto y no regenera, esa prueba se pone
roja y nombra el comando.

### Lo que queda fuera de P1.1, dicho

- **El YAML de `rapilink` NO se tocó.** Declarar la organización ahí crearía la
  divergencia que §6 llama peligrosa —«el repo lo declara y la base no»— y
  cargar ese YAML está prohibido por otro motivo medido: apagaría la encuesta de
  cierre, que vive en la base con un `solo_a` que el archivo no trae. El piloto
  corre con `origen: por_defecto`, visible en pantalla, hasta que alguien decida
  declararla desde la interfaz.
- **El edificio sigue siendo una rejilla plana.** Los pisos ya son un dato y el
  selector los agrupa, pero las once salas siguen una al lado de la otra sobre un
  mismo plano. Apilarlos es P1.2.
- **Los subdepartamentos** no se modelaron: no hay ninguno declarado y un nivel
  de anidamiento sin un caso que lo use es una forma que después hay que
  sostener.
- **No hay editor de organización todavía.** Se edita por `tenant_config`; la
  pantalla para hacerlo es P3.

---

## P1.2 · El edificio, y la aritmética que lo decide todo — 31/10/2026

### El problema que la rejilla plana no tenía

Apilar niveles introduce un fallo que **no se ve mirando una captura hasta que
ya está mal**. En esta proyección `y = 16·(gx+gy) − 26·gz`, así que un nivel más
alto se dibuja más arriba y tapa del de abajo la zona de `gx+gy` pequeño. Un
escritorio tapado **no da error, no da aviso y la escena lo sigue animando**: un
agente trabajando donde nadie lo ve.

Así que la primera decisión fue medirlo, no mirarlo. Invirtiendo la proyección
sobre el plano del nivel de arriba, un punto a altura `z` cae en la celda
`GY + (H − z)·0,8125`, y para no quedar tapado tiene que caer pasado el frente
de las salas de arriba. **Los dos desplazamientos del nivel se cancelan** y
queda:

```
(H − z) · 0,8125  >  fondo de la sala − gy del puesto
```

Tres consecuencias, ninguna evidente antes de escribirla:

1. **La profundidad del pasillo no interviene.** Lo que fija la separación es
   cuánta sala queda DETRÁS del escritorio.
2. Con salas de 10 celdas y puestos a 2,4, el mínimo es **13** — y lo manda la
   **placa** de un puesto normal (z 3,65), no la silla: va más alta, y cuanto
   más alto está un punto, más cerca queda del nivel de arriba.
3. Separar más **no es** la solución: para que dos bandejas no se solapen en
   nada harían falta más de treinta unidades, y eso son tres rebanadas
   lejanísimas unidas por un hilo. Otra vez oficinas flotando.

`ALTURA_DE_PISO = 15` deja 1,6 celdas de margen. **Y el aire que queda se llena
de estructura**, que es lo que separa un edificio en sección de tres bandejas:

```
núcleo        una torre de la altura de piso entera, con dos tramos de
              escalera, su ascensor y su columna. Apilados, se leen como una
              caja continua
columnas      cada 6 celdas en la franja de circulación, subiendo hasta la
              losa de arriba
losa          el canto del forjado, dos caras. Sin espesor un suelo no es una
              planta: es una alfombra, y tres alfombras apiladas no son un
              edificio
baranda       el borde abierto. Sin ella el nivel parece cortado, no terminado
```

### Lo que el navegador corrigió, y las pruebas no podían ver

Tres defectos salieron de mirar, no de medir — y los tres se convirtieron en
comprobación:

- **Cubiertas desiertas.** Todos los niveles compartían frente «para que la
  fachada no fuera una escalera», así que los pisos de tres salas arrastraban
  una losa tan larga como el de cinco. Ahora cada nivel mide lo suyo: un piso
  con menos salas es más corto, y eso es información verdadera.
- **Columnas que no sostenían nada.** El piso 1 tiene cinco salas y el 2 tiene
  tres: las columnas del tramo largo subían quince unidades hasta el aire y
  colgaban a la derecha. Ahora sólo las hay bajo la huella del nivel de arriba —
  y «el nivel de arriba» es el **inmediato de los declarados**, no `nivel + 1`:
  una empresa puede declarar el 1 y el 3.
- **Mástiles en el nivel aislado.** Sin el piso de arriba en la escena, las
  columnas se comían la sala. Cortadas a 2,5 siguen diciendo que el edificio
  continúa, que es lo único que tienen que decir.

### El nombre se mudó al canto de la losa

Con la separación medida, el muro de fondo **sólo se ve hasta 2,7 de sus 4
unidades** — y el cartel vive a 3,63. Un nombre que a veces se ve no es un
nombre. El cartel del muro sigue ahí para la sala mirada sola; en el edificio el
nombre va escrito en el canto del forjado, que además se lee de lejos, que es
como se mira un edificio.

### El zoom dejó de ser una constante

Medido: once salas en tres niveles ocupan **3.552 × 2.946 px de mundo** y entran
en una vista de 1.625 × 600 a escala **0,204**. El límite de la cámara era 0,4 y
su motivo sigue siendo bueno —en una SALA, por debajo, el mobiliario es una
mancha—. Ahora lo decide quien monta: el edificio pide 0,16, una sala no pide
nada.

---

## P1.3 · Navegación: edificio → piso → sala — 31/10/2026

Tres niveles de acercamiento, y el orden es el recorrido de quien busca algo. El
botón del edificio es siempre la vuelta atrás.

**Aislar un nivel lo BAJA al suelo.** Un piso flotando a dos pisos de altura no
dice nada, y encuadrar sobre el vacío deja las salas en una esquina. Es el mismo
compositor con `soloNivel`: tener una función para el edificio y otra para un
piso sería tener dos geometrías que se van separando sin que nadie lo note.

**Un nivel que no existe deja el edificio vacío, no el entero.** Caer a la vista
completa sería mostrar otra cosa que la pedida sin decirlo.

### Medido en el navegador (laboratorio aislado, 1.625 × 900)

```
El edificio          2.271 obj ·  97 fps   8 departamentos · 3 piso(s)
Piso 2 aislado         712 obj · 144 fps   3 salas · 3 de 11 puestos ocupados
NOC y Redes (sala)     293 obj · 144 fps   1 de 4 puestos · idéntica a antes
ficha desde el piso    «Agente de Ventas Virtual · Agente IA · Comercial y Marketing»
```

La sala sola **no cambió**: mismos 293 objetos que antes del edificio. La losa y
la baranda son dos campos de la planta que pone el compositor, justamente para
que mirar una sala siga siendo lo que era.

### Lo que NO se hizo en estas dos etapas

- **Las placas no se leen en la vista de conjunto.** A escala 0,2 un rótulo de
  13 px mide 2,6. Para el edificio hace falta texto en espacio de pantalla, que
  no escale con la cámara. Es trabajo de P2.
- **No hay puertas.** La circulación y las salas se tocan, pero el vano de paso
  entre el pasillo y cada sala no está dibujado.
- **Los subdepartamentos** siguen sin modelarse: no hay ninguno declarado.
- **La escena sigue oscura** en la vista de conjunto. Es palette, y entra en P2.

---

## P1.4 · La integración, medida dentro del CRM — 31/10/2026

Laboratorio aislado `oficinalab` (puertos 55500/55600/55700/55800, volúmenes
propios, variables inventadas, **sin leer el `.env` de la raíz**). Dos
organizaciones ficticias, autenticación real por el formulario.

| Qué | Resultado |
|---|---|
| La oficina dentro del CRM | `/centro-mando/v2` con la barra lateral, la organización de la sesión y el selector de 13 vistas |
| **Aislamiento multiempresa** | Con la sesión en la segunda organización: **«Sin estructura · 0 departamentos · 0 piso(s)»**, lienzo vacío y el selector **sin una sola sala ajena**. La organización no se filtra |
| Ciclo de vida | Salir y volver remonta con los **mismos 2.271 objetos**: sin fuga |
| Centro de Comando v1 | Sigue sirviendo, intacto |
| Evento real por E1 | Fila sembrada en `asistente.tool_calls` → la ficha muestra **CONSULTA · consultar_potencia_optica · 832f5c62**, y ese rastro **coincide con el cursor** `2220.832f5c62…` |
| Ejecución abierta | Fila en `asistente.ejecuciones` → «Un turno en curso», **separado** del historial (que decía 0) |
| Motor caído | «la última lectura falló» a los 23 s → **«el motor no responde» a los 41 s**, al cruzar el silencio de 40. Recuperado en **3 s** |

**Otra empresa, cero código.** Con una organización **declarada** en la base del
laboratorio —3 departamentos, 1 piso— la misma pantalla dibuja otro edificio y
rotula *«organización declarada por la empresa»*: 985 objetos a 144 fps. Es la
prueba de que esto es un producto y no una pantalla para una empresa. La base
quedó **restaurada** a la configuración del repositorio.

Una rareza conocida que el diseño aguanta: tras restaurar, la base **tiene** la
clave `organizacion` pero **vacía** —el editor escribe los defaults ausentes
(§13 D7)— y vacía significa «no declarada», así que vuelve a servirse la
estructura por defecto. Si «vacía» se hubiera interpretado como «declarada y sin
departamentos», el piloto se habría quedado sin edificio sin que nadie tocara
nada.

---

## P1.5 · La ficha dice QUÉ ocupa el puesto, y con qué verificarlo — 31/10/2026

La ficha decía «Agente IA» para cualquier cosa sentada. Ahora nombra el **tipo
de miembro**, que son tres cosas distintas y confundirlas es lo que hacía que la
oficina dibujara nueve empleados donde hay seis:

```
Agente IA ejecutable                        tiene instancia en el motor
Agente declarado, ausente del inventario    la configuración lo declara y no está
Puesto libre                                existe y nadie lo ocupa
```

Las **capacidades** no aparecen ahí a propósito: no ocupan un puesto, así que no
pueden ser el tipo de miembro de uno. Siguen en su bloque.

**Identificación verificable**, porque el nombre que se lee arriba es el *cargo*
y una empresa lo cambia cuando quiere:

```
Agente        supervisor_noc            el rol en la configuración
Puesto        operativo:principal       el identificador global
Departamento  NOC y Redes · Dirección de Operaciones
Piso          3
Atiende a     colaborador
```

**Advertencias.** Las incoherencias de la configuración se ven en la ficha y no
en una consola: una plantilla que el catálogo no tiene, un puesto declarado que
la plantilla no trae. No son fallos del flujo ni del motor, y callarlas dejaría
un hueco que nadie puede explicar.

**Lo que NO lleva, y por qué:** *acciones permitidas*. Esta pantalla no recibe
la lista blanca de herramientas del rol, y escribirla de memoria sería inventar
permisos — exactamente lo que la frontera existe para impedir. Servirla es una
decisión de qué dato llega al navegador, no un detalle de maquetado.

---

## P2 · El texto deja de encogerse con la cámara — 31/10/2026

Medido: la vista de conjunto entra a escala **0,204**, así que el nombre escrito
en el canto de la losa —13 px— mide **2,6** y no se lee. Agrandar la fuente no
sirve: en una sala quedaría gigante. Lo que hace falta es texto que **no
participe del zoom**.

Los rótulos de nivel se dibujan en el escenario, no en el mundo: se les aplica
la misma transformación al ancla y se deja el texto a tamaño de pantalla. Con
placa detrás, porque sobre una pantalla encendida el texto suelto se pierde.

```
P3 · Tecnología y dirección
P2 · Operación y clientes
P1 · Administración
```

**Lo que queda de P2:** la escena sigue oscura en la vista de conjunto, no hay
puertas dibujadas entre el pasillo y cada sala, y las placas de los puestos
siguen siendo texto del mundo — legibles en una sala y en un piso aislado, no en
el edificio entero. El mecanismo para arreglarlo ya está (`letreros`); lo que
falta es decidir cuántos mostrar sin llenar la vista de etiquetas.

---

## P3 · El constructor: la empresa se organiza sin tocar código — 31/10/2026

Hasta acá, dar de alta un ISP con otra estructura exigía editar `tenant_config`
a mano o cargar un YAML. `/settings/organizacion` crea, mueve, renombra y borra
pisos, departamentos y espacios.

```
GET  /configuracion/organizacion   la estructura + el catálogo de salas
                                   + los agentes que existen
PUT  /configuracion/organizacion   reemplaza el documento ENTERO
```

**Entero y no campo a campo.** Un organigrama no se edita así: mover un
departamento de piso, renombrarlo y quitarle un espacio son el mismo gesto para
quien lo hace, y guardarlos de a uno dejaría estados intermedios inválidos — un
departamento en un piso que todavía no existe, dos salas con el mismo
identificador.

**Ninguna regla de coherencia se escribió de nuevo.** Las once viven en
`schema.py::Organizacion` y el editor valida el `TenantConfig` completo antes de
escribir, por la misma puerta que el resto de `/settings`. Repetirlas en el
formulario sería tener dos verdades sobre lo mismo y descubrir el día que se
separen cuál manda. El mensaje del motor **viaja tal cual** a la pantalla: es el
que dice *qué* regla se rompió, y reemplazarlo por «revisá los datos» dejaría a
quien organiza la empresa adivinando.

El catálogo de salas viaja desde el motor como **lista de nombres**, no como
geometría: cuánto mide una sala sigue viviendo en el frontend. Es el mismo
reparto que `AreaDeTrabajo.icono`.

### El defecto que apareció al usarlo

Al agregar un departamento desde la pantalla, **Atención al Cliente perdió a su
segundo agente**: el pie de la oficina pasó de «6 de 37 puestos ocupados» a
**«5 de 40»**. Sin error, sin aviso, y sólo visible contando.

La causa: el formulario sólo pregunta por el puesto principal —declarar silla
por silla sería pedirle a quien organiza la empresa que sepa cómo se llaman los
puestos de una plantilla— y el documento se guarda entero, así que mandar sólo
el principal **borra los demás**.

Se arregló haciendo que las otras ocupaciones **viajen de ida y vuelta** en un
campo oculto. No se fusionan con lo que hay en la base: eso haría imposible
quitar una ocupación, que es justo lo que un editor tiene que poder hacer. Tres
pruebas nuevas, incluida la del campo oculto roto —un JSON inválido se descarta
entero, porque guardar media lista es peor que guardar ninguna.

**Medido después del arreglo:** «6 de 40 puestos ocupados», con
`soporte_tecnico_cliente` intacto.

### Medido en el navegador

```
la pantalla carga    3 pisos · 8 departamentos · 3 espacios, de la estructura
                     real, con el aviso «se está usando la estructura por
                     defecto: guardar acá la declara»
alta                 «Laboratorio de Fibra», piso 2, sala técnica
el edificio          9 departamentos · 3 piso(s) · organización declarada por
                     la empresa — 2.427 objetos a 99 fps, y la sala nueva en su
                     piso, con su botón en el selector
cero código          no se tocó una línea para que esa empresa exista
```

El laboratorio quedó **restaurado** a la configuración del repositorio.

### Lo que NO hace, y por qué

- **No mueve cosas arrastrando.** Es un formulario: filas con sus campos. Una
  distribución espacial editable con el ratón exige decidir antes qué es una
  posición válida —y hoy la posición de una sala la calcula el compositor del
  edificio a partir de su tamaño, no la elige nadie.
- **No edita los puestos de a uno**, por lo dicho arriba. El principal se
  elige; los demás se conservan.
- **No valida accesibilidad de rutas** porque en este modelo no hay rutas que
  validar: toda sala nace sobre la franja de circulación de su nivel y toda
  circulación toca el núcleo. Es una propiedad de cómo se compone el edificio,
  no algo que alguien pueda romper desde el formulario. El día que se puedan
  colocar salas libremente, hará falta.
- **La capacidad es la de la plantilla elegida** y se muestra al elegirla
  («Sala técnica (3 puestos)»). No hay un campo de capacidad propio: sería un
  número que puede contradecir a la geometría.

## Qué NO hacer

- **No construir los ocho departamentos a la vez.** Uno (NOC), de punta a punta,
  antes de invertir en escenarios y animaciones.
- **No modelar Odoo.** No existe en el repositorio; es desarrollo posterior.
- **No mover la organización a Django «de paso».** Si `tenant_config` sigue
  siendo el hogar o se migra a tablas es una decisión de la fase 0, con su
  medición.
- **No usar métricas simuladas como si fueran reales**, ni en capturas ni en
  demostraciones.
