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

### Norte — el cerebro de la empresa

El destino de esta plataforma no es un buscador con buenos modales: es la **capa única de acceso al conocimiento operativo de la empresa**. Que cualquier colaborador pregunte en su idioma y obtenga la respuesta, sin importar en qué sistema viva el dato ni si la respuesta exige cruzar tres fuentes.

Ese norte se persigue creciendo en **un solo eje**, y explícitamente **no** en el otro:

| Eje | Dirección | Por qué |
|---|---|---|
| **Alcance** — cuántos sistemas ve, cuántas preguntas puede responder | **Crecer sin techo** | Aquí vive el valor. Un cerebro es la suma de lo que sabe consultar. |
| **Autonomía** — cuánto decide o afirma el modelo por sí solo | **No crecer** | Aquí vive el riesgo. Ver la lección de `gemma3` en §7.1. |

> **Principio central:** *la inteligencia del sistema no está en el modelo, está en el catálogo de herramientas.* El modelo es la interfaz —traduce lenguaje a llamadas y datos a frases—; el conocimiento vive en los sistemas de la empresa y las garantías viven en el código. Hacer al sistema más inteligente significa **darle más alcance**, nunca darle más confianza.

**Qué falta para merecer el nombre** (ninguno de estos puntos se resuelve con un modelo mejor):

1. **Consultas agregadas.** Hoy toda herramienta responde sobre *un* cliente. Un cerebro responde "cuántos morosos hay en la zona norte" o "cómo viene la cartera contra el mes pasado". Requiere herramientas nuevas, no un modelo nuevo.
2. **Más fuentes.** WispHub es la primera, no la única.
3. **Identidad y área** (Fase 2). Sin saber quién pregunta no se puede ampliar el acceso a los datos sin ampliar el riesgo. Es el prerrequisito de todo lo demás.
4. **Memoria y auditoría.** Hoy la conversación muere al cerrar la consola.
5. **Informes** como salida, no solo frases en pantalla.

**Consecuencia técnica del norte:** un modelo de 4B es buen enrutador (medido: elige correctamente la herramienta), pero no es analista. Razonar sobre datos agregados y redactar un informe gerencial exige más capacidad — el salto a 8–14B en servidor (§9) deja de ser opcional el día que se persiga este norte en serio.

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
| **Soporte** | Estado de clientes, tickets | Nombre, estado, plan, facturas al día, saldo, fecha de corte, zona, **contacto (email, teléfono, dirección)** | IP, MAC, credenciales, precios del plan |
| **Facturación** | Facturas, pagos, cartera | Facturas, montos, estados de pago | Datos técnicos de red |
| **Técnica** | Datos de red, conectividad | IP, MAC, router, zona, ONU | (acceso técnico amplio) |
| **Administración** | Informes agregados | Datos consolidados/anonimizados | PII individual innecesaria |

> **Principio rector:** control de acceso por rol. Cada área ve solo las herramientas y campos que le corresponden.

---

## 4. Alcance

### 4.1 MVP — Módulo de Soporte (CONSTRUIDO ✅)

Ya implementado y funcionando:
- Asistente conversacional en consola.
- Consulta de cliente **por ID de servicio** y **por cédula** (`consultar_cliente_por_cedula`).
- Consulta de facturas y de tickets.
- Comportamiento de "asesor" (habla del cliente en tercera persona, no lo saluda).
- Filtro de PII: la IP, MAC y credenciales nunca llegan al modelo. Cubre las tres formas
  de respuesta de WispHub (objeto suelto, lista y paginado `{count, results}`) y es
  **fail-closed**: una herramienta sin lista blanca no deja pasar ningún dato.
- Toda la configuración (clave, modo real/simulado, URL base, modelo) vive en `.env`;
  el código no trae credenciales ni interruptores quemados. Por defecto arranca en **modo simulado**.
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
- **RF-04:** Consultar estado de un ticket de soporte por su número.
- **RF-04b:** Consultar los tickets **abiertos de un cliente**, por ID de servicio o por cédula.
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
- **RF-14:** Responder consultas **agregadas** (conteos, totales, comparaciones por periodo o zona) mediante herramientas parametrizadas que el modelo compone y el código calcula (ver decisión §12.5).
- **RF-15:** Toda respuesta agregada debe declarar los filtros y el periodo con que se calculó, para que el colaborador pueda detectar una interpretación errónea de su pregunta.

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
| Configuración y credenciales | `python-dotenv` (archivo `.env`) |
| API de datos | WispHub REST API (JSON, auth por API Key) |

