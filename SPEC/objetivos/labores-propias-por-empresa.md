# Objetivo · Labores propias por empresa, cada una con sus asuntos

> Abierto el 20/10/2026. Estado: **abierto** — **Fase 1 desplegada** el 20/10
> (`b1c75518`); Fase 2 **ampliada** el 20/10, tarde (la plantilla de cada caso,
> D9–D13), sin empezar: espera la medición B1.

Pedido del usuario, textual: «coloca que se pueda crear labor y al momento de
crearla uno le asigna los asuntos que cubre esa labor».

Viene de esto: en Rapilink la cuadrilla de instalación **solo hace clientes
nuevos**; los traslados los hace la de correctivo, «pero un cambio de domicilio
no es un correctivo». El 20/10 se desplegó `a3c6749c` (renombrar las 3 labores
por empresa) y el usuario eligió ir más allá: labores propias.

## Qué significa terminado

Cada empresa crea, renombra y da de baja sus labores desde la interfaz, cada
una con los asuntos de WispHub que cubre, y el asunto del ticket decide a qué
labor —y por lo tanto a qué cuadrilla— va el trabajo, sin que se rompa nada de
lo que ya existe.

## Decisiones del usuario (20/10/2026) — no se reabren sin una medición nueva

| # | Decisión | Por qué (lo que se le mostró) |
|---|---|---|
| D1 | **Labores propias por empresa**, no «usar las 3 con otro nombre» ni «cuadrilla con varias labores por día» | Eligió entre las tres opciones; aceptó que una cuadrilla sigue saliendo con UNA labor por día y que más labores parten la demanda en más pedazos (más órdenes `sin_cuadrilla`) |
| D2 | **La labor manda en los asuntos; la plantilla solo afina dentro de su labor**: los asuntos de una plantilla tienen que estar dentro de los de su labor | Con dos fuentes que pueden contradecirse, la jornada se arma con una labor y la orden sale con otra: queda sin cuadrilla |
| D3 | **Orden para decidir la labor de un caso: medido > asunto > grupo** (y al final la clase de la visita) | Lo que el Supervisor mide (cliente nuevo, corte de red) no lo puede pisar un texto |
| D4 | **Dar de baja una labor en uso se bloquea y nombra qué la usa** | Nada queda sin cuadrilla sin que se note |
| D5 | **Las 3 de fábrica (instalacion, correctivo, trabajos) se renombran y se les cargan asuntos, pero no se dan de baja** | El clasificador medido y la tabla de fábrica emiten esos códigos |
| D6 | **Los asuntos se cargan como texto, uno por línea**, comparados sin mayúsculas, tildes ni espacios de más | Sin tocar `nucleo/` ni traer a la pantalla asuntos de la cola, que traen datos de prospectos |
| D7 | **Una plantilla sin labor no puede tener asuntos**; puede seguir existiendo sin clasificar | Consecuencia directa de D2 |
| D8 | **«Medido» incluye de qué cliente cuelga el ticket**: un ticket colgado del cliente de instalaciones del ISP es instalación, diga lo que diga el asunto | Es la corrección 1 del 19/10 (`supervisor-aplica-las-correcciones.md`, 220 de 220); no se reabre |

### Ampliación del 20/10/2026, tarde — la plantilla de cada caso

Pedido del usuario, textual: «que las plantillas se puedan crear y esté
amarrada a qué asunto para que el supervisor sepa qué plantilla usar en
despacho». Va **dentro de esta ficha** y no en una nueva (recomendación del
`orquestador`): son los mismos invariantes (D2, D6, D7) y los mismos archivos
(`plantillas.py::crear/publicar/_asuntos`, el editor). Dos fichas serían dos
dueños de `_asuntos`.

