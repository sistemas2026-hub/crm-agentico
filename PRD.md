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

#### Campos de texto libre — redacción por patrón (RESUELTO, agosto 2026)

El filtro controla **qué campos** pasan, no **qué contiene** cada campo. Un campo de texto libre puede traer embebido cualquier dato, y la lista blanca no lo ve.

Caso real detectado en producción: la `descripcion` de un ticket de instalación contenía nombre completo, teléfono, email, dirección, coordenadas GPS, número de documento, plan contratado con precio y un enlace público al PDF de la solicitud — todo en un solo string de 419 caracteres.

Se decidió **mantener `descripcion`**: es el contenido del ticket y Soporte no puede trabajar sin él. La minimización de datos que da la lista blanca **no aplica** a los campos de texto libre — ahí llega lo que el operador haya escrito — así que hacía falta una capa más.

**Implementado**: `nucleo/seguridad/redaccion.py` — patrones de cédula/teléfono (8-11 dígitos), email, URL y coordenadas GPS, aplicados sobre los campos que `Herramienta.campos_texto_libre` declara (propiedad del campo, no del rol — corre para cualquiera que consulte, sin repetir la declaración por área). Reemplaza cada coincidencia por una etiqueta (`[email oculto]`, etc.), conserva el resto del texto intacto — sacar la PII sin volver el campo inútil para quien tiene que atender el ticket.

**Verificado contra datos reales, no un ejemplo de laboratorio** (17/08/2026): de 300 tickets reales, **136 (45%) traían un número de 8-11 dígitos embebido en la descripción** — más frecuente de lo que el caso original hacía pensar. La redacción lo saca (`"Telefono: 3113683499"` → `"Telefono: [numero de identificacion oculto]"`) sin tocar el resto del texto.

**Límite honesto, no resuelto**: solo cubre patrones estructurados (números, emails, URLs, coordenadas). Un nombre propio o una dirección en prosa libre (`"Calle 45 #12-30"`) no se detecta — eso exigiría NLP, no regex, y queda fuera de este alcance.

Configurado hoy en `consultar_ticket` (roles `soporte` y `administracion`). Al agregar un campo nuevo a una lista blanca, preguntarse si es texto libre — si lo es, agregarlo también a `campos_texto_libre` de esa herramienta. Guarda: `tests/test_redaccion.py`.

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
| **2** | Identidad de área; parametrizar herramientas y filtros por rol | ✅ Hecho — login real ya existe (JWT vía BottleCRM), ver §8.1 |
| **3** | Replicar patrón a Facturación y Técnica | ✅ Catálogo definido y verificado — Técnica ahora incluye SmartOLT (lectura de red + reinicio de ONT, ver §7.7), no solo WispHub |
| **4** | Generación de informes + exportación (Excel/PDF) | ✅ Excel y PDF (ver §8.4) |
| **5** | Interfaz web interna (reemplaza la consola) | ✅ En gran parte hecho — ver §8.1 |
| **6** | Auditoría/logs y despliegue en servidor on-premise | Auditoría ✅ (§8.2) · despliegue: pasos manuales pendientes en DESPLIEGUE.md → `## Pendientes` |

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

**Hecho también (agosto 2026, corrige lo que decía este párrafo antes):** identificación real, no elegir un área de una lista. `django-crm/frontend/src/hooks.server.js` implementa login con JWT emitido por BottleCRM (access + refresh token rotado, membresía de organización, `locals.user`/`locals.profile.role`) — es la app web la que gatea cada ruta (`redirect` a `/login` sin sesión). Sobre esa identidad real hay una capa de autorización propia del asistente: `asistente.tenant_users` mapea `profile_id` (el perfil real del CRM) → los agentes/roles que un ADMIN le asignó (`/agentes/asignaciones`, `persistencia.agentes_de_colaborador()`). `POST /chat` resuelve el rol a partir de ese `profile_id` — nunca lo manda el cliente — y es **fail-closed**: sin asignación, `403` ("Todavía no tienes ningún agente asignado"), no cae a un rol por defecto. Un colaborador con Soporte y Facturación asignados los ve fusionados en un solo turno, sin elegir a cuál le habla.

**Sigue sin resolver:**

- **Una sola clave de API para todos.** La clave de WispHub pertenece a un usuario del staff y hereda sus permisos, así que WispHub ve todas las consultas como si fueran de esa misma persona. **La separación por área es nuestra, no de WispHub.** Para que el control fuera real de punta a punta harían falta claves por colaborador.
- **La identidad del colaborador no queda en la fila de auditoría misma** — ver el matiz en §8.2: es recuperable, pero indirecto.

### 8.2 Auditoría (RF-13) — implementada, en base de datos (corrige la versión anterior de esta sección)

