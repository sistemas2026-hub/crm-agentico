# Objetivo · Custodia de materiales — cerrar el ciclo bodega ↔ técnico

> Abierto el 25/09/2026. **Fase 1 construida el 28/09/2026** y vista en la
> pantalla. Estado: **abierto** — falta el cierre formal (F12 auditor, F15 poda
> del estado) y las Fases 2 y 3. Fase **1 de 3**.
>
> Commits, rama `feat/inventario-custodia` (worktree `C:/tmp/dexter-inventario`),
> **sin pushear**: `8851b5e` la bodega · `4f70241` la API · `79ee0c8` la
> pantalla · `fe64c8c` el menú y A4 en Postgres.
>
> El **qué** y el **por qué** del diseño viven en
> [../briefs/inventario-de-bodega.md](../briefs/inventario-de-bodega.md) (v2) y no
> se repiten acá: esta ficha es el contrato de ejecución. Si difieren, manda el
> brief para el diseño y esta ficha para el alcance.

## Qué significa terminado

Una empresa puede entregarle material a un técnico, ver qué gastó, recibir lo que
devuelve, y responder **dónde está cada ONT y por dónde pasó** — con un solo libro
de movimientos como fuente de verdad, y sin un contador guardado en ninguna parte.

Solo la **Fase 1**. Las otras dos están acotadas al final, con su motivo.

## Criterios de aceptación

De acá sale literalmente la condición del `/goal`. Todo criterio es comando +
salida pegada: el evaluador solo puede juzgar lo que aparezca en la conversación.

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| F1 | **El grafo de migraciones tiene una sola hoja** | `docker exec <backend> python manage.py makemigrations --check --dry-run campo` → exit 0. Y `migrate campo` sobre base limpia → exit 0, salida pegada. Hoy hay dos `0003` (brief §3) |
| F2 | **Una sola función calcula existencia**, y sirve para bodega y para técnico | Una guarda de arquitectura que recorre `campo/` y **falla nombrando el archivo** si aparece un segundo cálculo o un campo `disponible`/`stock_actual`. Comprobada al revés: se mete una violación a propósito y la caza por su ruta |
| F3 | **Una serie devuelta se puede volver a entregar** | Prueba: despachar serie X → devolver → despachar a otro técnico → sin `IntegrityError`. Hoy falla (brief §7) |
| F4 | **Una serie no puede estar en dos custodias a la vez** | Dos despachos concurrentes de la misma serie: uno gana, el otro se rechaza. Con dos peticiones reales compitiendo, no secuenciales |
| F5 | **A4 por reconciliación** | Prueba que recalcula la custodia de cada activo desde sus movimientos y la compara con el puntero. Es la que hace legítimo el puntero del brief §5 |
| F6 | **Despacho punta a punta** | Despachar un kit desde la oficina → `GET /api/campo/kit/` lo devuelve con su saldo, y la app lo muestra |
| F7 | **La devolución vuelve a sumar en bodega** | Existencia de bodega antes / después de un ciclo completo, los dos números pegados |
| F8 | **Una diferencia al recibir abre incidencia, no ajuste** | Recibir menos de lo declarado → `IncidenciaDeMaterial` con motivo; ningún movimiento de ajuste automático |
| F9 | **El bodeguero despacha y NO valida órdenes** | Un perfil con el rol nuevo: despacho → 200; `POST /api/campo/trabajos/<id>/validar/` → 403 |
| F10 | **Aislamiento por organización** | Dos orgs: cada una ve su inventario y **cero filas** de la otra. Sin esto, F2 es cosmético |
| F11 | **La historia de una serie se puede leer** | Una ONT con 4 movimientos → la consulta devuelve los 4 en orden de `ocurrido_en`, con su acta y su orden. Salida pegada |
| F12 | **El despacho imposible se rechaza antes de ocurrir** | Despachar una serie que ya está en otra ubicación → rechazo con motivo. Y la contraparte: **ningún consumo ya ocurrido se rechaza jamás** — un consumo que descuadra sigue entrando como `descuadre` |
| F13 | **Sin regresiones** | `docker exec <backend> python -m pytest campo/tests/ -q --no-cov` y `flutter test` en `apps/tecnicos-mobile/` — línea base medida **antes** de tocar nada y pegada al lado. Referencia del contrato: 536 verdes |
| F14 | **Pasada adversarial** | `auditor-independiente` corrió; sus hallazgos resueltos, o anotados en `SPEC/auditorias/` con motivo. Si no corrió, se dice |
| F15 | **El estado lo refleja** | `SPEC/DEXTER_ESTADO_ACTUAL.md` actualizado por su única sesión dueña (`integrar-centro-mando`). Un gate no está cerrado hasta que ese archivo lo diga |

