# A-3 — Informe

```
ESTADO: PARCIAL

Código modificado:   0
Migraciones:         0
Producción:          SIN CAMBIOS
Efectos externos:    0

Responsable:   PENDIENTE
Momento:       PENDIENTE
Flujo:         DEFINIDO conceptualmente · 2 de 7 pasos no existen
Seguridad:     GAP    (5 gaps, uno crítico)
Auditoría:     GAP    (3 de 7 datos sin cubrir)

H-05:  SIN CAMBIOS
K-01:  SIN CAMBIOS
K-02:  SIN CAMBIOS
B-7:   SIN CAMBIOS
```

---

## 1. Por qué PARCIAL

De las ocho preguntas del objetivo, **tres quedaron respondidas con evidencia** y
**cinco son decisiones de negocio** que este paso no podía tomar sin inventarlas.

| Pregunta | Estado |
|---|---|
| ¿Quién registra? | **PENDIENTE** |
| ¿Quién consulta? | **PENDIENTE** |
| ¿Quién puede corregir? | **PENDIENTE** |
| ¿Qué información se registra? | **RESPONDIDA** — 10 campos, 2 constraints, 5 gaps identificados |
| ¿Cuándo se registra? | **PENDIENTE** |
| ¿Cómo queda auditado? | **RESPONDIDA** — 4 de 7 cubiertos, 3 gaps, mecanismo reutilizable identificado |
| ¿Cómo afecta una programación existente? | **RESPONDIDA** — alerta + escalamiento. **No cancela** |
| ¿Qué ocurre cuando la información cambia? | **PENDIENTE** — cuatro operaciones distinguidas, regla sin decidir |

---

## 2. El hallazgo principal

D-4.1 cerró diciendo que faltaba decidir **por dónde** se registra una ausencia.
A-3 fue a evaluar si el admin de Django podía servir de contingencia mientras
tanto, y encontró que **no**:

**[MEDIDO]** `/admin/` está en `EXEMPT_PATHS` del middleware `RequireOrgContext`
(`common/middleware/rls_context.py:123`). **El admin no fija `app.current_org`.**

**[MEDIDO]** La política de aislamiento compara contra esa variable:

```sql
org_id::text = NULLIF(current_setting('app.current_org', true), '')
```

**[DOCUMENTADO]** El propio archivo explica el efecto para el caso hermano de los
endpoints públicos, y dice que **fue verificado**:

> *"…the isolation policy … matches nothing when empty. **Verified as `crm_user`
> (non-superuser, no BYPASSRLS)**: invoice, estimate and csat_survey all return
> 0 rows with empty context."*

> **El admin funciona hoy únicamente porque el runtime se conecta como
> `postgres`, que tiene BYPASSRLS. Después de B-7 mostraría 0 filas y no podría
> insertar.**
>
> **La única vía de registro que existe es también la que B-7 rompe.**

Eso reordena la dependencia: no es *"falta una pantalla y mientras tanto usamos
el admin"*. Es que **no hay vía viable**, ni ahora ni después, sin trabajo previo.

---

## 3. Lo que ya está resuelto y no hacía falta decidir

**[MEDIDO]** La estructura está más completa de lo que D-4.1 dejó ver:

| Control | Estado |
|---|---|
| `ausencia_exige_motivo` | constraint en base |
| `disponibilidad_franja_valida` (`hora_fin > hora_inicio`) | constraint en base |
| RLS **habilitada y FORZADA** | ✔ |
| Políticas de aislamiento e inserción | **2** |
| Índice compuesto `(org_id, fecha, profile_id)` | **es exactamente el que usa H-05** |
| Los 4 campos que H-05 necesita | existen, NOT NULL |
| **El Supervisor NOC IA no escribe disponibilidad** | por diseño: ninguna función lo hace |

**No falta ningún campo para que H-05 funcione.**

---

## 4. Estado medido

```
operaciones_disponibilidad     0 filas · 6 índices · 2 constraints · RLS forzada · 2 políticas
rutas / serializers / vistas / permisos propios     ninguno
admin                          admin.site.register pelado (sin ModelAdmin)
usuarios con is_staff          1 de 5
perfiles                       {ADMIN: 1, USER: 4}  ← ningún SUPERVISOR ni OPERACIONES
django_admin_log               existe, 0 filas
campo_orden_trabajo            3 filas · 0 con programada_para · 0 en estado asignada
campo_asignacion_trabajo       3 filas · todas es_principal=True
business_calendar              1 fila · timezone=UTC · 0 festivos   (NO corregido)
```

