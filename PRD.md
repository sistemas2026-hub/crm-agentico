# PRD — Plataforma Interna de IA con SLM

> **Documento de Requisitos de Producto (Product Requirements Document)**
> Versión 1.0 · Asistente interno multi-área basado en un modelo de lenguaje pequeño (SLM)

---

## 1. Resumen ejecutivo

Plataforma interna de inteligencia artificial que permite a los colaboradores de la empresa —según su área— realizar consultas en lenguaje natural y generar informes, conectándose a los sistemas internos de la empresa (empezando por WispHub). El motor es un **modelo de lenguaje pequeño (SLM)** que corre localmente, sin depender de proveedores externos de nube, lo que protege los datos de clientes y reduce costos.

El sistema **no entrena** un modelo: usa un SLM pre-entrenado (Qwen3) y lo integra mediante *tool calling* a las APIs internas, con capas de validación, filtrado de datos sensibles y control de acceso por área.

**Estado actual:** el módulo de **Soporte** está construido y validado de punta a punta contra la API de WispHub en producción.

---

## 2. Problema y objetivo

### Problema
Los colaboradores necesitan consultar información dispersa en sistemas internos (clientes, facturas, tickets, datos de red) y generar informes. Hoy esto requiere navegar manualmente por las plataformas, conocer dónde está cada dato, y armar reportes a mano.

### Objetivo
Ofrecer un asistente conversacional interno que:
- Responda consultas en lenguaje natural sobre los datos de la empresa.
- Genere informes bajo demanda.
- Se comporte y muestre información **según el área/rol** del colaborador.
- Mantenga los datos de clientes seguros y dentro de la infraestructura de la empresa.

### Métricas de éxito
- Tiempo de consulta reducido frente al proceso manual.
- Adopción por parte de los colaboradores de cada área.
- Cero exposición de datos sensibles innecesarios (IP, MAC, credenciales) al modelo.
- Cero acciones sensibles (pagos) ejecutadas sin confirmación humana.

---

## 3. Usuarios y áreas

La plataforma es de **uso interno**. Quien la usa es siempre un **colaborador**, nunca el cliente final. El comportamiento y los permisos cambian por área:

| Área | Qué consulta / hace | Datos que SÍ necesita | Datos que NO debe ver |
|------|--------------------|----------------------|----------------------|
| **Soporte** | Estado de clientes, tickets | Nombre, estado, plan, facturas al día | IP, MAC, credenciales |
| **Facturación** | Facturas, pagos, cartera | Facturas, montos, estados de pago | Datos técnicos de red |
| **Técnica** | Datos de red, conectividad | IP, MAC, router, zona, ONU | (acceso técnico amplio) |
| **Administración** | Informes agregados | Datos consolidados/anonimizados | PII individual innecesaria |

> **Principio rector:** control de acceso por rol. Cada área ve solo las herramientas y campos que le corresponden.

---

## 4. Alcance

### 4.1 MVP — Módulo de Soporte (CONSTRUIDO ✅)

Ya implementado y funcionando:
- Asistente conversacional en consola.
- Consulta de cliente **por ID de servicio** y **por cédula**.
- Consulta de facturas y de tickets.
- Comportamiento de "asesor" (habla del cliente en tercera persona, no lo saluda).
- Filtro de PII: la IP, MAC y credenciales nunca llegan al modelo.
- Credenciales protegidas en archivo `.env`.
- Acción sensible (`registrar_pago`) con confirmación humana obligatoria.

### 4.2 Visión completa — Plataforma multi-área (POR CONSTRUIR)

- **Identidad y rol:** login que identifica al colaborador y su área.
- **Catálogo de herramientas por área:** cada área accede solo a sus herramientas.
- **Filtros de campo por área:** la misma consulta devuelve distintos campos según el rol.
- **Generación de informes:** consultas que agregan datos y producen un documento (texto, Excel o PDF).
- **Interfaz:** pasar de consola a una interfaz web interna.
- **Registro y auditoría:** log de quién consultó qué (sin registrar datos sensibles en texto plano).

### 4.3 Fuera de alcance (por ahora)
- Fine-tuning / entrenamiento del modelo.
- Atención directa al cliente final (la plataforma es interna).
- Integraciones con sistemas distintos a WispHub (fase posterior).

---

## 5. Requisitos funcionales