Lo que ya existía, medido: el editor tiene «Asuntos de WispHub que se
despachan con esta plantilla» y Despacho pre-elige con `plantilla_para_asunto`
(`ce3e9c34`, 19/10, **nunca auditado**). En producción, las 5 plantillas tienen
**0 asuntos** cargados. Al **crear** una plantilla no se pueden poner, y una
plantilla armada a mano no puede recibirlos por ningún camino (`publicar` da 409
`NO_EDITABLE`). Además, Despacho elige por asunto **sin mirar la labor
«Sugerido»**: es la contradicción por la que existe D2.

| # | Decisión | Por qué (lo que se le mostró) |
|---|---|---|
| D9 | **Quien usa la plantilla elegida es el Supervisor IA, cuando cree la orden solo** (Fase 2 de `supervisor-arma-la-jornada`). Esta ficha entrega **la elección**; crear la orden es de aquella | El usuario eligió esto entre: la persona que despacha, verla en Pendientes, o el Supervisor IA |
| D10 | **La plantilla la elige el código, nunca el modelo**, con una sola función: dentro de la labor del caso, la única plantilla activa de esa labor, o la que marca el asunto del ticket. **Si no hay una sola respuesta, no hay plantilla, y se dice por qué**: el Supervisor no crea esa orden y Despacho no pre-elige | CLAUDE.md §4 («el código calcula») y fail-closed. La usan el pre-llenado de Despacho y la Fase 2 de `supervisor-arma-la-jornada`; dos copias de la regla se desincronizan |
| D11 | **Los asuntos de una plantilla se marcan con casillas, de los de su labor**; con una sola plantilla en la labor no hace falta marcar nada | Elegido por el usuario: es D2 tal como está escrita («la plantilla solo afina») y elimina los errores de tipeo |
| D12 | **Las plantillas armadas a mano reciben asuntos y plazo sin tocar su formulario**, solo si la medición B1 muestra alguna **en uso**; si no, queda fuera y se dice | Elegido por el usuario («Sí, si hay alguna en uso»). **Resuelto el 21/10 con B1: queda fuera** (ver bitácora) |
| D13 | **El filtro de asuntos de Despacho marca «sin plantilla»** los asuntos de la cola que ninguna plantilla atiende | Elegido por el usuario: esa lista ya la ven los mismos roles, así que no reabre D6 |

Decisión tomada por defecto, revisable: una labor nueva entra con la prioridad y
el desempate más bajos, después de las 3 de fábrica (`operaciones/supervisor.py`
~1726, `campo/jornada_automatica.py::_DESEMPATE`). Si hiciera falta por empresa,
pasa a configuración (CLAUDE.md §3.3).

## El plan (arquitecto-dexter, 20/10/2026)

Cuatro fases, **cada una desplegable sola y segura**:

| Fase | Qué | Estimación |
|---|---|---|
| **F1** | `Labor(org, codigo, nombre, activa)` + `AsuntoDeLabor(org, labor, asunto, normalizado)` con `unique(org, normalizado)`, en `campo/labores.py`. Migración que **siembra** instalacion/correctivo/trabajos en **todas** las empresas (nombre desde `nombres_de_labor`; asuntos = unión de los de sus plantillas). `labores_de` lee la tabla. **Una sola** `labor_valida(org, codigo)` reemplaza las validaciones fijas. Se quita `choices=` sin cambiar valores. **Sin cambio de conducta** | ~1 día |
| **F2** | Pantalla de labores (crear, renombrar, dar de baja bloqueada en uso, asuntos). Regla D2 en **los 5 caminos** que escriben (`plantillas.crear`, `plantillas.publicar`, el de asuntos de una plantilla armada a mano, `TiposDeTrabajoView.patch`, edición de labor). Cuadrillas deja sus listas propias. **Ampliada (D9–D13)**: casillas de asuntos en la plantilla, la función única que elige la plantilla de un caso, Despacho la usa y marca «sin plantilla» | 1,5–2 días + ~1 día de la ampliación |
| **F3** | Una función que decide la labor de un caso (D3/D8), usada en la demanda de jornadas y en la sugerencia de Despacho. **Antes**, un informe de solo lectura de cuántos casos cambian de labor: el ciclo de la madrugada está ENCENDIDO | 1,5–2 días |
| **F4** | Borrar `ConfiguracionDeReparto.nombres_de_labor` y las tuplas `LABORES` | ~0,5 día |