**Esta sección describía un archivo `auditoria.log` en JSON que ya no es como funciona el motor multi-tenant.** Ese archivo solo lo sigue escribiendo `soporte_wisphub.py`, el prototipo de referencia de un solo tenant (ver §11) — nunca `nucleo/`. La auditoría real es una fila en Postgres por **acceso a datos** (ejecución de herramienta), no por mensaje: `asistente.tool_calls`, insertada por `persistencia.registrar_llamada_herramienta()` y mostrada en el panel "Ver proceso" de `/conversaciones`.

Columnas: `organization_id`, `conversation_id`, `herramienta`, `parametros` (enmascarados), `rol_solicitante`, `exito`, `n_registros`, `codigo_error`, `duracion_ms`, `es_escritura`, `creado_en`.

**Qué NO se registra:** ningún dato devuelto. Ni nombre, ni email, ni dirección, ni IP, ni plan. *Un log de auditoría que copia los datos que vigila deja de ser un control y pasa a ser una segunda base de datos sin proteger.*

**Enmascaramiento — más simple y más parejo de lo que decía esta sección antes.** `motor.py::_enmascarar()` no distingue por tipo de campo ni por largo del identificador: **todo** argumento de más de 4 caracteres se trunca a sus últimos 4 con el prefijo `...` (`"1044601347"` → `"...1347"`), sin importar si es cédula, teléfono o un ID de ticket de 5 dígitos. La afirmación anterior de que "los IDs cortos —ticket (5), factura (6)— se conservan" era falsa: con esta regla, cualquiera de más de 4 caracteres se enmascara igual.

**La identidad SÍ queda registrada — indirecta, no ausente.** Para los flujos disparados desde la web (`/asistente`, `/configuracion-guiada`), el frontend resuelve `profile_id` server-side (nunca del cliente, ver `routes/api/asistente/+server.js`) y manda `identificador_sesion: locals.user.id` — el motor lo guarda como `usuario_externo` de la conversación. Es decir: la conversación entera queda atada al colaborador real, no solo al área. Lo que falta es más chico que "no hay registro de quién": `asistente.tool_calls` guarda `rol_solicitante` (el rol, ya fusionado si el colaborador tiene varios asignados), no el `profile_id` como columna propia — para saber qué colaborador ejecutó una herramienta puntual hay que cruzar por `conversation_id` contra `conversations.usuario_externo`, no viene en la misma fila. Sumar esa columna (`profile_id` en `asistente.tool_calls`) es directo y queda como pendiente concreto.

**Pendiente real, distinto del que decía esta sección:** no hay política de retención/purga sobre `asistente.tool_calls` (antes decía "rotación del archivo", que ya no aplica — es una tabla, no un archivo).

### 8.3 Métrica de tasa de escalamiento (agosto 2026)

`cli/reporte_escalamiento.py` — cuántas conversaciones de los últimos N días terminaron en un humano, y por qué motivo (`asistente.conversations.motivo_escalamiento`), agregado en SQL.

Nace de un hueco concreto: el 15/08/2026 se agregó `escalamiento.intentar_resolver_antes` (una vuelta extra antes de escalar, ver `tests/test_escalamiento_paciente.py`) después de que un cliente escalara en su primer mensaje sin ningún diagnóstico intentado. El cambio se validó mirando dos conversaciones a mano — sin este reporte no había forma de saber si funcionaba sobre la población real. Mismo concepto que la "tasa de escalada" que Intercom Fin reporta como métrica de primera clase (investigado agosto 2026 comparando este proyecto contra Sierra, Decagon e Intercom Fin — ver también la guardia de salida en §7.4, del mismo relevamiento).

```
py -3.13 cli/reporte_escalamiento.py --tenant rapilink --dias 7
```

### 8.4 Informes exportables (RF-12, agosto 2026) — Excel y PDF

Antes de esto no existía ningún camino para generar un archivo real desde una conversación: `informe_materiales` (el único intento de "informe") es tipo `batch` y ni siquiera tiene ejecutor en `motor.py` — solo corre como script manual. RF-12 seguía sin cumplirse.

**Cómo funciona.** Una herramienta `tipo: agregado` marcada `exportable: true` (`nucleo/config/schema.py::Herramienta`) ofrece al modelo un argumento extra, `formato: texto|excel|pdf`. Si el colaborador pide explícitamente un archivo, `nucleo/herramientas/informes.py` (`generar_excel()`/`generar_pdf()`) toma el **mismo** dict que `agregado.ejecutar()` ya calculó (`total`, `desglose`, `interpretacion`) y lo vuelca al formato pedido — el código sigue calculando (PRD §12.5), esto solo cambia el empaque. `motor._GENERADORES_INFORME` mapea cada `formato` a su función y su mime; agregar un tercer formato es una entrada más en ese diccionario, no una rama nueva de lógica. PDF usa `reportlab` (pure-Python, sin dependencias de sistema — a diferencia de `weasyprint`, que necesita Cairo/Pango y complicaría la imagen de Docker). El modelo nunca ve los bytes del archivo, solo un identificador para poder mencionarlo — y su propia descripción le prohíbe explícitamente mostrar ese identificador al colaborador, porque no significa nada para una persona y el archivo ya aparece como adjunto en la conversación sin que haga falta.

