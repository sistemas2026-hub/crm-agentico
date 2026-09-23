# Dexter — cerebro del proyecto

Asistente interno de IA para ISPs (multi-tenant), primer despliegue: **Rapilink**. Un colaborador —o un cliente final por WhatsApp— pregunta en lenguaje natural y el sistema responde consultando WispHub, SmartOLT y el CRM, según su área. En producción.

Este archivo es el **punto de entrada único** de toda sesión, humana o IA. No contiene el detalle: dice qué invariantes no se rompen, qué se verifica antes de dar algo por bueno, y a qué documento ir para cada cosa.

---

## §1 · Jerarquía de autoridad

Se lee de arriba hacia abajo. **Cuando dos documentos se contradicen, gana el de más arriba** — y corregir al de abajo es parte del trabajo, no una tarea aparte.

| # | Documento | Manda sobre | Cuándo leerlo |
|---|---|---|---|
| 1 | **Este archivo** | La jerarquía misma, las reglas de trabajo, qué se verifica | Siempre, primero |
| 2 | [SPEC/DEXTER_CONTRATOS_GLOBALES.md](SPEC/DEXTER_CONTRATOS_GLOBALES.md) | Invariantes congelados (entrega, relevo, persistencia, método) | Siempre. Cambiarlos exige decisión explícita registrada, nunca una sesión que los reinterprete |
| 3 | [SPEC/DEXTER_ESTADO_ACTUAL.md](SPEC/DEXTER_ESTADO_ACTUAL.md) | Dónde estamos hoy: rama base, qué está cerrado, qué falta | Al empezar. Gana sobre cualquier conversación o recuerdo |
| 4 | [PRD.md](PRD.md) | **Qué** se construye y **por qué**: producto, requisitos, decisiones y su motivo | Antes de proponer o hacer cualquier cambio |
| 5 | [ARQUITECTURA.md](ARQUITECTURA.md) | **Cómo** se organiza el código y la regla núcleo/tenant | Antes de proponer o hacer cualquier cambio |
| 6 | [DESPLIEGUE.md](DESPLIEGUE.md) | Servidor, despliegue, base de datos | Antes de tocar cualquiera de los tres. Su sección **Diagnóstico** se consulta *antes* de depurar un fallo: varios de esos errores señalan a la causa equivocada |
| 7 | [SPEC/CONTRATO_RELEVO_IA_HUMANO.md](SPEC/CONTRATO_RELEVO_IA_HUMANO.md) | El relevo IA ↔ humano: estados, transiciones, invariantes | Al tocar la bandeja, el escalamiento o el control de una conversación |
| 8 | `.claude/skills/{wisphub,smartolt,bottlecrm}-api` | Lo ya verificado en vivo de cada API externa | Antes de usar un filtro, endpoint o parámetro nuevo |

Los 4, 5 y 6 cambian seguido y son fuente de verdad, no un resumen de este archivo: **leerlos del disco en cada sesión**, no asumir que siguen igual. Si `git log -5 -- PRD.md ARQUITECTURA.md` muestra commits que no reconocés, son de otro colaborador: revisalos antes de tocar nada relacionado.

Los demás documentos de [SPEC/](SPEC/) (checkpoints, auditorías, hallazgos) y los `M06-*` de la raíz son **historia con evidencia**: se consultan cuando hacen falta, no mandan.

---

## §2 · Mapa

Cuatro zonas en un solo repositorio. Detalle en [ARQUITECTURA.md](ARQUITECTURA.md).

```
nucleo/            EL MOTOR — Python 3.13 · Flask + gunicorn · genérico, nunca conoce un cliente
  canales/         entrada HTTP, webhook de WhatsApp, el turno
  modelo/          cliente LLM y el bucle de tool calling
  config/          schema (validación) · fuente (carga) · editor (escritura desde la interfaz)
  seguridad/       listas blancas · frontera · techo · interruptor · aprobación ·
                   idempotencia · redacción · guardia de salida · verificación
  relevo/          IA ↔ humano: control, transiciones, efectos externos, reconciliador
  seguimiento/     escalamiento · agendamiento · importación · verificación de acción
  persistencia/ recuperacion/ herramientas/ habilidades/ programador/ ingesta/
  observabilidad/ conectores/ facturacion/          (15 subpaquetes + reloj.py)

tenants/           DATOS por empresa, sin código. Semilla de alta; la fuente de verdad es la base
django-crm/        LA PLATAFORMA — BottleCRM vendorizado (Django+DRF+Celery) + SvelteKit
apps/tecnicos-mobile/   App de campo (Flutter, con operación offline)
supabase/          Migraciones SQL con ledger propio (checksum, lock, control de huecos)
cli/ tests/ evaluacion/ corpus/ conectores/
```

