# PASO M09-I — Gobierno y diseño final de autorización de autonomía

**Fecha:** 2026-09-17
**Naturaleza:** **diseño y auditoría**. No se escribió código, no se creó ninguna
migración, no se tocó producción, no se cambió el kill switch, no se habilitó
ninguna autonomía, no se seleccionó ninguna herramienta para automatizar.
Contra producción, **solo lecturas** (`read_only=True`).

**Etiquetas:** **[MEDIDO]** hecho comprobado · **[DISEÑO]** propuesta no
construida · **[DEPENDENCIA]** algo debe existir antes · **[RIESGO]** ·
**[PENDIENTE]** decisión humana.

---

## 0. El hallazgo que condiciona todo el paso

Antes de resolver P-1 se midieron los roles reales de producción, y apareció un
hecho que cambia el orden de todo lo demás.

**[MEDIDO]** La aplicación se conecta a la base como **`postgres`**:

```
DBUSER      = postgres.05b5a4b4-…        (Supavisor quita el sufijo)
session_user = postgres     current_user = postgres
```

**[MEDIDO]** Qué puede ese rol en producción:

```
postgres:  NOSUPERUSER  pero  BYPASSRLS ✔  CREATEROLE ✔  CREATEDB ✔  REPLICATION ✔
           asistente.tenant_config          → DELETE, INSERT, SELECT, UPDATE, TRUNCATE…
           asistente.interruptor_autonomia  → DELETE, INSERT, SELECT, UPDATE, TRUNCATE…
```

**[MEDIDO]** Los roles restringidos **existen y están correctamente acotados,
pero nadie se conecta como ellos**. Conexiones activas al momento de medir:

```
supabase_admin 31 · authenticator 1 · postgres 1 · pgbouncer 1 · supabase_storage_admin 1
motor_user 0 · app_backend 0 · crm_user 0 · job_executor 0 · scheduler_coordinator 0
```

| Rol | login | BYPASSRLS | Grants en `asistente` |
|---|:--:|:--:|---|
| `postgres` | **sí** | **sí** | **todo** |
| `motor_user` | sí | **sí** | **ninguno** |
| `app_backend` | no | no | `tenant_config` DML; `interruptor_autonomia` **solo SELECT** |
| `autonomia_operador` | no | no | `interruptor_autonomia` **INSERT, SELECT** |
| `crm_user`, `job_executor`, `scheduler_coordinator` | var. | no | acotados |

### Consecuencia, dicha sin rodeos

> **[RIESGO CRÍTICO]** Hoy **ninguna separación de autoridad basada en GRANT o en
> RLS es efectiva**, porque la aplicación se conecta con el rol que puede
> escribirlo todo y que además atraviesa RLS.
>
> La separación que hoy sí existe es **de código**: ninguna ruta del motor
> escribe `interruptor_autonomia` ni la autorización. Esa garantía es real y está
> probada (10.14A/B), pero es de **otra naturaleza** — protege contra el camino
> que no existe, no contra el que alguien agregue mañana.

**[DEPENDENCIA]** Por lo tanto: **P-1 no se puede cerrar con una tabla. Se cierra
con una tabla *más* el cambio de `DBUSER` a un rol restringido.** Diseñar la
tabla sin eso produce un control decorativo.

Ese cambio ya estaba pendiente de pasos anteriores (`DBUSER → crm_user`,
`MIGRATOR_*` en Dokploy) y **no se ejecuta aquí**.

---

## 1. P-1 — Dónde vive la autorización (organización, herramienta)

### 1.1 — Las cuatro alternativas

#### A. Dentro de `tenant_config` — **RECHAZADA**

| Criterio | Evaluación |
|---|---|
| Quién la modifica | **[MEDIDO]** `app_backend` (DML completo) y `postgres`. Y `nucleo/config/editor.py` la escribe: es el editor de agentes |
| Control | ninguno específico: es configuración de producto |
| RLS | existe, pero `postgres` la atraviesa |
| Auditoría | versionado (`config_version` = 146), sin actor por campo |
| **Riesgo de autoautorización** | **máximo.** El asistente tiene un editor de su propia configuración. Poner ahí sus permisos significa que ampliar su catálogo y ampliar su autoridad son la misma operación |
| Separación config/autoridad | **nula: es exactamente lo contrario** |
| Versionado | sí |
| Revocación | editar y recargar; el caché de `_config_de` sirve copia vieja cuando no puede verificar la versión — **una revocación podría tardar en verse** |
| Migraciones | ninguna |

**[MEDIDO]** El motivo decisivo ya estaba documentado en CLAUDE.md: `api.py::_config_de`
sirve una copia cacheada y, cuando no puede comprobar la versión, **sigue
sirviendo la vieja a propósito**; y `fuente.cargar` cae al YAML de la imagen si la
base no responde. Es la misma razón por la que el interruptor **no** vive en
`tenant_config`: esa ruta **falla ABIERTA**. Una autorización que falla abierta
no es una autorización.

#### B. Tabla independiente en `asistente` — **base de la propuesta**

| Criterio | Evaluación |
|---|---|
| Quién la modifica | **[DISEÑO]** solo un rol dedicado, vía función; **[DEPENDENCIA]** inútil mientras la app sea `postgres` |
| Control | GRANT, no RLS — **[MEDIDO]** `motor_user` tiene `BYPASSRLS=true`, así que RLS no lo detendría |
| RLS | útil para aislamiento entre tenants, **no** como control de autoridad |
| Auditoría | **[DISEÑO]** append-only: el historial es la tabla |
| Riesgo de autoautorización | **eliminado** si el rol de la app no tiene INSERT/UPDATE |
| Separación config/autoridad | **completa** |
| Versionado | **[DISEÑO]** por diseño append-only |
| Revocación | inmediata: una fila nueva de revocación |
| Migraciones | **[DISEÑO]** 1 tabla + grants + funciones |