**Restricción de arquitectura real, no cosmética.** `motor.py::responder()` corre **antes** de que exista `conversation_id` (se resuelve recién en `api.py`, al persistir el turno) — y `asistente.media` exige `conversation_id not null`. Por eso `responder()` devuelve un tercer valor, `medios_pendientes`, con el mismo patrón que ya usa `registro_herramientas` para la auditoría: el archivo se genera durante el turno, pero se guarda en `api.py` una vez que el conversation_id existe.

**Dos identificadores de `asistente.media`, no confundir.** `id` (la clave primaria, generada por Postgres) es la que usa el flujo existente de fotos de WhatsApp — no se conoce hasta después del INSERT. Un archivo generado por el motor necesita poder referenciar su propio identificador *antes* de que la fila exista, así que usa la columna `media_id` (texto, `unique(organization_id, media_id)`), elegida por código. Confirmado en vivo (17/08/2026) que confundir las dos —la misma trampa de "dos catálogos con la misma forma" que ya costó tiempo con zona/router de WispHub— hacía que el archivo se generara pero fuera irrecuperable con el identificador que el modelo mencionaba.

**La entrega no necesitó tocar el frontend.** El visor de conversaciones (`/conversaciones/[id]`) ya tenía una rama genérica para adjuntos que no son foto ni audio (enlace con ícono y tamaño en KB), unida por `mensaje_id` — el mismo mecanismo que ya muestra las fotos que manda un cliente. Un archivo generado por el motor pasa por el mismo camino sin ningún cambio de UI.

Guardas: `tests/test_informes.py` (el archivo refleja exactamente lo que el agregado calculó, sin inventar ni redondear — Excel y PDF, este último leído de vuelta con `pypdf` solo para el test, no es dependencia del motor) y el caso dorado "pedido explícito de reporte descargable llama al agregado" (`evaluacion/rapilink.casos.yaml`). Primer caso dorado con un rol **colaborador** (`administracion`), no `cliente_final`.

`contar_clientes`, `contar_facturas` y `contar_tickets` están marcadas `exportable`, en Excel y PDF, verificado en vivo contra producción. Al mismo tiempo se corrigió `contar_facturas.agrupar_por: zona`, que estaba declarado pero nunca podía funcionar (`zona` era `tipo: id`, y el motor de agregados solo agrupa catálogos cerrados `tipo: enum`) — se pasó a `enum` con las 5 zonas reales de WispHub, verificadas con el método del valor imposible.

### 8.5 Asistente de configuración guiada (agosto 2026)

CLAUDE.md ya lo pedía: *"la próxima empresa que se conecte no debería necesitar una sesión de código para algo que ya se resolvió una vez"*. Hasta ahora, conectar un sistema nuevo era 100% trabajo de un desarrollador: sondear la API a mano (`cli/sondear_api.py`), verificar cada filtro con el método del valor imposible, escribir el YAML, aplicarlo. Este rol (`configuracion_guiada`, gateado a ADMIN en la capa web) hace lo mismo pero conversando con un colaborador — sin que deje de sondear de verdad ni de exigir aprobación humana.

**Dos herramientas nuevas, quinta y sexta excepción a "el modelo nunca propone argumentos libres"** (las anteriores: `campo_busqueda` de verificar identidad, `confirma` de confirmar identidad, `area` acotada de derivar rol):

- `sondear_api` (`Herramienta.sondea_api`): hace un GET real contra una URL que el ADMIN describe, y devuelve un resumen (`count`, `campos_disponibles`, hasta 3 filas de muestra) — nunca el volcado completo.
- `proponer_herramienta` (`Herramienta.propone_herramienta`): guarda un borrador de `Herramienta` en `asistente.herramientas_propuestas`, `estado='pendiente'`. Nunca se activa sola.

**La superficie de ataque nueva, y cómo se cerró.** Es la única parte del proyecto que llama a una URL no verificada de antemano — eso es SSRF (Server-Side Request Forgery): sin control, un ADMIN (o una cuenta comprometida) podría hacer que el servidor "sondee" su propia red interna — el motor, el pooler de Postgres, o el endpoint de metadata de la nube (`169.254.169.254`, que en AWS/GCP/Azure expone credenciales sin autenticación). `nucleo/herramientas/sondeo.py` bloquea: solo `https`, y resuelve el host rechazando cualquier IP que caiga en un rango privado/interno/de enlace local (RFC 1918, loopback, link-local). Límite conocido y dejado escrito en el propio módulo: hay una ventana de DNS rebinding entre la verificación y la conexión real; el riesgo residual es bajo (solo lo dispara un ADMIN ya autenticado) pero no es cero.