**Archivos que exigen cuidado extra** — concentran demasiado y cualquier cambio ahí tiene superficie de conflicto alta:

| Archivo | Líneas |
|---|---|
| [nucleo/canales/api.py](nucleo/canales/api.py) | 9.091 |
| [nucleo/persistencia/db.py](nucleo/persistencia/db.py) | 4.625 |
| [nucleo/modelo/motor.py](nucleo/modelo/motor.py) | 4.153 |
| [nucleo/config/schema.py](nucleo/config/schema.py) | 3.577 |

---

## §3 · Las reglas de arquitectura

### 3.1 `nucleo/` es el motor; `tenants/` es configuración

`nucleo/` = genérico, **nunca** conoce un cliente. `tenants/` = configuración por empresa, **sin código**. Dar de alta un ISP es: fila en la tabla, archivo en la carpeta, cargar sus documentos. **Cero cambios en `nucleo/`.**

Si al escribir código en el núcleo aparece la necesidad de distinguir un cliente, no se resuelve con un `if`: significa que **falta un campo en la configuración**.

```
py -3.13 tests/test_nucleo_sin_tenants.py
```

Caza slugs, ramas por tenant y URLs de servicios concretos — también dentro de cadenas, que es donde se esconderían. Cuando falla **no se agrega una excepción**: se mueve el comportamiento a la configuración.

### 3.2 La base manda; el YAML es semilla

El motor lee `asistente.tenant_config` (JSONB, versionado), no el archivo. `tenants/<slug>.config.yaml` es la semilla inicial. Dos caminos escriben esa tabla —[cli/cargar_config.py](cli/cargar_config.py) y [nucleo/config/editor.py](nucleo/config/editor.py)— y los dos validan contra el mismo `TenantConfig`.

Consecuencia que ya costó tiempo: **lo que el repo declara no es lo que está desplegado**. Ver §6.

### 3.3 Esto es SaaS multi-tenant: diseñar para muchas empresas

Rapilink es el primer despliegue, no el único. Un dato que varía por empresa —el subdominio de una API externa, un ID de cuenta, cualquier config que no es igual para todo el mundo— se modela como **configuración editable desde la interfaz y persistida por tenant**: nunca un valor fijo en código, ni en un YAML que solo un desarrollador sabe editar.

*"Hoy solo hay un tenant"* no es excusa: la próxima empresa que se conecte no debería necesitar una sesión de código para algo que ya se resolvió una vez. El patrón ya construido: `TenantConfig.variables_tenant` + `Herramienta.base_url_ref` — mismo espíritu que `auth_ref` para secretos, pero para datos que no son secretos y aun así varían.

Esto nace de una corrección directa de un colaborador después de que se declarara el subdominio de SmartOLT como fijo *"porque hoy solo hay un tenant y cambiarlo es más trabajo"*. No repetir ese razonamiento — tampoco para priorizar: **ninguna métrica de una empresa decide si algo se construye.** Puede ordenar prioridades; no puede descartar una función que otra empresa necesita.

---

## §4 · Principios técnicos