Lo que el plan conserva a propósito: los valores guardados (`WorkType.labor`,
`JornadaDeCuadrilla.labor`, `Cuadrilla.labor_habitual`, `labor_por_grupo`) no
cambian, así que **no se migran datos de esas tablas**; las órdenes ya creadas
leen la labor viva de su plantilla (`campo/reparto.py:140-142`). Las constantes
de `clasificacion_de_trabajo` pasan a significar **clase** de visita, no labor
de la empresa; la traducción clase → grupo → labor usa `labor_por_grupo`.

## Criterios de aceptación

Comando + salida esperada. Las pruebas de backend corren **contra Postgres real
con un rol que el RLS ata** (receta en la memoria `pytest-backend-desde-worktree`:
Postgres efímero en la red `wt-cerebro-prod_default`, rol `crm_t`
`nosuperuser nobypassrls`, contenedor de un solo uso con el worktree montado).

### F1 — catálogo sin cambio de conducta

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 1.1 | `python -m pytest campo/tests/test_labores.py -q --no-cov` | `N passed`, 0 failed — salida pegada |
| 1.2 | Mutaciones: `labor_valida` que acepta cualquier texto, y que acepta una labor inactiva | las dos dejan 1.1 en rojo — salida pegada |
| 1.3 | La siembra cubre una empresa **sin** `ConfiguracionDeReparto` y **sin** plantillas | prueba dentro de 1.1 que lo afirma |
| 1.4 | `python manage.py makemigrations campo --check --dry-run` | `No changes detected in app 'campo'` |
| 1.5 | `grep -rnE "in dict\((WorkType\|JornadaDeCuadrilla)\.LABORES\)\|validas = dict\(" django-crm/backend --include=*.py \| grep -v tests/` | 0 líneas: `labor_valida` es la única validación |
| 1.6 | Regresión `python -m pytest campo operaciones cases -q --no-cov` | los mismos rojos que origin, medidos al empezar con la misma receta — lista pegada |
| 1.7 | Consulta de solo lectura **en producción** (la corre el usuario) antes del deploy de F1 | salida pegada: 0 choques de asuntos normalizados por empresa; plantillas sin labor con asuntos = 0 (si no, se resuelven antes). **Cómo**: `informe_de_labores` todavía no está en la imagen de producción, así que va como `python manage.py shell` en el backend desplegado con el mismo cálculo. **Nunca** levantar el backend del worktree contra la base de producción: su entrypoint corre `migrate` |
| 1.8 | `auditor-independiente` corrió sobre F1 | hallazgos resueltos o anotados con motivo en la bitácora |

### F2 — pantalla y regla D2

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 2.1 | `python -m pytest campo/tests/test_labores_pantalla.py -q --no-cov` | `N passed`, 0 failed |
| 2.2 | Mutaciones que mueren: dar de baja una labor en uso; dar de baja una de fábrica (D5); romper D2 en cada uno de los 3 caminos; plantilla sin labor con asuntos (D7) | cada una deja 2.1 en rojo |
| 2.3 | `npx vitest run "src/routes/(app)/supervisor-noc/cuadrillas"` (capa `+page.server.js` incluida) | `Tests N passed` |
| 2.4 | `npx svelte-check --output machine \| grep COMPLETED` desde el worktree sin contenedor | errores ≤ los de origin al empezar (161 el 20/10) |
| 2.5 | `npx vite build` | sin error |
| 2.6 | `revisor-de-pii` y `auditor-independiente` corrieron sobre F2 | hallazgos resueltos o anotados |
| 2.7 | **`AsuntoDeLabor` no queda como foto de la siembra** (auditor de F1): todo camino que cambia `WorkType.asuntos` o `WorkType.labor` mantiene D2 contra la tabla — también `bulk_create`/`update()`, que se saltean `save()` y por lo tanto `normalizado` | una prueba por camino; una mutación que deja de sincronizar en cada uno la deja en rojo |
| 2.8 | Crear una labor propia **siembra antes** las 3 de fábrica (auditor de F1): con filas parciales, `labor_valida` rechazaría `correctivo` | prueba: empresa sin filas → crear una propia → las 4 válidas |
| 2.9 | **`_filas` deja rastro cuando cae a las de fábrica** (guardia de F1): hoy se traga cualquier `DatabaseError` sin log, también un permiso denegado, y en F2 eso rechazaría labores propias en silencio | log por tipo (evento fijo, sin datos), y una prueba que lo afirma |