**La clave de la API nueva nunca toca al modelo.** `sondear_api` recibe `auth_ref` — el NOMBRE de un secreto que el ADMIN ya guardó desde la pantalla de Secretos (cifrado, patrón ya existente) — y lo resuelve server-side. Enviar la clave completa a través del chat la mandaría a DeepSeek como parte de la conversación, exactamente el tipo de exposición de credenciales que el resto del proyecto evita.

**`nucleo/config/editor.py` decía explícitamente que crear una herramienta "sigue siendo trabajo de código... esa superficie es sensible en seguridad".** Esto no relaja esa regla, la resuelve distinto: la preocupación nunca fue "una pantalla", fue "sin verificar y sin que un humano lo revise". Las dos garantías siguen intactas — nada llega al catálogo real sin pasar por el sondeo (evidencia auditable, guardada junto con la propuesta) y sin que un ADMIN apruebe el borrador exacto desde `/configuracion/propuestas/<id>/aprobar`. `editor.aprobar_herramienta_propuesta()` valida contra el mismo esquema que todo lo demás — un borrador mal armado se rechaza con el error específico, no se cuela.

**Verificado en vivo, no solo en el test unitario.** Primer intento real: el modelo propuso `tipo: catalogo` (no existe) sin `roles_permitidos` (obligatorio) — la aprobación lo rechazó correctamente, con el error exacto de Pydantic. Se afinó el prompt del rol con un ejemplo concreto de la forma exacta del esquema, y el segundo intento (sondear el catálogo de zonas de WispHub, sin filtros) produjo un borrador válido de punta a punta: sondeo real → propuesta con evidencia → aprobación → herramienta viva en el catálogo. Retirada después de verificar — era una prueba, no un pedido real de Rapilink.

Guardas: `tests/test_sondeo.py` (bloqueo SSRF contra IPs y hostnames reales, no solo la lógica en abstracto) y `tests/test_configuracion_guiada.py` (un borrador mal armado —incluidos los dos errores reales vistos en vivo— se rechaza antes de tocar el catálogo).

**Pantalla web** (agosto 2026): `/configuracion-guiada`, entrada "Conectar sistema nuevo" en Administrar (solo ADMIN, oculta del menú y con `redirect` en el `load()` para cualquiera más). Chat a un lado — mismo patrón que el simulador de WhatsApp — y panel de propuestas pendientes al otro, con Aprobar/Rechazar por propuesta — mismo patrón que la cola de revisiones de `/manual`. Las cuatro rutas server-side (`/api/configuracion-guiada` y sus tres sub-rutas de propuestas) repiten el gate `locals.profile?.role !== 'ADMIN'` que ya usa `/api/agentes`, en vez de confiar solo en que el menú esté oculto.

### 8.6 Escritura de tickets con aprobación humana real (`aprobacion_humana`, agosto 2026)

Primer caso concreto de escritura donde el propio colaborador de soporte propone la acción, no un ADMIN: crear un ticket, responder uno existente, o cambiarle el estado — directo desde WispHub, a partir de la documentación oficial de sus endpoints (`POST /api/tickets/`, `POST /api/tickets/{id}/respuesta/`, `PUT /api/tickets/{id}/`).

**Por qué no se reusó `requiere_confirmacion`.** Ese campo existe desde antes y el validador lo *fuerza* a `true` en toda herramienta de escritura (`if not solo_lectura and not requiere_confirmacion: raise ValueError`) — pero nunca se aplicó en tiempo de ejecución (`motor.py` no lo mira). Herramientas ya en producción y deliberadamente autónomas (`registrar_pago`, `activar_catv`, `crear_tag_crm`) lo llevan puesto solo para pasar la validación. Convertirlo en un gate real las hubiera frenado a todas de un día para el otro, sin que nadie lo pidiera. Por eso el gate nuevo es un campo separado y opt-in: `Herramienta.aprobacion_humana`, con su propia regla de coherencia (no tiene sentido en una herramienta `solo_lectura`).