- **El modelo compone, el código calcula** (PRD §12.5). Ninguna consulta agregada le pide al modelo sumar, contar o promediar. Python calcula; el modelo traduce lenguaje a parámetros y redacta. Si una implementación depende de que el modelo sume, está mal planteada.
- **Seguridad en código, nunca solo en el prompt** (PRD §7.4). El prompt es guía; el código es la garantía. Todo fail-closed: una herramienta sin lista blanca no devuelve nada, y olvidar fijar el tenant devuelve cero filas, no todas.
- **Crecer en alcance, no en autonomía.** Más sistemas y más preguntas respondidas: sin techo. Más cosas que el modelo decide o afirma solo: no. El criterio afilado no es *"¿esto es alcance o autonomía?"* sino **"¿sigue habiendo validación en código antes de que la acción tenga efecto?"**
- **La documentación de una API externa es una hipótesis**, nunca una fuente de verdad. Antes de usar un filtro nuevo, cargar la skill correspondiente y verificar con el método del valor imposible. Ya aparecieron huecos en las tres direcciones: campos obligatorios sin documentar, campos documentados que el serializer no valida, y formatos de fecha del ejemplo oficial que la API rechaza.
- **Un reintento solo sirve en la capa donde puede entrar información nueva.** La redacción final corre a propósito sin catálogo: pedirle tres veces que reescriba devuelve tres veces la misma frase (medido byte a byte, 09/09/2026). El reintento va en el bucle del agente, donde el modelo todavía puede llamar una herramienta. Una guarda que solo sabe *rechazar* texto no puede crear el dato que nadie fue a buscar.

---

## §5 · Seguridad y privacidad

**Tres capas sobre los datos**, cada una agregada cuando la anterior demostró no alcanzar:

1. **Listas blancas por rol y herramienta** — qué campos llegan al modelo. Fail-closed, alcanza objetos anidados y las tres formas de respuesta (objeto, lista, paginado).
2. **Redacción por patrón** ([nucleo/seguridad/redaccion.py](nucleo/seguridad/redaccion.py)) — la lista blanca controla *qué campos* pasan, no *qué contiene* cada campo. De 300 tickets reales, 136 traían un documento embebido en la descripción. Al agregar un campo a una lista blanca, preguntarse si es texto libre; si lo es, va también a `campos_texto_libre`.
3. **Guardia de salida** ([nucleo/seguridad/salida.py](nucleo/seguridad/salida.py)) — las dos anteriores protegen la *entrada* al modelo; ninguna mira el *texto* que el modelo redacta antes de llegar al cliente.

**La frontera de autorización**, para toda acción que produce un efecto ([nucleo/seguridad/frontera.py](nucleo/seguridad/frontera.py), detalle en `M06-A`/`M06-B`/`M06-C`). Ocho pasos, en este orden:

```
tenant → kill switch → techo de autonomía → autorización granular →
aprobación persistida y atada → auditoría → permiso → idempotencia → último metro
```

Cada paso **acota, nunca autoriza**: pasarlo no exime de los siguientes. Las herramientas `irreversible` (`registrar_pago`, `reiniciar_ont`, `activar_catv`, `cambiar_tipo_onu`, `agregar_promesa_pago`) salen **solo** por `frontera.critica()`; llegando al ejecutor por cualquier otro camino, no salen.

**Privacidad, no negociable:**

- **Nunca leer `.env`.** Ya pasó: 14 secretos quedaron en transcripciones. Enmascarar toda salida.
- Las respuestas crudas de la API de WispHub **no se persisten** (traen contraseñas, GPS, cédula). La auditoría (`tool_calls`) guarda solo metadatos: qué se consultó, quién y cuándo — nunca qué decía la respuesta.
- El log del motor no lleva datos de cliente: todo pasa por [nucleo/observabilidad/registro.py](nucleo/observabilidad/registro.py) — evento de texto fijo, campos redactados, excepciones por tipo y `archivo:línea`, nunca `str(e)`. A una persona se la nombra con `ref_sesion()` (HMAC), que sirve para buscar en el log y **nunca** como clave, identidad ni permiso.
- El payload crudo de Meta va al log y no se persiste ni se muestra. `autor_nombre` no va a logs, trazas, excepciones ni telemetría.
- DeepSeek está aprobado para todos los roles, incluida PII, por la autorización de tratamiento que firma el cliente (Ley 1581 art. 26) — ver PRD RNF-01 antes de cuestionar por qué datos de cliente salen a una API externa. **Esa autorización nombra al proveedor del modelo**: cualquier tercero nuevo (monitoreo, visión, transcripción) exige resolver eso antes de activarse. Ver [OBSERVABILIDAD_Y_PRIVACIDAD.md](OBSERVABILIDAD_Y_PRIVACIDAD.md).
- `BYPASSRLS` no es solo del service role: `postgres` y `motor_user` también lo tienen. El aislamiento real lo da `set local role app_backend` + `set local app.current_tenant`, ambos `local`.