**Ampliación (D9–D13): la plantilla de cada caso.**

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 2.10 | `python -m pytest campo/tests/test_plantilla_del_caso.py -q --no-cov` (rol `crm_t`). Afirma: la única activa de la labor; con varias, la que marca el asunto (normalizado); con varias y ninguna marcada, **ninguna, con motivo**; nunca una de otra labor, ni una inactiva; una armada a mano con asuntos, sí | `N passed`, 0 failed — salida pegada |
| 2.11 | Mutaciones que mueren: elegir por asunto sin mirar la labor; devolver la primera cuando hay varias y ninguna marcada; aceptar una inactiva; comparar el asunto sin normalizar | cada una deja 2.10 en rojo — salida pegada |
| 2.12 | **Una sola función**: `grep -rn "plantilla_para_asunto(" django-crm/backend --include=*.py \| grep -v "tests/"` | solo la definición y la llamada desde la función única — salida pegada |
| 2.13 | Despacho usa la función: `python -m pytest campo/tests/test_despacho_pantalla.py campo/tests/test_ficha_despachable.py -q --no-cov`. La ficha devuelve la plantilla de la función y, si no hay, el **motivo**; el filtro de asuntos trae `sin_plantilla` por asunto (D13) | `passed`; una mutación que pre-elige de otra labor deja rojo |
| 2.14 | Casillas (D11): crear y publicar con un asunto que no es de su labor → 400 nombrando la labor; con asuntos y sin labor → 400 (D7). Pruebas en `test_labores_pantalla.py` | `passed`; mutación por camino (crear, publicar) muere |
| 2.15 | Plantillas armadas a mano (D12): **si B1 muestra alguna activa**, un camino para asuntos y plazo que no toca el esquema, con prueba de que la versión publicada no cambia; **si no**, la bitácora lo dice con la salida de B1 | prueba en verde, o la línea en la bitácora |
| 2.16 | Pantallas: `npx vitest run "src/routes/(app)/supervisor-noc/plantillas" "src/routes/(app)/supervisor-noc/despacho" src/lib/v2/despacho-sugerencias.test.js` (capa `+page.server.js` incluida); casillas en el editor, motivo y marca «sin plantilla» en Despacho | sin rojos nuevos frente a origin (memoria `vitest-rojos-previos`) — salida pegada |
| 2.17 | `grep -n "plantilla_del_caso" SPEC/objetivos/supervisor-arma-la-jornada.md` | 1 línea: su Fase 2 usa esta función |
| 2.18 | `auditor-independiente` sobre la ampliación **y sobre `ce3e9c34`**; `revisor-de-pii` sobre quién lee `WorkType.asuntos` (hoy `GET /campo/plantillas/` lo devuelve a cualquiera con `IsCampoAuthenticated`) | hallazgos resueltos o anotados con motivo |