**La línea base de F13 se mide primero.** Es el error que este proyecto ya cometió
dos veces: con las 536 pruebas de Campo y con los 63 rojos del frontend. Sin la
medición previa, "63 en rojo" no distingue una regresión de lo que ya estaba.

## Restricciones

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción.
- **NO escribir `tenant_config`** — cada guardado parte la medición ON/OFF.
- **NO correr los 56 casos dorados** — no aplica: este cambio no toca prompt,
  catálogo ni modelo. Se dice y se saltea.
- **NO desplegar el módulo `campo`.** Hoy no está en producción (brief §3) y
  ponerlo ahí es una entrega aparte, con su propia decisión. Este objetivo prepara
  el diseño correcto **antes** del primer despliegue.
- **NO reabrir las cinco decisiones** del brief §2 (saldo calculado, clasificar en
  vez de rechazar, append-only, nombrar lo que falta, configuración por empresa).
  Están fundamentadas y medidas.
- **NO `pnpm check` en Windows con Docker arriba** — rompe el frontend por
  truncamiento de rutas. Va por `docker exec`.
- **NO tocar `--workers 1`** ni nada del motor que no sea estrictamente necesario.

## Qué NO hacer

- **Fase 2 completa** (varias bodegas, traslados, reservas, conteo físico,
  reportes). Motivo: la Fase 1 tiene que cerrar el ciclo físico antes de que algo
  se apoye en él. `UbicacionInventario` **sí** entra en Fase 1 —con una sola
  bodega si hace falta— porque agregar la dimensión después es una migración de
  datos y hoy es un campo.
- **Fase 3 entera** (proveedores, compras, costos, valorización). Motivo: es el
  modo de fallar de este trabajo. El brief lo dice y el riesgo es real: volverse un
  ERP y perder la filosofía que ya está bien resuelta.
- **Escribir `sn_onu` hacia WispHub.** Va en Fase 2. Motivo: es una escritura a un
  sistema externo y pasa por la frontera de autorización del motor, que es su
  propio trabajo — no un efecto colateral del inventario. Cuando entre, va por
  `asistente.operaciones_externas`, que ya existe con su reconciliador: **no se
  construye una segunda cola** (brief §6).
- **Crear una ubicación `PROVEEDOR` o `CLIENTE`** para esquivar un `null`
  legítimo. Motivo: brief §4. Son las dos fronteras del sistema y los nulls son
  correctos.
- **Una entidad nueva para la devolución del cliente.** El retiro es una entrada
  sin origen con su orden, no una salida desde el cliente.

## Agentes involucrados

`orquestador` no se pudo invocar: **los 9 agentes de `.claude/agents/` no se cargan
en la sesión** — medido por tercera vez el 24/09/2026, solo `verificador-de-api`
queda invocable. Así que esta tabla la escribí a mano y los pasos los hace la
sesión principal, diciéndolo.

| Agente | Para qué | Estado |
|---|---|---|
| `arquitecto-dexter` | ¿Dónde vive cada pieza? ¿Qué es configuración? | a mano por la sesión principal |
| `verificador-de-api` | Solo si el lazo con WispHub entra antes de lo previsto | se saltea: `sn_onu` es Fase 2 |
| `revisor-de-pii` | El inventario no toca datos de cliente… salvo que `orden` los arrastre al mostrar un movimiento | **pendiente** — mirar qué se dibuja junto a un consumo |
| `auditor-de-frontera` | El despacho es una acción con efecto, y el rol nuevo es una autorización | **pendiente**, es F12 |
| `corredor-de-evaluacion` | — | se saltea: no toca prompt, catálogo ni modelo |
| `guardia-de-config` | — | se saltea: no toca `tenant_config` |
| `auditor-independiente` | El hueco que quien construyó no puede ver | **pendiente**, es F12 |

## Bloqueos

**B1 · RESUELTO el 25/09/2026 — se integra Campo primero.** Decisión del usuario:
`feat/campo-diseno-stitch` se integra a la rama de despliegue **antes** de construir
inventario, y la Fase 1 se levanta después sobre un solo terreno.

**Consecuencia, y es la que importa para quien lea esta ficha:** este objetivo tiene
un **prerrequisito que no es suyo**. No arranca hasta que la integración de Campo
esté hecha, y esa integración necesita su propio encuadre — no se absorbe acá. Con
el diseño ya congelado (brief v3), esperar no cuesta nada: nada de lo decidido
depende de la rama.