---

## §6 · Cómo se verifica

**Tabla de disparadores.** Lo que tocaste decide qué corre — no el criterio del momento.

| Si tocaste… | Corré | Tarda |
|---|---|---|
| cualquier cosa en `nucleo/` | `py -3.13 tests/test_nucleo_sin_tenants.py` | segundos |
| prompt, catálogo de herramientas o modelo | `py -3.13 cli/evaluar.py rapilink` | ~23 min |
| lo mismo, con prisa o en verificación de humo | `py -3.13 cli/evaluar.py rapilink --humo` | ~3 min |
| **después de aplicar config a producción** | `py -3.13 cli/diferencias_config.py rapilink` **y** `py -3.13 cli/evaluar.py rapilink --humo --base` | seg. + 3 min |
| el editor de agentes | `py -3.13 tests/test_editor_config.py` | segundos |
| llamadas al modelo | `py -3.13 tests/test_timeouts_modelo.py` | segundos |
| persistencia | las pruebas contra **PostgreSQL real**, nunca solo en memoria |  |
| comparar modelos | `py -3.13 cli/banco_pruebas.py` |  |
| descubrir endpoints de WispHub (solo lectura) | `py -3.13 cli/sondear_api.py` |  |
| el interruptor de autonomía | `py -3.13 cli/autonomia.py rapilink` |  |

**Los casos dorados** (`evaluacion/<slug>.casos.yaml`) corren contra el motor **real** y afirman sobre la **traza** —qué herramientas se llamaron, a qué área se derivó, si hubo errores, qué no puede aparecer en la respuesta— nunca sobre la redacción: el modelo dice lo mismo de diez formas y un test que exige una frase exacta falla por lo que no importa.

Nacen de una lección cara (14/08/2026): tres bugs estuvieron rotos horas —una herramienta devolviendo un *error* donde debía haber un dato, un veredicto que no se calculaba, una precondición imposible de cumplir— y **ninguno se veía leyendo la respuesta**. Los tres se ven en la traza. Abrir el simulador a mano no los detecta. Cuando algo falle en producción, agregarlo al set con lo que *debería* haber pasado.

**`--base` no es opcional después de aplicar config**: sin él el corredor lee el YAML, que es justo el lado donde el dato sí estaba. Entre el 08 y el 09/09/2026, de 19 arreglos, **cuatro no eran bugs de lógica**: eran el repo declarando algo que producción no tenía. Ninguna prueba unitaria podía verlos. `diferencias_config.py` reporta la *dirección* de cada diferencia: "solo la base lo tiene" es normal (es la fuente de verdad); "el repo lo declara y la base no" es la que rompe.

### El método

```
afirmar sobre el EFECTO, nunca sobre la presencia del mecanismo
una prueba que dice que algo EXISTE no prueba que funcione
verificar antes de afirmar; distinguir VERIFICADO de INFERIDO
nunca declarar que un test pasó si no se ejecutó
PARSEA ≠ IMPORTA ≠ FUNCIONA
"no detectado por chequeo estático" ≠ "no hay diferencias"
```

El mismo día, tres pruebas estaban en verde con el síntoma vivo. Una afirmaba `deriva_a` y `usa` pero no que la respuesta no fuera una promesa; otra usaba la frase que sí funciona en vez de la que falla; la tercera afirmaba que una variable *existiera*, y **sobrevivió intacta a una inversión completa de la conducta**.

Corolario operativo: **código construido no es código que corre**. El reloj de tareas colgaba de un bloque `__main__` que gunicorn nunca ejecuta, y la reconciliación estaba probada y sin llamador. Ninguno dio error, log ni alerta. Al terminar algo, comprobar que *se ejecuta en la topología real*, no solo que existe.

---

