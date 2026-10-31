# PRD — Dexter: la operación de un ISP con IA

> **Documento de Requisitos de Producto (Product Requirements Document)**
> Plataforma SaaS multi-empresa para proveedores de internet. Reescrito en sus §1–§3 el 30/10/2026 (ver §8.17): la versión anterior describía un asistente interno con un modelo local, que dejó de ser el producto en agosto.

---

## 1. Resumen ejecutivo

Dexter es una plataforma para ISPs que **atiende a sus clientes por WhatsApp, responde a sus colaboradores por web y coordina su operación de campo** (Supervisor, Despacho, app de técnicos), consultando y actuando sobre los sistemas de la empresa: WispHub, SmartOLT y el CRM. Es multi-empresa: dar de alta un ISP es configuración, no código (ARQUITECTURA.md).

**Lo que se vende es capacidad: que el mismo equipo atienda más clientes, más rápido y con menos errores.** Primer despliegue: Rapilink (~7.272 clientes activos). El modelo de lenguaje es DeepSeek vía API, amparado en la autorización de tratamiento que firma el cliente (RNF-01); la historia del modelo local está en §7.1.

El sistema **no entrena** un modelo: lo integra mediante *tool calling* a las APIs de la empresa, con validación, filtrado de datos sensibles y una frontera de autorización en código antes de cualquier efecto.

---

## 2. Problema, tesis y principio

### Problema

Un ISP crece en clientes más rápido que en personas. Cada cliente nuevo trae mensajes, tickets, visitas y cobranza, y hoy cada uno pasa por alguien que busca el dato en tres sistemas, decide y lo vuelve a escribir en otro. El costo de atender crece con la base de clientes; el margen no.

### Tesis de negocio (30/10/2026)

> **Con el mismo equipo, el doble de clientes.**

Dexter absorbe el **volumen** —el primer contacto, el diagnóstico, la clasificación, el reparto, el seguimiento, el aviso— para que las personas del equipo dediquen su tiempo a lo que solo una persona puede resolver.

Se vende como capacidad y no como reemplazo de personal, por tres motivos: un ISP que crece no despide, deja de contratar, y eso es lo que paga; quien compra "reemplazo" compara contra un sueldo, quien compra capacidad compara contra su crecimiento; y el cliente final tiene que poder llegar a una persona cuando la necesita (§8.17, riesgos).

### Métrica norte y sus contrapesos

**Norte: casos resueltos por persona del equipo, por mes**, por empresa. Se calcula, no se declara (§12.5: el código calcula).

| Métrica | Qué mide | Por qué está |
|---|---|---|
| **Resolución sin persona** | % de conversaciones de clientes, en canal real, que se cierran sin que una persona escriba, tome el caso ni apruebe una acción | Es la palanca directa de la tesis |
| **Recontacto a 72 h** | Mismo cliente que vuelve a escribir dentro de 72 h del cierre | Contrapeso: una resolución falsa sube la métrica de arriba y baja esta |
| **Satisfacción** | Encuesta de cierre por WhatsApp | Contrapeso: cerrar rápido no es resolver |
| **Visitas evitadas** | Reinicio remoto con `ACCION_CONFIRMADA` y sin visita agendada en los 7 días siguientes | La visita es el costo más alto de un ISP |
| **Minutos humanos ahorrados** | Conversaciones resueltas sin persona × minutos por conversación, más visitas evitadas × minutos por visita; los dos los declara cada empresa | Traduce la métrica al idioma de quien compra |
| **Tiempo hasta resolución** | Del primer mensaje al cierre | Calidad percibida |

**Regla:** un cambio que sube *resolución sin persona* mientras sube el *recontacto* o baja la *satisfacción* es una regresión, aunque el número principal mejore.

### Principio: alcance sin techo, autonomía ganada con evidencia

| Eje | Dirección |
|---|---|
| **Alcance** — cuántos sistemas ve, cuántas preguntas responde, cuántas tareas toma | **Crece sin techo.** Aquí vive el valor |
| **Autonomía** — qué ejecuta sin que una persona lo apruebe | **Crece acción por acción y empresa por empresa, solo con evidencia y con validación en código antes del efecto** |

*Hasta el 30/10/2026 la segunda fila decía "no crecer". Se cambió porque congelaba la tesis: el reinicio remoto, la rama que resuelve sin visita, exige aprobación humana en cada caso desde M06-A (21/09/2026). El riesgo que motivaba "no crecer" —la lección de `gemma3`, §7.1— sigue intacto: lo que cambia es que la autonomía deja de ser una opinión y pasa a ser una medición.*

Una acción pasa de "una persona aprueba" a "la IA ejecuta" **solo si cumple las cuatro**:

1. **Su efecto se verifica en código después** — p. ej. `last_status_change` para un reinicio (§12, decisiones congeladas de CLAUDE.md). Sin verificación posible, siempre una persona (CLAUDE.md §10).
2. **Sus precondiciones se comprueban en código antes** (`exige_previas`), sobre datos medidos y no sobre el relato del modelo.
3. **Hay evidencia en esa empresa**: un mínimo de propuestas revisadas por personas en una ventana, con una tasa de aprobación sin cambios por encima de un umbral, y cero verificaciones fallidas atribuibles a la acción. Mínimo, ventana y umbral son configuración por empresa, con un piso fijo del núcleo que ninguna empresa puede bajar.
4. **Se degrada sola**: si las verificaciones fallidas o el recontacto de esa acción superan su umbral, vuelve a "una persona aprueba" sin intervención.

**Subir lo decide una persona viendo la evidencia; bajar lo hace el código.** El interruptor y el techo de autonomía (CLAUDE.md §8, PRD §8.6) siguen por encima de todo. Por este camino **nunca** salen solas: `registrar_pago`, las cancelaciones, ni ninguna acción cuyo efecto no se pueda medir.

> **Principio central:** *la inteligencia del sistema no está en el modelo, está en el catálogo de herramientas.* El modelo es la interfaz —traduce lenguaje a llamadas y datos a frases—; el conocimiento vive en los sistemas de la empresa y las garantías viven en el código.

### Requisitos permanentes de seguridad
- Cero exposición de datos sensibles innecesarios (IP, MAC, credenciales) al modelo.
- Cero acciones irreversibles sin aprobación humana, salvo las que ganaron autonomía por las cuatro condiciones de arriba.

---

## 3. Usuarios y áreas

Dexter tiene **tres tipos de usuario**: el **cliente final** del ISP (por WhatsApp, atendido por los agentes `cliente_final`, `soporte_tecnico_cliente`, `facturacion_cliente` y `ventas`), el **colaborador** (por web, según su área) y la **cuadrilla de campo** (app móvil). *Hasta el 30/10/2026 esta sección decía "uso interno, nunca el cliente final", que dejó de ser cierto en agosto.* Para los colaboradores, el comportamiento y los permisos cambian por área:

| Área | Qué consulta / hace | Datos que SÍ necesita | Datos que NO debe ver |
|------|--------------------|----------------------|----------------------|
| **Soporte** | Estado de clientes, tickets | Nombre, estado, plan, facturas al día, saldo, fecha de corte, zona, **contacto (email, teléfono, dirección)** | IP, MAC, credenciales, precios del plan |
| **Facturación** | Facturas, pagos, cartera | Facturas, montos, estados de pago | Datos técnicos de red |
| **Técnica** | Datos de red, conectividad | IP, MAC, router, zona, ONU | (acceso técnico amplio) |
| **Administración** | Informes agregados | Datos consolidados/anonimizados | PII individual innecesaria |

> **Principio rector:** control de acceso por rol. Cada área ve solo las herramientas y campos que le corresponden.

---

## 4. Qué hay hoy y hacia dónde va

### 4.1 Lo que hay (medido el 30/10/2026)

| Superficie | Para quién | Qué hace | Dónde vive |
|---|---|---|---|
| **Atención por WhatsApp** | Cliente final | Un router deriva a especialistas: **soporte técnico** (diagnóstico de "no tengo internet" en 11 ramas con WispHub y SmartOLT, reinicio remoto, agendamiento de visita), **facturación** (estado de cuenta, comprobante de pago), **ventas** (cobertura, planes curados, solicitud). Cada especialista verifica identidad; las notas de voz se transcriben; una guardia revisa el texto antes de enviarlo; el escalamiento a persona tiene 10 motivos y el pedido explícito lo detecta el código | `nucleo/` (§8.8–§8.10c) |
| **Asistente web** | Colaborador | Soporte, facturación, administración (consultas agregadas, informes Excel/PDF), configuración guiada de sistemas nuevos | `/asistente`, `/configuracion-guiada` |
| **Bandeja** | Operador | El relevo IA ↔ persona: control, asignación, tomar y devolver, aprobar acciones, ventana de 24 h, plantillas, rótulos, reincidencia, carga del equipo | `/conversaciones` (§8.11, §8.16) |
| **Tickets y casos** | Operador | CRM con importación y conciliación horaria con WispHub, área por departamento, alta de tickets en WispHub, calidad (encuesta de cierre por WhatsApp) | `/tickets` (§8.14, §8.15) |
| **Supervisor y Despacho** | Coordinador / NOC | Detecta situaciones de red, clasifica la labor de cada ticket, arma de madrugada la jornada de cada cuadrilla por zona y labor, propone material del día por bodega y kit, revisa el cierre de cada orden y le recuerda al técnico lo vencido | `/supervisor-noc` |
| **App de campo** | Técnico | Órdenes del día en el orden del Supervisor, trabajo sin señal, novedades de un toque, cierre con fotos, material recibido y escaneo de equipos | `apps/tecnicos-mobile` (Flutter) |
| **Inventario** | Bodega | Bodegas, custodia por técnico, material apartado por orden, devoluciones | `/inventario` |
| **Mensajes automáticos** | Empresa | Catálogo de 12 avisos por WhatsApp (ticket creado y cerrado, visita programada, recordatorio de pago, suspensión, confirmación y rechazo de pago, promesa, bienvenida, encuesta…), cada uno con su plantilla, su interruptor y su modo prueba. **Tienen disparador la encuesta y, desde el 30/10/2026 (sin desplegar), la visita programada**: los demás se configuran y no salen. Todo aviso proactivo pasa por `POST /avisos/evento` (`nucleo/seguimiento/avisos.py`), que aplica el horario de la empresa y busca el número | `nucleo/config/mensajes_catalogo.py` |
| **Centro de mando** | Dirección | Estado en vivo de cada agente | `/centro-mando` |
| **Gobierno** | Plataforma | Frontera de autorización de 8 pasos, interruptor, techo de autonomía, aprobación atada, idempotencia, listas blancas, redacción de texto libre, guardia de salida, auditoría sin datos | `nucleo/seguridad/` (§7.4, §8.6) |
| **Consumo** | Plataforma | Tokens y costo por empresa | `/consumo` |
| **Capacidad** | Dirección | Las seis métricas de §2 por período: resueltas sin persona con sus contrapesos (recontacto, satisfacción), visitas evitadas, minutos ahorrados, tiempo hasta resolver y casos por persona. *En código el 30/10/2026, sin desplegar* | `/capacidad`, `GET /reportes/capacidad` |

**Lo que todavía no hay**, y es lo que la tesis necesita (§2): una medición del trabajo que Dexter le ahorra a cada empresa; avisos que salgan solos; una forma de que una acción gane autonomía con evidencia; y un alta de empresa que no pida un desarrollador.

### 4.2 Hacia dónde va

El orden y el porqué están en §8.17. En una línea cada ola:

| Ola | Qué entrega | Cómo se sabe que sirvió |
|---|---|---|
| **1** | Tablero de capacidad · la falla de barrio se consulta antes de reiniciar · el backend falla cerrado sin empresa — **en código el 30/10/2026, sin desplegar** | Las seis métricas de §2 visibles por empresa; la batería pasa de 0/10 en falla de barrio |
| **2** | Los avisos del catálogo salen solos, más caída masiva y visita confirmada | Baja el volumen entrante en una caída; sube la satisfacción |
| **3** | Autonomía ganada, empezando por el reinicio remoto | Sube *resolución sin persona* sin que suba el recontacto |
| **4** | Alta de un ISP con WispHub + SmartOLT en un día y sin código; más de un proceso del motor | Una segunda empresa en producción |

### 4.3 Fuera de alcance (por ahora)
- Fine-tuning / entrenamiento del modelo.
- Una abstracción de "proveedor ISP" en código antes de que exista un cliente que no use WispHub (§8.17, decisión 6).
- Canal telefónico de voz (§8.17, "Qué no se hace").

*Esta lista decía "atención directa al cliente final" e "integraciones distintas a WispHub": las dos dejaron de estar fuera en agosto (WhatsApp, SmartOLT, BottleCRM).*

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

### Plataforma multi-área (hecho)
- **RF-08:** Autenticar al colaborador e identificar su área. ✅ JWT de BottleCRM (§8.1)
- **RF-09:** Exponer al modelo solo las herramientas permitidas para el área. ✅
- **RF-10:** Filtrar los campos devueltos según el área. ✅
- **RF-11:** Generar informes bajo demanda a partir de consultas en lenguaje natural. ✅
- **RF-12:** Exportar informes a formato descargable (Excel/PDF). ✅ (§8.4)
- **RF-13:** Registrar auditoría de consultas por usuario. ✅ (§8.2)
- **RF-14:** Responder consultas **agregadas** (conteos, totales, comparaciones por periodo o zona) mediante herramientas parametrizadas que el modelo compone y el código calcula (ver decisión §12.5). ✅
- **RF-15:** Toda respuesta agregada debe declarar los filtros y el periodo con que se calculó, para que el colaborador pueda detectar una interpretación errónea de su pregunta. ✅

### Hacia dónde va (§8.17)
- **RF-16:** Cada empresa ve, por período, las seis métricas de §2, calculadas por el código sobre conversaciones de canales reales. *(Ola 1)* ✅ en código, sin desplegar (§8.17)
- **RF-17:** Ninguna lectura del backend sirve datos sin una empresa resuelta: sin empresa, nada. *(Ola 1)* ✅ en código, sin desplegar (§8.17)
- **RF-18:** Un reinicio remoto solo se propone después de comprobar en código que no hay una caída compartida. *(Ola 1)* ✅ en código, sin desplegar (§8.17)
- **RF-19:** Cada aviso del catálogo de mensajes automáticos sale solo cuando ocurre su evento, si la empresa lo encendió; se agregan caída masiva y visita confirmada. *(Ola 2)* — *visita programada, ticket creado y caída masiva (con aprobación humana, pestaña Fallas de red) en código el 30-31/10/2026, sin desplegar*
- **RF-20:** Una acción gana o pierde autonomía por empresa según las cuatro condiciones de §2, y la evidencia que la sostiene se puede ver. *(Ola 3)*
- **RF-21:** Un ISP con WispHub + SmartOLT se da de alta sin cambios de código ni deploy. *(Ola 4)*
- **RF-22:** El motor corre en más de un proceso sin que una conversación pierda su hilo. *(Ola 4)*

---

## 6. Requisitos no funcionales

- **RNF-01 · Privacidad:** cumplimiento con la Ley 1581 de 2012 (protección de datos personales, Colombia).
  - **Ya no hay modelo local** (agosto 2026). El diseño original dejaba Ollama on-premise como resguardo: un rol sin enrutar, o un `override` mal escrito, se quedaba en casa. Ese resguardo **dejó de existir** cuando se sacó Ollama del VPS al pasar los embeddings a la API de OpenAI — era su único consumidor y el servidor no tenía memoria de sobra. Hoy `modelo_por_defecto` es DeepSeek, así que **todo** sale a una API externa, amparado en la misma autorización de tratamiento de abajo. Un nombre de modelo mal escrito ya no se queda en casa: falla el turno (`cliente.py::resolver` lo interpreta como local y no hay local que responda).
  - **Excepción aprobada (agosto 2026): DeepSeek (`deepseek-v4-flash`) para todos los roles**, incluidos los que llevan PII (`soporte`, `facturacion`, `cliente_final`). Base legal: la autorización de tratamiento que firma el cliente al contratar **cubre transferencia internacional de datos** (Ley 1581, art. 26 — la transferencia a países sin nivel adecuado de protección es lícita con autorización expresa e inequívoca del titular). Confirmado sobre el texto vigente de Rapilink; los ~7.272 clientes activos ya lo firmaron.
  - **Transcripción de voz con OpenAI (`gpt-4o-transcribe`, activa desde el 30/09/2026)**: el audio del cliente sale a OpenAI. **Decidido por el usuario el 30/10/2026**: la autorización de tratamiento que el cliente firma al contratar cubre este uso, con la misma base que DeepSeek. Queda una comprobación de texto, no de decisión: que la autorización hable de proveedores tecnológicos en general y no nombre solo a uno. Para cada empresa nueva, su propia autorización tiene que cubrir a los dos proveedores antes de encender la transcripción.
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
- **RNF-03 · Costo:** DeepSeek cuesta ~$0.24 por cada 1.000 consultas (agosto 2026); el consumo real por empresa se ve en `/consumo`. El costo que importa para la tesis no es el del modelo sino el de cada caso que termina en una persona o en una visita: por eso la métrica norte (§2) es de capacidad, no de tokens.
- **RNF-04 · Rendimiento:** 4.7–12 s por turno con DeepSeek (RNF-01), medido sobre la tarea real. El techo de concurrencia hoy es de un proceso con 8 hilos para todas las empresas juntas (§8.17, Ola 4); un segundo proveedor de respaldo ante una caída de DeepSeek espera a que su autorización de tratamiento esté resuelta.
- **RNF-05 · Mantenibilidad:** herramientas, filtros y prompts son configuración por empresa (`tenants/` como semilla, `asistente.tenant_config` como fuente de verdad); el núcleo no conoce a ninguna empresa y una guarda lo comprueba (ARQUITECTURA.md).
- **RNF-06 · Multi-empresa, fallando cerrado:** sin una empresa resuelta no se sirve ningún dato, en el motor (medido: 0 filas) y en el backend (Ola 1 de §8.17).

---

## 7. Arquitectura técnica

### 7.1 Stack

| Capa | Tecnología |
|---|---|
| Modelo de lenguaje | **DeepSeek** (`deepseek-v4-flash`) vía API, para todos los roles (RNF-01). Cliente: librería `openai`, contrato compatible |
| Embeddings y transcripción | OpenAI (`text-embedding-3-large`, `gpt-4o-transcribe`) |
| Motor | Python 3.13 · Flask + gunicorn (`nucleo/`) |
| Plataforma | BottleCRM vendorizado: Django + DRF + Celery (`django-crm/backend`) y SvelteKit (`django-crm/frontend`) |
| App de campo | Flutter, con operación sin señal (`apps/tecnicos-mobile`) |
| Base | PostgreSQL 17 (Supabase autoalojado, solo Postgres), migraciones por ledger propio (`supabase/`) |
| Sistemas del ISP | WispHub (gestión, tickets, facturas), SmartOLT (red de fibra), WhatsApp Cloud API (Meta) |
| Despliegue | Un VPS con Dokploy, autodeploy al pushear la rama de despliegue (§9, DESPLIEGUE.md) |

#### Historia — el modelo local (julio–agosto 2026)

Hasta agosto el motor corría un modelo local con Ollama. Se retiró por velocidad (42.6 s por turno contra 4.7–12 s, RNF-01) y por memoria del servidor. Lo que sigue queda porque sus lecciones aplican a **cualquier** cambio de modelo.

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

### 7.1.1 Historia — el equipo de desarrollo y por qué MoE

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

### 7.2 Componentes y flujo de un turno

```
Cliente (WhatsApp, /canales/whatsapp/<empresa>)   ·   Colaborador (web, sesión del CRM)
        │
        ▼
[ 1. Canal ]  ──► empresa por la URL o por la sesión; nota de voz → texto; guardar el mensaje primero
        │
        ▼
[ 2. Turno ]  ──► ¿la conversación la tiene una persona? entonces la IA no responde (relevo, §8.11)
        │
        ▼
[ 3. Rol ]  ──► router → especialista; cada rol trae su prompt, su catálogo y sus listas blancas
        │
        ▼
[ 4. Bucle de herramientas ]  ──► el modelo propone llamada y argumentos, con tope de vueltas
        │
        ▼
[ 5. Frontera ]  ──► empresa → interruptor → techo → autorización → aprobación atada →
        │            auditoría → permiso → idempotencia → último metro (CLAUDE.md §5)
        ▼
[ 6. Herramienta ]  ──► WispHub / SmartOLT / CRM; veredictos calculados en código
        │
        ▼
[ 7. Listas blancas + redacción ]  ──► qué campos llegan al modelo, y sin PII en el texto libre
        │
        ▼
[ 8. Redacción y guardia de salida ]  ──► el modelo redacta; el código revisa el texto
        │
        ▼
[ 9. Escalamiento y seguimiento ]  ──► ¿hace falta una persona? ¿una visita? ¿una verificación?
        │
        ▼
Respuesta entregada (aceptado ≠ entregado ≠ leído)
```

### 7.3 Patrón de tool calling

El modelo propone; el código valida, ejecuta y filtra; el resultado vuelve al historial con rol `tool`, y el bucle sigue hasta que el modelo responde con texto o llega al tope de vueltas. *Esta sección describía dos llamadas fijas, del prototipo de consola; el bucle reemplazó ese diseño (§12.3, punto 2).*

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

### 7.5 Extender: una herramienta, un rol, una empresa

Todo se extiende por configuración del tenant, no por código: una herramienta se declara en el catálogo (`herramientas`, con sus filtros verificados y su lista blanca por rol), un rol en `roles` (prompt, catálogo, campos permitidos), y una empresa es una fila más en `asistente.tenant_config`. Lo que el núcleo interpreta vive en `nucleo/config/schema.py`. *Esta sección mostraba los diccionarios de Python del prototipo (`HERRAMIENTAS_POR_AREA`, `CAMPOS_POR_AREA`); ese patrón se convirtió en la configuración de hoy.* El procedimiento y sus guardas están en CLAUDE.md §3 y §6.

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

## 8. Roadmap y decisiones

**Las fases 0–6 del plan original están cumplidas** (tabla de abajo, que queda como historia). **Lo que sigue son las cuatro olas de §8.17**, resumidas en §4.2. Las subsecciones §8.1–§8.17 registran, en orden de fecha, cada pieza construida y cada decisión con su evidencia.

| Fase | Entregable | Estado |
|------|-----------|--------|
| **0** | Prototipo de soporte en consola contra WispHub | ✅ Hecho |
| **1** | Consolidar soporte: prompt de asesor, filtro PII, consulta por cédula | ✅ Hecho |
| **2** | Identidad de área; parametrizar herramientas y filtros por rol | ✅ Hecho — login real ya existe (JWT vía BottleCRM), ver §8.1 |
| **3** | Replicar patrón a Facturación y Técnica | ✅ Catálogo definido y verificado — Técnica ahora incluye SmartOLT (lectura de red + reinicio de ONT, ver §7.7), no solo WispHub |
| **4** | Generación de informes + exportación (Excel/PDF) | ✅ Excel y PDF (ver §8.4) |
| **5** | Interfaz web interna (reemplaza la consola) | ✅ En gran parte hecho — ver §8.1 |
| **6** | Auditoría/logs y despliegue | ✅ Auditoría (§8.2) · en producción desde agosto 2026 en un VPS con Dokploy (§9), no on-premise |

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