### Módulo Soporte (hecho)
- **RF-01:** Consultar datos de un cliente por ID de servicio.
- **RF-02:** Consultar datos de un cliente por número de cédula (endpoint `api/clientes/?cedula=`).
- **RF-03:** Consultar facturas de un cliente y su estado (pagada/pendiente).
- **RF-04:** Consultar estado de un ticket de soporte.
- **RF-05:** Registrar un pago (acción sensible, requiere confirmación humana).
- **RF-06:** Responder en español, en tercera persona sobre el cliente.
- **RF-07:** No inventar datos; si no existe, indicarlo explícitamente.

### Plataforma multi-área (por construir)
- **RF-08:** Autenticar al colaborador e identificar su área.
- **RF-09:** Exponer al modelo solo las herramientas permitidas para el área.
- **RF-10:** Filtrar los campos devueltos según el área.
- **RF-11:** Generar informes bajo demanda a partir de consultas en lenguaje natural.
- **RF-12:** Exportar informes a formato descargable (Excel/PDF).
- **RF-13:** Registrar auditoría de consultas por usuario.

---

## 6. Requisitos no funcionales

- **RNF-01 · Privacidad:** los datos de clientes no salen de la infraestructura de la empresa. El SLM corre local/on-premise. Cumplimiento con la Ley 1581 de 2012 (protección de datos personales, Colombia). *Validar con el área legal.*
- **RNF-02 · Seguridad en capas:** las reglas duras (filtrado de PII, confirmación de acciones sensibles) se aplican en **código**, no solo en el prompt. El prompt guía el comportamiento; el código garantiza los límites no negociables.
- **RNF-03 · Costo:** volumen bajo (~300 consultas/día). Un SLM local elimina el costo por token de proveedores externos.
- **RNF-04 · Rendimiento:** consultas de lectura con respuesta ágil. Modelo principal de 4B suficiente para las tareas actuales; escalar a 8–14B solo si un área requiere razonamiento más complejo.
- **RNF-05 · Mantenibilidad:** herramientas, filtros y prompts parametrizados por área, para replicar el patrón sin reescribir el motor.

---

## 7. Arquitectura técnica

### 7.1 Stack

| Componente | Tecnología |
|-----------|-----------|
| Modelo (motor) | Qwen3 4B vía **Ollama** (local) |
| Lenguaje | Python 3.13 |
| Cliente del modelo | librería `ollama` |
| Llamadas HTTP | `requests` |
| Credenciales | `python-dotenv` (archivo `.env`) |
| API de datos | WispHub REST API (JSON, auth por API Key) |

Modelos alternativos ya evaluados para reparto por tarea: **phi4-mini** (clasificación y extracción, el más rápido), **gemma3:4b** / **qwen3:4b** (generación), **qwen3** (tool calling, el más fiable).

### 7.2 Componentes y flujo

```
Colaborador (lenguaje natural)
        │
        ▼
[ 1. Identidad y área ]  ──► define herramientas y filtros permitidos
        │
        ▼
[ 2. Motor SLM (Qwen3 + Ollama) ]  ──► decide qué herramienta llamar y con qué argumentos
        │
        ▼
[ 3. Capa de validación ]  ──► valida los argumentos (el modelo propone, el código dispone)
        │
        ▼
[ 4. Confirmación humana ]  ──► solo para acciones sensibles (pagos)
        │
        ▼
[ 5. Ejecución de herramienta ]  ──► llama a la API de WispHub (o simulado)
        │
        ▼
[ 6. Filtro de PII ]  ──► descarta campos sensibles según el área
        │
        ▼
[ 7. Motor SLM redacta ]  ──► respuesta final en español, tercera persona
        │
        ▼
Colaborador (respuesta / informe)
```

### 7.3 Patrón de tool calling (dos llamadas al modelo)

1. **Primera llamada:** se envía el mensaje del usuario + la lista de herramientas. El modelo responde con `tool_calls` (qué herramienta y qué argumentos) o con texto directo.
2. El código **valida**, **confirma** (si es sensible), **ejecuta** contra la API y **filtra** el resultado.
3. El resultado filtrado se agrega al historial con rol `tool`.
4. **Segunda llamada:** el modelo redacta la respuesta final usando el dato ya en mano.

### 7.4 Seguridad en dos capas (crítico)

