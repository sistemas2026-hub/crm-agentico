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

- **RNF-01 · Privacidad:** cumplimiento con la Ley 1581 de 2012 (protección de datos personales, Colombia).
  - **Ya no hay modelo local** (agosto 2026). El diseño original dejaba Ollama on-premise como resguardo: un rol sin enrutar, o un `override` mal escrito, se quedaba en casa. Ese resguardo **dejó de existir** cuando se sacó Ollama del VPS al pasar los embeddings a la API de OpenAI — era su único consumidor y el servidor no tenía memoria de sobra. Hoy `modelo_por_defecto` es DeepSeek, así que **todo** sale a una API externa, amparado en la misma autorización de tratamiento de abajo. Un nombre de modelo mal escrito ya no se queda en casa: falla el turno (`cliente.py::resolver` lo interpreta como local y no hay local que responda).
  - **Excepción aprobada (agosto 2026): DeepSeek (`deepseek-v4-flash`) para todos los roles**, incluidos los que llevan PII (`soporte`, `facturacion`, `cliente_final`). Base legal: la autorización de tratamiento que firma el cliente al contratar **cubre transferencia internacional de datos** (Ley 1581, art. 26 — la transferencia a países sin nivel adecuado de protección es lícita con autorización expresa e inequívoca del titular). Confirmado sobre el texto vigente de Rapilink; los ~7.272 clientes activos ya lo firmaron.
  - Motivación medida, no solo de costo: el modelo local tarda 42.6 s por turno (~180 s si estaba descargado de memoria); DeepSeek, 4.7-12 s — hasta 17× más rápido en la misma tarea real (`cli/prueba_velocidad.py`). A ~$0.24 por cada 1.000 consultas, resuelve directamente la tensión de RNF-04 con el técnico en campo.
  - **La persistencia se reparte** (decisión de agosto 2026, al adoptar Supabase hospedado para la arquitectura multi-tenant). El criterio es uno solo: *sale a la nube lo que no identifica a una persona*.

| Dato | Dónde | Por qué |
|---|---|---|
| Corpus documental, fragmentos, embeddings | Supabase | Una guía de configuración de ONT no menciona a ningún cliente |
| Configuración, roles, sets de evaluación | Supabase | Sin PII |
| Agregados de consumo (`usage_daily`) | Supabase | Cifras, no personas |
| **Respuestas de la API de WispHub** | **No se persisten** | El registro de cliente trae 54 campos: cédula, dirección, coordenadas GPS y **cuatro contraseñas**. Nadie autorizó replicar eso, y el sistema no lo necesita para funcionar |
| Bitácora de acceso (`tool_calls`, `audit_log`) | Supabase, **solo metadatos** | Qué se consultó, quién y cuándo — nunca qué decía la respuesta |
| Contenido de conversaciones y número de WhatsApp | Supabase, **en claro** | Decidido en agosto 2026. Ver abajo |

  - **`tool_calls` guarda un resumen, no el payload:** `exito`, `n_registros`, `duracion_ms`, `codigo_error`. Es el mismo criterio que ya aplica `registrar_auditoria()` en el sistema actual, y cumple el propósito de auditoría sin replicar la base de clientes fuera del país.
  - **Conversaciones en claro, sin anonimizar** (decidido agosto 2026). Se evaluó anonimizar por patrones y se descartó: es fiable con cédulas y teléfonos pero imperfecta con nombres y direcciones, así que **no garantizaba cumplimiento y sí degradaba el historial de depuración** — lo peor de los dos mundos. La base legal correcta no es técnica sino la **autorización de tratamiento** que el cliente firma al contratar.
  - ✅ **Tarea legal resuelta** (agosto 2026): la autorización de tratamiento vigente de Rapilink contempla transferencia internacional. Es la misma base legal que habilita el uso de DeepSeek arriba.
  - **Retención sugerida: 12 meses** para conversaciones. Cubre depuración, auditoría y análisis; más allá es solo superficie de riesgo. Es configuración, no estructura.
  - ⚠️ **La región del proyecto Supabase se define una sola vez y no se puede cambiar sin migrar.** Elegirla es un paso previo a crear el proyecto, no posterior.
  - ⚠️ **Validación legal ahora obligatoria antes de producción**, no opcional: la adopción de infraestructura hospedada cambia el análisis que motivó este requisito.