**Actualización 21/09/2026 (M06-A): las acciones irreversibles exigen aprobación humana atada a la acción.** Decisión de negocio: `registrar_pago` (R4) y `reiniciar_ont`, `activar_catv`, `cambiar_tipo_onu` (R3) exigen aprobación humana obligatoria. Se marcan `Herramienta.irreversible` y salen **solo** por `frontera.critica()`, que exige en orden: tenant → kill switch → etapa de Autonomía 2 (+B-7) → autorización granular (+nivel) → **aprobación persistida y atada** a tenant + herramienta + origen + huella canónica de los argumentos (`nucleo/seguridad/aprobacion.py`) → auditoría → permiso → idempotencia → último metro (`frontera.exigir` vuelve a comparar la huella contra lo que sale). Una irreversible que llegue al ejecutor por cualquier otro camino (conversación, panel, ruta de servicio, ejecutor directo) no sale.

Una primera versión dejó las R3 sin gate porque la cola de aprobación no revalidaba las condiciones previas, no creaba la verificación posterior y había un defecto que registraba una verificación sobre una acción solo propuesta. Se corrigió el **mecanismo**, no la decisión: al aprobar se vuelven a **medir** las previas (fallan cerradas), la verificación se anota contra la conversación de origen (sin conversación no se aprueba), y una propuesta ya no deja verificación pendiente. Diferencias de conducta a tener presentes: (1) el kill switch **sí** frena una irreversible aprobada — `humana()` sigue sin mirarlo para todo lo demás; (2) la aprobación se persiste **antes** del efecto con compare-and-set, y si una barrera la frena queda `aprobada` con el código del bloqueo, sin reintentarse; (3) `fecha_pago` se fija al proponer; (4) al cliente nadie le avisa cuando se aprueba: se entera en su siguiente mensaje, por la verificación. `agregar_promesa_pago` (R4) queda con su aprobación anterior, no atada: no estaba en la decisión. Detalle en `M06-A_FRONTERA_AUTORIZACION.md`; las guardas son `tests/test_m06a_gate_critico.py` y `tests/test_m06a_frontera_autorizacion.py`.

**Actualización 21/09/2026 (M06-B): techo de autonomía por niveles.** El kill switch sigue siendo binario (¿puede actuar sola?); lo acompaña un **techo** por empresa (¿hasta qué nivel?): 0 observar · 1 recomendar · 2 coordinar · 3 ejecutar autorizado. Tope de política global: 3, constante del núcleo (el 4 de M09-J, "crítico, siempre humano", lo gobierna el gate de irreversibles, no un número). Es el mismo `asistente.nivel_autonomia` de Autonomía 2, ahora consultado como paso propio de la frontera justo después del kill switch (`nucleo/seguridad/techo.py`) y leído en un solo lugar. **Acota, nunca autoriza**: una acción que lo pasa sigue necesitando etapa, autorización granular, aprobación si corresponde, idempotencia y último metro. Falla cerrado sin asumir nivel (sin fila, inválido, ilegible, de otra empresa → no ejecuta; antes "sin fila" se leía como 0). Cada herramienta exige un nivel (`Herramienta.nivel_autonomia`); ninguna lo declara todavía, así que el efectivo es el de siempre: 0 lectura, 2 escritura. Solo lo mueve `autonomia_operador` vía `cli/autonomia.py --techo N --desde M`, con compare-and-set y cada intento auditado en `asistente.techo_autonomia_intentos`. De paso se cerró un hueco: una herramienta con `aprobacion_humana` (p. ej. `agregar_promesa_pago`) ya no puede salir por la puerta autónoma. Detalle en `M06-B_TECHO_AUTONOMIA.md`.

**Actualización 21/09/2026 (M06-C): aislamiento de la autorización y aprobación R4 completa.** `asistente.autorizacion_herramienta` y `asistente.ejecucion_autonoma` tenían GRANTs pero no RLS; ahora tienen RLS forzada por organización con el mismo patrón que el interruptor y el techo (el runtime lee autorizaciones y escribe su bitácora solo de su empresa; el operador autoriza y lee solo la suya). `agregar_promesa_pago` pasa a la puerta crítica (`irreversible`): todo R3 y R4 va atado. Y toda aprobación atada lleva un **sello** (hash de tenant, organización, herramienta, origen, huella y aprobador) escrito al aprobar y recalculado al ejecutar: antes el origen y el tenant solo se exigían "no vacíos", ahora se comparan. Detalle en `M06-C_AISLAMIENTO_Y_PROMESA.md`.

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

El link fijo del formulario de contratación (`variables_tenant.VENTAS_FORMULARIO_URL`, `https://rapilinksas.co/solicitud` — confirmado por el usuario con capturas del formulario real) ya está cargado, reemplazando el placeholder inicial. El mecanismo para referenciar una variable de tenant dentro del prompt de un rol (`{CLAVE}`, sustituido en `piezas_del_system()`) es nuevo y genérico, reutilizable para cualquier dato similar en el futuro.

Verificado en vivo, de punta a punta: cobertura por localidad (`contar_clientes` con filtro `localidad`, ya existía — solo se sumó `ventas` a sus roles permitidos), precio real de un plan (`consultar_planes` → `consultar_plan_detalle`, coincide exacto con la API — el precio no viene en el listado, solo en el detalle por ID, otro hueco de documentación encontrado en el camino), y el flujo completo router → verificación fallida → confirmación → derivación real a `ventas` (no solo anunciada). Dos casos dorados nuevos, con sesión explícitamente sin verificar (el default del set ya viene verificado, y correr estos casos sin ese ajuste no probaba nada). Cargado a producción: `cli/cargar_config.py` protege contra pisar ediciones hechas desde la interfaz — comparó valor por valor contra la base (v47, sin sincronizar desde el 17/08) antes de subir, confirmó que las 14 diferencias reportadas eran todas correcciones de texto de sesiones previas nunca sincronizadas, y no una edición real desde `/agentes`.

### 8.9 La verificación se muda del router a cada especialista (agosto 2026)

El diseño de §8.8 tenía un problema real, señalado por el usuario mirando el simulador: con la verificación centralizada en el router, alguien que escribía *"tengo problemas con mi internet"* (un cliente real reportando una falla) y se equivocaba tipeando la cédula dos veces terminaba con una pregunta de ventas (*"¿ya sos cliente o querés contratar?"*) que no tenía nada que ver con lo que había pedido — porque la recuperación tras un "no encontrado" repetido no sabía distinguir un simple error de tipeo de un prospecto genuino, y ofrecía la misma salida genérica sin importar el tema original.

**El cambio de fondo, no un parche.** El router (`cliente_final`) dejó de verificar identidad: su catálogo quedó reducido a `[derivar_a_area]`, y deriva apenas entiende de qué se trata — sin esperar ninguna verificación. Cada especialista (`facturacion_cliente`, `soporte_tecnico_cliente`) ganó su propia copia de `verificar_identidad_por_cedula`/`confirmar_identidad`, y pide la cédula en su propio contexto ("para revisar tu conexión..." en soporte, distinto de facturación) — así el reintento nunca se mezcla con un tema que la persona nunca mencionó. `ventas` sigue sin exigir verificación por defecto (su interlocutor típico no es cliente todavía), pero ganó las mismas herramientas de forma opcional para el caso explícito que el usuario pidió cubrir: un cliente actual que quiere sumar un servicio nuevo a su cuenta existente.

**`Rol.deriva_verificacion` (nuevo campo), y por qué no alcanzaba con reusar `exige_verificacion=False`.** Tanto el router como `ventas` tienen `exige_verificacion=False`, pero por motivos opuestos — `ventas` porque su interlocutor típicamente no es cliente; el router porque esa responsabilidad ahora es de otro. Con un solo booleano, el router hubiera heredado el texto de prompt de `ventas` ("todavía no es cliente, no busques verificar"), que es literalmente falso para la mayoría de quien le escribe. `deriva_verificacion=True` activa un tercer bloque de texto genérico ("no verificás vos, lo hace el área a la que derivás") — sin que el núcleo tenga que nombrar ningún rol de tenant específico.

**Un segundo bug de código real, no solo de prompt, para que el router pudiera derivar sin estar verificado.** El mismo gate de `_ejecutar_derivacion` (§8.8) que se corrigió para permitir derivar HACIA un área sin verificación seguía bloqueando la llamada cuando el rol ACTUAL (ahora el router) tenía `exige_verificacion=True` — y como el router ya no tiene ninguna herramienta para subir `sesion.nivel`, quedaba en un punto muerto: nunca iba a poder derivar a ningún lado. Se resolvió poniendo `cliente_final.exige_verificacion: false` — coherente con que no le queda ninguna herramienta que gatear.

**La instrucción de reintento (`_ejecutar_verificacion`, agregada en §8.8) se simplificó, no se volvió más compleja.** Ya no presupone que el segundo "no encontrado" significa "capaz quiere contratar" — ahora pide un dato alternativo (otro documento, o el nombre completo) sin cambiar de tema, y solo si eso tampoco resuelve, ofrece escalar a un colaborador humano como salida real, no como primer reflejo. La vía de escape para un prospecto que se autodeclara "todavía no soy cliente" se mantiene, disponible desde cualquier especialista, no solo desde el router.

**Un bug de datos preexistente, encontrado al reescribir los casos dorados, sin relación con este cambio.** `consultar_plan_tv` declaraba `roles_permitidos: [cliente_final]`, pero su único consumidor real siempre fue `soporte_tecnico_cliente` (ver su `puede_consultar`) — `cliente_final` nunca lo tuvo en su propio catálogo. Quedaba sin detectar porque el guarda que lo hubiera encontrado (`test_editor_config.py`, "herramienta que se quedaría sin rol") pasaba por una coincidencia no relacionada: `cliente_final` también tenía las herramientas de verificación como exclusivas, y esas disparaban el mismo rechazo esperado por otro motivo. Al mover la verificación fuera del router, la coincidencia dejó de ocurrir y el bug real salió a la luz. Corregido.

**Un bug real en el corredor de casos dorados, encontrado al escribir el caso de "cliente actual pidiendo otro servicio".** `cli/evaluar.py` mandaba TODOS los mensajes de un caso al mismo rol declarado, sin seguir `sesion.rol_siguiente` entre mensajes — a diferencia de `atender_turno()` en producción, que sí lo hace. Cualquier caso de varios mensajes que esperara una derivación a mitad de conversación le seguía mandando los mensajes siguientes al rol viejo, y fallaba con `HERRAMIENTA_DESCONOCIDA` por un motivo que no tenía nada que ver con lo que decía probar. Corregido con la misma lógica que ya usa producción.

Tres casos dorados existentes asumían el diseño anterior (verificar antes de derivar) y se reescribieron para reflejar el nuevo: ahora afirman que el router deriva de inmediato y que es el especialista quien no entrega datos sin verificar. Verificado en vivo el escenario que motivó el cambio: *"tengo problemas con mi internet"* → deriva a soporte → pide cédula en contexto de soporte → falla dos veces → sigue pidiendo confirmación sin mencionar ventas ni escalar de entrada.