#### C. Reutilizar una estructura existente

**[MEDIDO]** Candidatas examinadas:

| Estructura | ¿Sirve? |
|---|---|
| `asistente.acciones_propuestas` | **no**: su unidad es una ocurrencia con payload, no una política |
| `PropuestaSupervisor` | **no**: es una recomendación, no una autorización |
| `asistente.interruptor_autonomia` | **no como tabla** — es por organización, no por herramienta — **pero sí como PATRÓN** |

**[MEDIDO]** El patrón del interruptor ya está construido y probado:

- tabla **append-only** (el estado es la última fila, el historial no se pierde);
- **rol dedicado NOLOGIN** (`autonomia_operador`);
- **función `SECURITY DEFINER`** como única vía de escritura (`autonomia_detener`);
- RLS habilitada **y forzada**, política por `asistente.org_actual()`;
- **lectura sin caché** antes de cada decisión, y **fail-closed**.

**[MEDIDO]** Y no es un caso aislado: el esquema `asistente` ya tiene **14
funciones**, de ellas **11 `SECURITY DEFINER`** (toda la familia `job_*`). El
patrón es el idioma de esta base, no una invención.

#### D. Combinación — **PROPUESTA SELECCIONADA**

### 1.2 — La propuesta

**[DISEÑO]** *Nada de esto existe.*

> **Una tabla nueva en `asistente`, construida con el patrón del interruptor.**

```
  asistente.autorizacion_herramienta          -- append-only
  ───────────────────────────────────────────────────────────
  organization_id        uuid    → public.organization
  herramienta            text
  nivel_requerido        smallint
  estado                 text    ('concedida' | 'revocada')
  condiciones            jsonb
  vigencia_hasta         timestamptz  (null = ver P-3)
  huella_herramienta     text    -- ver §7
  actor                  text    -- quién
  tipo_actor             text    -- persona | servicio | motor
  motivo                 text    -- obligatorio
  creado_en              timestamptz
```

**[DISEÑO]** Reglas que la definen:

1. **Append-only.** No hay UPDATE ni DELETE. Revocar es insertar una fila
   `revocada`. El historial **es** la auditoría de autorización (§11).
2. **Dos funciones `SECURITY DEFINER` separadas**, no una con un parámetro:
   `autorizacion_conceder(...)` y `autorizacion_revocar(...)`. Separarlas permite
   dar GRANT distinto a cada una — que es todo el §2.
3. **El rol de la aplicación tiene SELECT y nada más.** El control es el GRANT.
4. RLS habilitada y forzada para aislamiento entre tenants — **no** como control
   de autoridad: **[MEDIDO]** `motor_user` tiene `BYPASSRLS`.
5. **Ausencia de caché.** Se lee antes de cada decisión, como el interruptor.
6. **Fail-closed:** sin fila → no autorizado. Un `null` no es permisivo.

**[DEPENDENCIA]** Esta propuesta **no aporta ninguna garantía** hasta que
`DBUSER` deje de ser `postgres`. Mientras tanto la protección real sigue siendo
de código.

**[PENDIENTE]** Si la autorización debe además existir a nivel de organización
global (un "techo de la instalación") o solo por tenant.

---

## 2. P-2 — Activar, detener, revocar: tres acciones distintas

### 2.1 — Lo que ya existe

**[MEDIDO]** La asimetría ya está a medio construir, y a favor:

```
asistente.autonomia_detener(...)   SECURITY DEFINER   → EXISTE
asistente.autonomia_activar(...)                      → NO EXISTE
```

Activar hoy solo se puede por escritura directa como `postgres`. Detener tiene
una función con validaciones (exige actor, exige motivo, valida la organización).

### 2.2 — Un desajuste que conviene nombrar

**[MEDIDO]** `autonomia_operador` —el rol pensado para **detener**— tiene
`INSERT, SELECT` sobre `interruptor_autonomia`, y su política
`tenant_aislado_operador` solo restringe por `organization_id`. El único `CHECK`
de la tabla limita `estado ∈ {activo, detenido}`.

> **[RIESGO]** El **privilegio** de `autonomia_operador` permite insertar una fila
> `activo`. Lo que lo restringe a detener es la **función**, no el permiso.
> Hoy no es explotable —el rol es `NOLOGIN` y nadie se conecta como él— pero el
> día que algo se conecte, el rol "que solo detiene" podría activar.

**[DISEÑO]** Corrección: un `CHECK` que ate el rol al valor, o un `GRANT INSERT`
retirado dejando solo `EXECUTE` sobre la función. La segunda es más limpia: si la
única vía es la función, el privilegio no puede ser más ancho que la intención.

### 2.3 — La matriz de autoridad

**[DISEÑO]** Solo con roles que **[MEDIDO]** existen.

| Operación | ADMIN | SUPERVISOR | OPERACIONES | Rol de base |
|---|:--:|:--:|:--:|---|
| **Detener** autonomía | ✔ | ✔ | ✔ | `autonomia_operador` (EXECUTE) |
| **Revocar** autorización | ✔ | ✔ | ✔ | `autonomia_operador` (EXECUTE) |
| **Activar** autonomía | ✔ | ✘ | ✘ | rol dedicado, **distinto** |
| **Conceder** autorización | ✔ | ✘ | ✘ | rol dedicado, **distinto** |
| **Modificar nivel máximo** | ✔ | ✘ | ✘ | rol dedicado, **distinto** |
| Modificar condiciones | ✔ | ✘ | ✘ | rol dedicado, **distinto** |