### F3 — el asunto decide la labor

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 3.1 | Informe de solo lectura corrido por el usuario en producción **antes del push** | salida pegada: cuántos casos de Despacho cambian de labor, por par (actual → nueva), **sin asuntos crudos** |
| 3.2 | Pruebas de la función de decisión: el orden D3/D8 | `passed`; una mutación que invierte medido y asunto las deja en rojo |
| 3.3 | Las pruebas de las correcciones del 19/10 siguen verdes: `test_u2`, `test_u4`, `test_u5`, `test_h`, `test_h2` | salida pegada |
| 3.4 | `revisor-de-pii` (el `porque` no cita el asunto; el informe no lo imprime) y `auditor-independiente`; `auditor-de-frontera` **solo si** F3 reemplaza `clf.clasificar` en `operaciones/supervisor.py:440-455`, o si la Fase 3 de `supervisor-arma-la-jornada` ya está en origin | corrieron, o se dice por qué se saltea |
| 3.5 | Deploy de día; la primera madrugada (03:00 Bogotá) revisada | línea de la corrida de la madrugada pegada |

### F4 — limpieza

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| 4.1 | `grep -rnE "\bLABORES\b\|nombres_de_labor" django-crm/backend django-crm/frontend/src --include=*.py --include=*.js --include=*.svelte \| grep -v "migrations/\|tests/\|\.test\."` | 0 líneas |
| 4.2 | Antes del push, el usuario comprueba en producción (solo lectura) que **toda empresa con `nombres_de_labor` no vacío tiene sus filas en `campo_labor`** | salida pegada: 0 empresas sin filas. *Reescrito el 20/10 (auditor de F1)*: el criterio viejo pedía que `Labor.nombre` reflejara la columna, y desde F1 la columna queda congelada mientras `Labor.nombre` cambia — se contradecían. Lo que se pierde al borrar la columna es el nombre de una empresa que **nunca** se sembró, y eso es lo que se mide |
| 4.3 | 1.4 y 1.6 otra vez | igual que en F1 |

### Cierre

| # | Evidencia |
|---|---|
| C.1 | Las 4 fases desplegadas, cada una confirmada con `/_app/version.json` o el log que corresponda |
| C.2 | La sesión de `integrar-centro-mando` refleja el cierre en `SPEC/DEXTER_ESTADO_ACTUAL.md` (esta sesión entrega los hashes) |

## Restricciones

- **NO push** sin el permiso explícito del usuario: push a `fix/integracion-wisphub` es DEPLOY A PRODUCCIÓN.
- **NO escribir `tenant_config`**, ni cargar config, ni migrar contra producción.
- **NO correr los 56 casos dorados**; tampoco aplican (no se toca el motor).
- Stage por rutas explícitas: nunca `git add .` ni `git add -A`.
- **NO tocar `nucleo/`** ni el prompt del Supervisor (`operaciones/diagnostico_de_ticket.py`, `operaciones/cerebro.py`).
- **NO cambiar los valores guardados** de `WorkType.labor`, `JornadaDeCuadrilla.labor`, `Cuadrilla.labor_habitual`, `labor_por_grupo`.
- **NO renombrar** las claves `labor`, `labor_sugerida`, `labor_verificada` de la evidencia de las propuestas: son clase, están guardadas, y las leen `armado_de_jornadas.py:419` y el patrón `_VISITA`.
- **NO reabrir** la corrección 1 del 19/10 (D8).
- **NO conectar en paralelo** `clasificacion_de_trabajo._del_texto` / `mapa_de_texto`: se reutiliza o se quita; no queda un segundo camino asunto → labor.
- **`operaciones/armado_de_jornadas.py` tiene un solo dueño a la vez**: antes de F3, acordar con la sesión de `supervisor-arma-la-jornada` (su Fase 2 está pendiente).
- **F3 no se despliega sin el informe 3.1**, y se despliega de día.
- **F4 (`RemoveField`) solo después** de que F1–F3 lleven al menos una versión en producción.
- **Esta ficha NO crea órdenes** (D9): entrega la función que elige la plantilla. Crear la orden sola es la Fase 2 de `supervisor-arma-la-jornada`, con su `auditor-de-frontera`.
- **NO ofrecer en ninguna pantalla los asuntos de la cola** (D6 sigue en pie): las casillas salen de los asuntos de la labor, que escribe una persona.