### 8.10 Catálogo de venta curado, separado del catálogo técnico (agosto 2026)

Probando `ventas` en vivo, un prospecto preguntó por "300 megas" y `consultar_planes` (el catálogo técnico de WispHub, 55 entradas) devolvió **tres** resultados distintos con ese número — variantes duplicadas y nombres legacy pensados para facturar clientes existentes, no una lista pensada para vender. Cuál de esos es el plan que de verdad se ofrece hoy es una decisión humana; dejársela al modelo (o hardcodearla en el YAML) repite exactamente el error que CLAUDE.md ya prohíbe para datos de empresa.

**`PlanVenta`/`TenantConfig.planes_venta` (nuevo, `nucleo/config/schema.py`):** lista curada de `{nombre_wisphub, localidades}` — `localidades` vacío significa "disponible en cualquier zona con cobertura"; con entradas, solo se ofrece ahí. Se filtra por la misma `localidad` que `ventas` ya le pregunta al prospecto para chequear cobertura (`contar_clientes`) — deliberadamente no por `zona`/`router` de WispHub, que son catálogos con IDs independientes que la conversación de ventas nunca toca (ver skill `wisphub-api`).

**`consultar_planes_venta` (nueva herramienta, `tipo: interno`):** no llama a ninguna API — lee `planes_venta`, filtra por localidad, listo. El modelo la llama SIEMPRE primero; `consultar_planes` (el catálogo técnico) queda reservado para resolver el ID de un plan ya confirmado por la lista curada, nunca como punto de partida. Con `planes_venta` vacío (estado inicial, real en producción hasta que el usuario cargue su lista real) la herramienta devuelve una lista vacía con una advertencia explícita, y el prompt le prohíbe al modelo caer de vuelta al catálogo ruidoso — verificado en vivo: ante "qué planes hay" sin nada cargado, dice que no tiene la lista para esa zona y ofrece confirmar con un colaborador, en vez de inventar o mostrar las 55 variantes técnicas.

Verificado con datos de ejemplo en memoria (sin tocar el archivo versionado, mientras no llega la lista real del cliente): un plan sin `localidades` aparece en cualquier zona consultada; uno con `localidades` específicas solo aparece ahí. Caso dorado nuevo cubre la degradación seria con la lista vacía; el filtrado por zona con datos reales queda pendiente de un caso dorado hasta que el tenant cargue su catálogo curado real.

---

### 8.10b TR-069 — integrado y funcionando, pero PENDIENTE de habilitación masiva (agosto 2026)

SmartOLT expone `GET /api/onu/get_onu_router_hosts/{sn}`, que devuelve los equipos conectados al router del cliente: nombre (`HostName`), si están conectados ahora (`Active`), y si entraron por WiFi (`802.11`) o por cable (`Ethernet`). Responde en 2-3 segundos, no es el endpoint pesado. Es lo único que deja ver **del lado de adentro de la casa** — hasta ahí el diagnóstico llega a la ONT y después hay que preguntar.

Resuelve exactamente los tres casos de `no_internet` que hoy solo se distinguen preguntando: falla **un aparato** (varios activos, WiFi y cable), falla **el WiFi** (solo los de cable activos), o **no hay nada conectado** (lista vacía con la ONT en línea).

**La herramienta (`consultar_dispositivos_conectados`) está construida y verificada**, con la lista blanca acotada a `HostName`, `Active` e `InterfaceType` — la MAC y la IP de cada aparato del cliente NO llegan al modelo. Se verificó contra un cliente con 11 equipos conectados: el filtro las descarta.

**Por qué queda pendiente:** de 5.329 ONUs, **solo 5 tienen TR-069 habilitado** (medido 19/08/2026), y de esas 5 dos responden con datos, una con lista vacía y **dos fallan** con `tr069_unable_to_process_command`. Habilitar TR-069 de forma masiva es una operación de red que va junto con la integración del CRM, no una decisión del asistente. Hasta entonces, las ramas que dependen de esta herramienta se van a ejercitar en el 0,1% de los clientes.

**Decisión (21/08/2026): el árbol de diagnóstico NO se apoya en TR-069.** Se diseña con lo que SÍ está disponible para todos — WispHub (estado de cuenta, ping) y SmartOLT (estado de ONU, señal, causa de caída, incidentes de red) — y el dato de dispositivos entra como confirmación *opcional* cuando existe. El respaldo cuando falla no es "no hay nadie conectado" (eso sería mentirle a alguien) sino **preguntarle al cliente**, que es como se hacía antes de tener la herramienta.

**Un fallo de TR-069 no es una lista vacía.** Está escrito en la descripción de la herramienta y es la trampa más fácil de este endpoint: tratar "no pude ver" como "no hay nada conectado" le diría a un cliente que no tiene ningún equipo cuando en realidad no se pudo mirar.

Cuando la habilitación masiva esté hecha, lo que falta es solo **volver a apoyarse en ella** en el árbol y agregar sus casos dorados — la herramienta, el filtro de campos y la normalización de la respuesta (`extraer_de` con notación de punto, y diccionarios indexados por número convertidos a lista) ya están construidos y probados.

---

### 8.10c `no_internet` — cerrado en código, con una rama que solo se confirma en una caída real (agosto 2026)

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

### 8.11 Bandeja de conversaciones — el relevo entre la IA y una persona (reescrita el 16/09/2026)

**Por qué se reescribió.** La versión anterior era una tabla de 18 funciones copiadas de Intercom, Zendesk, Front y respond.io, y tenía dos errores de método:

1. **Esos productos están hechos para que una persona atienda desde el primer mensaje**, así que lo que optimizan es escribir rápido (citar, macros, atajos). Aquí la IA atiende primero y la persona entra en el relevo: recibe un caso, entiende qué hizo la IA, actúa, y lo devuelve o lo cierra. Las etapas que no existen en un inbox genérico —devolver a la IA, intervenir sin escalada, aprobar lo que la IA propone— no estaban en la lista, y "citar un mensaje" figuraba como lo siguiente mientras el relevo estaba roto.
2. **Frenaba funciones con datos de Rapilink** (cuántos operadores tiene, ~5 conversaciones por día). Eso varía por empresa —una trabaja con 1 operador, otra con 10— y la bandeja es la misma para todas. Es el mismo error que la regla multi-tenant prohíbe para la configuración, aplicado a la priorización.

**Fuente de verdad del diseño: [SPEC/CONTRATO_RELEVO_IA_HUMANO.md](SPEC/CONTRATO_RELEVO_IA_HUMANO.md).** Esta sección resume el porqué y el orden; el modelo de estados, las transiciones, las invariantes, los 16 defectos con su evidencia y los tests viven en el contrato. Si difieren, manda el contrato.

**Cómo se llegó.** Dos revisiones independientes del código coincidieron en el hueco principal (no se puede devolver a la IA desde la bandeja). Después, una auditoría externa (sin acceso al repo) marcó que D1–D7 no eran siete problemas sino síntomas de una carencia: **no existía un modelo explícito del relevo IA ↔ humano**, solo cinco booleanos con combinaciones ambiguas. El contrato se escribió sobre un mapeo del código en `92ebe78` y pasó una ronda de auditoría (arquitectura base aprobada; 14 correcciones incorporadas en la versión 2).

**Qué define el contrato, en una línea cada cosa:**
- **Control** (`ia`/`humano`) y **asignación** se guardan en base; la memoria del proceso nunca decide la pausa.
- **A quién le toca actuar** se calcula con reglas en orden sobre hechos guardados (control, asignación, origen de los mensajes, aprobaciones, pendiente interno), nunca se guarda.
- **Origen y autor** de cada mensaje van aparte del `rol` que usa el modelo, y el `rol` nunca se reemplaza.
- **Eventos del relevo** en una tabla donde solo se agregan filas, con esquema versionado y sin datos crudos.
- **Efectos externos** (caso CRM, ticket) en una cola con reintento: un fallo de integración no le devuelve la conversación a la IA.
- **Devolver a la IA** solo se completa cuando el mensaje que la acompaña fue aceptado por el canal.
- **Acciones aprobables** con revalidación declarada por herramienta y vigencia; si no se puede comprobar, no se ejecuta.

**Defectos encontrados (detalle y evidencia en el contrato, §13):** D1–D7 de la primera revisión, más D8 (tras un reinicio la IA toma como propio lo que escribió una persona), D9–D10 (la pausa se pone o se levanta solo en memoria), D11 (aprobar una acción: doble ejecución posible, quién aprobó sale del request, sin revalidación), D12 (notas internas en el insumo de resúmenes), D13 (el cierre por inactividad cierra conversaciones que esperan a una persona), D14–D16. **D7 estaba mal descrito en la versión anterior de esta sección:** las acciones de la IA que esperan aprobación no se aprueban en `/tickets/approvals` (ese es el cierre de casos del CRM); no aparecen en **ninguna** pantalla.

**Verificado después:** la lista de conversaciones se pide entera cada 8 s y la consulta no tiene `LIMIT` (`+layout.svelte:65-67`, `db.py:469-481`). **De otro alcance:** cada instalación del frontend atiende un solo tenant (`PRIVATE_ASISTENTE_TENANT`).

**Ya hecho:** estados de entrega + reintentar (06/09/2026); ventana de 24 h + plantillas (08/09/2026, §8.12); buscador de documentación dentro de la conversación (`/api/sugerencias`; copia, no inserta).

#### Orden de construcción (acordado en auditoría, 16/09/2026)

| # | Trabajo | Por qué en esta posición |
|---|---------|--------------------------|
| 0 | **Contrato del relevo + invariantes** | Sin modelo, cada arreglo parcha booleanos y rompe el anterior |
| 1 | **D3 falla cerrado** (UI + backend) | Hoy se contaminan historiales con mensajes que el cliente no escribió |
| 2 | **Origen y autor de mensajes + D8** | Integridad del historial que reconstruye la IA tras cada deploy |
| 3 | **D1: devolver a la IA** (en fases, con entrega aceptada) | Cierra el ciclo humano → IA |
| 4 | **D4 + D5: asignación y cola** | La cola deja de mentir |
| 5 | **Intervenir completo** | Tomar el control sin escalada |
| 6 | **D7: aprobación en contexto** + revalidación | La intervención humana propia del producto |
| 7 | **Desenlace + cierre + sincronización del ticket** | Cierre operacional verdadero y dato para aprender |
| 8 | **Paginación y búsqueda en servidor** | Deuda de escala; va después de los problemas de corrección |
| 9 | **Ficha de handoff con fuente y frescura** | Entender el caso en segundos (extiende la ficha que ya arma el código) |
| 10 | **Transcripción de audio** | ✅ Hecha: las notas de voz se transcriben antes del turno (`nucleo/canales/transcripcion.py`, `gpt-4o-transcribe`); el texto fijo `"[El cliente envio un audio]"` queda solo si la transcripción falla (verificado el 30/10/2026) |
| 11 | **Borrador asistido** | Depende de 9 |
| 12 | **Comodidades** (citar, borradores, @menciones, macros, atajos) | Las de equipos grandes, diseñadas para no estorbar a quien trabaja solo |

Fuera de la bandeja, anotadas en la auditoría como de alto valor: **correlación de averías** (varios clientes de la misma PON escalando a la vez → posible incidencia común; verificar antes qué expone SmartOLT) y **datos con frescura** en toda ficha técnica (fuente + hora de cada medición).

