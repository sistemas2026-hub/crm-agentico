---
name: bottlecrm-api
description: Integrar o ampliar la conexion con la API de BottleCRM (django-crm). Usar al agregar herramientas de BottleCRM al catalogo de un tenant, o al tocar filtros, envolturas de respuesta y auth contra ese sistema. Contiene los hallazgos ya confirmados en vivo (Docker local, agosto 2026).
---

# API de BottleCRM — lo que ya se verifico en vivo

BottleCRM (`github.com/Django-CRM/Django-CRM`) es el CRM compartido para el
producto comercial (ver `PRD.md`/plan de fases). Repo clonado aparte, en
`c:\Users\Usuario\django-crm` — no vive dentro de `crm-agentico` (ver
ARQUITECTURA.md: nucleo/ nunca conoce un sistema concreto, esto es config de
tenant, no codigo).

## Auth

`Authorization: Bearer bcrm_pat_...` — mismo `auth_esquema: Bearer` que ya es
el default de `Herramienta` (a diferencia de WispHub, que necesita
`Api-Key`). El token se generа en **Settings → API tokens** (o
`POST /api/profile/tokens/` estando logueado) y **hay que mintearlo con
`scopes` explicitos** (ej. `{"scopes": ["cases:read"]}`) — confirmado en
codigo y en vivo: sin `scopes` declarados el token queda con acceso total de
lectura Y escritura, no lo que quiere una herramienta de solo lectura. Un
token sin el scope correcto responde `403` con
`{"detail": "This token is not scoped for write access to ..."}`.

El MCP que este proyecto tenia (`/mcp`) **se eliminó** — la via oficial hoy
es API REST + PAT, documentado en su propio
`docs/integrations/ai-agents.md`.

## El sobre de respuesta NO es el estandar de DRF — confirmado en vivo

A diferencia de lo que uno asumiria de una API DRF tipica
(`{count, next, previous, results}`), **cada endpoint tiene su propio sobre
a medida**. Verificado con datos reales (`GET /api/cases/`, agosto 2026):

```json
{
  "open_count": 4, "urgent_count": 0, "awaiting_first_reply": 4,
  "cases_count": 5, "offset": 2,
  "cases": [ {"...": "un caso"} ],
  "status": [...], "priority": [...], "type_of_case": [...],
  "accounts_list": [...], "contacts_list": [...], "users": [...]
}
```

Por eso existe `Herramienta.extraer_de` en `nucleo/config/schema.py`: para
`/api/cases/` hace falta `extraer_de: cases` antes de que
`nucleo/seguridad/listas_blancas.py` pueda filtrar los campos (esa funcion
solo reconoce dict suelto, lista, o `{results, count}` — este sobre no
encaja en ninguna forma sin extraer la clave primero).

**No asumir que otro endpoint (`/api/leads/`, etc.) usa el mismo patron de
sobre** — cada uno es distinto (confirmado por `docs/api/conventions.md` del
propio proyecto). Sondear cada uno antes de conectarlo, igual que con
WispHub.

## Campos reales de un `case` (verificado en vivo, no solo por codigo)

```
id, name, status, priority, case_type, closed_on, description,
created_by, created_at, is_active, account, contacts, teams,
assigned_to, tags, org, custom_fields, escalation_count,
last_escalation_fired_at, sla_first_response_hours, sla_resolution_hours,
first_response_at, resolved_at, sla_paused_at,
first_response_sla_deadline, resolution_sla_deadline,
is_sla_first_response_breached, is_sla_resolution_breached,
parent, is_problem, parent_summary, child_count, time_summary
```

`account`, `assigned_to`, `tags`, `contacts`, `teams` vienen como **objetos
anidados pesados** (ej. `account` trae el `AccountSerializer` completo, con
telefono, ingresos anuales, direccion...) — mismo cuidado que con
`servicio` en los tickets de WispHub: una lista blanca que deje pasar
`account` entero filtraria datos de la cuenta del cliente que nadie pidio.
Usar notacion con punto (`account.id`, `account.name`) si hace falta algo de
ahi, nunca el objeto entero.

`status`: `New, Assigned, Pending, Closed, Rejected, Duplicate`.
`priority`: `Low, Normal, High, Urgent`. `case_type`: `Question, Incident,
Problem`.

## Filtros de `/api/cases/` verificados en vivo (agosto 2026)

`nucleo/modelo/motor.py` arma el esquema de argumentos de una herramienta a
partir de `Herramienta.filtros_verificados` (el mismo campo que ya existia
para herramientas tipo `agregado`, reusado ahora tambien para `http`) --
cada entrada ahi ya paso el metodo del valor imposible, nunca es un filtro
sin probar.

| Filtro (clave interna) | `param` real | Tipo | Notas |
|---|---|---|---|
| `buscar` | `search` | texto | Contains sobre `name` O `description`. Imposible=0, real=cuenta esperada. |
| `estado` | `status` | enum | Valores API: `New, Assigned, Pending, Closed, Rejected, Duplicate`. El YAML mapea claves en espanol -> el valor real que espera la API. |

Otros filtros que el codigo fuente de `cases/views.py` expone pero que
**todavia no se sondearon en vivo** (no asumir que sirven sin probarlos
igual que los de arriba): `priority`, `account`, `case_type`,
`assigned_to`, `tags`, `created_at__gte/__lte`, `sla_breached`.

## Entorno local de referencia (Docker, agosto 2026)

- `docker compose up --build` desde `django-crm/` — **cuidado con CRLF**: si
  se clona en Windows con `core.autocrlf=true`, `docker/backend/entrypoint.sh`
  se rompe dentro del contenedor Linux (`set: -: invalid option`,
  `$'\r': command not found`). Se corrige con
  `sed -i 's/\r$//' docker/backend/entrypoint.sh` en el archivo del host (esta
  montado como volumen, no hace falta rebuildear la imagen).
- `docker compose exec backend python manage.py seed_data --email x@x.test`
  crea la organizacion `MicroPyramid` con datos de prueba (incluye 5 `cases`).
- `docker compose exec backend python manage.py devlogin x@x.test --org MicroPyramid`
  da un JWT sin pasar por OAuth — usarlo para mintear el PAT via
  `POST /api/profile/tokens/` sin tocar el navegador.