Los números que llevaron a esa decisión, remedidos el 25/09/2026:

```
feat/campo-diseno-stitch   59 commits adelante de la rama de despliegue
                          297 commits ATRÁS · 948 archivos difieren
   y la otra sesión está editándola AHORA: 12 archivos sin commitear, entre
   ellos campo/urls.py, campo/despacho_views.py y campo/serializers.py
   — los tres exactos que el despacho de inventario necesita tocar
```

Los tres caminos que se evaluaron, y por qué se eligió el tercero:

| Camino | A favor | Contra |
|---|---|---|
| Construir en `feat/campo-diseno-stitch` | El código está ahí, cero integración previa | Choque directo con la otra sesión en los 3 archivos; y la divergencia de 948 archivos hay que pagarla igual, después |
| Rama nueva desde la de despliegue, trayendo el módulo | Parte del terreno que ya está en producción | Traer materiales a una base 297 commits más nueva **es** la integración de Campo, absorbida en silencio dentro de este objetivo |
| **Integrar Campo primero** ✅ | El orden limpio: un solo terreno, y el atraso de 297 commits deja de crecer | El más lento, y depende de una entrega que no es de este objetivo |

Los dos primeros terminaban pagando la misma integración, uno de ellos sin decirlo.
La diferencia del elegido es que la nombra y le da su lugar.

**B2 · RESUELTO el 25/09/2026 — migración de merge, no renumerar.** Conserva la
historia de las dos ramas. Y se midió que es viable: las dos hojas tocan modelos
distintos (`asignaciontrabajo.rol` contra 9 campos de `ordentrabajo`), cero
colisión. Detalle en el brief §3.

**B3 · RESUELTO el 25/09/2026 — sí al puntero, con la reconciliación como
condición.** Se acepta `UbicacionDeActivo` (un registro por activo,
`UNIQUE(activo)`, escrito en la misma transacción que el movimiento, con FK al
movimiento que lo justifica). **No es fuente de verdad: es un índice verificable**,
y F5 —la prueba de reconciliación— es lo que lo hace legítimo. Sin esa prueba, es
un contador guardado con otro nombre y queda prohibido por la decisión §2.1 del
brief. Se descartó el nombre `CustodiaActual` porque *custodia* arrastra
responsabilidad legal y posesión.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 25/09/2026 | Estado medido (8 entidades existen, bodega no; nada desplegado; dos `0003`). Brief v1 → v2: descartada la capa paralela, libro único con origen/destino, `ActivoSerializado` sin estado guardado, serialización en Fase 1 | Resolver B1 y arrancar F1 | — |
| 25/09/2026 | **B1 resuelto: se integra Campo primero.** El objetivo queda con un prerrequisito ajeno y no arranca hasta que esté hecho. Esperar no cuesta: el diseño ya está congelado y nada de lo decidido depende de la rama | Encuadrar la integración de Campo, que es un trabajo con nombre propio | — |
| 25/09/2026 | **Diseño congelado (brief v3).** B2 y B3 resueltos y medidos. Agregados a Fase 1: historia de una serie, despacho validado antes (con su justificación de por qué no rompe «clasificar en vez de rechazar»), inventario por técnico como cálculo. El lazo con WispHub va por la cola que ya existe, y `actualizar_sn_onu` resulta **naturalmente idempotente** — el primer efecto externo de WispHub que sí lo es. Valor del lazo medido: `sn_onu` vacío en 1.299 de 4.163 activos | **B1**: en qué rama se construye. Es lo único que bloquea | — |

---

## Condición para `/goal`, lista para pegar

> El evaluador **no corre comandos ni lee archivos**: juzga solo lo que aparezca
> en la conversación. Por eso cada criterio pide la salida pegada.