**Construcción en fases B1–B7** (contrato §15), cada una auditada antes de integrarse; se construye en `feature/bandeja-relevo` y **un único responsable integra y despliega** (separación de git, no de diseño: es un solo desarrollo). B1 D3 falla cerrado · B2 origen y autor de mensajes · B3 control, asignación y eventos · B4 sincronizaciones externas y reconciliador · B5 acciones y revalidación · B6 frontend del relevo y desenlaces · B7 lectores del legado y backfill.

**Gates antes de desplegar** (contrato §16): G1 el motor exige `MOTOR_SERVICE_TOKEN` (**verde en producción**) · G2 reloj activo (medido en producción: sí, ciclo ~60 min) · G3 acciones pendientes contadas · G4 evidencia del backfill · G5 casos dorados · G6 preflight de DDL y backfill (sin sesiones retenidas, volumen medido) · G7 reconciliador con cadencia propia de 1–5 min. · G8 revisión de las 16 conversaciones reales de legado · G9 recibo de entrega (**verde en producción** el 16/09/2026: `wamid` persistido y entregado correlacionado; ya no es pendiente) Restricción transversal: **ninguna transacción de base abierta mientras se espera una operación externa** (`idle_in_transaction_session_timeout = 60s` en producción).

**Dos decisiones de la auditoría que no hay que redescubrir:** (1) si el evaluador decidió que hace falta una persona, un fallo del CRM o de WispHub **no** le devuelve la conversación a la IA; (2) la medición de razonamiento ON/OFF **nunca** justifica quitar una aprobación humana: la config nueva de revalidación se activa cuando la medición cierre.

#### Reglas que gobiernan este orden

- **Ninguna métrica de una empresa decide si algo se construye.** Puede ordenar prioridades; no puede descartar una función que otra empresa necesita.
- **Las macros siguen bloqueadas por método, no por tamaño:** se guardan en `tenant_config`, y cada guardado parte la medición de razonamiento ON vs OFF en un grupo nuevo. Se destraban cuando termine esa medición.

#### Descartado, con motivo

- **Traducir mensajes:** los clientes de un ISP local escriben en el idioma del ISP. Reabrir si entra una empresa con clientela multilingüe.
- **Llamadas desde la bandeja, enlace directo a un mensaje, galería de adjuntos:** no resuelven ninguna etapa del relevo.
- **Mensajes interactivos de WhatsApp (botones, listas):** no son de la bandeja; son del roadmap del asistente.

---

### 8.12 La ventana de 24 h de WhatsApp, visible antes de escribir (08/09/2026)

Meta solo acepta texto libre dentro de las 24 h desde el **último mensaje del cliente**; fuera de eso solo pasan plantillas aprobadas. El motor ya sabía enviarlas y ya manejaba el rechazo `131047` — pero eso aparecía **después** de escribir la respuesta.

**El punto delicado es de dónde sale la fecha.** `conversations` tiene `actualizado_en` y `ultimo_mensaje_en` a mano, y las dos son la respuesta equivocada: se mueven cuando escribimos nosotros, así que la pantalla diría "quedan 23 h 58 min" y el envío fallaría igual. La ventana se calcula con un subselect sobre `rol = 'user'` y nada más. Fijado en `tests/test_ventana_whatsapp.py`.

**La UI informa, el backend manda.** El cálculo local no autoriza: el manejo del rechazo de Meta sigue vivo, y el contador descuenta tiempo transcurrido en vez de recalcular desde una fecha absoluta.

**Enviar una plantilla no reabre la ventana** — se guarda con rol `assistant`, que es el rol que el cálculo ignora. No hay bandera que alguien pueda olvidar de apagar.

**Limitación real de la cuenta, que esta pantalla destapó:** Rapilink tiene **una sola plantilla aprobada** en Meta (`bienvenida`, categoría MARKETING, sin variables) y su texto dice *"Bienvenido a Isergy"*. Para retomar un caso de soporte hace falta una plantilla **UTILITY** propia, y aprobarla lleva días. **Acción operativa pendiente, independiente del desarrollo.**

---

### 8.13 DECISIÓN — una plataforma para varios ISPs, no una instalación por cliente

**Decidido el 24/09/2026.** Ante la pregunta de cómo se vende Dexter cuando
aparezca el segundo ISP, se elige **una sola plataforma donde entran varias
empresas**, y se descarta el despliegue por cliente.

Lo que se descarta y por qué: un stack completo por ISP no cuesta código —hoy
funcionaría tal cual— pero se paga en mantenimiento para siempre. Cada
actualización se repite N veces, cada cliente puede quedar en una versión
distinta, y el día que una migración falle en uno solo hay que diagnosticar un
entorno que ya no es igual a los demás.

**El motor ya está listo para esto.** La URL del webhook lleva el tenant
(`/canales/whatsapp/<slug>`), las credenciales van cifradas por empresa en
`asistente.tenant_secrets`, y el aislamiento está medido: `app_backend` sin
fijar empresa ve **0 filas**, no todas. BottleCRM ya es multi-organización.

**Lo que falta es el frontend.** Saca el tenant de una variable de entorno y
nunca de la organización de quien inició sesión. Medido el 24/09/2026:

| | |
|---|---|
| Archivos | 70 |
| Apariciones | 80 |
| De ellas, **la misma línea exacta** (`const tenant = env.PRIVATE_ASISTENTE_TENANT;`) | **73** |
| Que deriven el tenant de la sesión | **0** |
| Repartidas en | `routes/api` 46 · `routes/(app)` 13 · `lib/server` 11 |

Que 73 de 80 sean idénticas cambia el tamaño del problema: **no son 80
ediciones a medida, es un ayudante y una sustitución mecánica**, más cuatro
casos particulares. Y el ayudante tiene que ser uno solo — el esquema del
formulario de Campo ya enseñó qué pasa cuando el mismo dato se interpreta en
varios lugares.

**El problema de diseño que queda abierto, y no es menor.** El motor resuelve
`slug → organization_id` (`asistente.tenant_config`). La plataforma necesita la
**inversa**, y el frontend no puede consultarla: se conecta a través de Django,
que entra como `crm_user` y **no tiene privilegios sobre el esquema
`asistente`**. Es el mismo principio que ya gobierna el contexto técnico —
*"Django no habla con WispHub ni con SmartOLT; el motor sí"*— así que la
resolución debería pedírsela al motor, no abrir un segundo camino.

**El supuesto del que depende todo esto está comprobado** (24/09/2026, contra
el esquema): `asistente.tenant_config` tiene `organization_id` como **clave
primaria** y `slug` con **restricción UNIQUE**. Es una biyección, así que la
inversa es una función y el diseño se sostiene. Si no lo hubiera sido —una
organización con varios tenants— habría que haber replanteado todo antes de
tocar una línea.

La tabla además tiene RLS por organización (`organization_id =
asistente.org_actual()`), así que el endpoint que resuelva la inversa tiene que
fijar el contexto como cualquier otra lectura.

**Dos decisiones que van junto con esta:**

- **El dominio del webhook.** `motor.rapilinksas.co` lleva la marca del primer
  cliente. Con esta decisión tomada, conviene mudarlo a un dominio neutro
  **antes** del segundo ISP: después obliga a que *cada* cliente reconfigure su
  webhook en Meta a mano.
- **`--workers 1`.** El historial caliente de las conversaciones vive en la RAM
  del proceso. Aguanta con hilos, pero es un techo real con varias empresas, y
  se levanta el día que ese historial viva en `asistente.conversations`.

**Y una advertencia medida:** esta deuda **crece sola**. Cuando se anotó por
primera vez eran 23 lugares; hoy son 80. Cada pantalla nueva del asistente suma
otra aparición, así que posponer la ejecución encarece la decisión que ya se
tomó.

### 8.14 DECISIÓN — el área de un caso sale del departamento del ticket, y cada persona ve siempre lo suyo (20/10/2026)

**El error que la originó.** El usuario comparó los tickets abiertos de WispHub
en Soporte y Operativo (64) con las tarjetas de Dexter (37 + 35 = 72) y no
coincidían. Medido en producción ese día con un comando de solo lectura: **816 de
816 casos abiertos sin `Case.area` escrita**. El campo existe desde el 16/10 y el
backend lo aceptaba, pero el alta lo descartaba y la relectura de WispHub nunca
lo mandaba. Así el área de cada caso salía de la persona asignada, y las
tarjetas contaban personas, no departamentos.

**Lo que se decidió**, con el usuario:

1. El área de un caso la da la regla de importación (`importacion_tickets.destinos`,
   departamento y asunto del ticket), al crearlo **y cada vez que se relee**. Si
   el ticket cambia de departamento en WispHub, el caso cambia de área. Si la
   regla no resuelve un área declarada, no se escribe nada: no se adivina y no
   se borra.
2. **El departamento Operativo de WispHub es el área `operativo`** en Dexter.
   Hasta ese día iba a `soporte_tecnico`. Consecuencia buscada: las tarjetas de
   Tickets coinciden con los departamentos. Consecuencia aceptada: los tickets
   nuevos de Operativo se asignan a gente de operativo.
3. **Una persona siempre ve en Tickets los casos que tiene asignados**, aunque
   sean de otra área. Sin esto, escribir el área sacaba de la lista de un
   técnico los tickets que le tocan. Las tarjetas por área siguen contando por
   el área del caso, y la pantalla dice cuántos de la lista son de otra área.

**Lo que la reabre:** que una persona necesite ver un área entera que no es la
suya (eso es un rol, no esta regla), o que un departamento de WispHub deje de
corresponder a un área de Dexter. Lo primero se resuelve con permisos; lo
segundo, en `destinos`, que es configuración del tenant.

### 8.15 DECISIÓN — Dexter se concilia con WispHub cada hora, sin trabajo manual (20/10/2026)

**El error que la originó.** Con las áreas ya completas, el usuario volvió a
comparar y sobraban 7 tickets en Dexter: los había cerrado en WispHub esa
tarde, y Dexter relee 200 casos por hora, así que tardaba hasta ~4 h en
enterarse. Además, dos tickets borrados en WispHub (404) dejaban su caso
abierto para siempre, y una relectura en paralelo devolvió 80 de 808 con
`429` que quedaban escritos como error. Pidió que se mantenga sincronizado
«bajo cualquier pronóstico de error, que no se tenga que repetir ni cerrar
manual».

**Lo que se decidió:**

1. Cada vuelta del reloj pide a WispHub la **lista entera de abiertos** de los
   últimos `conciliar_meses` (configuración del tenant; 24 en Rapilink), en
   tramos de 59 días: sin fechas WispHub solo devuelve el último mes.
2. La reconciliación relee **primero** los casos abiertos en Dexter que ya no
   están en esa lista. Un cierre en WispHub se ve en la vuelta siguiente.
3. Un `429`, un 5xx o una caída de red **no se escriben**: el caso queda para
   la vuelta siguiente.
4. Un ticket que da 404 dos veces, separadas por una hora, queda «Eliminado» y
   el Supervisor lo cierra por el mismo camino y con las mismas compuertas que
   un «Cerrado». **Nunca en masa:** solo si esa vuelta consiguió la lista
   entera y el ticket no está en ella, y nunca más de 10 por vuelta; si son
   más, no se declara ninguno y queda una alarma en el log. Una credencial
   rota da 404 a todo, y eso no puede cerrar casos.

**Lo que la reabre:** que WispHub exponga un filtro por fecha de cierre o de
modificación (sería una sola consulta en lugar de los tramos), o que el tope
de 10 eliminados por vuelta se quede corto con borrados reales.

### 8.16 DECISIÓN — La bandeja como WhatsApp: un chat por número (21/10/2026)