## Qué NO hacer

| Fuera | Motivo |
|---|---|
| Elegir los asuntos del catálogo vivo de WispHub | D6: obliga a pasar por `nucleo/` (~1 día más); texto libre basta |
| Cuadrilla con varias labores por día | Descartado en D1 |
| Dar de baja las 3 de fábrica | D5 |
| Tocar la app móvil | No consume la labor (VERIFICADO por arquitecto: `trabajo_vista.dart:689-711` solo saca un icono del código de la plantilla) |
| Un campo `Labor.grupos` | `labor_por_grupo` ya es esa tabla |
| Otro normalizador de asuntos | Se usa `campo.plantillas.normalizar_asunto` |

## Agentes involucrados

Devuelto por el `orquestador` (20/10/2026).

| Agente | Para qué | Estado |
|---|---|---|
| `arquitecto-dexter` | Dónde vive cada pieza, plan por fases | **corrió** (20/10) |
| `auditor-independiente` | F1 (sin cambio de conducta, siembra completa, mutaciones), F2 («en uso», un 4.º camino que rompa D2, capa servidor, prioridad de una labor nueva), F3 (orden de fuentes, asunto contra la skill wisphub-api, labor dada de baja, `mapa_de_texto`, pruebas de las correcciones) | **corrió sobre F1** (20/10, ver bitácora); F2 y F3 pendientes |
| `revisor-de-pii` | F2 (de dónde salen los asuntos, qué queda en `Activity`/logs, qué nombra el bloqueo, **quién lee `WorkType.asuntos`**), F3 (el `porque` y el informe sin asuntos crudos) | pendiente |
| `auditor-de-frontera` | F3, solo si se cumple la condición de 3.4 | se decide en F3 |
| `guardia-de-release` | Antes de cada push: migración de datos al desplegar (rol, todas las empresas, `unique` contra datos reales), RemoveField en F4 | **corrió sobre F1** (20/10): listo para push, sin bloqueos; ver bitácora |
| `verificador-de-api` | — | **se saltea**: no hay llamada nueva a WispHub (D6) |
| `corredor-de-evaluacion` | — | **se saltea**: no cambia prompt, catálogo ni modelo del motor; el Supervisor no tiene set dorado. La medición de F3 es el informe 3.1, y se declara al entregar |
| `guardia-de-config` | — | **se saltea**: no toca `tenant_config` ni `tenants/*.config.yaml` |

## Bloqueos

- **Ninguna decisión de producto abierta** (D1–D8 cerradas el 20/10).
- **Antes del deploy de F1:** la consulta 1.7 en producción, que corre el usuario.
- **Antes de F3:** acordar con la sesión de `supervisor-arma-la-jornada` quién es dueño de `operaciones/armado_de_jornadas.py`; la recomendación del orquestador es que F3 entre antes que esa Fase 2.
- **B1 · antes de construir la ampliación** (la corre el usuario, solo lectura, backend de producción): por plantilla, labor, activa, editable, cantidad de asuntos y plazo; plantillas activas por labor; casos y asuntos distintos en Despacho (**solo números**, sin el texto de los asuntos). Decide D12 (¿hay alguna armada a mano activa?) y cuántas labores tienen más de una plantilla. Validado el 20/10 contra Postgres con datos dentro de una transacción revertida:

  ```
  python manage.py shell <<'EOF'
  from collections import Counter
  from campo.models import WorkType
  from campo import plantillas as P
  from common.models import Org
  from common.tasks import set_rls_context
  from operaciones import paso_a_despacho as pad
  for org in Org.objects.order_by("name"):
      tipos = list(WorkType.objects.filter(org=org).order_by("labor", "codigo"))
      set_rls_context(org.id)
      aprob = pad.aprobados_para_despacho(org)
      cola = pad.casos_en_despacho(org, aprob) if aprob else None
      if not tipos and cola is None:
          continue
      print("==", org.name)
      por_labor = Counter()
      for t in tipos:
          v = P.ultima_publicada(t)
          editable = bool(v) and P.leer_definicion(v.esquema)[0] is not None
          print("   plantilla", t.codigo, "| labor:", t.labor or "-", "| activa:", t.activo, "| editable:", editable, "| asuntos:", len(t.asuntos or []), "| plazo:", t.plazo_dias)
          if t.activo:
              por_labor[t.labor or "-"] += 1
      print("   activas por labor:", dict(por_labor))
      if cola is None:
          print("   Despacho: nadie aprobo ninguno")
      else:
          print("   Despacho: casos", cola.count(), "| asuntos distintos", cola.values("name").distinct().count())
  EOF
  ```