## §7 · Reglas de desarrollo y git

- **Push a `fix/integracion-wisphub` = DEPLOY A PRODUCCIÓN.** Autodeploy. Decirlo con esa palabra antes de hacerlo, aunque la sesión haya empezado con "no deploy".
- **Un solo dueño de producción.** Solo una sesión pushea; las demás entregan hashes. El estado de git se mide con `fetch` antes de afirmarlo, nunca de memoria.
- **Stage por rutas explícitas.** Prohibidos `git add .`, `git add -A`, `commit -a` y también `git add SPEC/`: un directorio entero es el mismo gesto que un `add .`, basta con que haya quedado un archivo ajeno adentro. Verificar siempre con `git diff --cached --name-only` antes de commitear.
- **No amend.** No mocks productivos. No conectarse a producción para obtener capturas.
- **El sistema es uno solo.** No dividir el trabajo en "lo mío" y "lo del colaborador": si algo está mal, se arregla, sin preguntar de quién es el archivo.
- Los mensajes de commit van en español y dicen **el efecto**, no el mecanismo — como los que ya están en el historial.
- Este repositorio se comparte; antes de un `git pull`, `git novedades` (ver §9) muestra qué cambió del otro lado sin mezclar nada.

---

## §8 · Operación

- **Las migraciones van siempre por el ledger**, nunca con `psql`: `psql` se saltea el checksum, el lock y el control de huecos, y no deja registro.
  ```
  py -3.13 cli/migrar_asistente.py --estado
  py -3.13 cli/migrar_asistente.py --aplicar
  ```
- **La config no se aplica sola.** Un `pull` que trae `tenants/*.config.yaml` cambiado deja el entorno corriendo la versión vieja. Cargarla con `cli/cargar_config.py`; si se **niega**, no forzar a ciegas: hay algo en la base que el archivo no trae (típico: un agente creado desde la interfaz). Exportar, revisar el diff, y recién ahí.
- **Horas siempre en America/Bogotá al reportar.** La base y los logs son UTC.
- **Nunca `pnpm check` en Windows con Docker arriba** — rompe el frontend por truncamiento de rutas. Usar `docker exec <frontend> pnpm check`, o un worktree aislado sin contenedor de frontend.
- **Dónde vive cada interruptor importa.** El de autonomía **no** está en `tenant_config` y no es capricho: esa ruta falla ABIERTA por dos caminos medidos (`api.py::_config_de` sirve una copia cacheada cuando no puede comprobar la versión, y `fuente.cargar` cae al YAML de la imagen si la base no responde — cortar la base reactivaría la autonomía). Vive en `asistente.interruptor_autonomia`, se lee sin caché antes de cada escritura y falla CERRADO. Ver [nucleo/seguridad/interruptor.py](nucleo/seguridad/interruptor.py). Igual criterio para `RELOJ_HABILITADO`: la config del tenant dice *qué* hacer; si un proceso debe estar corriendo es una decisión de operación.

---

## §9 · Configuración de una sola vez por máquina

Git no versiona hooks ni alias — se activan a mano una vez por copia local:

```
git config core.hooksPath .githooks
git config alias.novedades '!git fetch origin && echo "--- commits nuevos ---" && git log HEAD..origin/fix/integracion-wisphub --oneline && echo "--- archivos que cambiaron ---" && git diff --stat HEAD origin/fix/integracion-wisphub'
```

Los hooks avisan cuando un `pull` trae cambios en los documentos de contexto, en la config de un tenant o migraciones nuevas — las tres cosas que **no se aplican solas** y cuyo síntoma, cuando faltan, no señala la causa.

---

## §10 · Cómo se toman decisiones