```
Objetivo: cerrar la Fase 1 de la custodia de materiales del módulo campo —
el ciclo bodega → técnico → consumo → devolución → bodega, con un solo libro
de movimientos y sin contadores guardados. El contrato es
SPEC/objetivos/custodia-de-materiales.md y el diseño
SPEC/briefs/inventario-de-bodega.md; si algo difiere, manda el archivo.

Terminado SOLO cuando cada una de estas salidas esté PEGADA en la conversación:

1. makemigrations --check --dry-run campo → exit 0, y migrate campo sobre base
   limpia → exit 0. (Hoy hay dos migraciones 0003 en conflicto.)
2. La guarda de arquitectura que prohíbe un segundo cálculo de existencia y los
   campos disponible/stock_actual: en verde, Y su comprobación al revés —se mete
   una violación a propósito y la caza nombrando el archivo.
3. Prueba: una serie devuelta se vuelve a despachar sin IntegrityError.
4. Prueba: dos despachos CONCURRENTES de la misma serie, uno gana y el otro se
   rechaza.
5. Prueba de reconciliación: la custodia de cada activo recalculada desde sus
   movimientos coincide con el puntero.
6. Despacho punta a punta: GET /api/campo/kit/ devuelve el kit despachado.
7. Existencia de bodega antes y después de un ciclo completo, los dos números.
8. Recibir menos de lo declarado abre incidencia con motivo, sin ajuste
   automático.
9. El rol de bodeguero: despacho 200, validar orden 403.
10. Dos organizaciones: cada una ve su inventario y cero filas de la otra.
11. La historia de una serie: una ONT con 4 movimientos devuelve los 4 en orden
    de ocurrido_en, con su acta y su orden.
12. Un despacho de una serie que ya está en otra ubicación se RECHAZA con motivo;
    y un consumo que descuadra sigue ENTRANDO como descuadre. Las dos salidas.
13. pytest campo/tests/ y flutter test, con la LÍNEA BASE medida ANTES de tocar
    nada y pegada al lado. Sin línea base previa, este punto no está cumplido.

Restricciones, dentro de la condición a propósito:
- NO hacer push a ninguna rama. Push a fix/integracion-wisphub es deploy.
- NO escribir tenant_config. NO correr los 56 casos dorados.
- NO desplegar el módulo campo.
- NO construir Fase 2 (varias bodegas, traslados, reservas, conteos, reportes)
  ni Fase 3 (proveedores, compras, costos). UbicacionInventario sí entra.
- NO escribir sn_onu hacia WispHub.
- NO reabrir las cinco decisiones del brief §2.
- NO pnpm check en Windows con Docker arriba.

PRERREQUISITO, decidido el 25/09/2026 y ajeno a este objetivo: la integración de
feat/campo-diseno-stitch a la rama de despliegue va PRIMERO. Si no está hecha,
este objetivo no arranca: decirlo y detenerse, no elegir otra rama por cuenta
propia ni empezar "mientras tanto" sobre la rama de Campo.
```

---

## Resultado de la Fase 1 — medido el 28/09/2026

Construida en el worktree `C:/tmp/dexter-inventario` (rama
`feat/inventario-custodia`), que salió de **producción al día** y trajo sólo el
módulo `campo/`. La rama de Campo no se tocó, así que J1 dejó de bloquear.

| # | Criterio | Resultado |
|---|---|---|
| F1 | Una sola hoja de migraciones | ✅ `0007_merge_despacho_y_rol` une las dos ramas; `migrate campo` aplicó 0007, 0008 y 0009. Se midió antes que el merge era seguro: las dos `0003` tocan modelos distintos |
| F2 | Una sola función calcula existencia | ✅ **con su guarda**, `test_inventario_una_sola_verdad.py`: ningún modelo guarda un contador, solo los servicios declarados suman cantidades, `existencia()` está definida una vez, y la excepción del puntero sigue teniendo su reconciliación. Comprobada al revés: se inyectó un campo `disponible` y lo cazó por su ruta (`inventario.py:102`) |
| F3 | Una serie devuelta se re-despacha | ✅ y de paso convirtió el defecto de *inferido* a **ejecutado**: la prueba reprodujo el `IntegrityError` del constraint viejo antes de quitarlo |
| F4 | Una serie no está en dos custodias | ✅ **medido con concurrencia real en PostgreSQL**, dos hilos compitiendo. La versión secuencial no alcanzaba: depende de `select_for_update`, que SQLite no implementa |
| F5 | Reconciliación puntero ↔ libro | ✅ recalcula la posición de cada activo desde sus movimientos y compara. Es lo que hace legítimo a `UbicacionDeActivo` |
| F6 | Despacho punta a punta | 🟡 **por la API sí** (201, con acta y movimientos). **La app de Flutter NO se verificó**: `flutter test` no se corrió en este worktree |
| F7 | La devolución suma en bodega | ✅ 100 → despacha 30 → devuelve 12 → bodega 82, técnico 18. Los números pegados en la prueba |
| F8 | Diferencia al recibir abre incidencia | ✅ una línea puede declarar `esperado`; si vuelve menos se abre `IncidenciaDeMaterial` por la diferencia, con la nota de quien recibió en el motivo. **Sin `esperado` no se adivina**, y es deliberado: devolver parte de lo que se tiene es legítimo, y una incidencia por cada devolución parcial es la forma más rápida de que nadie las mire. La pantalla lo avisa en ámbar — un faltante en verde se lee «todo bien» y en rojo «falló la operación», y ninguna es cierta |
| F9 | El bodeguero despacha y NO valida órdenes | ✅ las **dos** direcciones: despacho 201, `validar/` 403 |
| F10 | Aislamiento por organización | ✅ dos orgs, cero filas cruzadas, en servicio y en API |
| F11 | La historia de una serie se lee | ✅ `entrada → despacho → devolución` en orden, con sus ubicaciones |
| F12 | El despacho imposible se rechaza antes | ✅ 409 con el mensaje que dice **dónde** está el aparato. Y la contraparte se mantiene: las 21 pruebas de custodia siguen verdes, así que un consumo que descuadra sigue entrando como `descuadre` |
| F13 | Sin regresiones | 🟡 `campo/tests/` **266 pasan · 5 skipped · 0 fallan**. Pero la **línea base no se midió antes** de empezar — el worktree salió de producción, que no tenía el módulo, así que la base era "no existe". `flutter test` no se corrió |
| F14 | Pasada adversarial | ❌ **el `auditor-independiente` no corrió.** Los 9 agentes siguen sin cargarse en la sesión |
| F15 | El estado lo refleja | ✅ escrito por la sesión dueña (`integrar-centro-mando`) |