**[DISEÑO]** El principio, hecho estructura:

> **Parar y revocar comparten un rol amplio. Arrancar y conceder comparten uno
> estrecho, y es otro.** No es el mismo rol con un parámetro: son funciones
> distintas con GRANT distinto.
>
> El motivo es operativo, no estético: si detener exigiera el mismo rol que
> activar, en una emergencia la única persona autorizada podría estar durmiendo.
> Un control de seguridad que no se puede accionar cuando hace falta no es un
> control.

**[MEDIDO]** Roles de base existentes y su papel: `autonomia_operador` (detener,
ya creado), `app_backend` (solo SELECT sobre el interruptor — correcto),
`motor_user` (sin grants en `asistente` — correcto), `postgres` (todo — **el
problema**, §0), `job_executor` y `scheduler_coordinator` (sin papel aquí).

**[DISEÑO]** El rol estrecho para conceder/activar **no existe** y habría que
crearlo. Se declara como diseño futuro, no se crea.

### 2.4 — Lo que la IA no puede hacer

| Prohibido | Garantía |
|---|---|
| Activar autonomía | **[MEDIDO]** ninguna ruta escribe `interruptor_autonomia`; no hay función de activar |
| Conceder su propia autorización | **[DISEÑO]** el rol de la app tendría solo SELECT |
| Elevar su nivel | **[MEDIDO]** `nivel_autonomia_requerido` no está en `CAMPOS_MODIFICABLES` (M09-F) |
| Autorizarse en ejecución | **[MEDIDO]** `_Permiso` lo construye **solo** `frontera`; no hay `autorizado=True` pasable |
| Modificar permisos | **[MEDIDO]** `supervisor.py` no toca `Profile` — una **ausencia de código** |
| Modificar sus condiciones | **[DISEÑO]** tabla sin INSERT para el rol de la app |

**[RIESGO]** Cuatro de esas seis garantías son hoy "no existe el camino". Es
real, y es **distinto** de "el camino existe y está cerrado con llave". El §0 es
la razón.

---

## 3. P-3 — Vigencia de las autorizaciones

**[DISEÑO]** Las cuatro opciones, con su mecánica:

| Opción | Cómo funcionaría | A favor | En contra |
|---|---|---|---|
| **No vencer** | `vigencia_hasta = null`; vive hasta revocarse | simple; sin sorpresas operativas | una autorización de prueba queda viva para siempre, y nadie la recuerda |
| **Vencer por fecha** | `vigencia_hasta` fijo; al pasar, no autorizado | explícito; el que concede elige | la fecha se elige una vez y se copia sin pensar |
| **Vencer por período** | se deriva de `creado_en` + un intervalo de política | uniforme | un cambio de política mueve todas las vigencias a la vez |
| **Requerir renovación** | vence **y** exige un acto humano nuevo | el más seguro | costo operativo real y recurrente |

**[DISEÑO]** Lo que sí puede cerrarse sin decidir la periodicidad:

1. **El campo `vigencia_hasta` debe existir desde el principio.** Agregarlo
   después obliga a decidir qué pasa con las filas viejas, y la respuesta
   cómoda ("no vencen") es justamente la que no se quiere.
2. **Vencida ⇒ NO EJECUTAR, y NO renovar sola.** Una autorización que se renueva
   sola no es una autorización: es un permiso permanente con un campo de fecha
   decorativo.
3. **El vencimiento no borra nada.** Append-only: la fila sigue, y se puede ver
   que venció y cuándo.
4. **Vencimiento ≠ revocación.** Vencer es que se acabó el plazo; revocar es una
   decisión. Deben distinguirse en la auditoría, igual que M09-F distinguió
   expirada de rechazada.

**[PENDIENTE]** **La periodicidad es una decisión de negocio y no se elige aquí.**
Elegir "90 días" porque suena razonable sería inventar una política. Lo que hace
falta antes es saber con qué frecuencia el negocio revisa permisos operativos —
un dato que este documento no tiene.

---

## 4. P-4 — Las 27 herramientas de escritura, clasificadas

**[DISEÑO]** No se asume que las 20 sin compuerta deban recibir `aprobacion_humana`.
La clasificación primero; la conclusión, después.

Crít. = crítico · Nivel = **[DISEÑO]** propuesto · Aprob = aprobación por ocurrencia
Gate hoy = **[MEDIDO]** · Todas: kill switch ✔, auditoría ✔, tenant obligatorio

