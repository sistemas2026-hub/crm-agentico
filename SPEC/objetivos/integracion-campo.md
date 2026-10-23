# Objetivo · Integrar Dexter Campo sin perder garantías

> Abierto el 25/09/2026. Estado: **abierto**, no arrancado.
>
> Es el **prerrequisito** de [custodia-de-materiales.md](custodia-de-materiales.md),
> y no se absorbe en él: se decidió el 25/09/2026 nombrarlo y hacerlo primero,
> porque los dos caminos alternativos terminaban pagando esta misma integración y
> uno de ellos sin decirlo.
>
> **Este no es un trabajo de código: es un trabajo de decisiones archivo por
> archivo.** Lo que lo hace peligroso ya pasó una vez (§2).

## Qué significa terminado

`feat/campo-diseno-stitch` queda integrada a la rama de despliegue **sin que
ninguna garantía de producción haya retrocedido**, y las guardas que estaban en
verde antes siguen en verde después — medido, no supuesto.

## 1 · Estado inicial, medido el 25/09/2026

```
rama origen    feat/campo-diseno-stitch   (worktree C:/wisphub/_wt_campo)
rama destino   fix/integracion-wisphub    (push ahí ES deploy)

     59 commits adelante del destino
    297 commits ATRÁS
    948 archivos difieren
```

Y el diff se parte en tres conjuntos que **no tienen el mismo riesgo ni el mismo
tratamiento**:

| Conjunto | Cuántos | Qué es |
|---|---|---|
| `D` | **548** | Existen en el destino y **faltan** en Campo. No los borró: nacieron en los 297 commits que le faltan |
| `A` | **210** | Existen solo en Campo. Lo que la integración viene a traer |
| `M` | **190** | Existen en los dos y difieren. **Acá git va a pedir decisiones, y acá está el riesgo real** |

### La corrección de método que ordena todo lo demás

**La dirección del merge decide qué conjunto importa.** Integrando Campo *hacia* la
rama de despliegue:

- Los **548 `D` no son un riesgo del merge**: el destino los tiene y git no borra lo
  que el destino tiene. Se vuelven un riesgo **solo** si alguien toma la rama de
  Campo como base, o resuelve un conflicto tomando «todo de Campo».
- Los **190 `M` son el riesgo real.** Cada uno es una decisión, y una decisión mal
  tomada revierte trabajo nuevo sin que nada falle.
- Los **210 `A` son el riesgo simétrico**: entra código que nadie del lado de
  producción revisó nunca.

Confundir los 548 con el peligro lleva a blindar lo que no hace falta y a pasar por
arriba los 190 que sí.

## 2 · El antecedente: ya pasó, y hay un commit que lo prueba

`452e6bb` (24/09/2026), en esta misma rama:

> *"Esta rama ya no puede borrarle a produccion la frontera de autorizacion. Esta
> copia esta 283 commits atras de la que despliega, y su tenant config no tiene NI
> UNO de los campos de la frontera: `irreversible`, `nivel_autonomia`,
> `exige_declaracion`, `aprobacion`. Cargarlo sobre la base habria dejado al motor
> desplegado ejecutando acciones irreversibles sin la puerta que hoy las frena.
> **Nada lo impedia de verdad.**"*

Tres cosas que hay que leer de ahí, y ninguna es opcional:

1. **El daño no venía de un merge de código: venía de cargar la config de una rama
   atrasada.** `tenants/rapilink.config.yaml` está entre los 190 `M`.
2. **La guarda que lo frena vive en `cli/cargar_config.py`** — y ese archivo también
   está entre los 190 `M`. Una resolución que tome el lado de Campo **desarma la
   guarda que protege de la rama de Campo**.
3. El propio commit declara el resto pendiente: *"No arregla el atraso de la rama —
   eso es su propio trabajo, 12 archivos en conflicto."* **Este objetivo es ese
   trabajo.**

## 3 · Inventario de archivos, clasificado

### 🔴 ROJO — nunca se acepta automáticamente, y el lado del destino gana salvo prueba en contrario

Lo que está en `M` y toca una garantía, una identidad o la autoridad del proyecto:

```
tenants/rapilink.config.yaml         el archivo del incidente de §2. La base es la
                                     fuente de verdad, no este archivo
cli/cargar_config.py                 la guarda que frena ese incidente
nucleo/seguridad/verificacion.py     el ÚNICO de seguridad presente en las dos ramas
nucleo/observabilidad/registro.py    la garantía de que no salen datos de cliente
nucleo/seguimiento/forzado.py        lo que obliga a escalar
nucleo/seguimiento/escalamiento.py
nucleo/config/schema.py              donde viven los campos de la frontera
nucleo/config/editor.py
django-crm/backend/common/rls/       aislamiento por organización
django-crm/backend/common/scopes.py
django-crm/backend/common/audit_log.py
django-crm/backend/crm/settings.py
CLAUDE.md · PRD.md · ARQUITECTURA.md · DESPLIEGUE.md   ← autoridad, §1 de CLAUDE.md
```

Y el conjunto `D` de seguridad, que **no debe desaparecer bajo ninguna resolución**:

```
nucleo/seguridad/    frontera · aprobacion · autonomia2 · autorizacion ·
                     idempotencia · interruptor · techo        (7 archivos)
nucleo/relevo/       los 12, incluido reconciliador y su worker
supabase/            17 migraciones, entre ellas las de operaciones_externas,
                     interruptor_autonomia, techo_autonomia y aprobacion_vinculante
django-crm/backend/operaciones/permissions.py
```

### 🟡 AMARILLO — revisión manual, uno por uno

```
nucleo/canales/api.py          9.091 líneas    ┐
nucleo/persistencia/db.py      4.625 líneas    │ los CUATRO monolitos que
nucleo/modelo/motor.py         4.153 líneas    │ CLAUDE.md §2 marca como
nucleo/config/schema.py        3.577 líneas    ┘ superficie de conflicto alta
django-crm/backend/campo/      models · views · urls · serializers · admin ·
                               services/despacho · services/validador
django-crm/backend/campo/migrations/    el conflicto de las dos 0003
django-crm/backend/common/     models · utils · urls · views/user_views · packs/loader
evaluacion/rapilink.casos.yaml
~20 pruebas de tests/          las que difieren en los dos lados
```

Los cuatro monolitos concentran el riesgo por construcción: es la deuda **D3** del
proyecto, cobrándose acá.

### 🟢 VERDE — se integran sin revisión individual, con las guardas al final

```
apps/tecnicos-mobile/          190 archivos, casi todos A (la app y sus pruebas)
django-crm/frontend/           240, mayormente componentes y estilos
documentos/                    48 (avatares, prototipos del centro de mando)
SPEC/auditorias/               22, historia con evidencia
```

Verde **no** quiere decir que no puedan romper: quiere decir que un error ahí se ve
en las guardas y no borra una garantía en silencio.

## 4 · Reglas de integración

```
NO hacer
  merge ciego, ni resolver conflictos "por el último commit"
  tomar el lado de Campo en bloque en NINGÚN archivo rojo
  medir qué está integrado con `merge-base --is-ancestor`
  cargar tenants/rapilink.config.yaml de esta rama a ninguna base
  `git add .`, `git add -A`, `commit -a`, ni `git add SPEC/`
  push a la rama de despliegue: eso es deploy, y no es parte de este objetivo

SÍ hacer
  medir por CONTENIDO: `git patch-id --stable`
  antes de resolver un rojo, mirar en qué dirección va: si el lado de Campo es
    más viejo, el destino gana y se anota
  línea base de TODAS las guardas ANTES de tocar nada, pegada
  los 548 `D` se verifican al final: ninguno desapareció
  una decisión por archivo rojo, escrita, con su motivo
```