**El error que la originó.** Reportado por el usuario: *"cuando uno escribe
desde el mismo numero de telefono se crea una nueva conversacion como si fuera
otro numero nuevo"*. Medido en el código ese día: no era una carrera ni un
formato de número distinto. `registrar_mensaje` reutiliza solo una conversación
`abierta`, y cuatro caminos la cierran (la IA cuando el cliente confirma, el
plazo, el operador y las 24 h de inactividad). Lo siguiente que escribe ese
número abre otra conversación, y la bandeja —que listaba conversaciones— la
mostraba como una ventana nueva. Era la conducta del contrato del relevo.

**Lo que se decidió**, con las palabras del usuario: *"el sistema puede cerrar
la conversacion pero debe mostrar los mensajes anteriores como whatsapp"*; y
que el equipo **pueda escribirle** a un número aunque su última conversación
esté cerrada.

1. Por dentro nada cambia: cerrar sigue siendo cerrar, y el desenlace, las
   métricas, el Supervisor y el resumen que recibe la IA son por conversación.
2. La bandeja muestra un **chat** por número `(canal, usuario_externo)`, con
   las conversaciones anteriores arriba y una marca de cierre entre ellas que
   dice solo lo que quedó registrado. Lo calcula el motor
   (`GET /conversaciones?por_numero=1`, `GET /conversaciones/<id>/hilo`).
3. Si un número tiene dos conversaciones abiertas, ninguna queda escondida: la
   fila lleva el estado de la más urgente y la ventana avisa de la otra con un
   enlace para atenderla.
4. Escribirle a un chat cerrado **no reabre** la conversación: abre una nueva
   del mismo número, en manos de quien escribe (T21). Fuera de las 24 h, solo
   plantilla; a un número dado de baja, nada. Desde la pantalla del ticket,
   igual: si el número ya tiene una abierta se escribe ahí, y la copia va al
   ticket del caso. En el simulador no corre.
5. Lo que encontró el diseño en el camino: el motor **aceptaba** texto, media y
   plantilla en una conversación cerrada; solo la pantalla lo impedía. Ahora el
   motor lo rechaza (contrato X26).

Contrato del relevo v3.2 (C19, C20). Ficha:
`SPEC/objetivos/bandeja-como-whatsapp.md`.

**Lo que la reabre:** que una empresa necesite ver cada conversación por
separado en la cola (sería un ajuste de la bandeja, no un cambio del relevo), o
que T18 empiece a registrar quién cerró y cuándo — entonces la marca de cierre
lo diría sin cambiar nada más.

### 8.17 DECISIÓN — la reestructura por la tesis de capacidad (30/10/2026)

**El error que la originó.** El usuario preguntó si el proyecto iba por buen camino para su negocio —venderles a los ISPs que con menos personal rinden más— y delegó en esta sesión decidir qué reestructurar. La revisión encontró que **el PRD no decía cuál era el negocio** (su §1 describía un asistente interno con un modelo local; sus métricas eran "tiempo de consulta" y "adopción") y que su principio **congelaba la autonomía** justo donde vive el ahorro. Se revisó el código en cinco frentes en paralelo (medición, autonomía, alta de un ISP, proactividad, escala) y se verificó a mano lo que decide.

**Lo medido ese día** (VERIFICADO salvo donde dice otra cosa):

| Hallazgo | Evidencia |
|---|---|
| La única cifra de resultado en una pantalla es la tasa de escalada, y no filtra por canal: mezcla pruebas con clientes | `persistencia.tasa_escalamiento` (`db.py`), `/agentes`; `canales.REALES` no se aplica |
| Lo resuelto sin persona, el recontacto, las visitas evitadas y las aprobaciones **se pueden calcular con datos que ya se guardan**; nadie los junta | `conversations.control`/`cerrada_por_tipo`, `relevo_eventos`, `messages.origen` (desde 16/09), `verificaciones_accion`, `acciones_propuestas.estado` |
| `reiniciar_ont` exige aprobación humana en **cada** caso | `irreversible: true`, `aprobacion_humana: true` en `tenants/rapilink.config.yaml` (M06-A, 21/09) |
| Ninguna herramienta declara `nivel_autonomia`; nada conecta la tasa de aprobación con el nivel | `techo.py`; `indicadores.py` calcula `tasa_aceptacion` sin consumidor |
| Dexter casi no le escribe primero a ningún cliente: hay un **catálogo de 11 avisos** configurables con su plantilla e interruptor, pero **solo la encuesta tiene disparador** | `nucleo/config/mensajes_catalogo.py::EVENTOS`; `mensajes_automaticos.enviar` solo lo llama `encuesta.py`; `POST /avisos/whatsapp/<tenant>` sin llamador fuera de tests |
| La falla de barrio se diagnostica como una casa: 0/10 | Con la ONU en línea, el prompt reinicia sin consultar `consultar_incidente_red` (`SPEC/DEXTER_ESTADO_ACTUAL.md`, validación de producción) |
| El frontend ya es multi-empresa; **el backend Django no**: 9 lecturas de `MOTOR_TENANT` con respaldo `or "rapilink"` (fallan ABIERTO) y un correo de Rapilink fijo | `solicitudes/entrega.py:120,215,291` · `gestion.py:65` · `views.py:140` · `campo/services/despacho.py:453,510` · `telemetria.py:47` · `operaciones/cierre_de_caso.py:254` · `entrega.py:32` |
| El reloj descubre las empresas leyendo `tenants/*.config.yaml`: dar de alta una exige commit y deploy | `nucleo/reloj.py` |
| La config de Rapilink tiene 7.299 líneas; ~60-70 % es contenido propio de la empresa (prompts, escalamiento, catálogos) | INFERIDO por secciones; los conectores compartidos ya existen (`conectores/wisphub.yaml`, `smartolt.yaml`) |
| Un solo proceso con el historial en memoria; un solo proveedor de modelo sin respaldo | `--workers 1 --threads 8` (`docker-compose.prod.yml`), `api.py::_sesiones`; `cliente.py::chat()` |
| La transcripción de voz manda el audio del cliente a OpenAI y no había registro de que la autorización de tratamiento lo cubriera | `nucleo/canales/transcripcion.py` (30/09/2026). **Resuelto por el usuario el 30/10/2026** (RNF-01) |

**Lo que se decidió**, en el orden en que se construye. Cada ola se mide con la métrica de §2 antes de pasar a la siguiente.

**Ola 1 — medir, y cerrar lo que falla abierto**

1. **Tablero de capacidad.** Las métricas de §2, por empresa, calculadas en el motor (`db.py` → endpoint → pantalla), filtradas a `canales.REALES` y con fecha de corte desde que existe `messages.origen`. Los minutos por conversación y por visita son configuración de cada empresa (`TenantConfig.capacidad`). La tasa de escalada actual se corrige para que filtre por canal. Contrato: `SPEC/objetivos/tablero-de-capacidad.md`. *Va primero porque sin él ninguna de las demás olas puede probar que acerca la tesis, y la Ola 3 lo necesita como insumo.*
2. **La falla de barrio se consulta antes de tocar una casa.** `reiniciar_ont` agrega `consultar_incidente_red` a sus `exige_previas`, con la condición de que no haya caída compartida: la garantía queda en código y no depende del orden del prompt (§7.4). El prompt se alinea después. Se mide con `cli/bateria_flujos.py` (hoy 0/10). *En una caída general es cuando más personas hacen falta: es el peor momento para que la IA mande a reiniciar treinta casas.*
3. **El backend Django falla cerrado.** Se quitan los 9 respaldos `or "rapilink"` y el correo fijo: sin tenant no se sirve nada. Es un defecto de seguridad de la misma familia que `app_backend` sin tenant (ARQUITECTURA.md), no una mejora de multi-empresa.

**Ola 1 hecha en código el 30/10/2026 (rama `producto/tesis-de-negocio`, sin desplegar).** Lo medido:

- *Tablero*: `nucleo/persistencia/capacidad.py` (conteos en SQL) + `nucleo/observabilidad/capacidad.py` (tasas y minutos) + `GET /reportes/capacidad` + pantalla `/capacidad` (solo ADMIN). `tests/test_tablero_capacidad_base.py` contra PostgreSQL real afirma el número exacto de cada métrica, y caza tres mutaciones (sin filtro de canal real, ignorar las acciones aprobadas, la tasa de escalada vieja sin filtro). La cadena hasta la pantalla la cubre `capacidad-servidor.test.js`. Decisiones de esta sesión: "fin" de una conversación es su **último mensaje que no es una nota**, no el evento `cerrada` (los cierres de legado y T18 no lo dejan); cualquier acción propuesta cuenta como "con persona"; los minutos son **dos** parámetros (por conversación y por visita) y las personas del equipo un tercero, no "por tipo de caso", porque una conversación no tiene un tipo confiable; **Rapilink no tiene minutos declarados** y el tablero los muestra en null hasta que la empresa los dé.
- *Falla de barrio*: `reiniciar_ont` exige `consultar_incidente_red` con `es_incidente_de_red: false` (`tests/test_reinicio_no_en_caida_de_barrio.py`). El motor la vuelve a medir al aprobar. **Lo que falta medir:** la batería de flujos (`cli/bateria_flujos.py`), que pasa por el turno y necesita la red de producción; el humo de `cli/evaluar.py` dio 8/9, igual a su línea base, pero no tiene caso de reinicio. El prompt no se tocó: el motor le dice al modelo qué previa falta.
- *Backend*: los 9 respaldos y el buzón fijo, con su guarda de arquitectura (`common/tests/test_motor_tenant_falla_cerrado.py`). **Antes del deploy** hay que tener `SOLICITUDES_EMAIL_DESTINO` en Dokploy (DESPLIEGUE.md, Pendientes).

**Lo que cambió la auditoría del mismo día** (`revisor-de-pii`, `auditor-de-frontera`, `auditor-independiente` sobre `20687706`). Dos hallazgos inflaban el tablero **a favor de Dexter**, que es justo el número que se le muestra a quien compra:

| Hallazgo | Qué se hizo |
|---|---|
| La visita que agenda el código no pasa por `tool_calls` (queda en `conversations.ticket_operativo`), así que un reinicio seguido de visita automática contaba como visita evitada. La prueba lo escondía: fabricaba el evento en `tool_calls` | Un `ticket_operativo` del mismo cliente en la ventana también desmiente la visita evitada; la prueba siembra ese caso por la columna real |
| Ventanas incompletas contaban como resultado: un reinicio de ayer como visita evitada, una conversación cerrada hace una hora como "sin recontacto" | Solo se evalúan reinicios con sus días ya cumplidos y conversaciones con sus 72 h ya cumplidas; los que siguen en ventana se informan aparte |
| Una conversación que abre un operador (T21) contaba como recontacto | Recontacto = un mensaje **del cliente** en otra conversación |
| Una nota interna corría el fin y volvía "con persona" a la conversación | Las notas (`rol = 'nota'`) no cuentan para ninguna de las dos cosas |
| Visita automática y cierre por inactividad contaban como "resueltas sin persona" | Un ticket operativo es "con persona"; las cerradas por inactividad van aparte (`por_inactividad`), porque un cliente que dejó de contestar no confirma que esté resuelto |
| El divisor de la métrica norte eran los operadores que tocaron la bandeja | Pasa a `capacidad.personas_del_equipo`, declarado por la empresa como los minutos; lo medido queda como dato informativo |
| La guarda M06-A del reinicio quedó con 6 fallos nuevos (el doble de prueba no preparaba la previa nueva) | Corregido: vuelve a sus 2 fallos preexistentes. **Error de método propio**: comparé las suites por archivo y M06-A ya estaba en rojo, así que el aumento no se vio. Desde acá se comparan por comprobación |
| Lo nuevo de la config solo vivía en el YAML, y el YAML de Rapilink no se puede cargar entero (pisaría la encuesta en modo prueba) | `cli/cargar_claves.py`: sube **solo** las claves nombradas, por el mismo camino validado del editor. Y los tres números que declara la empresa se editan desde `/capacidad` (§3.3), `PUT /configuracion/capacidad` |
| Un cierre de caso sin empresa quedaba rotulado "el motor no respondió" | Motivo propio, `FALTA_MOTOR_TENANT`: se sabe que no salió nada |