**Reparto por tarea — medido sobre el flujo real (julio 2026):**

| Modelo | 1ª llamada (elegir herramienta) | 2ª llamada (redactar el dato) |
|---|---|---|
| **qwen3:4b** | ✅ El fiable en tool calling. En uso. | ✅ Correcto, 15.6 s (razona antes de responder) |
| **phi4-mini** | Sin evaluar aquí | ✅ Correcto, 6.9 s (~2× más rápido) |
| **gemma3:4b** | Sin evaluar aquí | ❌ **No usar.** Su plantilla no maneja el rol `tool`: ignoró el dato entregado e **inventó** cliente, plan y factura. Viola RF-07. |

Configurable por `.env`: `MODELO_SLM` (decide) y `MODELO_REDACCION` (redacta). Por defecto ambos son `qwen3:4b`.

> **Lección:** un modelo que no soporta el rol `tool` no falla con error — responde con datos inventados y tono seguro. Antes de cambiar de modelo hay que verificar que respeta el dato de la herramienta, no solo que "responde bien".

**Sobre el razonamiento de Qwen3:** el modelo razona antes de responder y Ollama devuelve eso en un campo `thinking` separado. Medido: `think=False` **no** lo apaga (solo hace que el razonamiento crudo caiga en `content`, a la vista del asesor), y el interruptor `/no_think` tampoco. La estrategia es dejar que Ollama lo separe y **descartarlo del historial** — reenviarlo acumula 2.500–5.400 caracteres inútiles por turno. Un turno completo (dos llamadas + herramienta) toma ~25 s.

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
  - El filtro es **fail-closed**: si una herramienta nueva se agrega sin lista blanca, su resultado se descarta entero en vez de pasar crudo. Al extender el sistema, el olvido falla del lado seguro.
  - El filtro se aplica a **cualquier forma** de respuesta (objeto, lista, paginado). Un filtro que solo entienda objetos sueltos deja pasar listas completas con PII.
  - El filtro alcanza los **objetos anidados** (notación `servicio.id_servicio`). Dejar pasar un objeto entero porque su nombre está en la lista blanca es una fuga: el `servicio` que viene dentro de un ticket incluye la IP del cliente y el router con sus credenciales.
  - La **confirmación manual** impide ejecutar un pago sin aprobación humana.

#### Límite conocido: los campos de texto libre

El filtro controla **qué campos** pasan, no **qué contiene** cada campo. Un campo de texto libre puede traer embebido cualquier dato, y la lista blanca no lo ve.

Caso real detectado en producción: la `descripcion` de un ticket de instalación contenía nombre completo, teléfono, email, dirección, coordenadas GPS, número de documento, plan contratado con precio y un enlace público al PDF de la solicitud — todo en un solo string de 419 caracteres.

Se decidió **mantener `descripcion`**: es el contenido del ticket y Soporte no puede trabajar sin él. Pero conviene tenerlo presente:

- La minimización de datos que da la lista blanca **no aplica** a los campos de texto libre. Ahí llega lo que el operador haya escrito.
- Si en algún momento se exige minimización estricta (auditoría legal, área con acceso restringido), un campo así necesita **redacción por patrón** (regex de cédulas, teléfonos, emails, URLs) además de la lista blanca. No está implementado.
- Al agregar un campo nuevo a una lista blanca, preguntarse si es texto libre. Si lo es, la decisión no es solo "¿este campo sirve?" sino "¿qué puede venir escrito adentro?".

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

Documentación oficial: <https://wisphub.net/api-docs/> (el spec OpenAPI está en `https://wisphub.net/static/yaml/api/api-main.yaml`).

- **Base URL producción:** `https://api.wisphub.io` — confirmado en vivo. La doc usa `api.wisphub.net` en sus ejemplos; **nuestras llamadas van a `.io`**. Configurable vía `WISPHUB_BASE_URL`.
- **Auth:** header `Authorization: Api-Key <clave>`. La clave se genera en Lista de Personal → "Generar Mi APIKey", y **hereda los permisos del usuario** que la generó (Lista de Clientes, Lista de Facturas, Registrar Pagos…).
- Todas las respuestas de lista son paginadas: `{count, next, previous, results}`, con `limit` y `offset`.

**Endpoints usados (verificados contra la API real, julio 2026):**