**El mecanismo, genérico — no específico de tickets.** Cuando el modelo llama una herramienta con `aprobacion_humana: true`, `motor.py` no ejecuta nada contra la API externa: resuelve los argumentos (misma `_resolver_argumentos()` que usa la ejecución normal — filtros verificados, argumentos fijos, fechas automáticas, inyección de sesión) y guarda la propuesta en `asistente.acciones_propuestas` (`estado='pendiente'`), con un resumen legible (`Herramienta.plantilla_resumen`, ej. `"Crear ticket '{asunto}' para el servicio {servicio}"`). Al modelo le vuelve una instrucción explícita de no confirmar que ya se hizo. Un humano aprueba o rechaza desde `/acciones/propuestas` (tres endpoints nuevos en `nucleo/canales/api.py`); solo al aprobar se ejecuta de verdad, vía `motor.ejecutar_accion_aprobada()`, contra la herramienta HTTP real del catálogo. Aprobar registra el resultado (éxito o error de la API) pero el estado queda `'aprobada'` en ambos casos — aprobar es "un humano autorizó la intención", no "necesariamente salió bien".

**`espejar_campos` (nuevo, genérico).** WispHub pide el mismo valor duplicado en dos campos (`asunto`/`asuntos_default`, `departamento`/`departamentos_default`) — capricho de su API, no algo que el modelo deba resolver ni que amerite lógica especial. `Herramienta.espejar_campos: {origen: destino}` copia el valor ya resuelto de un campo a otro, como paso final de `_resolver_argumentos()`.

**El catálogo de `asunto` es un enum cerrado, no texto libre.** `crear_ticket` obliga a que el modelo elija una de las ~31 opciones reales de WispHub (`filtros_verificados.asunto`, tipo enum) — mismo mecanismo que ya filtraba parámetros de consulta, reusado para el cuerpo de un POST, porque `_resolver_argumentos()` termina siempre en el mismo diccionario `argumentos` sin importar el método HTTP.

**Verificado en vivo de punta a punta (19/08/2026), no solo con las guardas de esquema.** Contra el cliente de prueba (`servicio` 6555, "PRUEBA TEMPORAL"): `crear_ticket` propuso, quedó pendiente, se aprobó y creó el ticket real `#90354` (estado Nuevo, técnico resuelto por nombre vía `consultar_tecnicos`); `responder_ticket` agregó una respuesta real; `actualizar_estado_ticket` lo cerró. Los tres pasaron por el ciclo completo propuesta → `asistente.acciones_propuestas` → aprobación → escritura real, sin atajos.

**Ese mismo intento encontró un hueco real en la documentación de WispHub — y en el motor.** `POST /api/tickets/` rechazó el primer intento con `400`: exige `estado` y `tecnico`, ninguno marcado como obligatorio en la documentación oficial. `estado` se resolvió fijándolo en código (`argumentos_fijos`: todo ticket nuevo nace "Nuevo") pero `tecnico` es una decisión real del modelo — y ahí apareció el hueco más serio: `motor.py` mandaba `"required": []` fijo al esquema de function-calling para **toda** herramienta, sin una sola excepción, así que no había forma de decirle al modelo que un campo era obligatorio. Se agregó `Herramienta.requeridos` (`nucleo/config/schema.py`) — lista de claves de `filtros_verificados` que sí entran al `required` real que ve el modelo — y se verificó que el modelo, con ese único cambio, resolvió `tecnico` por nombre sin que se lo pidieran explícitamente. Detalle completo, incluidos los payloads exactos, en la skill `wisphub-api`.

### 8.7 Herramientas de facturas — detalle, formas de pago, promesa de pago, y un bug real corregido (agosto 2026)

A partir de la documentación oficial de WispHub para `/api/facturas/` pegada por el usuario, se decidió qué construir y qué no: `consultar_facturas` y `registrar_pago` ya existían; se agregaron `consultar_factura_detalle` (una factura por ID, con sus artículos), `consultar_formas_pago` (catálogo, para resolver `forma_pago` por nombre) y `agregar_promesa_pago` (con `aprobacion_humana: true`, mismo mecanismo que las herramientas de tickets). Deliberadamente **no** se construyeron `crear_factura` (genera un documento contable con prorrateo e impuestos — le corresponde al motor de facturación de WispHub, no a este asistente), `DELETE /api/facturas/{id}/` ni el borrado masivo (`/facturas/eliminar-facturas/`, hasta 500 por request) — mismo criterio que ya excluye el borrado de clientes: ninguna herramienta de este catálogo expone destrucción de datos.

**`registrar_pago` estaba roto en producción, y nadie lo había notado.** No declaraba `filtros_verificados`: el modelo no tenía forma de decirle a qué factura se refería, así que `url_de()` nunca podía resolver el marcador `{id}` del endpoint (`/api/facturas/{id}/registrar-pago/`) y la llamada fallaba siempre con `ErrorHerramientaHttp` — sin caso dorado ni prueba en vivo que lo hubiera ejercitado hasta ahora. Se corrigió y se verificó con un pago real: factura de prueba `#143512` pasó de "Pendiente de Pago" a "Pagada", con `forma_pago`, `referencia` y `total_cobrado` reflejados — confirmado leyendo la factura de nuevo desde la API, no solo confiando en la respuesta del POST.