- **B3 · antes de desplegar F2:** revisar la primera madrugada después de F1 (21/10, 03:00 Bogotá). No frena el código.
- **B4 · coordinación:** avisarle a la sesión de `supervisor-arma-la-jornada` que su Fase 2 elige la plantilla con `plantilla_del_caso` (2.17), y que sin plantilla no se crea la orden.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 20/10/2026 | Ficha abierta. Plan de `arquitecto-dexter` y de `orquestador`. Decisiones D1–D8 del usuario | Todo F1 | `b37c0a5a` |
| 20/10/2026 | **F1 construida.** `campo/labores.py` (Labor, AsuntoDeLabor, `labores_de`, `labor_valida`, siembra), migración `0036` que siembra las 3 en toda empresa, `choices=` quitado sin cambiar valores, comando `informe_de_labores`. Medido: 1.1 (24 → 33 passed tras la auditoría), 1.2 (las 2 mutaciones de la ficha, 6 y 3 rojos), 1.3, 1.4 (`No changes detected`), 1.5 (0 líneas), 1.6 (mismos 106 rojos que origin; passed 4186 → 4202), informe antes/después en base local | 1.7 en producción; push | `a1c0f528` |
| 20/10/2026 | **Auditoría de F1 (`auditor-independiente`), ocho hallazgos.** Resueltos en código, cada uno con prueba y mutación que la prueba mata (9 de 9): (1) 4 de los 6 lugares que validan no tenían prueba con una labor propia → `test_g1`–`g3`; (3) `" correctivo "` pasaba la validación y quedaba guardado con espacios → comparación exacta, `test_g4`/`g5`; (4) `labor_nombre` de las jornadas ahora es el de la empresa (cambio querido) → afirmado en `test_g1`; (5) el admin de Django aceptaba cualquier labor → formulario con `labor_valida`, `test_g6`; (6) el PUT de nombres pasó a tocar solo los que venían → vuelve a reemplazar la tabla entera, `test_g7`; y el worker de Celery puede leer antes de que `migrate` cree la tabla → `_filas` cae a las de fábrica con savepoint, `test_g8`. **Anotados**: (2) `AsuntoDeLabor` es una foto de la siembra → criterio 2.7; filas parciales → 2.8; (7) 4.2 contradecía el diseño → reescrito; (8) el informe no está en producción antes del deploy → procedimiento en 1.7 | 1.6 otra vez sobre el arreglo; push | este commit |
| 20/10/2026 | **1.7 en producción** (la corrió el usuario, solo lectura, `manage.py shell` en el backend desplegado): 8 empresas, `TOTAL choques: 0 - plantillas sin labor con asuntos: 0`, ninguna con `nombres_de_labor` propios → la siembra les pone los de fábrica | push | — |
| 20/10/2026 | **`guardia-de-release` sobre F1: listo para push.** Medido: la siembra no viola ningún `unique` (repetidos en una plantilla, en dos labores, en dos empresas), ninguna tabla que lee tiene RLS (rol no superusuario siembra todas las empresas), la 0036 va y vuelve (`migrate campo 0035` y otra vez adelante), los `AlterField` son no-op, no hay otra 0036 en ninguna rama. **1.6 re-medido sobre el arreglo**, misma receta en las dos: origin 22 rojos / HEAD 22 rojos, los mismos (+25 passed = `test_labores`). Inferido (no medido en producción): `migrate` corre como `crm_migrator` y los default privileges dan acceso a `crm_user` a las tablas nuevas. Riesgos anotados: `_filas` sin log → 2.9; asuntos escritos desde el admin como texto o de más de 255 letras abortarían la siembra (la API no lo permite; chequeo de solo lectura antes del push); rollback = `migrate campo 0035` **antes** de revertir el código | push | `b1c75518` |
| 20/10/2026 | **F1 DESPLEGADA** (push `fbc02764..b1c75518`, 16:51 Bogotá, con permiso explícito del usuario). Antes del push, solo lectura en producción: 5 plantillas, `no_lista 0`, `max_largo 0` → **ninguna plantilla tiene asuntos cargados** (el «0 choques» de 1.7 era por eso). Después, en el backend desplegado: `[X] 0036_labores_por_empresa` e `informe_de_labores` → `tablas de labores: SI`, las 8 empresas con correctivo/instalacion/trabajos activas, de fábrica, 0 asuntos, `TOTAL choques: 0`. El informe corre como `crm_user` y no atrapa errores: los privilegios sobre las tablas nuevas quedan medidos, no inferidos. `/_app/version.json` no cambió (el deploy no tocó el frontend), así que la prueba del deploy es el backend | Revisar la primera madrugada (armado sin `errores`); F2 | `9a79581c` |
| 20/10/2026, tarde | **F2 ampliada (D9–D13)** con `/objetivo` y el `orquestador`: la plantilla de cada caso va dentro de esta ficha. El usuario eligió: la usa el Supervisor IA al crear la orden (D9), la elige una función única en código (D10), asuntos por casillas de su labor (D11), plantillas a mano sí si hay alguna activa (D12), marca «sin plantilla» en Despacho (D13). La medición B1 quedó en Bloqueos | B1; F2 entera | `610eb9c7` |
| 21/10/2026 | **B3 medido: la primera madrugada después de F1 terminó completa.** Solo lectura, en el backend de producción: `Rapilink \| activo: True \| ultima corrida: 2026-10-21`. `ultima_corrida` se escribe al final de `correr_para` (`campo/tasks.py`), después de armar las jornadas, proponer el reparto (que valida labores con `labor_valida`), revisar pendientes y avisar: si cualquiera de esos pasos hubiera lanzado una excepción, la fecha seguiría en la del 20. **No cubierto**: el conteo de la demanda de Despacho tiene su propio `try` y, si falla, solo deja un aviso `no se pudo contar la demanda de Despacho` en el log del worker, que no se miró | B1; F2 entera | `bf19b201` |
| 21/10/2026 | **B1 medido en producción** (solo lectura, por el usuario). **Rapilink**: 3 plantillas activas y editables, **una por labor** — `correctivo_fibra` (correctivo), `traslado_servicio` (**instalacion**), `retiro_equipos` (trabajos) —, 0 asuntos, sin plazo; Despacho con **65 casos y 33 asuntos distintos**. **Rapilink Telecomunicaciones**: 2 plantillas armadas a mano (`ftth_correctivo`, `ftth_instalacion`), activas, **sin labor**, y **nadie aprobó ningún caso** para Despacho. Consecuencias: (1) **D12 queda fuera**: las únicas armadas a mano son de una empresa sin Despacho, y sin labor no podrían tener asuntos igual (D7); 2.15 se cumple con esta línea. (2) Con una plantilla por labor, `plantilla_del_caso` resuelve **por la labor sola**: hoy los asuntos de plantilla no desempatan nada en Rapilink; lo harán el día que una labor tenga dos (p.ej. si `traslado_servicio` pasa a correctivo, como el usuario planteó el 20/10). (3) La labor instalacion de Rapilink **no tiene plantilla de instalación nueva** (el catálogo trae `instalacion_fibra`, no adoptada): su única plantilla es la de traslado | F2 entera | este commit |