- **RNF-02 · Seguridad en capas:** las reglas duras (filtrado de PII, confirmación de acciones sensibles) se aplican en **código**, no solo en el prompt. El prompt guía el comportamiento; el código garantiza los límites no negociables.
- **RNF-03 · Costo:** volumen bajo (~300 consultas/día). El modelo local no tiene costo por token; el `override` a DeepSeek (agosto 2026) agrega ~$0.24 por cada 1.000 consultas — a este volumen, unos pocos dólares al mes.
- **RNF-04 · Rendimiento:** originalmente se priorizó calidad sobre latencia, aceptando los 42.6 s/turno de `qwen3:30b-a3b`. La tensión con el técnico en campo (§14 del diseño multi-tenant) queda **resuelta por DeepSeek** (RNF-01): 4.7-12 s por turno con calidad de texto equivalente, medido sobre la misma tarea de producción. Desde agosto 2026 DeepSeek es el **default**, no un `override`: ya no hay modelo local al que caer.
- **RNF-05 · Mantenibilidad:** herramientas, filtros y prompts parametrizados por área, para replicar el patrón sin reescribir el motor.

---

## 7. Arquitectura técnica

### 7.1 Stack

| Componente | Tecnología |
|-----------|-----------|
| Modelo (motor) | **DeepSeek** (`deepseek-v4-flash`) vía API. Hasta agosto 2026 fue **Qwen3 30B-A3B** (MoE, Q4_K_M) vía **Ollama** local — ver RNF-01 |
| Lenguaje | Python 3.13 |
| Cliente del modelo | librería `openai` (contrato compatible; también `anthropic`). `ollama` queda solo para `cli/banco_pruebas.py` y `cli/prueba_velocidad.py`, que comparan modelos contra el Ollama de la máquina de quien los corre |
| Llamadas HTTP | `requests` |
| Configuración y credenciales | `python-dotenv` (archivo `.env`) |
| API de datos | WispHub REST API (JSON, auth por API Key) |

**Motor elegido: `qwen3:30b-a3b-q4_K_M`.** Es un modelo **MoE** (mezcla de expertos): 30B de parámetros totales pero solo **~3B activos por token**. Esa es la razón de la elección y no el tamaño: ocupa memoria como un 30B pero **calcula como un 3B**, que es lo único que lo hace viable sin GPU dedicada. Un denso equivalente daría ~2-3 tok/s en el equipo actual — inservible.

**Reparto por tarea — medido con `banco_pruebas.py` (agosto 2026):**

| Modelo | Elegir herramienta | Argumentos | Respeta el dato | Inventa | RF-15 | tok/s | `thinking` |
|---|---|---|---|---|---|---|---|
| **qwen3:30b-a3b** | ✅ 100% | ✅ 100% | ✅ 100% | 0 | ✅ 100% | 11.2 | 658 car. |
| **qwen3:4b** | ✅ 100% | ✅ 100% | ✅ 100% | 0 | ✅ 100% | 52.0 | 2.154 car. |
| **phi4-mini** | ❌ **12.5%** — no sirve para decidir | ❌ 12.5% | ✅ 100% | 0 | ✅ 100% | 57.9 | **0** |
| **gemma3:4b** | ❌ **No usar.** Su plantilla no maneja el rol `tool`: ignoró el dato entregado e **inventó** cliente, plan y factura. Viola RF-07. | | | | | | |

Configurable por `.env`: `MODELO_SLM` (decide) y `MODELO_REDACCION` (redacta).

> **Lección 1:** un modelo que no soporta el rol `tool` no falla con error — responde con datos inventados y tono seguro. Antes de cambiar de modelo hay que verificar que respeta el dato de la herramienta, no solo que "responde bien". Esto se comprueba con `banco_pruebas.py`, que **no llama a la API**: entrega resultados de herramienta fijos e inventados a propósito y verifica si el modelo los repite.

> **Lección 2 — decidir y redactar son habilidades distintas.** phi4-mini acierta el **100%** repitiendo el dato y el **12.5%** eligiendo la herramienta. Un modelo puede ser excelente en la segunda llamada e inútil en la primera, así que hay que medir las dos por separado. Es lo que justifica que `MODELO_SLM` y `MODELO_REDACCION` sean variables independientes.

**Sobre el razonamiento de Qwen3:** el modelo razona antes de responder y Ollama devuelve eso en un campo `thinking` separado. Medido: `think=False` **no** lo apaga (solo hace que el razonamiento crudo caiga en `content`, a la vista del asesor), y el interruptor `/no_think` tampoco. La estrategia es dejar que Ollama lo separe y **descartarlo del historial** — reenviarlo acumula 2.500–5.400 caracteres inútiles por turno.