## 5 · Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| I1 | **Línea base medida antes de empezar** | Las guardas de §6 de CLAUDE.md corridas sobre el destino intacto, salidas pegadas. Sin esto nada de lo que sigue significa algo |
| I2 | **Ninguno de los 548 desapareció** | El mismo `git diff --name-status` contra el destino post-integración → **cero `D`** en `nucleo/seguridad/`, `nucleo/relevo/`, `supabase/` y `django-crm/backend/operaciones/` |
| I3 | **Los 7 de seguridad y los 12 de relevo existen y son los del destino** | `git patch-id --stable` o hash del blob, iguales al del destino. No "existen": **son los mismos** |
| I4 | **Las 64+ migraciones siguen completas y el ledger las entiende** | `py -3.13 cli/migrar_asistente.py --estado` → 0 pendientes, 0 checksums distintos |
| I5 | **El grafo de migraciones de Django tiene una sola hoja** | `makemigrations --check --dry-run campo` → exit 0. Es el conflicto de las dos `0003` |
| I6 | **La guarda de arquitectura del núcleo, verde** | `py -3.13 tests/test_nucleo_sin_tenants.py` |
| I7 | **La guarda de PII, verde** | `py -3.13 tests/test_registro_sin_pii.py` |
| I8 | **La guarda de la frontera, verde** | `py -3.13 tests/test_escalada_forzada.py` y `test_bloqueos_en_traza.py` |
| I9 | **Ninguna prueba que estaba verde quedó en rojo** | `py -3.13 cli/correr_pruebas.py` contra la línea base de I1, diferencia nombrada archivo por archivo |
| I10 | **El frontend no empeoró** | `docker exec <frontend> pnpm check` y `pnpm vitest run` contra la base de I1. Nunca `pnpm check` en Windows con Docker arriba |
| I11 | **La app de Campo sigue verde en las dos compilaciones** | `flutter test` con la bandera de demostración apagada **y** encendida. Referencia: 536 |
| I12 | **Cada archivo rojo tiene una decisión escrita** | Una tabla en la bitácora: archivo · qué lado ganó · por qué |
| I13 | **Nada se coló en el stage** | `git diff --cached --name-only` revisado antes de cada commit |
| I14 | **Pasada adversarial** | `auditor-independiente`, y `auditor-de-frontera` sobre los rojos. Si no corrieron, se dice |
| I15 | **El estado lo refleja** | `SPEC/DEXTER_ESTADO_ACTUAL.md`, por su única sesión dueña |

## 6 · Restricciones

- **NO push** — push a `fix/integracion-wisphub` es deploy a producción. Esta
  integración produce un árbol integrado y verificado; **publicarlo es otra
  decisión, de una persona.**
- **NO escribir `tenant_config`** ni cargar config desde esta rama (§2).
- **NO correr los 56 casos dorados** salvo que el resultado de I9 lo pida: `--humo`
  primero.
- **NO `pnpm check` en Windows con Docker arriba.**
- **NO tocar la rama de Campo mientras otra sesión la esté editando** — hoy tiene 12
  archivos sin commitear, entre ellos `campo/urls.py`, `despacho_views.py` y
  `serializers.py`. Coordinar primero.
- **NO amend, NO `--no-verify` sin decirlo.**

## 7 · Qué NO hacer

- **No construir inventario "mientras tanto".** Es el prerrequisito de la otra
  ficha, y empezar en paralelo reproduce el cruce que motivó esta decisión.
- **No podar los 21 worktrees** ni la rama de Campo al terminar. Es decisión de una
  persona.
- **No arreglar los 63 rojos históricos del frontend ni los 2 de CI.** Son línea
  base, no regresiones. Mezclarlos vuelve I9 ilegible.
- **No renumerar migraciones.** Ya está decidido: merge (custodia-de-materiales B2).

## 8 · Bloqueos

**J1 · La otra sesión está editando la rama de Campo** (12 archivos sin commitear,
tres de ellos en el camino de esta integración). **No arranca hasta que ese árbol
esté quieto o esa sesión haya entregado.**

**J2 · Decisión de entrega, no de código:** ¿esta integración termina en un árbol
verificado sin publicar, o se publica? La ficha asume lo primero. Publicar es un
deploy y lo decide una persona.

## 9 · Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 25/09/2026 | Ficha creada con el inventario medido: 548 `D` · 210 `A` · 190 `M`, y la corrección de método (la dirección del merge decide qué conjunto es el riesgo). Clasificación roja/amarilla/verde con archivos reales. Antecedente `452e6bb` documentado | Resolver J1 y medir la línea base (I1) | — |

### Decisiones por archivo rojo

Se llena durante el trabajo. Una fila por archivo, y **ninguna fila vacía al
cerrar**: un rojo sin decisión escrita es un rojo sin revisar.

| Archivo | Qué lado ganó | Por qué |
|---|---|---|
| | | |