| Uso | Endpoint | Nota |
|---|---|---|
| Cliente por cédula | `GET /api/clientes/?cedula=` | Búsqueda exacta. |
| Cliente por ID | `GET /api/clientes/?id_servicio=` | **No** se usa `/api/clientes/{id}/`: ver abajo. |
| Facturas de un cliente | `GET /api/facturas/?cliente=<usuario>` | **El filtro es el `usuario`, no el ID.** Ver abajo. |
| Ticket | `GET /api/tickets/{id_ticket}/` | |
| Registrar pago | `POST /api/facturas/{id_factura}/registrar-pago/` | Cuerpo: `{total_cobrado, accion, forma_pago, referencia, fecha_pago}`. `accion`: `0` solo registra, `1` registra y reactiva el servicio. |

**Dos trampas que costaron un diagnóstico y conviene no volver a pisar:**

1. **`/api/clientes/{id}/` (detalle) devuelve campos DISTINTOS de `/api/clientes/` (lista).** El detalle trae `facturas_pagadas` pero **no** `estado_facturas`, `saldo` ni `fecha_corte` — justamente los que necesita Soporte. Por eso ambas consultas de cliente usan el endpoint de lista con filtro: misma forma, una sola lista blanca.

2. **`GET /api/facturas/?cliente=` espera el `usuario` del cliente** (formato `nombre-completo@empresa`), **no** el `id_servicio`. Pasarle el ID devuelve `count: 0` en silencio, y cualquier parámetro mal escrito (`id_servicio`, `cedula`, `search`…) es **ignorado**: el API responde con las 8.700 facturas de la empresa. Las dos fallas son silenciosas y producen respuestas confiadamente falsas — "no tiene facturas" para todos, o las facturas de otro. Mitigación en código: buscar primero el `usuario` del cliente, y **verificar** que las filas devueltas le pertenecen antes de entregarlas.

**Otros datos útiles del spec** (para las herramientas de agregación de §12.5):

- `/api/facturas/` filtra por `estado` (1 Pendiente de Pago, 2 Pagada, 3 Cancelada, 4 En Revisión, 5 Se Transfirió), `zona`, `cajero`, `facturadas`, y rangos `fecha_emision__range_0/_1`, `fecha_vencimiento__range_*`, `fecha_pago__range_*`. **Si no se pasa filtro de fecha, aplica por defecto los últimos 3 meses de emisión.**
- `/api/clientes/` filtra por `estado` (1 Activo, 2 Suspendido, 3 Cancelado, 4 Gratis), `plan_internet`, `router`, `sectorial`, `tecnico`, `asesor`, `ciudad`, `localidad`, y variantes `__contains`. **No** tiene filtro por zona.
- `/api/tickets/` filtra por `estado` (**numérico**: 1 Nuevo, 2 En Progreso, 4 Cerrado; `?estado=Nuevo` devuelve 0 sin error), `fecha_creacion_0/_1` y `mis_tickets`. Volumen real: 268 nuevos, 13 en progreso, 2.255 cerrados.
- **`/api/tickets/` NO tiene filtro por cliente.** Probados 8 nombres de parámetro (`servicio`, `cliente`, `id_servicio`, `usuario`, `search`, `cliente__usuario`…): todos ignorados, devuelven los 2.536. El cliente tampoco expone sus tickets (`/clientes/{id}/` y `/clientes/{id}/perfil/` no tienen ningún campo de soporte; `informacion_adicional` viene vacío). Solución: filtrar por estado en el API y cruzar por cliente en código — solo los abiertos (~280, 3 páginas, ~6 s); barrer los 2.255 cerrados no vale una consulta interactiva.
- **El `next` del paginado viene en `http://`** (`http://api.wisphub.io/api/tickets/?...`). Seguirlo enviaría la clave del API en texto plano: se pagina con `offset` propio sobre HTTPS y no se sigue nunca esa URL.
- Endpoints aún no usados que sirven al norte: `/api/clientes/{id}/saldo/`, `/api/zonas/`, `/api/plan-internet/`, `/api/staff/`, `/api/gastos/`.
- Sandbox: `https://sandbox-api.wisphub.net` (según doc; no probado).

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
| El modelo calcula mal un dato agregado | No calcula: compone la consulta y Python hace la cuenta (§12.5) |
| El modelo interpreta mal la pregunta y da un número exacto sobre el filtro equivocado | La respuesta declara siempre filtros y periodo usados (RF-15) |
| Consulta agregada que desborda el contexto del modelo | Tope duro de filas; se envía resumen + top-N, nunca el dataset (§12.5) |

---

## 11. Notas para el asistente de código (IDE)