**Otro hueco de documentación, en dirección opuesta al de los tickets.** `POST /api/facturas/{id}/registrar-pago/` rechazó el primer intento real con `400 {"fecha_pago": ["Este campo es requerido."]}`, pese a que la doc la marca opcional ("solo tiene efecto con un permiso especial"). Se resolvió con `fechas_automaticas` (ya existía, para tickets) — pero ese mecanismo tenía el formato de fecha **hardcodeado** a `DD/MM/AAAA` (lo que exige WispHub en tickets) como una constante de `motor.py`, con un comentario propio que ya anticipaba el problema: *"si aparece otro con un formato distinto, esto pasa a ser un campo de config en vez de una constante"*. Este fue ese caso: `registrar-pago` exige `YYYY-MM-DD HH:mm`. Se agregó `Herramienta.formato_fechas_automaticas` (default = el formato de tickets, así que ninguna herramienta existente cambió de comportamiento) y `registrar_pago` declara el suyo propio.

**Y un tercer hueco, en `POST /api/promesa-pago/`**: la doc marca `id_factura` como requerido, pero el serializer no lo valida — un valor imposible (`999999999`) no generó error junto con los demás campos vacíos. Se forzó igual vía `Herramienta.requeridos`: no hay que confiar en que la API vaya a rechazar lo que falte, sobre todo cuando ya se demostró que no siempre lo hace. El formato de fecha del ejemplo oficial (`fecha_limite: "2022/08/26"`, con barras) también estaba mal — la API real exige guiones (`YYYY-MM-DD`), confirmado con un `400` de formato real antes de acertar.

Verificado en vivo: `consultar_factura_detalle` y `consultar_formas_pago` funcionaron directo contra la factura y el catálogo reales; `agregar_promesa_pago` se probó con un `POST` real exitoso (antes de que la factura quedara pagada por la prueba de `registrar_pago`) y, por separado, se confirmó que `_resolver_argumentos()` arma el payload exacto que la API acepta. Guarda nueva en los casos dorados: uno confirma que `consultar_factura_detalle` no inventa el total, y otro que el modelo no propone una promesa de pago sobre una factura que ya está saldada — verificado que razona sobre el estado antes de proponer, no que llama a ciegas.

### 8.8 Rol `ventas` — el primer `cliente_final` que no verifica identidad (agosto 2026)

Nace de un bug real visto en el simulador: un colaborador escribió *"para solicitar un servicio"* y el router pidió cédula de inmediato. Un prospecto (todavía no cliente) nunca iba a pasar esa verificación — genuinamente no está en WispHub. Antes de esto, "instalaciones nuevas" derivaba ciego a un colaborador humano; el flujo real de la empresa (confirmado por el usuario, con captura de pantalla de un ticket real) es: alguien escribe pidiendo contratar, un humano confirma cobertura por barrio y comparte un formulario externo (datos, documentos, firma) que termina creando un ticket sobre un cliente placeholder ("INSTALACIONES-NUEVAS") en WispHub. El rol `ventas` reemplaza la primera parte de esa conversación — calificar el interés, chequear cobertura, contestar planes y precios reales — sin tocar la parte de captura de documentos/firma, que sigue siendo el mismo formulario externo de siempre.

**Decisión de diseño, después de descartar la alternativa:** se evaluó que el router reconociera la intención ("quiero contratar") y saltara la verificación desde el primer mensaje, pero el modelo se resistió a esto de forma consistente en varias reescrituras del prompt (probado en vivo, múltiples corridas) — tiene un sesgo fuerte hacia "pedir un identificador antes de ayudar con cualquier trámite de cuenta". Se volvió al diseño más simple, alineado con el proceso real de la empresa: **el router siempre intenta verificar primero**, sin excepción por intención. Si la búsqueda no encuentra a nadie, dos señales guían el resto: (1) puede ser un simple error de tipeo — se da un reintento antes de asumir otra cosa; (2) si la persona confirma explícitamente que no es cliente, recién ahí se deriva a `ventas`. Un cliente actual pidiendo sumar OTRO servicio sigue el mismo camino de verificación que cualquier otro trámite — la excepción es solo para quien genuinamente no está en el sistema.

**Dos bugs de código reales, no de prompt, encontrados en el camino:**