> **Lección 3 — la latencia es el `thinking`, no el hardware.** Medido en la misma máquina: qwen3:4b genera 2.154 caracteres de razonamiento por turno y tarda 51.8 s; phi4-mini genera **0** y tarda 3.1 s. Son ~16× de diferencia y ambos van a la misma velocidad bruta (52 vs 58 tok/s). El tiempo no se va en calcular: se va **generando tokens que después se descartan**. Ninguna GPU corrige eso — solo los generaría más rápido. Por eso la 2ª llamada, donde el dato ya está resuelto y no hay nada que razonar, debe usar un modelo sin `thinking`.

> **Lección 4 — tok/s no es la métrica; el tiempo por turno sí.** El 30B-A3B genera a **11.2 tok/s contra 52 del 4B (4.6× más lento por token) y aun así responde antes**: 42.6 s contra 51.8 s. Razona con 658 caracteres donde el 4B necesita 2.154. Un modelo más grande puede ser **más rápido en la práctica** porque llega a la respuesta con menos rodeos. Comparar modelos por tok/s lleva a la conclusión contraria a la correcta.

*(Nota: la cifra histórica de ~25 s por turno se midió antes; las 51.8 s de agosto salen de una corrida con el modelo de 18 GB cargado en memoria. Las comparaciones entre modelos son válidas —misma corrida, mismas condiciones— pero el absoluto conviene remedirlo en frío.)*

### 7.1.1 Equipo de desarrollo y por qué MoE

| | |
|---|---|
| Equipo | ASUS TUF Dash F15 (portátil) |
| CPU | Intel i5-12450H, 12 hilos |
| RAM | **32 GB** |
| GPU | RTX 3050 Laptop — **4 GB de VRAM real** |

La VRAM es el límite: el panel de Windows reporta "20 GB totales", pero son 4 GB dedicados + 16 GB compartidos con la RAM del sistema, que van por el bus y no sirven para inferencia rápida. **Con 4 GB de VRAM no cabe ningún modelo grande en la tarjeta**, así que el peso recae en CPU + RAM — y ahí es donde MoE deja de ser una preferencia y pasa a ser la única opción viable:

| Modelo | Memoria | Cómputo/token | Estimado en este equipo |
|---|---|---|---|
| Denso 27B | ~17 GB | 27B | ~2-3 tok/s — inservible |
| **30B-A3B (MoE)** | ~18 GB | **3B** | **usable** |

Este equipo sirve para **construir y evaluar**, no para producción: es un portátil (hace throttling en cargas sostenidas como el informe de materiales) y no aguanta clientes concurrentes. La máquina de producción se decide **con los datos de `banco_pruebas.py`**, no con estimaciones.

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
  - **La guardia de salida** (`nucleo/seguridad/salida.py`, agosto 2026) es una tercera capa, agregada después de que las dos de arriba demostraran ser insuficientes: ambas protegen la *entrada* de datos al modelo, ninguna mira el *texto* que el modelo redacta antes de que llegue al cliente. Los casos dorados ya declaraban `responde_sin` para atrapar fugas de plomería interna (un código de error repetido tal cual, una fabricación sobre "cómo se sabe" la identidad), pero solo en evaluación — nada lo detenía en producción. La guardia corre el mismo chequeo en tiempo real, sobre los dos puntos donde `motor.py::responder()` devuelve texto redactado. Patrón con precedente en el rubro: Decagon lo llama *"capa de supervisor que atrapa errores antes de que el cliente los vea"* (investigado agosto 2026 comparando este proyecto contra Sierra, Decagon e Intercom Fin). **Deliberadamente no reusa `Rol.nunca_revelar`**: esa lista son nombres de *campo* para filtrar datos crudos de API, no frases prohibidas en lenguaje natural — `cliente_final` tiene `cedula` y `direccion` ahí, y el agente dice "pasame tu cédula" en cada verificación; buscar esa palabra en el texto libre habría bloqueado el flujo normal. Los patrones de la guardia son solo códigos internos del motor (`IDENTIDAD_NO_VERIFICADA`, `PRECONDICION_NO_CUMPLIDA`, etc.), tokens que nunca aparecen en español legítimo. Guarda: `tests/test_guardia_salida.py`.

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