- El proyecto **no entrena** modelos; integra un SLM pre-entrenado vía tool calling. No sugerir fine-tuning salvo que se identifique una necesidad concreta que el prompting/RAG no resuelva.
- Respetar la **arquitectura de dos capas de seguridad**: nunca mover el filtrado de PII ni la confirmación de acciones sensibles a solo el prompt.
- Al agregar herramientas nuevas, replicar el patrón completo: definición → validación → ejecución (simulada + real) → filtro de campos. **Obligatorio** registrar su entrada en `CAMPOS_PERMITIDOS`: sin ella el filtro descarta el resultado completo (fail-closed) y la herramienta no devolverá nada.
- Mantener la ruta simulada y la real devolviendo la **misma forma** de dato; si divergen, lo que funciona en pruebas falla en producción.
- Mantener credenciales y conmutadores de entorno solo en `.env`, nunca en el código.
- **Nunca pedirle al modelo que calcule.** Conteos, sumas, promedios y comparaciones se resuelven en Python; el modelo solo compone los parámetros de la consulta y redacta el resultado (§12.5). Si una implementación propuesta depende de que el modelo sume, está mal planteada.
- El código base de referencia es el módulo de Soporte (`soporte_wisphub.py`).

---

## 12. Del asistente al cerebro — impacto sobre lo construido

Análisis del código actual (`soporte_wisphub.py`) frente al norte de §2. **Nada hay que tirar.** El motor sobrevive; lo que cambia son firmas y dos supuestos estructurales.

### 12.1 Sobrevive sin tocar

- El patrón por herramienta: definición → validación → ejecución (simulada + real) → filtro. Es la unidad que se replica N veces.
- El filtro **fail-closed** y su normalización de formas de respuesta.
- La confirmación humana como concepto y `ACCIONES_SENSIBLES` como registro.
- Configuración por `.env` y el descarte del `thinking` del historial.

### 12.2 Cambios de firma (mecánicos)

| Hoy | Cerebro | Motivo |
|---|---|---|
| `filtrar_campos(nombre, datos)` | `filtrar_campos(nombre, datos, area)` | `CAMPOS_PERMITIDOS` pasa a `CAMPOS_POR_AREA` (§7.5): técnica ve IP, soporte no. |
| `HERRAMIENTAS` (constante) | `herramientas_de(area)` | Cada área ve solo su catálogo. |
| `SYSTEM` (constante) | `construir_system(area)` | El tono y las reglas cambian por rol. |

### 12.3 Cambios estructurales (los que cuestan)

1. **La confirmación está atada a la consola.** `requiere_confirmacion()` llama a `input()` y bloquea. En una interfaz web el flujo se parte en dos peticiones —proponer la acción, ejecutarla tras la aprobación—, lo que obliga a `responder()` a dejar de ser una función síncrona y pasar a manejar *estado* (una acción pendiente por sesión). Es el refactor más profundo del salto a web.
2. **`responder()` hace una sola ronda de herramientas.** Las preguntas de cerebro encadenan pasos ("buscá el cliente por cédula y *después*, con su ID, traeme sus facturas"). Hay que convertirlo en bucle con tope de iteraciones —el tope no es opcional: sin él, un modelo confundido puede llamar herramientas indefinidamente.
3. **El historial es una lista única, de un usuario, sin poda.** Multiusuario exige sesión por colaborador; conversaciones largas exigen ventana de contexto acotada.
4. **El filtro protege *qué* campos, no *cuántos* registros.** Una consulta agregada puede devolver miles de filas; volcarlas al contexto de un modelo de 4B lo desborda y degrada la respuesta. Resuelto por la decisión de §12.5.
5. **Trazas por `print()`** → logging estructurado para cumplir RF-13 (auditoría), sin volcar datos sensibles en texto plano.
6. **`ollama.chat` asume `localhost`.** Con el modelo en un servidor, pasa a `ollama.Client(host=...)` configurable por `.env`.
7. **Sin manejo de fallos del modelo.** Hoy, si Ollama está caído, el script revienta. Un servicio para varias áreas debe degradar con un mensaje claro.

### 12.4 Orden recomendado

Los puntos de §12.2 son prerrequisito de todo (son la Fase 2). La decisión de §12.5 hay que aplicarla **desde la primera** herramienta de agregación: define si el modelo ve datos o resúmenes, y rehacerla más tarde implica reescribir cada herramienta agregada, una por una.

---

### 12.5 DECISIÓN — Consultas agregadas: el modelo compone, el código calcula