| Herramienta | Efecto | I/E | Rev | Crít | Nivel | Aprob | Evidencia | Idem | Gate hoy |
|---|---|:--:|:--:|:--:|:--:|:--:|:--:|:--:|---|
| `registrar_pago` | financiero | E | no | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `agregar_promesa_pago` | financiero | E | parc | **sí** | 4 | **sí** | completa | exige | `aprobacion_humana` |
| `reportar_comprobante_pago` | financiero | I | sí | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `cerrar_ticket_operativo` | dato | E | no | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `completar_ticket_instalacion` | dato | E | no | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `cerrar_caso_crm` | dato | E | no | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `cancelar_solicitud_servicio` | dato | E | no | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `responder_ticket` | comunicación | E | no | **sí** | 4 | **sí** | completa | exige | `aprobacion_humana` |
| `responder_ticket_operativo` | comunicación | E | no | **sí** | 4 | **sí** | completa | exige | **ninguno** |
| `cambiar_tipo_onu` | infraestructura | E | no | **sí** | 4 | **sí** | completa | exige | `exige_previas` |
| `activar_catv` | infraestructura | E | parc | **sí** | 4 | **sí** | completa | exige | `exige_previas` |
| `reiniciar_ont` | infraestructura | E | sí | **sí** | 4 | **sí** | completa | exige | `exige_previas` |
| `actualizar_estado_ticket` | dato | E | sí | no | 3 | no | propuesta+args | exige | `aprobacion_humana` |
| `reasignar_ticket_instalacion` | dato | E | sí | no | 3 | no | propuesta+args | exige | **ninguno** |
| `crear_ticket` | dato | E | parc | no | 3 | no | propuesta+args | **exige** | `aprobacion_humana` |
| `crear_ticket_caso` | dato | E | parc | no | 3 | no | propuesta+args | **exige** | **ninguno** |
| `crear_ticket_instalacion` | dato | E | parc | no | 3 | no | propuesta+args | **exige** | **ninguno** |
| `agendar_visita_tecnica` | dato | E | parc | no | 3 | no | propuesta+args | **exige** | **ninguno** |
| `agendar_visita_internet` | dato | E | parc | no | 3 | no | propuesta+args | **exige** | **ninguno** |
| `registrar_solicitud_servicio` | dato | I | parc | no | 3 | no | propuesta+args | exige | **ninguno** |
| `importar_caso_externo` | dato | I | sí | no | 2 | no | propuesta | exige | **ninguno** |
| `sincronizar_respuestas_externas` | dato | I | sí | no | 2 | no | propuesta | exige | **ninguno** |
| `crear_caso_soporte` | dato | I | parc | no | 2 | no | propuesta | exige | **ninguno** |
| `registrar_pedido_wifi` | dato | I | sí | no | 2 | no | propuesta | no exige | **ninguno** |
| `reconciliar_caso_externo` | dato | I | parc | no | 2 | no | propuesta | exige | **ninguno** |
| `crear_tag_crm` | dato | I | sí | no | 2 | no | propuesta | no exige | **ninguno** |
| `proponer_herramienta` | dato | I | sí | no | 2 | no | propuesta | no exige | **ninguno** |

### Lo que la clasificación muestra

**[MEDIDO]** **12 de 27 son críticas** y quedan en nivel 4 — aprobación por
ocurrencia. De esas 12, **8 no tienen hoy ninguna compuerta propia**.

**[DISEÑO]** Y la respuesta a P-4 **no** es "ponerle `aprobacion_humana` a las 20":

> `aprobacion_humana` es un **booleano por herramienta**, evaluado en el camino
> conversacional del motor. El modelo de M09-H es **por (organización,
> herramienta, nivel, condiciones, vigencia)**. Marcar las 20 duplicaría el
> control en dos lugares con semánticas distintas — y dos listas que deberían
> coincidir terminan divergiendo. Es exactamente el motivo por el que
> `operaciones/permissions.py` **importa** `ROLES_GESTION` en vez de copiarlo.

**[DISEÑO]** Lo correcto: **`nivel_requerido = 4` ya implica aprobación por
ocurrencia**. La compuerta se deriva del nivel, no de un segundo campo.

**[PENDIENTE]** Qué hacer con `aprobacion_humana` en las 4 que ya lo declaran:
¿se mantiene como camino paralelo del flujo conversacional, o se subsume? Afecta
comportamiento vivo hoy y requiere decisión.

**No se selecciona ninguna herramienta. No se recomienda cuál automatizar.**

---

## 5. Política de autorización efectiva

**[DISEÑO]**

```
AUTORIZACION_EFECTIVA =
        tenant válido y coincidente con el permiso
  AND   herramienta registrada en el catálogo
  AND   herramienta autorizada para ese tenant  (fila 'concedida' vigente)
  AND   nivel_autonomia_org  >=  nivel_requerido
  AND   todas las condiciones declaradas se cumplen
  AND   kill switch  ==  ACTIVO
  AND   idempotencia válida  (si la herramienta la exige)
  AND   evidencia presente   (si la herramienta la exige)
  AND   actor / contexto válido
  AND   permisos de rol suficientes
```

**[DISEÑO]** Obligatorios **siempre**, sin excepción por tipo:

| Control | Por qué no admite excepción |
|---|---|
| Tenant válido | sin tenant no hay interruptor que consultar |
| Herramienta registrada | ejecutar lo no declarado es ejecutar cualquier cosa |
| Herramienta autorizada | es el núcleo del modelo: el nivel es techo, no llave |
| Nivel suficiente | el techo |
| Kill switch activo | es el freno de toda la etapa |
| Actor / contexto válido | sin actor no hay a quién atribuirlo |
| Auditoría | una acción sin rastro no ocurrió, o no se puede demostrar que sí |

**[DISEÑO]** Dependen del tipo de herramienta:

| Control | Cuándo |
|---|---|
| Idempotencia | obligatoria en **creación** (un ticket duplicado es trabajo real duplicado); prescindible en operaciones naturalmente idempotentes |
| Evidencia | según lo que declare la herramienta |
| Aprobación por ocurrencia | **derivada**: `nivel_requerido == 4` |
| Plan de reversión | obligatorio desde nivel 3 |

**[DISEÑO]** Y la regla de evaluación:

> Es una **conjunción**, y el rechazo debe nombrar **cuál** término falló.
> Un "no autorizado" genérico obliga a adivinar, y quien adivina relaja la
> condición equivocada.

---

## 6. Configuración ≠ autoridad — los cinco escenarios

**[DISEÑO]** Comportamiento exigido. Ninguno está implementado.

| Caso | Situación | Resultado exigido | Por qué |
|---|---|---|---|
| **A** | cambia `tenant_config` | **NO concede autonomía** | la configuración dice *qué sabe hacer* el asistente, no *qué le está permitido*. Además **[MEDIDO]** esa ruta falla ABIERTA (caché + caída al YAML) |
| **B** | cambia `nivel_autonomia` | **NO autoriza ninguna herramienta** | el nivel es un techo. Subirlo con cero autorizaciones deja cero herramientas ejecutables |
| **C** | herramienta autorizada | **sigue necesitando nivel suficiente** | autorizar no eleva el techo |
| **D** | nivel suficiente **+** herramienta autorizada | **sigue necesitando kill switch y el resto** | la conjunción del §5 |
| **E** | kill switch DETENIDO | **cero ejecución autónoma** | el freno es incondicional |

**[DISEÑO]** A y B son **duales**, y ahí está la idea entera: hacen falta **dos
actos independientes**, de distinta naturaleza, y ninguno alcanza solo.

**[DISEÑO]** El caso E merece una precisión: "cero ejecución **autónoma**".
Una acción **humana reactiva** no debe bloquearse. **[MEDIDO]** La frontera ya
tiene las dos puertas separadas: `frontera.humana(...)` exige actor y evidencia;
`frontera.autonoma(...)` consulta el interruptor. *El kill switch existe para
frenar a la IA, no para frenar a la empresa.*

---

## 7. Versionado — cuándo una autorización deja de valer

**[DISEÑO]** El problema: una autorización dice *"esta herramienta puede
ejecutarse"*. Si la herramienta cambia, ya no es la misma cosa.

**[DISEÑO]** Solución: `huella_herramienta` — un hash de lo que define su
**efecto**, no de lo cosmético.

| Cambia… | ¿Entra en la huella? | Autorización previa |
|---|:--:|---|
| Endpoint o método HTTP | **sí** | **se invalida** — es otro efecto |
| `nivel_requerido` | **sí** | **se invalida** — se autorizó otro riesgo |
| `solo_lectura` | **sí** | **se invalida** |
| Argumentos requeridos | **sí** | **se invalida** — otro alcance |
| `base_url` / tenant destino | **sí** | **se invalida** — podría apuntar a otro sistema |
| Condiciones declaradas | **sí** | **se invalida** |
| Descripción, texto de confirmación | no | se mantiene |
| Filtros de solo lectura | no | se mantiene |
| Implementación interna sin cambio de contrato | no | se mantiene, **[RIESGO]** la huella no lo ve |
| Política global de autonomía | n/a | **[PENDIENTE]** ¿invalida todo, o solo hacia adelante? |
| `config_version` del tenant | no por sí solo | se mantiene salvo que cambie la huella |

**[DISEÑO]** La regla:

> **Si la huella de la herramienta difiere de la registrada al conceder, la
> autorización no aplica.** No se "actualiza sola": **requiere una concesión
> nueva.** Fail-closed.

**[RIESGO]** La huella cubre el **contrato declarado**, no la implementación. Un
cambio en `http.py` que altere el comportamiento sin tocar el catálogo no la
movería. Mitigación: revisión de código, no una huella más grande — una huella
que intentara cubrir la implementación invalidaría todo en cada despliegue y
entrenaría a la gente a reconceder sin mirar.

---

## 8. Revocación

**[DISEÑO]** Seis caminos, un mismo efecto inmediato:

| Camino | Quién | Efecto |
|---|---|---|
| Manual | ADMIN / SUPERVISOR / OPERACIONES | fila `revocada` |
| **Emergencia** | cualquier rol de gestión | **detener el kill switch** — más rápido y más ancho |
| Por cambio de herramienta | el sistema | la huella no coincide → no aplica (§7) |
| Por cambio de política | ADMIN | **[PENDIENTE]** alcance |
| Por vencimiento | el sistema | no aplica; **no se renueva sola** |
| Por incidente | cualquier rol de gestión | detener + revocar |

**[DISEÑO]** Qué pasa con lo que ya estaba en curso:

| Objeto | Comportamiento |
|---|---|
| **Propuestas existentes** | **se conservan.** Una propuesta no es una ejecución; revocar no invalida haber detectado algo cierto |
| **Ejecuciones pendientes** | **no se ejecutan.** La autorización se evalúa **al ejecutar**, no al encolar |
| **Ejecuciones RUNNING** | **no se cancelan.** La llamada ya salió; "cancelar" daría una falsa sensación de que no ocurrió. Se **marcan** y se auditan. **[RIESGO]** nadie puede saber si el tercero la aplicó — el mismo límite del timeout |
| **Reintentos** | **se detienen.** Un reintento es una ejecución nueva y necesita autorización vigente |
| **Scheduler** | **[MEDIDO]** hoy **0 trabajos** registrados; el registro es cerrado. Un trabajo futuro debe evaluar autorización **en cada turno**, no al registrarse |
| **Idempotencia** | **se conserva.** Las filas de `operaciones_externas` no se borran: son el registro de lo que ya ocurrió. Borrarlas permitiría que un reintento futuro **repita** una operación ya hecha |

**[DISEÑO]** La distinción que ordena la tabla: **revocar cambia lo que puede
pasar, nunca lo que ya pasó.**