**Límites que quedan escritos, no resueltos:**

- *"No sé" pasa como "no hay caída".* `consultar_incidente_red` devuelve `es_incidente_de_red: false` también cuando no pudo ubicar la ONU, en los primeros minutos de una caída (SmartOLT agrupa con 2–5 min de demora) y ante un cuerpo inesperado. La previa acota y no autoriza —siguen la señal, el ping y la aprobación humana—, así que lo peor es un reinicio inútil. Cerrarlo exige que la herramienta distinga "sin dato" de `false`, y eso cambia lo que ve el modelo: queda para cuando se mida.
- *Una visita cargada a mano en el sistema del ISP no se ve* desde Dexter: la visita evitada sigue siendo una estimación, y la pantalla lo dice.
- *Una instalación sigue siendo de una empresa*: `MOTOR_TENANT` y `SOLICITUDES_EMAIL_DESTINO` son por proceso, y `docker-compose.prod.yml` trae `MOTOR_TENANT` con default `rapilink`. El código falla cerrado; la topología, todavía no. Es la Ola 4.

**Para desplegar, en este orden** (lo decide una persona; push = deploy):

1. `SOLICITUDES_EMAIL_DESTINO` cargada en Dokploy (DESPLIEGUE.md, Pendientes).
2. Push, y que el motor y el backend levanten.
3. `py -3.13 cli/cargar_claves.py tenants/rapilink.config.yaml --clave capacidad --clave "herramientas[reiniciar_ont].exige_previas" --clave "herramientas[reiniciar_ont].descripcion"`: primero sin `--aplicar`, mirar, y después con `--aplicar`.
4. `py -3.13 cli/diferencias_config.py rapilink` y `py -3.13 cli/evaluar.py rapilink --humo --base` (CLAUDE.md §6).
5. Que la empresa declare en `/capacidad` sus minutos y sus personas.

**Ola 2 — que la IA inicie, no solo responda**

4. **Avisos proactivos por WhatsApp.** El catálogo, las plantillas y los interruptores ya existen (28/10/2026): lo que falta es **conectar el disparador** de cada aviso a su evento, y sumar dos eventos al catálogo. En este orden: (a) **caída masiva** a los clientes del PON afectado —evento nuevo; la detección ya existe en `operaciones/deteccion.py` y `correlacion.py`—; (b) **ticket cerrado** como seguimiento ("¿quedó funcionando?"), que además alimenta el recontacto; (c) **visita confirmada** —evento nuevo— y **ticket creado**; (d) **recordatorio de pago** y **suspensión**, que son de disparo diario contra WispHub. Todo respeta la baja (Ley 1581) y el modo prueba por números que ya tiene el catálogo. *Un aviso de caída evita cientos de mensajes entrantes; es la reducción de volumen más grande disponible.* **Bloqueo operativo:** plantillas UTILITY aprobadas por Meta para cada empresa (se crean desde Dexter desde octubre; la aprobación la da Meta y tarda días).

   **Avance del 30/10/2026 (sin desplegar)** — ficha `SPEC/objetivos/avisos-proactivos.md`:
   - *La puerta común*: `POST /avisos/evento` → `nucleo/seguimiento/avisos.py`. Decide **cuándo** (`horario_avisos`, 7 a 20 h por defecto: el día se publica de madrugada y un WhatsApp a las 3 a. m. espera a la mañana; contesta `todavia_no` con los segundos y el CRM reagenda), **a quién** (el chat del caso si es de canal real; si no, el teléfono del ISP normalizado con `autenticacion.indicativo_pais`, sin default) y **si sale** (`mensajes_automaticos.enviar`: interruptor, prueba, baja, plantilla, una vez por clave). El número sale en la forma de `usuario_externo`, que es lo que compara la baja: un `+57 300…` la saltaría.
   - *Visita programada*: evento nuevo `visita_programada`. Al publicar el día (Supervisor o madrugada), el CRM pide un aviso por orden con clave `visita:<orden>:<fecha>` —reprogramar a otro día avisa de nuevo, republicar el mismo no—, con la franja prometida en la hora de la empresa. Pruebas: `test_destino_de_aviso.py`, `test_avisos_proactivos.py`, `test_avisos_endpoint.py` (motor) y `campo/tests/test_aviso_de_visita.py` (CRM).
   - *Auditoría del mismo día* (`auditor-de-frontera`, `revisor-de-pii`), resuelta antes del commit: un identificador de WhatsApp sin teléfono (BSUID) se convertía en un número inventado al quitarle las letras y salteaba la baja —ahora no se usa como número y, si pidió la baja, no se le escribe tampoco al móvil del ISP—; el aviso salía con la empresa de la variable de entorno —ahora la de la organización de la orden, `tenant_de_organizacion`, sin default—; una visita cancelada, movida o vencida entre la publicación y el envío se avisaba igual —la tarea repite las reglas de `publicar`—; la ruta aceptaba cualquier aviso de cliente con contexto libre —ahora una lista cerrada, `PROACTIVOS`—; y la dirección viajaba sin que la plantilla la usara —ya no—. **Queda escrito, no resuelto**: con varios móviles en el ISP y ninguno conocido, el aviso va al primero, que puede ser de un familiar (el mismo riesgo que ya acepta la verificación de identidad); medirlo en datos reales antes de encender el aviso.
   - *Ticket creado* (`ticket_creado_cliente`): cuando una persona abre un ticket desde "Nuevo ticket", el cliente no está en el chat y vuelve a escribir para preguntar si quedó registrado. Lo pide el CRM al **atar el caso a su ticket del ISP** (`/importacion/casos/{id}/vincular/`, después del commit): es la única vía por la que nace un ticket desde Dexter, así que los importados de WispHub quedan afuera solos. **El CRM manda solo el número de ticket; el motor confirma el hecho contra el ISP** (`avisos.hecho_del_ticket`): lee el ticket (`importacion_io.ticket_para_aviso`, que exige que el ISP devuelva ESE ticket) y de ahí salen el servicio, el asunto y la clave `ticket:<proveedor>:<número>`, que arma el motor. Con el servicio, el motor lee nombre y móvil de la ficha (`contacto_del_servicio`, solo con una herramienta de lectura y solo si la fila es la del servicio pedido) — en memoria, solo si le falta el destino o el nombre, y después del horario. El asunto viaja **solo si es del catálogo del ISP**: en WispHub es texto libre y 126 de 3.418 tickets traen ahí nombre y barrio de un prospecto. Un ticket sobre el cliente ficticio de instalaciones no se avisa (`servicio_sin_titular`): su ficha tiene un teléfono que no es el del prospecto. Si el ISP no contesta, `isp_no_contesta` con `reintentar_en`, y el CRM reagenda igual que fuera de horario (ayudante común `common/avisos_al_cliente.py`). Un caso terminado (cerrado, rechazado, duplicado) no se avisa: al cerrar sale la encuesta. **Cada aviso proactivo tiene un contrato** (`mensajes_catalogo.PROACTIVOS`): qué datos del contexto acepta de quien pide —nunca `empresa` ni `fecha`— y de dónde sale el destino. *Por qué así (auditorías de frontera y PII del mismo día)*: en la primera versión el motor le creía al CRM servicio, asunto y clave; con el token de servicio se podía recorrer el padrón entero y mandarle cualquier texto a cualquier cliente con una plantilla aprobada de la empresa, y el asunto se releía al enviar —editable con texto libre durante la noche que el aviso esperaba—. Pruebas: `test_avisos_proactivos.py` y `test_avisos_endpoint.py` (motor, 14 mutaciones cazadas), `cases/tests/test_aviso_ticket_creado.py` (CRM). **Por verificar antes de encender** (`verificador-de-api`): que el detalle `GET /api/tickets/{id}/` traiga `servicio.id_servicio` como el listado — si no lo trae, el aviso no sale (falla cerrado, no a otra persona). **Anotado, no resuelto**: la ruta `/avisos/evento` queda abierta si `MOTOR_SERVICE_TOKEN` no está cargado (es la regla de todas las rutas internas del motor), y un aviso con `telefono` (la visita) sigue aceptando claves distintas de quien tiene el token.
   - *Caída masiva* (`caida_masiva`, 31/10/2026): pestaña nueva **Supervisor NOC → Fallas de red** — hasta hoy ninguna pantalla mostraba las situaciones de red; solo el Supervisor las veía por chat. Lista las caídas de PON vivas y, por cada una, dos pasos: **«Preparar el aviso»** muestra a cuántos clientes y quiénes quedan afuera (equipos sin cliente, clientes no activos) y si el aviso puede salir (apagado, plantilla sin aprobar, modo prueba); **«Avisar a N clientes»** lo aprueba una persona —queda escrito quién y cuándo en `AvisoDeCaida` y en la línea de tiempo de la situación, una sola vez por situación— y sale por tandas (`aviso_de_caida.lote`, 25 por defecto, un minuto entre tandas). **A quién** lo calcula el motor (`nucleo/seguimiento/aviso_de_caida.py`): las ONU del puerto en LOS desde SmartOLT pidiendo solo serial, estado y hora (`fields=`, verificado el 19/10/2026: ningún dato de cliente viaja); de esas, **solo el grupo que se cayó junto** —un puerto acumula equipos muertos hace meses, 10 de 17 el 21/08/2026, y decirle a un ex cliente «estamos arreglando su servicio» es mentirle—, con la misma ventana de 20 minutos que `incidentes.py`; serial → servicio por el padrón del ISP (que ahora guarda el serial, en sus dos formas, sin exponerlo en ninguna búsqueda); y solo clientes en un estado que la empresa declara (`aviso_de_caida.estados_que_se_avisan`, sin default: sin declaración no se arma nada). **Qué caídas**: solo alertas de fibra (`los`, `partial_los`); un corte de energía no es una falla del ISP. **La lista no se le cree al CRM**: en cada tanda el motor vuelve a leer quiénes siguen en la falla y descarta al resto —quien recuperó el servicio entre la aprobación y su tanda no recibe un aviso viejo—; si la situación se resuelve, el envío se **detiene**. **La clave la arma el motor con lo que midió**: `caida:<servicio>:<hora en que cayó SU equipo>` — estable mientras ese cliente sigue caído (aprobar dos situaciones de la misma falla, o reintentar una tanda, no avisa dos veces) y nueva solo si su equipo volvió y se cayó otra vez. *Lo que cambió la auditoría de frontera y PII del 31/10/2026* (sin hallazgos altos; 5 medios y 7 bajos, todos resueltos salvo los anotados): la clave dependía de la `situacion` del pedido y se podía repetir; el grupo elegido era el **más grande** y un corte viejo con más equipos muertos le ganaba a la falla de hoy —ahora es **el más reciente** que junta el mínimo—; el envío podía quedar «en curso» para siempre si la cola perdía una vuelta —ahora cada vuelta lleva una **ficha de turno** (una copia reentregada por Redis no hace nada), las esperas largas se parten por debajo del `visibility_timeout`, y una tarea periódica retoma lo perdido cada 10 minutos—; un corte breve del motor detenía el envío —ahora se reintenta—; un aviso apagado a mitad seguía leyendo fichas —ahora 409 y se detiene, con el motivo en pantalla—; Meta caído hacía perder el aviso a ese cliente —ahora queda pendiente—; quedan fuera el cliente ficticio de instalaciones y un serial que el padrón tiene en dos fichas. **Anotado, no resuelto**: el padrón puede tener hasta `padron_vigencia_horas` (una ONU reasignada en esas horas cae en la ficha vieja); y las plantillas de Meta se leen una vez por cliente dentro de cada tanda. Si el aviso está apagado o sin plantilla aprobada, se dice en la vista previa y la aprobación se niega (`mensajes_automaticos.listo`), en vez de consumir la aprobación con «apagado» cliente por cliente. Pruebas: `test_aviso_de_caida.py` y `test_aviso_de_caida_rutas.py` (motor, 12 mutaciones cazadas), `operaciones/tests/test_aviso_de_caida.py` (CRM, 18), `fallas.test.js` y `fallas/page-server.test.js` (pantalla). **Antes de encender**: crear y aprobar en Meta la plantilla `falla_en_la_red` (sugerida en el catálogo), cargar `aviso_de_caida` a la base y probar en modo prueba con un número propio.
   - *Lo que falta de la Ola 2*: pagos y recordatorios diarios; avisar «ya quedó restablecido» al cerrar una caída que se avisó. La asignación a mano desde Despacho también avisa desde el 31/10/2026 (a una cuadrilla con la fecha de la jornada; a un técnico, solo si la orden tiene fecha programada).