- **Lo que varía por empresa es configuración; lo que la interpreta es motor.** Esa pregunta se responde antes de escribir la primera línea.
- **Medir antes de decidir, y dejar escrita la medición.** Las decisiones de este proyecto se sostienen en números: *7 de 63* conversaciones escaladas reciben un mensaje posterior; *136 de 300* tickets traen un documento embebido; el mismo equipo sano devuelve `1 de 3` y `3 de 3` en corridas seguidas. Una decisión sin medición se reabre sola cada sesión.
- **No reabrir una decisión cerrada sin una medición nueva que mueva el número** que la cerró.
- **Toda decisión se registra con fecha, evidencia y el error que la originó**, en el documento que corresponda por §1. Ese patrón es lo más valioso que tiene el repositorio: no lo rompas escribiendo conclusiones sin su porqué.
- **Escalar al humano** cuando la garantía no se puede dar en código: una lectura que no se puede comparar contra el dato real, una acción irreversible, un efecto que ningún endpoint puede confirmar.

---

## §11 · Protocolo para agentes IA

**Antes de tocar nada**

1. Leer §1 en orden. PRD y ARQUITECTURA se leen **del disco**, completos, sin que se pida.
2. `git fetch` antes de afirmar cualquier estado de git, y antes de dar por buena una rama.
3. Lo que un recuerdo o un resumen diga sobre un archivo, función o bandera: **verificar que siga existiendo** antes de recomendarlo.

**Mientras trabajás**

- Responder primero **si se puede y qué hace falta**; los obstáculos no bloqueantes van después, y solo tras leer el código.
- No ampliar el alcance en silencio, y no achicarlo tampoco: si algo queda fuera, se dice explícitamente y por qué.
- Un dato de empresa nuevo se modela como configuración (§3.3), aunque parezca más trabajo hoy.

**Nunca sin permiso explícito**

- `push` a la rama de despliegue, o cualquier cosa que toque producción.
- Leer `.env` o cualquier archivo de secretos.
- Mocks productivos, capturas contra producción, `--forzar` a ciegas sobre config o migraciones.

**Al entregar**

- Decir **qué se verificó y cómo**, distinguiendo medido de inferido. Si una prueba no se corrió, decirlo; si falló, mostrar la salida.
- Decir qué quedó fuera y por qué. Reducir el alcance es decisión del usuario, no del agente.
- Si el trabajo cerró un gate o cambió el estado, actualizar [SPEC/DEXTER_ESTADO_ACTUAL.md](SPEC/DEXTER_ESTADO_ACTUAL.md): **un gate no está cerrado hasta que ese archivo lo refleje**, y se poda al actualizar — una sección vieja no es inocua, la siguiente sesión la lee como verdad.

### §11.1 Los agentes de este repositorio

Viven en [.claude/agents/](.claude/agents/). **No están partidos por cargo** (arquitecto / desarrollador / QA) sino por **superficie de falla**: cada uno tiene su procedimiento, sus archivos y su comando. El rol de "arquitecto" es este archivo más la sesión principal; el de "desarrollador" es la sesión principal, que es la única que puede repreguntarle al usuario.

| Agente | Cuándo se invoca | Escribe |
|---|---|---|
| `arquitecto-dexter` | **Antes de construir algo nuevo**: ¿ya existe? ¿dónde vive? ¿código o configuración? | No |
| `verificador-de-api` | Antes de que un filtro, endpoint o parámetro nuevo entre al catálogo | Solo la skill de esa API |
| `revisor-de-pii` | Al tocar listas blancas, campos de texto libre, logs o cualquier dato que llegue al modelo | No |
| `auditor-de-frontera` | Al tocar una herramienta con efecto, la frontera, el techo, el interruptor o la idempotencia | No |
| `corredor-de-evaluacion` | Después de cambiar prompt, catálogo o modelo; lee la **traza**, no la redacción | No |
| `guardia-de-config` | Deriva repo ↔ base. La revisión barata y frecuente: tras un `pull`, al cargar config | No |
| `guardia-de-release` | Checklist completo de salida: ledger, variables, guardas, git. Delega config en el anterior | No |
| `auditor-independiente` | Al cerrar un bloque, antes de integrarlo: busca el hueco que quien construyó no puede ver | No |

Siete de los ocho son **de solo lectura a propósito**: su valor es una pasada independiente, y un auditor que además edita empieza a defender lo que escribió. Ninguno hace `push`, despliega ni toca producción.