---

## 9. Batería de pruebas de no-bypass

**[DISEÑO]** Ninguna existe. Son especificación, no resultados.

| # | Escenario | Esperado | Qué demuestra |
|---|---|---|---|
| 1 | Nivel 0 + herramienta autorizada | **BLOQUEADO** | autorizar no eleva el techo |
| 2 | Nivel 1 + herramienta autorizada | **BLOQUEADO** | nivel 1 **no ejecuta**, ni siquiera lo autorizado |
| 3 | Nivel 2 + herramienta nivel 3 | **BLOQUEADO** | el techo se compara, no se redondea |
| 4 | Nivel 3 + herramienta **no** autorizada | **BLOQUEADO** | **el nivel es techo, no llave** |
| 5 | Nivel 3 + autorizada + kill switch DETENIDO | **BLOQUEADO** | el freno es incondicional |
| 6 | Tenant inexistente | **BLOQUEADO** | **[MEDIDO]** ya se comporta así |
| 7 | Tenant vacío | **BLOQUEADO** | **[MEDIDO]** ya se comporta así |
| 8 | Evidencia requerida ausente | **BLOQUEADO** | |
| 9 | Idempotencia inválida | **BLOQUEADO** | |
| 10 | Permiso de rol insuficiente | **BLOQUEADO** | |
| 11 | `tenant_config` modificado | **NO concede autonomía** | caso A del §6 |
| 12 | `nivel_autonomia` modificado | **NO autoriza herramienta** | caso B del §6 |
| 13 | Autorizada pero política revocada | **BLOQUEADO** | la revocación es inmediata |
| 14 | La IA intenta elevar su nivel | **BLOQUEADO** | |
| 15 | La IA intenta autorizarse una herramienta | **BLOQUEADO** | |
| 16 | La IA intenta activar el kill switch | **BLOQUEADO** | |

### Cómo deben escribirse, o no valen

**[DISEÑO]** Tres exigencias que vienen de errores ya cometidos en este proyecto:

1. **Afirmar sobre el EFECTO, nunca sobre la presencia del mecanismo.** Una
   prueba que comprueba que existe una variable **sobrevivió intacta a una
   inversión completa de la conducta** (CLAUDE.md).
2. **Cada prueba debe fallar si se desarma su guarda.** Si no se comprobó que
   falla al quitarla, no se sabe si prueba algo.
3. **"0 llamadas" no es "bloqueado".** En M09-E dos pruebas dieron 0 llamadas
   porque no había nada que hacer. Cada escenario necesita un candidato real que
   **habría** ejecutado.

**[DISEÑO]** Y las tres últimas (14–16) no se prueban con un `assert` sobre una
lista de rutas, sino **intentando la operación** con el rol y el contexto de la
IA y exigiendo que levante.

---

## 10. Fallbacks — todos fail-closed

**[DISEÑO]** Respuesta exacta. Ninguna excepción.

| Condición | Respuesta | Estado |
|---|---|---|
| Configuración inexistente | NO EJECUTAR + registrar | **[DISEÑO]** |
| **Autorización inexistente** | NO EJECUTAR. *Sin fila no es permisivo* | **[DISEÑO]** |
| **Nivel inexistente** | tratar como **0**, nunca como "sin límite" | **[DISEÑO]** |
| Herramienta inexistente | NO EJECUTAR | **[MEDIDO]** ✔ |
| **Autorización vencida** | NO EJECUTAR; **no renovar sola** | **[DISEÑO]** |
| **Autorización revocada** | NO EJECUTAR | **[DISEÑO]** |
| Kill switch detenido | NO EJECUTAR | **[MEDIDO]** ✔ |
| Kill switch **ilegible** | NO EJECUTAR — *sin control no es autorización* | **[MEDIDO]** ✔ |
| Evidencia incompleta | NO EJECUTAR | **[MEDIDO]** ✔ al proponer |
| Idempotencia ausente | NO EJECUTAR si la exige | **[DISEÑO]** |
| Tenant inválido | NO EJECUTAR | **[MEDIDO]** ✔ |
| Permiso insuficiente | NO EJECUTAR (403) | **[MEDIDO]** ✔ |
| Conflicto concurrente | primera decisión gana; 409 | **[MEDIDO]** ✔ |
| Timeout | **NO REINTENTAR** — la llamada pudo salir | **[MEDIDO]** ✔ |
| Resultado ambiguo | `NO_VERIFICABLE`, **nunca** `NO_CONFIRMADA` | **[MEDIDO]** ✔ |

**[DISEÑO]** Los tres donde un descuido se disfraza de valor por defecto —
**autorización inexistente**, **nivel inexistente**, **autorización vencida** —
comparten forma: *la ausencia de un dato nunca es un permiso*. Es el mismo
criterio por el que el kill switch **nace DETENIDO**.

---

## 11. Auditoría — dos registros separados

**[DISEÑO]** Autorización y ejecución responden preguntas distintas y tienen
ciclos de vida distintos: una autorización dura meses y se ejecuta mil veces; una
ejecución ocurre una vez. Mezclarlas obliga a repetir la política en cada fila.

### Auditoría de AUTORIZACIÓN — **[DISEÑO]**

**No hace falta tabla aparte:** la propia tabla append-only del §1 **es** la
auditoría. Cada fila lleva:

```
organización · herramienta · nivel_requerido · nivel_autorizado
actor · tipo_actor · fecha · vigencia · decisión (concedida|revocada)
motivo (obligatorio) · versión (huella_herramienta) · revocación
```