1. **El gate de ejecución no conocía `exige_verificacion` (campo nuevo, `Rol.exige_verificacion`, default `True`).** Se agregó el campo y se referenció en el prompt, pero el gate real en `motor.py` (`nivel_exigido`) seguía calculado solo a partir de `orientado_a == "cliente_final"`, ignorando el campo nuevo. Resultado: toda herramienta de `ventas` (incluso `contar_clientes`, sin ningún dato sensible) quedaba bloqueada con `IDENTIDAD_NO_VERIFICADA` aunque el prompt ya le hubiera dicho al modelo que no hacía falta verificar. Como ese error se excluye a propósito del registro de auditoría (es el gate de seguridad funcionando, no una falla), parecía que el modelo simplemente se negaba a llamar herramientas — costó varias rondas de reescritura de prompt antes de mirar el código y encontrar que el bloqueo era real.
2. **El mismo gate bloqueaba la propia llamada a `derivar_a_area`.** Corregido el bug anterior, `ventas` ya funcionaba una vez adentro — pero el router nunca lograba derivar ahí: `derivar_a_area` es una herramienta del rol ACTUAL (el router, que sí exige verificación), así que el gate la bloqueaba a ella también, antes de que pudiera llegar al área de destino que no la necesita. Se agregó una excepción puntual: si la herramienta es una derivación y el área de destino elegida por el modelo declara `exige_verificacion=False`, el gate la deja pasar. Sin este segundo fix, el primero no alcanzaba — el modelo podía usar `ventas` una vez adentro, pero nunca conseguía entrar.

**Pendiente, no bloqueante:** el link fijo del formulario de contratación (`variables_tenant.VENTAS_FORMULARIO_URL`) quedó con un valor placeholder — falta cargar el real desde `/settings` una vez que el usuario lo confirme. El mecanismo para referenciar una variable de tenant dentro del prompt de un rol (`{CLAVE}`, sustituido en `piezas_del_system()`) es nuevo y genérico, reutilizable para cualquier dato similar en el futuro.

Verificado en vivo, de punta a punta: cobertura por localidad (`contar_clientes` con filtro `localidad`, ya existía — solo se sumó `ventas` a sus roles permitidos), precio real de un plan (`consultar_planes` → `consultar_plan_detalle`, coincide exacto con la API — el precio no viene en el listado, solo en el detalle por ID, otro hueco de documentación encontrado en el camino), y el flujo completo router → verificación fallida → confirmación → derivación real a `ventas` (no solo anunciada). Dos casos dorados nuevos, con sesión explícitamente sin verificar (el default del set ya viene verificado, y correr estos casos sin ese ajuste no probaba nada).

---

### 8.9 TR-069 — integrado y funcionando, pero PENDIENTE de habilitación masiva (agosto 2026)

SmartOLT expone `GET /api/onu/get_onu_router_hosts/{sn}`, que devuelve los equipos conectados al router del cliente: nombre (`HostName`), si están conectados ahora (`Active`), y si entraron por WiFi (`802.11`) o por cable (`Ethernet`). Responde en 2-3 segundos, no es el endpoint pesado. Es lo único que deja ver **del lado de adentro de la casa** — hasta ahí el diagnóstico llega a la ONT y después hay que preguntar.

Resuelve exactamente los tres casos de `no_internet` que hoy solo se distinguen preguntando: falla **un aparato** (varios activos, WiFi y cable), falla **el WiFi** (solo los de cable activos), o **no hay nada conectado** (lista vacía con la ONT en línea).

**La herramienta (`consultar_dispositivos_conectados`) está construida y verificada**, con la lista blanca acotada a `HostName`, `Active` e `InterfaceType` — la MAC y la IP de cada aparato del cliente NO llegan al modelo. Se verificó contra un cliente con 11 equipos conectados: el filtro las descarta.

**Por qué queda pendiente:** de 5.329 ONUs, **solo 5 tienen TR-069 habilitado** (medido 19/08/2026), y de esas 5 dos responden con datos, una con lista vacía y **dos fallan** con `tr069_unable_to_process_command`. Habilitar TR-069 de forma masiva es una operación de red que va junto con la integración del CRM, no una decisión del asistente. Hasta entonces, las ramas que dependen de esta herramienta se van a ejercitar en el 0,1% de los clientes.

**Decisión (21/08/2026): el árbol de diagnóstico NO se apoya en TR-069.** Se diseña con lo que SÍ está disponible para todos — WispHub (estado de cuenta, ping) y SmartOLT (estado de ONU, señal, causa de caída, incidentes de red) — y el dato de dispositivos entra como confirmación *opcional* cuando existe. El respaldo cuando falla no es "no hay nadie conectado" (eso sería mentirle a alguien) sino **preguntarle al cliente**, que es como se hacía antes de tener la herramienta.

**Un fallo de TR-069 no es una lista vacía.** Está escrito en la descripción de la herramienta y es la trampa más fácil de este endpoint: tratar "no pude ver" como "no hay nada conectado" le diría a un cliente que no tiene ningún equipo cuando en realidad no se pudo mirar.