**Dos capas que no se mezclan.** Estos ocho son agentes **para construir Dexter**, y viven en `.claude/agents/`. Los *agentes del producto* —el router, `soporte_tecnico_cliente`, `facturacion_cliente`, `ventas`— son roles del tenant, viven en `asistente.tenant_config`, se editan desde `/agentes` y no son código. Que la palabra sea la misma no los vuelve lo mismo: uno se toca con un commit, el otro con `cli/cargar_config.py`.

**Cobertura, y su hueco.** Los ocho cubren el **motor**. Un cambio en `django-crm/frontend/` o en `apps/tecnicos-mobile/` hoy solo encuentra a `arquitecto-dexter` y `auditor-independiente`.

```
Agentes futuros, no creados todavía:
  especialista-frontend   (SvelteKit: accesibilidad, estado, privacidad en la UI)
  especialista-mobile     (Flutter: operación offline, conflictos, sincronización)

Crear cada uno cuando ese módulo tenga carga suficiente y una falla propia
que ya haya costado tiempo — no antes. Un agente sin cicatriz no encuentra nada.
```

### §11.2 Flujo de cambios con agentes

**Cuándo aplica.** Un cambio es *relevante* si cumple al menos una: toca `nucleo/`, agrega o modifica una herramienta del catálogo, llama a una API externa, produce un efecto fuera del sistema, o cambia qué dato llega al modelo. Una corrección de texto, un ajuste de estilo o un arreglo de una línea con su guarda ya en verde **no** necesita el flujo: aplicarlo a todo lo convierte en ceremonia, y una ceremonia se saltea.

```
Idea nueva
    │
    ▼
1. arquitecto-dexter        ¿ya existe? ¿dónde vive? ¿código o configuración?
    │                        — puede terminar el trabajo acá, y eso es un éxito
    ▼
2. verificador-de-api       solo si toca un sistema externo: el contrato real,
    │                        medido, no el documentado
    ▼
3. implementación           sesión principal (la única que puede repreguntarte)
    │
    ├──► 4a. auditor-de-frontera     ¿qué acción tiene efecto, y por qué caminos?
    ├──► 4b. revisor-de-pii          ¿qué dato sale, y hacia dónde?
    │        (independientes: van en paralelo)
    ▼
5. corredor-de-evaluacion   la traza, no la redacción
    │
    ▼
6. auditor-independiente    el hueco que quien construyó no puede ver
    │
    ▼
7. guardia-de-config  →  guardia-de-release
    │
    ▼
una persona decide el deploy
```

**Los pasos se saltean diciéndolo, nunca en silencio.** Si un cambio no toca una API externa, el paso 2 no corre y se dice. Si un paso se omite por tiempo, eso se declara al entregar — omitir sin decirlo es lo que convierte un proceso en un adorno.

---

## §12 · Decisiones congeladas

Cada una costó un incidente, una medición o las dos. No se redescubren ni se revierten sin decisión explícita.