### Auditoría de EJECUCIÓN — **[MEDIDO]** parcial

Conserva sus campos y **[DISEÑO]** suma los seis de M09-H: nivel solicitado,
nivel autorizado, tipo de actor, autorización aplicada, estado del kill switch al
ejecutar, motivo de rechazo (cuál término de la conjunción falló), recurso
afectado.

**[RIESGO]** `recurso afectado` guarda **un identificador, nunca el dato**. Las
respuestas crudas de WispHub no se persisten: traen contraseñas, GPS y cédula.

**[DISEÑO]** El puente entre ambas: la ejecución referencia **qué fila de
autorización** la permitió. Sin eso, reconstruir "por qué se permitió aquello en
marzo" exige adivinar qué política estaba vigente.

---

## 12. P-5 — WhatsApp

**[MEDIDO]** No se modificó `whatsapp.py`. El WhatsApp reactivo actual se
mantiene **sin cambios**: los nueve puntos de llamada son reactivos.

**[DISEÑO]** Requisitos que debería cumplir una comunicación **proactiva** futura:

1. Camino **físicamente separado** del reactivo — función nueva, no una bandera
   en la existente. *La clasificación debe ser una propiedad del código, no un
   juicio que se repite en cada llamada.*
2. Pasar por la frontera: tenant, nivel, autorización, kill switch, idempotencia.
3. `nivel_requerido = 4` — es comunicación a una persona: irreversible en el
   único sentido que importa, que ya la leyó.
4. Autorización **por plantilla**, no por "enviar WhatsApp" en bloque.
5. Idempotencia con **origen estable** — un recordatorio duplicado es una molestia
   real para el destinatario.
6. Respetar la baja del canal (`canal_bajas` **[MEDIDO]** ya existe).
7. Auditar destinatario **como identificador**, nunca el número en claro.

**[PENDIENTE]** Qué verificar **documentalmente** antes de construirlo, sin
asumir nada:

- si fuera de la ventana de 24 h el proveedor exige plantilla preaprobada, y cuál
  es la ventana exacta vigente;
- qué categorías de plantilla existen y cuáles aplican a un aviso operativo;
- qué límites de tasa y de calidad aplican, y qué pasa al excederlos;
- qué obligaciones legales de consentimiento aplican a un mensaje proactivo bajo
  la Ley 1581 — distinto de responder a quien escribió primero.

> **[RIESGO]** Ninguno de esos cuatro puntos debe darse por sabido. La regla de
> este proyecto es que la documentación de un tercero es una **hipótesis**, y ya
> costó tiempo al menos dos veces (el límite de tasa de SmartOLT, los filtros que
> WispHub ignora en silencio).

---

## 13. M10 — abiertos

**[MEDIDO]** Ninguno resuelto. Ninguno se declara resuelto.

| # | Hallazgo | Estado |
|---|---|---|
| 1 | **7 tablas `campo_*` sin RLS ni políticas** | **abierto** |
| 2 | **69 de 135 tablas `public` sin política** | **abierto** |
| 3 | Aislamiento de las OT dependiente **del ORM** | **abierto** |
| 4 | Defecto B.4 | **abierto** |
| 5 | Ejecutor del motor sin instrumentar donde corresponde | **abierto** |
| 6 | 20 de 27 escrituras sin compuerta propia (M09-H) | **abierto** |
| 7 | **La aplicación se conecta como `postgres`** (§0) | **abierto — nuevo en M09-I** |
| 8 | **`autonomia_operador` tiene privilegio para activar** (§2.2) | **abierto — nuevo en M09-I** |

**[DEPENDENCIA]** El **7** es ahora el de mayor alcance: mientras siga abierto,
ningún control basado en GRANT o RLS es efectivo, y eso incluye la propuesta del
§1.

---

## A. Decisiones arquitectónicamente cerradas

| # | Decisión |
|---|---|
| A-1 | **El nivel es un techo, no una llave.** Autorización efectiva = conjunción (§5) |
| A-2 | **La autorización NO vive en `tenant_config`** — esa ruta falla ABIERTA |
| A-3 | **Tabla append-only propia con el patrón del interruptor**: rol dedicado + `SECURITY DEFINER` + GRANT, no RLS |
| A-4 | **Conceder y revocar son funciones distintas con GRANT distinto.** Parar y revocar: rol amplio. Arrancar y conceder: rol estrecho |
| A-5 | **`vigencia_hasta` existe desde el diseño inicial**; vencida ⇒ no ejecutar, **no renovar sola** |
| A-6 | **La aprobación por ocurrencia se deriva del nivel 4**, no de un segundo campo booleano |
| A-7 | **Cambio de huella ⇒ la autorización no aplica**; exige concesión nueva |
| A-8 | **Revocar cambia lo que puede pasar, nunca lo que ya pasó.** Idempotencia se conserva; RUNNING no se cancela, se marca |
| A-9 | **La auditoría de autorización es la propia tabla append-only**; la de ejecución la referencia |
| A-10 | **Todo control es fail-closed. La ausencia de un dato nunca es un permiso** |
| A-11 | **La comunicación proactiva de WhatsApp es un camino separado**, nivel 4, autorizado por plantilla |

## B. Decisiones que requieren aprobación humana