**[MEDIDO]** H-05 tiene **ocho requisitos** y **cuatro faltan**. Registrar
ausencias **no basta**: M03 tiene 0 de 3 órdenes programadas y 0 de 3 en estado
`asignada`.

---

## 5. Gaps levantados — nueve

| # | Gap | Tipo |
|:--:|---|---|
| **A3-1** | **El admin no fija `app.current_org`; B-7 rompe la única vía** | **crítico** |
| A3-2 | No hay ruta, vista, serializer ni permiso | operativo |
| A3-3 | La auditoría no registra **qué cambió** | auditoría |
| A3-4 | `auditoria.ENTIDAD_*` no contempla disponibilidad | auditoría |
| A3-5 | Sin rango multi-día: 15 días de ausencia = 15 filas | datos |
| A3-6 | Anular = borrar: se pierde que alguien lo declaró | historial |
| A3-7 | `DisponibilidadTecnico` plenamente editable en el admin | seguridad |
| A3-8 | M03 sin órdenes programadas ni en `asignada` | dependencia |
| A3-9 | `business_calendar` UTC, 0 festivos | dependencia |

**Ninguno se corrigió.**

---

## 6. Regla de detención (§26)

Se aplicó **seis veces**:

| # | Lo que habría exigido cambiar algo | Qué se hizo |
|:--:|---|---|
| 1 | Hacer que el admin fije `app.current_org` (arregla A3-1) | **no** — es modificar código y middleware |
| 2 | Crear ruta/serializer/vista para disponibilidad | **no** — §26 |
| 3 | Agregar un `ModelAdmin` restrictivo como el de `PropuestaSupervisor` | **no** — §13 prohíbe modificar el Admin |
| 4 | Agregar `ENTIDAD_DISPONIBILIDAD` a `auditoria.py` | **no** — es código |
| 5 | Corregir `business_calendar` | **no** — §19 |
| 6 | Elegir un cargo responsable | **no** — candidatos listados con pros y contras, sin elegir |

---

## 7. Archivos

### Creados

| Archivo | Qué es |
|---|---|
| `A-3_GESTION_DISPONIBILIDAD.md` | 16 secciones + matriz de actores + matriz de decisiones + matriz de necesidades de H-05 |
| `A-3_IMPLEMENTACION.md` | este informe |

### NO modificados — verificado

| Área | Estado |
|---|---|
| `operaciones/models.py` · `DisponibilidadTecnico` | **sin cambios** |
| `operaciones/admin.py` | **sin cambios** |
| `operaciones/supervisor.py` · detectores · `_ordenes_en_riesgo` | **sin cambios** |
| `operaciones/habilidades.py` · fichas H-05 y H-C4 | **sin cambios**, huellas intactas |
| `PropuestaSupervisor` | **sin cambios** |
| `common/middleware/rls_context.py` | **sin cambios** |
| `campo/` · `business_hours/` · `cases/` | **sin cambios** |
| `nucleo/` completo | **sin cambios** |
| `directivas/K-01…K-05` | **sin cambios** |
| Rutas · serializers · permisos · RLS | **sin cambios** |
| Migraciones | **ninguna** |
| Datos | **ninguno creado ni modificado** |

**Código modificado: 0 archivos.**

---

## 8. Producción

# SIN CAMBIOS

```
ledger 50 · kill switch DETENIDO · 0 PropuestaSupervisor · 192 django_migrations
operaciones_disponibilidad 0 · business_calendar 1 / 0 festivos · tenant_config v146
```

Solo **lecturas** (`read_only=True`).

## 9. Efectos externos

# 0

---

## 10. Lo que este paso deja claro

**[MEDIDO]** Para que H-05 emita su primera señal hacen falta **cuatro cosas**, y
el orden no es el que se suponía:

1. **Resolver A3-1** — que exista una vía de registro que sobreviva a B-7;
2. decidir quién registra y cuándo (A-1, A-2 de D-4.1);
3. que alguien cargue una ausencia;
4. que **M03** programe una orden en estado `asignada`.

> **La dependencia más dura no es de negocio: es técnica y está delante de las
> decisiones.** Decidir quién carga ausencias antes de resolver A3-1 produce una
> decisión sin efecto — y con B-7, ni siquiera el admin serviría.

**Ninguna decisión fue tomada. Ningún cargo fue elegido. Ninguna persona fue
nombrada.**