Cuando la habilitación masiva esté hecha, lo que falta es solo **volver a apoyarse en ella** en el árbol y agregar sus casos dorados — la herramienta, el filtro de campos y la normalización de la respuesta (`extraer_de` con notación de punto, y diccionarios indexados por número convertidos a lista) ya están construidos y probados.

---

### 8.10 `no_internet` — cerrado en código, con una rama que solo se confirma en una caída real (agosto 2026)

El caso quedó con **once ramas** y cada una sabe dónde termina. Cuatro se resuelven sin humano y sin visita (suspensión por mora → facturación; falla en un solo aparato; solo WiFi; equipo sano en todos los aparatos → reinicio remoto). Tres agendan visita solas (fibra cortada confirmada; sin energía con corriente confirmada y sin recuperarse; ping sin respuesta con la ONU en línea, reinicio hecho y sin MAC). Cuatro terminan en una persona a propósito, porque mandar un técnico no las resolvería.

**El atajo por evidencia** (`escalamiento.evidencia_suficiente`): cuando la red ya dijo la causa —pérdida de señal óptica, o el 1490 fuera de rango— no se le hace contestar al cliente el checklist del manual. El checklist está escrito para una persona que atiende por teléfono y en esas ramas pide datos que no existen: el 21/08/2026 exigía *"¿qué mensaje aparece en el dispositivo?"* a alguien sin ninguna conexión de la cual leer un mensaje. Solo se salta el verificador donde la evidencia viene de la **red**, nunca del relato del cliente — por eso "equipo sin energía" NO está en la lista: esa confirmación la da el cliente.

**El veto** (`escalamiento.no_agendar_si`): una caída que afecta a varios vecinos del mismo puerto se ve, desde la ONU de uno solo, **idéntica a su propia fibra cortada** — misma causa `sin señal optica`, que es justamente la evidencia que agenda sola. Sin el veto, treinta reportes de la misma caída despachan treinta técnicos a treinta casas por una falla que no está en ninguna de ellas. Vive en código, en la ruta que escribe el ticket, y no en el prompt (RNF §7.4): el modelo compone el mensaje, pero no es quien decide la escritura.

**Lo que el cliente ve de un incidente de red**: solo `es_incidente_de_red` y `desde_por_tiempos` — que su caída es general y desde cuándo, que es lo que le explica que no es su equipo. Cuántos vecinos están caídos, qué porcentaje del puerto, en qué zona y en qué caja es panorama interno de la red (mismo criterio que `olt_id`/`board`/`port`, RF-07).

**Verificado en vivo (21/08/2026)** con la ONU de prueba puesta fuera de servicio a propósito: la rama de visita produjo el **ticket 90662** en WispHub, asunto `No Tiene Internet`, con el diagnóstico real en la descripción (ONU Offline, ping 100% de pérdida, sin incidente de red, corriente confirmada, reinicio hecho). El serial llegó solo desde WispHub por la recuperación de sesión, sin sembrarlo.

Tres defectos salieron de esa corrida, ninguno visible en lo que el asistente contesta:

- **El caso quedaba colgado.** Al repreguntar por un dato del checklist se posponía la escalada, y el caso solo volvía si el modelo decidía escalar otra vez por su cuenta. Si en el turno siguiente preguntaba otra cosa, la verificación no corría nunca más: el agente le prometía un técnico al cliente en cada turno y no había un solo ticket detrás. Es la falla con la que se abrió este trabajo. Ahora el agendamiento pospuesto se retoma solo (`estado["agendamiento_pendiente"]`), y con `repreguntado_agendamiento` ya en `True` la segunda vuelta termina sí o sí: o ticket, o persona.
- **Una causa sin mapear dejaba al agente ciego.** `_aplicar_mapeos` se callaba ante un valor desconocido, confiando en que el dato crudo seguía disponible — falso justo para el rol que diagnostica, cuya lista blanca solo deja pasar `_interpretado`. La herramienta devolvía `{"ONU details": {}}`.
- **El asunto del ticket era de TV.** `argumentos_fijos` pisa cualquier valor que se le pase, así que una falla de fibra entraba como `Problemas De Tv`. Se separa en `agendar_visita_internet`, que es para lo que `agendamiento_automatico` es un mapa caso→herramienta.

**Lo que sigue sin poder verificarse:** las ramas que dependen de un estado que la cuenta de prueba no puede producir a demanda — señal fuera de rango, y la caída compartida (`no_agendar_si`). Esas están cubiertas por `tests/test_agendamiento_veto.py` sobre el historial ya filtrado, y se confirman en campo cuando ocurran. Tampoco tienen caso dorado, y no solo por el equipo: el corredor de casos dorados llama a `motor.responder`, que **no** incluye el agendamiento — esa ruta vive en el canal.

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