| # | Decisión | Por qué no se toma aquí |
|---|---|---|
| B-1 | **Periodicidad de vigencia** (P-3) | dato de negocio: cada cuánto se revisan permisos operativos |
| B-2 | Qué pasa con `aprobacion_humana` en las 4 que lo declaran (P-4) | cambia comportamiento vivo hoy |
| B-3 | Alcance de un cambio de política: ¿invalida lo concedido o solo aplica hacia adelante? | |
| B-4 | ¿Existe un techo global de instalación además del de tenant? | |
| B-5 | Nombre y grants exactos del rol estrecho de concesión | requiere B-1 y decidir quién lo custodia |
| B-6 | Los cuatro puntos documentales de WhatsApp (P-5) | **hay que verificarlos, no asumirlos** |
| B-7 | **Mover `DBUSER` fuera de `postgres`** | ya pendiente de pasos anteriores; ahora es **prerequisito de todo el modelo** |

## C. Controles que deben implementarse antes de autonomía

En orden de dependencia:

| # | Control | Bloqueado por |
|---|---|---|
| C-1 | **Guarda de arquitectura**: falla si aparece `requests.post/put/patch/delete` fuera de los puntos declarados | nada |
| C-2 | **Los seis campos de auditoría de ejecución** | nada |
| C-3 | **`DBUSER` fuera de `postgres`** | B-7 |
| C-4 | Tabla de autorización + rol + funciones | C-3, B-5 |
| C-5 | `nivel_autonomia` por organización, default 0 | C-4 |
| C-6 | Evaluación de la conjunción en `http.py::ejecutar` | C-4, C-5 |
| C-7 | Cerrar el privilegio de activar de `autonomia_operador` | C-3 |
| C-8 | RLS de `campo_*` (M10) | — |

**[MEDIDO]** C-1 y C-2 no dependen de ninguna decisión pendiente, son aditivos y
no cambian el comportamiento de nada.

## D. Pruebas obligatorias antes de activar cualquier herramienta

1. **Las 16 del §9**, todas en verde.
2. **Cada una comprobada por desarme**: se quita la guarda y la prueba **falla**.
3. **Prueba adversarial de la frontera** al estilo 10.14B, incluyendo los caminos
   nuevos que introduzca la autorización.
4. **Cero efectos externos** medidos con espía que **cuenta y levanta**, no que
   solo cuenta.
5. **Concurrencia**: dos concesiones o revocaciones simultáneas sobre la misma
   herramienta.
6. **Revocación en caliente**: revocar con una ejecución encolada y comprobar que
   no sale.
7. **Prueba con `session_user` real y restringido**, no con `postgres`. Sin esto
   las pruebas de GRANT no prueban nada.

## E. Dependencias M10

Las ocho de la §13, todas abiertas. **La 7 (`DBUSER = postgres`) es prerequisito
del modelo entero**: sin ella, la tabla de autorización es un control decorativo.
La 1 (`campo_*` sin RLS) sigue bloqueando toda autonomía sobre órdenes de trabajo.

## F. Orden recomendado de implementación posterior

```
 1. Guarda de arquitectura                      (sin bloqueos)
 2. Seis campos de auditoría de ejecución       (sin bloqueos)
 ───────── decisiones humanas B-1, B-5, B-7 ─────────
 3. DBUSER fuera de postgres                    (habilita todo lo demás)
 4. Tabla de autorización + rol + funciones
 5. nivel_autonomia por organización, default 0
 6. Conjunción evaluada en http.py::ejecutar
 7. Cerrar el privilegio de activar de autonomia_operador
 8. Las 16 pruebas de no-bypass, con desarme
 ───────── recién aquí se puede hablar de una herramienta ─────────
```

**Los pasos 1 y 2 pueden empezar sin ninguna aprobación adicional.** El 3 es una
decisión de infraestructura ya pendiente. Del 4 en adelante todo depende del 3.

**Nada de esto está construido. Este documento no autoriza a construirlo, ni
selecciona ninguna herramienta.**

---

### Anexo — qué se midió en este paso

| Medición | Resultado |
|---|---|
| Rol de conexión de la aplicación | **`postgres`** (`DBUSER=postgres.<ref>`, `session_user=postgres`) |
| Atributos de `postgres` en producción | NOSUPERUSER, **BYPASSRLS ✔ CREATEROLE ✔ CREATEDB ✔ REPLICATION ✔** |
| Grants de `postgres` sobre `tenant_config` e `interruptor_autonomia` | **DML completo en ambas** |
| Grants de `motor_user` en `asistente` | **ninguno** |
| `motor_user` BYPASSRLS | **true** — por eso el control debe ser GRANT, no RLS |
| Grants de `app_backend` | `tenant_config` DML; `interruptor_autonomia` **solo SELECT** |
| Grants de `autonomia_operador` | `interruptor_autonomia` **INSERT, SELECT** → **permite insertar `activo`** |
| Políticas de `interruptor_autonomia` | 2, ambas solo por `organization_id`; RLS **forzada** |
| `CHECK` de estado | solo `estado ∈ {activo, detenido}` |
| Funciones en `asistente` | 14, de ellas **11 `SECURITY DEFINER`** — el patrón está establecido |
| `autonomia_activar` | **NO EXISTE** — solo `autonomia_detener` |
| Conexiones activas por rol | `supabase_admin` 31 · `postgres` 1 · otros de Supabase; **0** como `motor_user`, `app_backend`, `crm_user`, `job_executor`, `scheduler_coordinator` |

Producción al cerrar el paso, sin cambios respecto de M09-F, M09-G y M09-H:

```
ledger 50 · kill switch DETENIDO · 0 filas ACTIVO · 0 PropuestaSupervisor
40 acciones_propuestas · operaciones_externas 0 · 192 django_migrations
tenant_config v146 · {ADMIN: 1, USER: 4}
```