- **`ACCION_CONFIRMADA` no significa que el problema del cliente esté resuelto.** Significa que la acción produjo el efecto técnico que el sistema puede medir — en `reiniciar_ont`, que el equipo reinició y volvió. Que la casa tenga internet no lo dice ningún endpoint: lo sabe el cliente, y hay que preguntárselo. Ver [nucleo/seguimiento/verificacion_accion.py](nucleo/seguimiento/verificacion_accion.py).
- **La condición de éxito de una acción no puede ser una mejora del ping.** Medido dos veces: el mismo equipo sano devuelve `1 de 3`, `2 de 3` y `3 de 3` en corridas seguidas (15/08/2026), y un reinicio real y confirmado dejó el ping en `3 de 3` **antes y después** (02/09/2026). Lo que prueba un reinicio es `last_status_change`: un sello discreto, comparado contra sí mismo.
- **Una conversación escalada le sigue contestando al cliente, a propósito.** Mientras está en pausa y **ninguna persona escribió todavía**, cada mensaje recibe el texto del tenant (`escalamiento.mensaje_ya_escalada`, uno solo; lo que varía por motivo es el *anuncio* inicial). En cuanto una persona escribió, el bot se calla: repetir "un compañero lo va a revisar" después de "ya se realizó su cambio" contradice al equipo. Se evaluó callar y se decidió NO hacerlo (12/09/2026): solo **7 de 63** conversaciones escaladas reciben algún mensaje posterior, así que la redundancia que ahorraría es chica y el costo es asimétrico — quien escribe y no recibe nada no puede distinguir "me están leyendo" de "esto está roto". No reabrir sin una medición nueva que mueva ese 7 de 63.
- **Una mutación externa se ejecuta una vez, y la garantía vale lo que valga el `origen`.** `asistente.operaciones_externas` excluye por clave primaria (`insert ... on conflict do nothing`), nunca por un `select` previo — ahí vive la carrera. La clave es `origen|herramienta|hash(argumentos RESUELTOS)`, no los que propuso el modelo, y el `origen` identifica la SOLICITUD: el wamid en WhatsApp, el `run_id` en el scheduler, la cabecera `Idempotency-Key` en `/interno`. Una clave nueva por intento es un identificador único, **no** una clave idempotente. Lo que no puede prometer: si la llamada salió y la respuesta se perdió, nadie sabe si el tercero la aplicó.
- **Entrega: `aceptado ≠ entregado ≠ leído`**, y `unknown ≠ failed`. Solo un rechazo definitivo habilita reintento; un `pendiente` jamás se reenvía — el cliente lo recibiría dos veces.
- **Persistencia: guardar primero, entregar después.** Un fallo de entrega nunca borra lo escrito, y un éxito que no quedó registrado no es un éxito. **Ninguna transacción de base abierta mientras se espera una operación externa.**

---

## §13 · Deuda y riesgos conocidos

Escritos para que no se redescubran cada sesión. Ninguno es un descuido: son decisiones pendientes con su motivo.

| # | Qué | Por qué importa |
|---|---|---|
| D1 | **No hay CI automática en este repositorio.** [.github/](.github/) solo tiene `CODEOWNERS`; los workflows de [django-crm/.github/workflows/](django-crm/.github/workflows/) no los lee GitHub Actions (solo mira la raíz). Los 145 archivos de `tests/` son scripts sueltos, sin runner agregado | Las guardas de §6 dependen de que alguien se acuerde de correrlas |
| D2 | **El deploy no tiene puerta.** Un push a la rama de despliegue publica sin que nada haya corrido antes | Junto con D1: nada mecánico impide desplegar con una guarda en rojo |
| D3 | **Monolitos de archivo** (§2) | Superficie de conflicto alta entre sesiones y revisiones difíciles |
| D4 | **El motor corre con `--workers 1`** y el historial caliente vive en RAM del proceso | Techo real de escala; se levanta el día que ese historial viva en `asistente.conversations` |
| D5 | **El segundo ISP no entra todavía.** El motor ya es multi-empresa; `PRIVATE_ASISTENTE_TENANT` está en 23 lugares del frontend y nunca se deriva de la organización del usuario | Es una decisión de producto (¿una instalación por ISP, o una plataforma?) y conviene tomarla **antes** de escribir el código |
| D6 | **Un solo modelo externo, sin respaldo local.** Un nombre de modelo mal escrito falla el turno en vez de degradar | Ver PRD RNF-01 |
| D7 | **`editor._editar` reescribe defaults ausentes**: una mutación de una clave produjo 68 hojas distintas | El diff de una edición mínima deja de ser auditable |
| D8 | **`test_rutas_sql` cuenta bases globales** — falla si otra suite crea bases en paralelo | No bloqueante; correrla sola hasta arreglarla |
| D9 | **Sentry apagado a propósito**, y no se enciende hasta resolver si un proveedor externo de monitoreo entra en la autorización de tratamiento | [OBSERVABILIDAD_Y_PRIVACIDAD.md](OBSERVABILIDAD_Y_PRIVACIDAD.md) |
| D10 | **`ARQUITECTURA.md` desactualizado** (lista 9 submódulos de `nucleo/`; hay **15**, medido el 23/09/2026 — `SPEC/CONTEXTO_PROYECTO.md` decía 11, también viejo) y `PRD.md` con numeración duplicada (dos §8.9 y dos §8.10) | Corregir al pasar por ahí, no como tarea aparte |