**Decidido (28/07/2026).** Ante la pregunta "¿el modelo debe ver los datos o solo resúmenes?", se descartan las dos respuestas obvias:

- **Que vea las filas** — desborda el contexto y, sobre todo, lo pone a hacer aritmética. Un SLM se equivoca sumando con el mismo tono seguro con el que acierta.
- **Que solo reciba resúmenes precocinados** — seguro, pero solo responde las preguntas que alguien programó de antemano. Techo bajo: cada pregunta nueva del negocio exige una herramienta nueva. Eso es un tablero con chat, no el cerebro de §2.

**Se adopta la tercera vía: el modelo COMPONE la consulta, el código la CALCULA.**

El modelo traduce la pregunta a los *parámetros* de una herramienta de agregación parametrizada. No ve el dataset y no calcula nada:

```
"cuántos morosos hay en la zona norte este mes"
        │
        ▼  el modelo solo produce esto:
consultar_agregado(metrica="conteo", entidad="clientes",
                   filtros={"estado_pago": "moroso", "zona": "NORTE"},
                   periodo="2026-07")
        │
        ▼  Python filtra, agrupa y cuenta
{"total": 143}
        │
        ▼  el modelo redacta
"Clientes morosos en zona NORTE, julio 2026: 143."
```

Es la misma fortaleza que el modelo ya demostró (traducir intención a parámetros), aplicada al análisis. Con **una** herramienta parametrizada se cubren cientos de preguntas sin programar cada una.

**Reglas de implementación (obligatorias):**

1. **Todo número que lea el asesor tuvo que calcularlo Python.** Si el modelo tuvo que sumar para responder, el diseño está mal.
2. **Tope duro de filas hacia el modelo** (`LIMITE_FILAS`, hoy 50). Si el resultado es mayor: resumen + top-N + conteo total. Nunca la cola. Ver filas está permitido cuando las filas *son* la respuesta ("los 5 morosos con más deuda"), siempre acotadas y ordenadas por el código.
   - **Para contar no hace falta traer filas.** El paginado del API ya devuelve `count` con el total real: una consulta agregada pide `limit=1` y lee ese número. Contar 8.700 facturas es una sola llamada; que el modelo cuente 8.700 filas es imposible. *Verificado: `GET /api/facturas/?estado=1&limit=1` → `count: 3640` facturas pendientes.*
   - **Un total truncado es una respuesta incorrecta silenciosa.** Si se entregan menos filas que el total, el paquete debe declararlo (campo `aviso`) y el `total` debe ser siempre el `count` del API, nunca el número de filas traídas.
3. **Lista blanca de agregación**: qué campos se pueden filtrar, cuáles agrupar, qué métricas existen, qué rango máximo de periodo. Es el principio de siempre —el modelo propone, el código dispone— aplicado ahora a la *forma* de la consulta, no solo a sus argumentos.
4. **La respuesta debe declarar cómo se interpretó la pregunta.** Nunca *"hay 143"*; siempre *"Clientes morosos en zona NORTE, julio 2026: 143"*.

**Confirmación empírica de la regla 2 (julio 2026).** Al implementar `consultar_tickets_de_cliente` se le entregaron al modelo 50 tickets (~14.000 caracteres). Resultado: `qwen3:4b` **dejó de seguir el prompt** —respondió en inglés—, se puso a "analizar" la lista y concluyó que *"50 nuevas instalaciones están activas en la zona CORTE 15"*, una afirmación que nadie le pidió y que no se deduce del dato. Con el mismo caso reducido a conteo + desglose por estado + los 5 más recientes (1.283 caracteres), la respuesta volvió a ser correcta, en español y breve. No es una cuestión de eficiencia: **un modelo pequeño saturado de datos deja de obedecer las reglas de comportamiento**, y ahí el riesgo deja de ser la latencia y pasa a ser la exactitud.

**Por qué la regla 4 no es cosmética.** Esta decisión no elimina el error del modelo: lo traslada de la aritmética a la *interpretación*. El modelo ya no suma mal, pero puede componer un filtro equivocado —entender "zona norte" como `NORTE` cuando en WispHub se llama `ZONA 1`— y devolver un número impecablemente calculado sobre la pregunta incorrecta. Ese error es más peligroso que uno evidente, porque nadie lo nota. Declarar la interpretación permite que el asesor, que sí conoce los nombres reales, lo detecte de inmediato. Misma filosofía que el filtro fail-closed: no confiar, hacer visible.