**Ola 3 — la autonomía ganada (§2)**

5. **El mecanismo de las cuatro condiciones**, genérico en el núcleo: el código calcula por empresa y por acción si es elegible (evidencia de `acciones_propuestas` + `verificaciones_accion`), lo muestra, una persona lo promueve, y el código lo degrada solo. **Primera candidata: `reiniciar_ont`**, que ya cumple 1 y 2 (`last_status_change`, `exige_previas`). *Esto no revierte M06-A: M06-A sigue vigente para cada acción hasta que su evidencia la promueva. Es la medición nueva que exige CLAUDE.md §10 para mover una decisión cerrada.*

   **Avance del 31/10/2026 (sin desplegar)** — ficha `SPEC/objetivos/autonomia-ganada.md`. *Fase A, solo medición*: `nucleo/seguridad/autonomia_ganada.py` decide por empresa y acción si es **candidata** (1 y 2, mirando su config: `verificacion` con comprobaciones y `exige_previas` — sin nombres; con la config de Rapilink, de las 15 que piden aprobación, solo `reiniciar_ont`) y si es **elegible** (3: en la ventana de la empresa, un mínimo de propuestas revisadas por una persona, una tasa de aprobación sin cambios, **cero** verificaciones no confirmadas y **cero** ejecuciones fallidas o inciertas). Los umbrales son configuración (`autonomia_ganada.acciones`), con un **piso del núcleo** que el schema exige y que una config vieja no puede bajar: 20 revisadas, 14 días, 90 %. Revisada es lo que una persona decidió; vencida y cancelada no cuentan. La ventana se mide por cuándo se decidió. Se muestra en `/capacidad` → «Autonomía ganada», con lo que le falta a cada acción. **No cambia nada de lo que se ejecuta**: ejecutar por `frontera.critica()` (C) y degradar sola (D) son las fases siguientes, y pasan por `auditor-de-frontera`. *Fase B, promover* (mismo día): una persona ADMIN, desde `/capacidad`, con una casilla de confirmación obligatoria, le da autonomía a una acción elegible; el motor **vuelve a medir la evidencia en ese momento** y no promueve si no alcanza. Vive en `asistente.autonomia_ganada` (migración `202610310200`), fuera de `tenant_config` y con el criterio del interruptor: solo agregar, la escribe `autonomia_operador`, el runtime solo lee y puede **degradar** por una función cuyo estado está fijo en el cuerpo; sin fila, sin tabla o sin base, ninguna acción es autónoma. Retirarla siempre se puede, con motivo.

**Ola 4 — vender a la segunda empresa sin una sesión de código**

6. **Alta en un día para un ISP con WispHub + SmartOLT.** La config se parte en tres capas: conectores compartidos (ya existen), un **paquete base de agentes** con prompts genéricos parametrizados por variables de la empresa (el mecanismo `{CLAVE}` de §8.8 ya existe), y lo propio de cada empresa. El reloj descubre las empresas desde la base, no desde archivos. El webhook pasa a un dominio neutro (§8.13). **No se construye una abstracción de "proveedor ISP"** hasta que exista un cliente que no use WispHub: diseñarla con un solo proveedor a la vista produce la abstracción equivocada. Mientras tanto, ningún código nuevo fuera de `conectores/` asume un campo de WispHub que no venga ya asumido.
7. **El techo de escala.** El historial caliente pasa a `asistente.conversations` para poder correr más de un proceso (D4). Un segundo proveedor de modelo como respaldo (D6) **solo después** de resolver la autorización de tratamiento para ese proveedor (CLAUDE.md §5).

**En paralelo, sin ola:** el CI corre las pruebas con Postgres y el deploy deja de publicar con una guarda en rojo (D1, D2). Cuantas más acciones salgan solas, más cara es una regresión que nadie vio.

**Qué no se hace, con su motivo:**

- **Canal telefónico de voz.** Duplicaría el motor de atención por un canal que WhatsApp ya absorbe en estos clientes, y exige un tercero nuevo con su análisis legal. Reabrir si una empresa demuestra que la mayoría de su volumen entra por teléfono.
- **Autonomía para `registrar_pago`** por el camino de §2: su efecto contable no lo verifica ningún endpoint de forma independiente. Reabrir con un cruce contra el extracto bancario.
- **Bajar los contrapesos** (recontacto, satisfacción) para mostrar un número principal más alto.

**Riesgos que esta decisión deja escritos:**

- **Transcripción con OpenAI.** El usuario decidió el 30/10/2026 que la autorización que firma el cliente la cubre (RNF-01). Para cada empresa nueva, su autorización tiene que cubrir a los proveedores de modelo y de transcripción antes de encenderlos.
- **El régimen de protección de usuarios de telecomunicaciones** probablemente exige que el usuario pueda llegar a una persona (INFERIDO, no verificado contra la norma). El diseño ya lo cumple —`frases_pide_humano` lo detecta en código— y la tesis no lo toca.

**Lo que la reabre:** que el tablero de la Ola 1 muestre que la resolución sin persona no sube con las olas 2 y 3 (la tesis sería falsa para este producto), o que una empresa cliente pida explícitamente lo contrario de la autonomía ganada.

---

## 9. Despliegue

Un VPS gestionado con **Dokploy**: el motor, el CRM (backend, Celery, frontend) y un Supabase autoalojado del que se usa solo Postgres. **Pushear la rama de despliegue publica a producción** (autodeploy). El procedimiento, las variables, el webhook de WhatsApp y el diagnóstico de fallos viven en [DESPLIEGUE.md](DESPLIEGUE.md); las reglas de quién despliega y cómo se verifica, en CLAUDE.md §6–§8.

*Esta sección recomendaba un servidor on-premise con GPU para un modelo local. Dejó de aplicar en agosto, cuando el modelo pasó a DeepSeek (RNF-01).*

---

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|--------|-----------|
| Fuga de datos de clientes hacia el modelo | Listas blancas fail-closed + redacción del texto libre + guardia de salida, en código (§7.4) |
| Una empresa ve datos de otra | `app_backend` + empresa fijada en cada transacción: sin empresa, 0 filas. El backend Django todavía no falla cerrado (Ola 1, §8.17) |
| Una acción irreversible sale por error del modelo | Frontera de 8 pasos; las irreversibles solo por `frontera.critica()` con aprobación atada (§8.6) |
| **La autonomía crece más rápido que la evidencia** | Las cuatro condiciones de §2: efecto verificable, previas en código, aprobaciones medidas, degradación automática. Subir lo decide una persona |
| **Se sube la resolución sin persona cerrando casos sin resolverlos** | Contrapesos obligatorios en el tablero: recontacto a 72 h y satisfacción (§2) |
| El modelo inventa datos | Siempre consultar herramienta; veredictos calculados en código; casos dorados sobre la traza |
| El modelo calcula mal un dato agregado | No calcula: compone la consulta y Python hace la cuenta (§12.5) |
| El modelo interpreta mal la pregunta y da un número exacto sobre el filtro equivocado | La respuesta declara siempre filtros y periodo usados (RF-15) |
| Incumplimiento normativo (Ley 1581) | Autorización de tratamiento que firma el cliente, que cubre a los proveedores de modelo y transcripción (RNF-01); baja respetada en todo aviso proactivo |
| El cliente no puede llegar a una persona | El pedido explícito lo detecta el código (`frases_pide_humano`), no el modelo |
| Caída de DeepSeek | Hoy sin respaldo (D6). Un segundo proveedor espera su autorización de tratamiento (RNF-04) |
| Un deploy publica con una guarda en rojo | CI sin Postgres y sin puerta del lado del servidor (D1, D2); va en paralelo a las olas (§8.17) |

---

## 11. Notas para el asistente de código (IDE)

Las reglas de trabajo viven en **CLAUDE.md**, que manda sobre este documento. Las tres que más se olvidan:

- **Nunca pedirle al modelo que calcule.** Conteos, sumas, promedios y comparaciones se resuelven en Python; el modelo compone los parámetros y redacta (§12.5).
- **Toda herramienta nueva necesita su lista blanca por rol**: sin ella devuelve nada (fail-closed). Si un campo es texto libre, va también a `campos_texto_libre`.
- **Quitar una aprobación humana exige las cuatro condiciones de §2**, con su evidencia medida en el tablero de capacidad. Nunca "porque el modelo ya lo hace bien".

*Esta sección hablaba del prototipo `soporte_wisphub.py`, de `CAMPOS_PERMITIDOS` y de una ruta simulada: son de julio de 2026 y ya no describen el motor.*

---

## 12. Del asistente al cerebro — historia (julio 2026) y la decisión que sigue vigente

*§12.1–§12.4 son el análisis de julio de 2026 sobre el prototipo `soporte_wisphub.py`, y quedan como historia: los cambios que pedían ya están hechos (áreas, bucle de herramientas, sesión por usuario, aprobación en dos pasos, registro sin PII). **§12.5 sigue vigente** y es una regla del motor.*

Análisis del código de entonces (`soporte_wisphub.py`) frente al norte de aquel momento. **Nada hay que tirar.** El motor sobrevive; lo que cambia son firmas y dos supuestos estructurales.

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
5. **Trazas por `print()`** → logging estructurado para cumplir RF-13 (auditoría), sin volcar datos sensibles en texto plano. *Estado (16/09/2026, D20):* el camino de un turno ya no usa `print` — todo pasa por `nucleo/observabilidad/registro.py`, que no escribe teléfonos, wamids, textos de clientes ni el texto de las excepciones (ver ARQUITECTURA.md, "El log del motor no lleva datos de clientes"). También el reloj, la importación de tickets, el analista y el editor de configuración. Solo quedan `print` en tres módulos que no reciben datos de clientes (arranque del coordinador y del ejecutor, aviso del DBHOST), listados con su motivo en `tests/test_registro_sin_pii.py`, que además revisa que ninguno interpole una excepción ni una variable de PII.
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