- **Prompt (`SYSTEM`):** define el comportamiento deseable (tono, tercera persona, no inventar). Es guía, no garantía — un modelo puede ser inducido a desviarse.
- **Código:** garantiza los límites no negociables. Aunque el prompt fallara:
  - El **filtro de campos** (lista blanca por herramienta/área) impide técnicamente que IP, MAC o credenciales lleguen al modelo.
  - La **confirmación manual** impide ejecutar un pago sin aprobación humana.

### 7.5 Parametrización por área (guía para extender)

El patrón para escalar de un área a varias:

```python
# El SYSTEM se construye según el área del colaborador
def construir_system(area): ...

# Cada área ve solo sus herramientas
HERRAMIENTAS_POR_AREA = {
    "soporte":     [consultar_cliente, consultar_cliente_por_cedula, consultar_ticket],
    "facturacion": [consultar_facturas, registrar_pago],
    "tecnica":     [consultar_datos_red],
    # ...
}

# Cada área tiene su propia lista blanca de campos
CAMPOS_POR_AREA = {
    "soporte":  ["id_servicio", "usuario_rb", "estado", "plan_internet"],
    "tecnica":  ["id_servicio", "ip", "mac_cpe", "router", "zona"],  # técnica SÍ ve red
    # ...
}
```

El motor (validación, tool calling, filtrado, confirmación) **no cambia**: solo recibe distintas herramientas y filtros según el área. Lo construido para Soporte es la plantilla.

### 7.6 Notas de integración con WispHub

- **Base URL producción:** `https://api.wisphub.net` (confirmar en la doc oficial).
- **Auth:** header `Authorization: Api-Key <clave>` (formato confirmado en producción).
- **Endpoints usados:** `/api/clientes/{id}/`, `/api/clientes/?cedula=`, `/api/facturas/`, `/api/tickets/{id}/`, `/api/facturas/{id}/pagar/`.
- El endpoint por cédula devuelve una **búsqueda** (lista o `results`); tomar el primer resultado.
- Sandbox de pruebas disponible: `https://sandbox-api.wisphub.net`.

---

## 8. Roadmap por fases

| Fase | Entregable | Estado |
|------|-----------|--------|
| **0** | Prototipo de soporte en consola contra WispHub | ✅ Hecho |
| **1** | Consolidar soporte: prompt de asesor, filtro PII, consulta por cédula | ✅ Hecho |
| **2** | Login + identidad de área; parametrizar herramientas y filtros por rol | Pendiente |
| **3** | Replicar patrón a Facturación y Técnica | Pendiente |
| **4** | Generación de informes + exportación (Excel/PDF) | Pendiente |
| **5** | Interfaz web interna (reemplaza la consola) | Pendiente |
| **6** | Auditoría/logs y despliegue en servidor on-premise | Pendiente |

---

## 9. Despliegue

- **Desarrollo:** laptop actual (RTX 3050, 4 GB VRAM, 32 GB RAM). Suficiente para desarrollar y probar con modelos de 3–4B.
- **Producción:** servidor dedicado / on-premise (por privacidad de datos de clientes y disponibilidad para varios colaboradores). La laptop **no** es el entorno de producción.
- **Recomendación de modelo en servidor:** GPU de 16–24 GB para correr con holgura un modelo principal de 8–14B si alguna área lo requiere, manteniendo 4B para tareas ligeras.

---

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Fuga de datos de clientes | SLM local + filtro de PII en código + `.env` fuera de la nube |
| Pago ejecutado por error del modelo | Confirmación humana obligatoria en código |
| El modelo inventa datos | Prompt "no inventar" + siempre consultar herramienta; validación |
| Modelo inducido a desviarse del prompt | Límites duros en código, no solo en prompt |
| Incumplimiento normativo (Ley 1581) | Validación con área legal antes de escalar; auditoría |
| Crecer a todas las áreas a la vez | Escalar por fases: consolidar un área antes de replicar |

---

## 11. Notas para el asistente de código (IDE)

- El proyecto **no entrena** modelos; integra un SLM pre-entrenado vía tool calling. No sugerir fine-tuning salvo que se identifique una necesidad concreta que el prompting/RAG no resuelva.
- Respetar la **arquitectura de dos capas de seguridad**: nunca mover el filtrado de PII ni la confirmación de acciones sensibles a solo el prompt.
- Al agregar herramientas nuevas, replicar el patrón completo: definición → validación → ejecución (simulada + real) → filtro de campos.
- Mantener las credenciales solo en `.env`, nunca en el código.
- El código base de referencia es el módulo de Soporte (`soporte_wisphub.py`).
