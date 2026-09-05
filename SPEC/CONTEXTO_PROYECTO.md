# CONTEXTO DEL PROYECTO — estado técnico actual

> Documento de contexto para el agente de desarrollo.
> Fuente de verdad para implementación: [MASTER_SPEC_CRM_AGENTE_IA_RAPILINK_v1.2.md](MASTER_SPEC_CRM_AGENTE_IA_RAPILINK_v1.2.md).
> `PRD.md` y `ARQUITECTURA.md` (raíz del repo) son documentación complementaria/histórica.

Cada afirmación de la sección "Estado actual conocido" lleva una etiqueta:

| Etiqueta | Significa |
|---|---|
| **CONFIRMADO** | Verificado directamente contra el sistema (base, código o respuesta real) |
| **CONOCIDO** | Documentado y consistente, pero no reverificado en este momento |
| **NO VERIFICADO** | No se pudo comprobar con los accesos disponibles |

---

## 1. Arquitectura

Una plataforma con dos mitades que corren juntas y hablan por red interna:

| Pieza | Qué es | Tecnología |
|---|---|---|
| **CRM** (`django-crm/`) | La plataforma de gestión y la interfaz web | Django + DRF (backend), SvelteKit (frontend) |
| **Motor** (`nucleo/`) | El agente IA: routing, herramientas, escalamiento, seguridad | Python 3.13 + Flask |
| **Base** | Persistencia única de ambas mitades | PostgreSQL sobre Supabase autohospedado (pooler Supavisor) |

El frontend habla con el motor por la red interna del compose (`http://motor:5000`); el motor habla con Postgres abriendo transacción con `set local role app_backend` y `set local app.current_tenant` — el aislamiento multitenant falla cerrado (sin tenant fijado, cero filas).

Sistemas externos: **WhatsApp** (Meta Cloud API), **WispHub** (`api.wisphub.io`), **SmartOLT** (header `X-Token`), **OpenAI** (solo embeddings) y **DeepSeek** (modelo de lenguaje).

## 2. Estructura relevante

```
nucleo/                  EL MOTOR — genérico, nunca conoce un cliente
  canales/               whatsapp y web; api.py es el punto de entrada HTTP
  config/                schema.py (validación), fuente.py (carga), editor.py (escritura)
  habilidades/           procedimientos que se cargan cuando hacen falta
  herramientas/          tipos genéricos: http · agregado · sql · batch · interno
  ingesta/               fragmentación, contextualización, versionado del corpus
  modelo/                cliente LLM y motor.py (el bucle de tool calling)
  observabilidad/        auditoría, consumo del LLM
  persistencia/          repositorios sobre Postgres
  recuperacion/          búsqueda híbrida y ensamblado del prompt
  seguimiento/           escalamiento, forzado, agendamiento, verificación de acción,
                         estado de escalada, seguimiento operativo
  seguridad/             listas blancas, verificación de identidad, guardia de salida

django-crm/              LA PLATAFORMA — CRM vendorizado + las pantallas propias
tenants/                 DATOS por empresa, sin código (semilla de alta)
supabase/                migraciones SQL
cli/                     utilidades operativas
evaluacion/              sets dorados por tenant
tests/                   guardas, incluida la del núcleo
SPEC/ · PROMPTS/         esta documentación
```

> **Nota:** el mapa de `ARQUITECTURA.md` lista 9 submódulos de `nucleo/`; los reales son 11 — no incluye `habilidades/` ni `seguimiento/`. Es desactualización de ese documento, no una discrepancia de diseño.

**La única regla de arquitectura:** `nucleo/` nunca conoce un cliente; `tenants/` es configuración sin código. Se verifica con `py -3.13 tests/test_nucleo_sin_tenants.py`.

**La configuración vive en la base, no en el YAML.** `asistente.tenant_config.config` (JSONB, versionado) es lo que el motor lee; `tenants/<slug>.config.yaml` es la semilla de alta. Dos caminos escriben esa tabla: `cli/cargar_config.py::cargar()` (el YAML) y `nucleo/config/editor.py::_editar()` (la interfaz). Los dos validan contra `TenantConfig` antes de guardar.

## 3. Flujo principal

```
Cliente
  → WhatsApp (o el simulador / la web del CRM)
  → nucleo/canales/api.py            webhook: firma HMAC, deduplicación, ACK inmediato
  → atender_turno()                  sesión, pausa por intervención humana, límites
  → motor.responder()                bucle de tool calling
  → router (cliente_final)           deriva por área con derivar_a_area
  → agente especializado             facturacion_cliente · soporte_tecnico_cliente · ventas
  → herramientas / datos             WispHub · SmartOLT · CRM · corpus · agregados
  → respuesta al cliente  |  escalamiento a una persona
```