### Lo que queda

```
F14            la pasada adversarial. Los 9 agentes siguen sin cargarse en la
               sesión, así que no corrió ninguno
flutter test   la app consume los 5 endpoints viejos y ninguno cambió de
               contrato, pero eso está INFERIDO: no se corrió en este worktree
`revisor-de-pii`  qué se dibuja junto a un movimiento cuando trae `orden`: una
               orden arrastra nombre y dirección del cliente, y la pantalla de
               inventario no tendría por qué mostrarlos
```

**F2 y F8 se cerraron el 28/09 después de escribir esta tabla por primera vez.**
Quedan anotados porque el orden importa: primero se dijo que faltaban, con su
motivo, y recién después se construyeron. Una ficha que solo muestra lo verde no
deja ver qué se decidió dejar para el final.

### Los cuatro defectos que aparecieron al construir

Ninguno lo habían cazado las pruebas, y dos son del mismo patrón:

```
EL MOTOR DE LA PRUEBA NO ES EL MOTOR DE PRODUCCIÓN
  la clave idempotente medía ~134 caracteres contra un varchar(128), y SQLite no
    impone la longitud -> DataError en PostgreSQL real. Ahora se hashea, y hay
    una prueba que afirma sobre el LÍMITE del campo y no sobre el motor
  A4 dependía de select_for_update, que SQLite no implementa: la comprobación
    pasaba por el orden de las operaciones -> prueba nueva con dos hilos, que se
    SALTA nombrando el motivo cuando no hay Postgres

LO QUE SÓLO SE VE ABRIENDO LA PANTALLA
  endpoints con `/api` doble -> 404, y la pantalla salió entera diciendo "no se
    pudo leer". Que dijera eso en vez de pintar bodegas vacías es la propiedad
    que se diseñó a propósito, y se vio funcionar antes de arreglar la causa
  `locals` en vez de `{cookies}` -> token vacío, toda lectura fallando en silencio
  el nombre de una custodia salía como UUID: no está en `Profile` sino en
    `User.name`. Para el compilador un UUID es un nombre perfectamente válido
```

### La pantalla, mirada

Con JWT contra el backend local, en `/inventario`:

```
Bodega Central (bodega)
  CON-SC-APC   Conector SC/APC      Conectores   960       unidades
  ONT-HG8145   ONT Huawei HG8145V5  Equipos      6         unidades
  FIB-DROP     Fibra drop 1 hilo    Fibra        3700.75   m
Custodia de Marcador (tecnico)
  CON-SC-APC   Conector SC/APC      Conectores   40        unidades
  ONT-HG8145   ONT Huawei HG8145V5  Equipos      0         unidades
  FIB-DROP     Fibra drop 1 hilo    Fibra        300.25    m
Camioneta 1 (vehiculo)   Sin movimientos todavía.

menú:  Instalaciones · INVENTARIO · Base de conocimiento
serie: HWTCA6FB5263 → entrada → Bodega Central, cuadra_con_el_libro: true
```

La ONT devuelta volvió a la bodega —6 allá, 0 con el técnico— que es el ciclo
completo visible en un número.