**Trampa nueva, encontrada al integrar SmartOLT (agosto 2026):** el endpoint de ping (`POST /clientes/{id}/ping/`) usaba una `interfaz` tomada de `interfaz_lan` del cliente. Si ese campo está **vacío**, no hay problema (caso normal, documentado arriba). Pero si está **poblado con un valor que ya no corresponde** a ese equipo, el ping falla con `"input does not match any value of interface"` — mismo síntoma que "el equipo no responde", pero es un dato de WispHub desactualizado, no una falla real de red. Se decidió dejar de mandar `interfaz` del todo: `arp_ping=false` sin interfaz ya pinguea bien (verificado), y no depender de que ese campo esté siempre bien cargado evita esta clase de falso negativo silencioso.

### 7.7 Notas de integración con SmartOLT

SmartOLT es donde el ISP administra las ONUs autorizadas en la OLT de fibra — se integró (agosto 2026) para convertir el diagnóstico ciego de conectividad (antes solo `ping_cliente`) en uno concluyente: distinguir equipo sin energía, sin señal óptica, señal débil o equipo sano. Documentación completa y verificada en vivo: `.claude/skills/smartolt-api/SKILL.md`.

**Auth:** header `X-Token: <api_key>` (no `Authorization`, no `Bearer`) — distinto de WispHub, por eso `Herramienta` tiene un campo `auth_header` configurable, no fijo en `nucleo/`.

**El identificador es la misma llave que WispHub.** `sn_onu` (WispHub) funciona directo como `unique_external_id` de SmartOLT, sin traducción — confirmado con el método del valor imposible. Cubre el **68%** de los clientes activos: el resto no tiene `sn_onu` cargado en WispHub, y para esos el diagnóstico cae al camino alternativo (preguntar por las luces del equipo). Un script de backfill (`cli/proponer_sn_onu.py` + `cli/aplicar_sn_onu.py`) cruza el nombre del cliente contra el nombre de la ONU para proponer candidatos — aplicado en producción, subió la cobertura al ~93%, con 286 casos que quedaron para revisión manual por ambigüedad o falta de candidato.

**Límite de tasa:** 1.000 llamadas/hora (confirmado por cabecera `X-RateLimit-*`, no por documentación de terceros — una búsqueda inicial daba 15/hora, que resultó ser la cifra de un caso de uso masivo distinto).

**El reinicio de ONT no pide aprobación humana — decisión explícita del cliente.** En su lugar, precondiciones en código (`Herramienta.exige_previas`): solo se ejecuta si la señal y el ping ya dieron resultado favorable **en esa misma conversación**, mirando siempre la llamada más reciente (una señal buena hace tres mensajes que después empeoró no cuenta). Mismo principio de RNF-02 (seguridad en código, no en el prompt) aplicado a una acción de escritura, no solo a la lectura de PII.

**Tiempos de recuperación, medidos en vivo — dos números que no hay que confundir:** el estado de SmartOLT (`onu_status`) tarda ~6 minutos en reflejar que la ONU volvió a estar en línea (el reregistro GPON completo). El equipo responde a un **ping real** mucho antes, ~73 segundos — y ese es el número que le importa al cliente. El texto que promete algo al cliente usa el segundo, no el primero.

**El código calcula, el modelo compone (ver §12.5), aplicado también acá:** los umbrales de señal óptica (G-GO-04: -8 a -25 dBm aceptable) y la traducción de la causa de caída (`dying-gasp` → sin energía eléctrica; `LOSi/LOBi`/`LOFi` → falla óptica) se calculan en código (`Herramienta.veredictos`/`Herramienta.mapeos`, genéricos en `nucleo/`), nunca los interpreta el modelo sobre el dato crudo en inglés.

---

## 8. Roadmap por fases

| Fase | Entregable | Estado |
|------|-----------|--------|
| **0** | Prototipo de soporte en consola contra WispHub | ✅ Hecho |
| **1** | Consolidar soporte: prompt de asesor, filtro PII, consulta por cédula | ✅ Hecho |
| **2** | Identidad de área; parametrizar herramientas y filtros por rol | ✅ Hecho (login real pendiente, ver §8.1) |
| **3** | Replicar patrón a Facturación y Técnica | ✅ Catálogo definido y verificado — Técnica ahora incluye SmartOLT (lectura de red + reinicio de ONT, ver §7.7), no solo WispHub |
| **4** | Generación de informes + exportación (Excel/PDF) | Pendiente |
| **5** | Interfaz web interna (reemplaza la consola) | Pendiente |
| **6** | Auditoría/logs y despliegue en servidor on-premise | Auditoría ✅ (§8.2) · despliegue pendiente |

---

### 8.1 Estado de la Fase 2 — qué quedó hecho y qué no

**Hecho.** El motor está parametrizado por área: `construir_system(area)`, `herramientas_de(area)` y `campos_de(area, herramienta)`. El mismo cliente devuelve distintos campos según quién pregunte (verificado contra la API real, 54 campos crudos):