El escalamiento no es una rama del prompt: vive en `nucleo/seguimiento/` y puede forzarse en código aunque el modelo no lo pida.

## 4. Agentes

Los roles son **configurables por tenant**. La lista exacta la manda siempre la configuración vigente en base, no este documento ni el YAML.

En la configuración actual de Rapilink hay **8 roles** — orientados al cliente (`cliente_final` como router, `facturacion_cliente`, `soporte_tecnico_cliente`, `ventas`), internos (`soporte`, `facturacion`, `administracion`) y `configuracion_guiada`, que permite conectar un sistema nuevo conversando con un ADMIN, con sondeo real de la API y aprobación humana antes de tocar el catálogo.

## 5. Sistemas externos

### WispHub — información comercial, de servicio y de facturación
Clientes, planes, facturas, saldo, estado de corte, zonas y **tickets** (crear, responder, cambiar estado — los tres con aprobación humana). Los procesos que la empresa definió como humanos (registrar el pago, reconectar) se ejecutan **en WispHub por una persona**, no por el agente.
La documentación de su API es una hipótesis: ningún filtro entra al catálogo sin verificarse con el método del valor imposible.

### SmartOLT — diagnóstico de fibra
Estado de la ONT, señal óptica, causa de caída (`dying-gasp` = sin energía; `LOSi/LOBi/LOFi` = falla óptica), incidentes por puerto, y una acción autorizada: **reinicio de ONT**. Ese reinicio no pide aprobación humana por decisión explícita del cliente, pero tiene precondiciones en código (`exige_previas`) y verificación posterior del efecto real.
La llave es `sn_onu` de WispHub, que funciona directo como identificador de SmartOLT.

### WhatsApp — entrada y salida de conversaciones
Única ruta del motor publicada a internet (`/canales/whatsapp/<tenant>`), autenticada por la firma del cuerpo (`X-Hub-Signature-256`), fail-closed. El envío proactivo vive deliberadamente fuera de ese prefijo.

### CRM — casos, intervención humana e interfaz operativa
Casos, historial de conversaciones, panel de escalamiento, cola de revisión, edición de agentes y las pantallas de configuración. Es donde una persona retoma lo que el agente escaló y devuelve el turno.

## 6. Estado actual conocido

### Configuración de producción
- `asistente.tenant_config` para `rapilink` está en **v117**, hash `6395c996…`, `actualizado_en` 2026-09-05 16:16:11 UTC. **CONFIRMADO** (lectura directa de la base).
- La configuración se movió varias veces el 04–05/09/2026 por trabajo legítimo en curso de otro colaborador. **CONFIRMADO**.

### Protección de configuración
- La guarda de alineación Git cubre las **dos direcciones** (copia adelantada y atrasada) y trata el estado indeterminado como bloqueo, en las dos puertas de escritura. Centralizada en `nucleo/config/editor.py::problemas_de_alineacion_git()`. Publicada en el commit `43469b1`. **CONFIRMADO** (28 aserciones en `tests/test_guarda_alineacion_git.py`).
- `llm` y `limites` están en `SECCIONES_EDITABLES`, así que una carga del YAML ya no puede borrarlas en silencio. **CONFIRMADO**.
- Que ese commit esté **corriendo en el contenedor productivo**: **NO VERIFICADO** — el despliegue no expone el commit, y no hay acceso a Dokploy desde el entorno de desarrollo.

### Consumo del LLM
- Conteo de tokens y costo por tenant, tope de gasto que ya puede dispararse, tarifas con ventanas de horario pico, y auditoría contra el saldo real del proveedor. **CONFIRMADO**: la migración `usage_daily.saldo_proveedor_usd` está aplicada en producción y tiene un valor real ($7.50 para el 2026-09-04).
- Pantalla `/consumo` en el CRM y endpoints propios en el motor. **CONOCIDO**.

### Habilidades
- Procedimientos versionados en tabla propia con RLS, que se cargan por código y rol. **CONOCIDO**.

### Pruebas
- **50 Golden Cases** en `evaluacion/rapilink.casos.yaml`. **CONFIRMADO**.
- La suite de `tests/` pasa completa salvo `test_informes.py`, que falla por `reportlab` ausente en el entorno local. **CONFIRMADO**.

### Catálogo vigente
- 56 herramientas; 4 con aprobación humana (`crear_ticket`, `responder_ticket`, `actualizar_estado_ticket`, `agregar_promesa_pago`); 3 con precondiciones en código; 3 que fuerzan escalada si fallan. **CONFIRMADO**.