| Área | Campos | Ve |
|---|---|---|
| Soporte | 15 | Identidad, contacto, servicio, estado de pago |
| Técnica | 16 | Identidad, servicio, **red** (IP, MAC, ONU, antena, router) |
| Facturación | 16 | Identidad, contacto, pago, **precios** |
| Administración | 7 | Estado y servicio, **sin PII** |

El control es doble y se aplica en código: una herramienta que no está en `herramientas` del área no se le muestra al modelo **y** se rechaza si igual la invoca; una que no tiene entrada en `campos` no devuelve nada (fail-closed). Ambas condiciones se verifican; no alcanza con una.

**Credenciales: ningún área.** `password_servicio`, `password_cpe`, `password_router_wifi`, `password_ssid_router_wifi` y `usuario_router_wifi` están fuera de todas las listas, incluida Técnica. Un técnico que necesite una credencial la saca de WispHub; pasarla por el modelo no le ahorra un paso y la deja escrita en el historial de la conversación.

**NO hecho — pendiente para la interfaz web (Fase 5):**

- **Es identificación, no autenticación.** No hay contraseña: quien abre la consola elige su área de una lista. Sirve para acotar lo que cada uno ve y para probar el catálogo, pero no impide que alguien elija otra área. La autenticación real requiere la capa web.
- **Una sola clave de API para todos.** La clave de WispHub pertenece a un usuario del staff y hereda sus permisos, así que WispHub ve todas las consultas como si fueran de esa misma persona. **La separación por área es nuestra, no de WispHub.** Para que el control fuera real de punta a punta harían falta claves por colaborador.
- **Sin auditoría** (RF-13): no queda registro de quién consultó qué. Con la identidad ya disponible, es el paso natural siguiente.

### 8.2 Auditoría (RF-13) — implementada

Una línea JSON por **acceso a datos** (ejecución de herramienta), no por mensaje de la conversación. Archivo `auditoria.log`, fuera del repositorio.

```json
{"ts":"2026-07-28T21:56:29-05:00","area":"soporte",
 "herramienta":"consultar_cliente_por_cedula","args":{"cedula":"******1347"},
 "estado":"ok","sensible":false,"registros":1,"ms":762}
```

**Qué se registra:** cuándo, qué área, qué herramienta, sobre qué registro, con qué resultado, cuántos registros devolvió y cuánto tardó. Los `estado` posibles distinguen los cuatro caminos: `ok`, `error_api`, `argumentos_invalidos`, `rechazado_por_area`, `cancelado_por_operador`. Este último es el que deja constancia de que un humano **negó** una acción sensible.

**Qué NO se registra:** ningún dato devuelto. Ni nombre, ni email, ni dirección, ni IP, ni plan. *Un log de auditoría que copia los datos que vigila deja de ser un control y pasa a ser una segunda base de datos sin proteger.*

**Enmascaramiento:** los identificadores de 8 dígitos o más se ocultan salvo los últimos 4 (`1044601347` → `******1347`). Cubre cédulas y teléfonos. Los IDs cortos —servicio (4), ticket (5), factura (6)— se conservan: son los que hacen útil la auditoría y no identifican a una persona por sí solos.

**Pendiente:** el log registra el **área**, no la persona — porque hoy no hay autenticación (§8.1). Cuando exista login real, el campo `area` debe acompañarse del identificador del colaborador; el resto de la estructura no cambia. Tampoco hay rotación del archivo.

### 8.3 Métrica de tasa de escalamiento (agosto 2026)

`cli/reporte_escalamiento.py` — cuántas conversaciones de los últimos N días terminaron en un humano, y por qué motivo (`asistente.conversations.motivo_escalamiento`), agregado en SQL.

Nace de un hueco concreto: el 15/08/2026 se agregó `escalamiento.intentar_resolver_antes` (una vuelta extra antes de escalar, ver `tests/test_escalamiento_paciente.py`) después de que un cliente escalara en su primer mensaje sin ningún diagnóstico intentado. El cambio se validó mirando dos conversaciones a mano — sin este reporte no había forma de saber si funcionaba sobre la población real. Mismo concepto que la "tasa de escalada" que Intercom Fin reporta como métrica de primera clase (investigado agosto 2026 comparando este proyecto contra Sierra, Decagon e Intercom Fin — ver también la guardia de salida en §7.4, del mismo relevamiento).

```
py -3.13 cli/reporte_escalamiento.py --tenant rapilink --dias 7
```

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
