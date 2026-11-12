# Objetivo · El Supervisor NOC diagnostica la red como un ingeniero de soporte

> Abierto el **12/11/2026**, a pedido del usuario, sobre una especificación suya
> de 10 módulos de conocimiento FTTH y 5 roles especialistas. Estado: **abierto**.
>
> **Lo primero que hay que saber, y lo que cambia el tamaño del trabajo:** el rol
> `supervisor_noc` **ya existe y corre en producción** (`tenants/rapilink.config.yaml:1939-2026`),
> con prompt, 11 herramientas, listas blancas, 13 campos en `nunca_revelar`,
> pantalla propia (`django-crm/frontend/src/routes/(app)/supervisor-noc/`) y
> backend (`django-crm/backend/operaciones/`, 70 módulos). Esto **no es un
> proyecto nuevo: es una extensión de uno que corre.**

## Qué significa terminado

El Supervisor NOC, ante un cliente sin servicio, llega a un diagnóstico que
distingue **falla confirmada · causa probable · hipótesis sin comprobar ·
acción recomendada · solución validada**, apoyado en más de una fuente, y lo
dice con la confianza al lado de cada afirmación.

Eso ya lo hace en parte. Lo que falta, en una línea: **ver la planta física**
(hoy solo ve equipos sueltos, no la infraestructura que los une), **ver la
salud de la OLT** (temperatura, voltaje, uptime: el contrato está verificado y
nadie lo llama), y **poder actuar** sobre lo que diagnostica.

## Lo que NO se construye, porque ya existe

Medido por `arquitecto-dexter` el 12/11/2026 sobre `C:\wt-cierre`, con la guarda
de arquitectura en verde como base (`tests/test_nucleo_sin_tenants.py` →
`[OK] El nucleo no conoce a ningun cliente`, 129 archivos).

| Lo que la especificación pide | Ya es |
|---|---|
| Un rol "Supervisor NOC" | `rapilink.config.yaml:1939` |
| 5 especialistas coordinados | Un rol = prompt + catálogo + lista blanca. Decidido en `nucleo/modelo/motor.py:17-23`: *"un «coordinador + subagentes» no es mas que «un modelo, un prompt y un catalogo de tools distintos segun quien pregunta»"* |
| Correlación de alarmas | `operaciones/correlacion.py`, jerarquía PON > OLT > zona, dedup por índice único parcial |
| Detección de microcortes | `nucleo/herramientas/estabilidad.py` (la palabra no está en el repo; el mecanismo sí) |
| MTTR, FRT, SLA, backlog | `cases/analytics.py` envuelto por `operaciones/indicadores.py`, con tres estados de cobertura |
| Topología OLT/puerto PON/zona/caja | Herramienta `consultar_topologia_ont`, `rapilink.config.yaml:5946` |
| Fallas masivas | `nucleo/herramientas/incidentes.py` + `operaciones/deteccion.py` |
| Análisis de fotos | `nucleo/canales/vision.py` + `campo/inspeccion_visual.py` |
| Validación post-reparación | `nucleo/seguimiento/verificacion_accion.py` |
| Vecinos en LOS del mismo puerto | `diagnostico_servicio.py:195-269` (`_vecinos_en_los`) |

## Las dos decisiones que el usuario tomó el 12/11/2026

**1. Entra un inventario de planta externa.** CTO, splitters, puertos, qué
cliente cuelga de dónde. Es el trabajo más grande de este objetivo y la llave
de tres cosas que hoy **no se pueden calcular con ningún dato existente**:
"CTO saturada", presupuesto óptico y "sectores con alta concentración de daños".

**2. El Supervisor NOC pasa a poder ejecutar, con la frontera de por medio.**
Tomada después de que esta sesión advirtiera que choca con dos cosas escritas:

- `SPEC/FUERA_DE_ALCANCE.md` §3 — *"No agregar herramientas que escriban
  configuración WiFi en el equipo del cliente"*.
- El propio prompt del rol — *"NO EJECUTA NINGUNA ACCION"*.

El usuario la reafirmó. **Esa decisión se aplica así, y no de otra forma:**

- Toda acción nueva entra como herramienta `irreversible` y sale **solo** por
  `frontera.critica()`. Llegando al ejecutor por cualquier otro camino, no sale.
- `SPEC/FUERA_DE_ALCANCE.md` §3 se actualiza **en el mismo commit** que la
  primera acción, con la fecha y el motivo. Un documento de autoridad que dice
  lo contrario de lo que el código hace es peor que no tenerlo.
- El techo de autonomía sube **por decisión explícita y registrada**, nunca
  como efecto lateral de agregar una herramienta.
- El prompt del rol deja de decir "NO EJECUTA NINGUNA ACCION" cuando la primera
  acción exista, no antes.

## El defecto que esta búsqueda encontró, y hay que arreglar primero

**El umbral de potencia que decide "buena o débil" está fijo en el núcleo.**

```
nucleo/herramientas/diagnostico_servicio.py:109   SENAL_MINIMA_DBM = -25.0
```

Mientras el esquema del proyecto ya declara, en dos lugares, que ese dato es
del tenant:

- `nucleo/config/schema.py:1641` — *"nucleo/ no sabe que es un dBm ni cuales son
  los limites de Rapilink"*
- `nucleo/config/schema.py:4151` — *"VA EN LA CONFIG DEL TENANT porque depende de
  la planta de cada empresa --el largo de los tramos, los splitters, el tipo de
  ONU-- y no de este software"*

**El efecto medido el 12/11/2026, en producción:** la pantalla de revisión de
cierre de una orden real dijo *"La medida al salir (-21 dBm) está dentro de lo
que la empresa considera bueno **(-27 a -8)**"*. Rapilink editó su plantilla de
campo a **-27**. El diagnóstico del motor sigue usando **-25**.

Una ONT a -26 dBm es **"débil"** para el motor y **"buena"** para la revisión de
campo, el mismo día, en la misma empresa. Nadie lo reportó porque las dos
pantallas no se miran juntas.

`campo/plantillas.py:147` (-28) **no** es parte del defecto: es plantilla de
partida, semilla, y el comentario de ese archivo lo declara.

**La guarda de arquitectura no lo caza, y eso también es un hallazgo:**
`test_nucleo_sin_tenants.py` busca slugs, ramas por tenant y URLs. Un **número**
fijo que debería ser configuración le pasa por al lado, en verde.

## El plan, en olas

Cada ola se puede soltar sola. El orden es por dependencia, no por gusto.

### Ola 0 — el defecto y lo que es configuración pura (horas)

| # | Qué | Código o config |
|---|---|---|
| 0.1 | `SENAL_MINIMA_DBM`/`SENAL_MAXIMA_DBM` salen de la configuración del tenant, con el valor de hoy como respaldo. Y la guarda nueva que lo mide | **código** |
| 0.2 | Que `test_nucleo_sin_tenants.py` también cace un umbral numérico declarado en `nucleo/` cuando el esquema lo declara del tenant | **código** |
| 0.3 | `consultar_topologia_ont` entra a `puede_consultar` de `supervisor_noc` — hoy la herramienta existe y el rol no la tiene | **config** |

0.3 es, de todo este documento, el mejor cambio por esfuerzo: es una línea de
configuración y le da al Supervisor la vista de planta que hoy no usa.

### Ola 1 — contrato ya verificado, cero llamadores (días)

Las dos están **verificadas en vivo** en `.claude/skills/smartolt-api/SKILL.md` y
no las llama nadie. Es capacidad pagada y sin usar.

| # | Qué | Evidencia |
|---|---|---|
| 1.1 | Temperatura, voltaje y uptime de OLT | `get_olts_uptime_and_env_temperature`, `SKILL.md:920` (OLT 4: `normal`, 53,22 V) |
| 1.2 | Stream de eventos de alarma | `get_event_stream?events=pon.outage_started`, HTTP 200, `SKILL.md:918`. La URL lleva token y expira en 900 s: **no se loguea**, y eso exige código |
| 1.3 | MTBF, al lado de MTTR | `operaciones/indicadores.py`, reusando sus tres estados de cobertura |

### Ola 2 — el inventario de planta (semanas)

La decisión del usuario. Tabla nueva: CTO, splitter, puerto, acometida, y qué
servicio cuelga de dónde. Dos preguntas abiertas que hay que resolver **antes**
de la primera migración: de dónde salen los datos iniciales, y quién los
mantiene cuando un técnico mueve a un cliente de puerto.

### Ola 3 — lo que el inventario desbloquea

CTO saturada · presupuesto óptico y atenuación por tramo · sectores con alta
concentración de daños · reincidencia de fallas **por servicio** (el tercer
sentido de esa palabra en este repo; ver abajo).

### Ola 4 — el Supervisor que actúa

Primera acción, con `frontera.critica()`, auditoría de frontera obligatoria y
la actualización de `FUERA_DE_ALCANCE.md` §3 en el mismo commit.

### Ola 5 — consolidación multi-especialista

La **única** pieza de mecanismo genuinamente nueva. Hoy `derivar_a_area` es un
relevo **secuencial**: el especialista toma la conversación y el rol anterior
deja de atender (`motor.py:4382-4395`). No existe fan-out + consolidación.
Toca `nucleo/modelo/motor.py`, 4.153 líneas, monolito de §2/D3.

## Lo que es configuración y no se programa

Si esto se escribe en `nucleo/`, la guarda de §3.1 lo caza — y si es un número,
no lo caza, que es justo el defecto de arriba.

1. **Documentos para el RAG**: manuales de OLT, planos de planta, inventario de
   CTO, procedimientos. Camino: `corpus/<tenant>/` → `cli/cargar_corpus.py`.
   El `corpus/` del repo hoy solo tiene un `README.md`.
2. **Procedimientos y árboles de decisión** → `asistente.habilidades`, con su
   `cuando_usarla` escrito por una persona (`habilidades/catalogo.py:21-26`: el
   disparador no lo calcula un coseno).
3. **Prompts de los 5 especialistas** → `roles:` del tenant, mismo molde que
   `supervisor_noc:1939`.
4. **Rangos de potencia por empresa** → `Herramienta.veredictos` y
   `TenantConfig.umbral_rx_dbm`.
5. **Marcas y modelos de OLT** → dato de empresa. Una rama por marca en
   `nucleo/` es un `if` por cliente con otro nombre.

## Las trampas, con su evidencia

Cada una ya costó algo. No se redescubren.

1. **El ping no prueba que algo funcione.** §12, y ya rechazó un botón:
   `SPEC/auditorias/1.8-NETWORK.md:36-40`. El mismo equipo sano devuelve `1 de 3`
   y `3 de 3` en corridas seguidas. Sirve para **descartar**, nunca para afirmar.
2. **`LOS` es ambiguo; `dying gasp` concluye.** `SKILL.md:352-358` y
   `rapilink.config.yaml:6659`: fibra cortada y equipo desenchufado *"desde la
   OLT se ven identicos"*. Un correlacionador que trate LOS como "falla de red"
   cierra casos a gente sin servicio.
3. **`ACCION_CONFIRMADA` ≠ problema resuelto**, y la condición de éxito no puede
   ser una mejora del ping (§12, medido dos veces).
4. **La IA puede pedir atención, nunca negar un cierre.**
   `campo/inspeccion_visual.py:24-36`: el punto de IA jamás vale `False`. Un
   "auditor técnico" que repruebe una instalación por IA invierte esa decisión
   del 31/10/2026.
5. **Un proveedor de visión distinto no es una decisión técnica.** §5: la
   autorización de tratamiento nombra al proveedor (Ley 1581 art. 26). Bloquea la
   extracción estructurada de seriales y etiquetas, que el proveedor actual no
   soporta (`vision.py:22-33`, medido 02/10/2026).
6. **Nada predice.** §4: el modelo compone, el código calcula. Y
   `operaciones/gobierno.py:460`: *"Que dos situaciones compartan PON no prueba
   que una sea reincidencia de la otra. La coincidencia es el dato; el
   diagnostico es de quien sabe."*
7. **Traceroute, DNS, jitter y saturación son integraciones externas nuevas.**
   Ni WispHub ni SmartOLT los exponen. `FUERA_DE_ALCANCE.md` §8 exige
   autorización explícita antes de código.
8. **"Reincidencia" ya nombra dos cosas distintas** y ninguna es la del módulo 10:
   `db.py:1046` (conversaciones del mismo número) y `gobierno.py:448`
   (situaciones operativas, que exige actor humano). La tercera —fallas repetidas
   del mismo servicio— no existe. Tres catálogos con la misma forma.
9. **`cli/evaluar.py` no mide esto.** §6: no pasa por `atender_turno`, y el
   Supervisor entra por `/interno/herramienta/` con `sesion=None`, que es un
   tercer camino. Lo que mide su conducta son las suites de
   `operaciones/tests/`, que piden Postgres y **no corren en CI** (D1).
10. **D5 aplica de lleno.** Cada pantalla nueva suma una aparición más de
    `PRIVATE_ASISTENTE_TENANT` (70 archivos / 80 apariciones al 24/09/2026).
    CLAUDE.md dice tomar esa decisión **antes** de escribir el código, y esto son
    varias pantallas.

## Criterios de aceptación

Comando y salida pegada, nunca prosa. Un criterio que no se puede pegar no es
un criterio.

### Ola 0

```
# 0.1 — el umbral sale de la config, y hay guarda que lo mide
py -3.13 tests/test_nucleo_sin_tenants.py
# esperado: [OK] El nucleo no conoce a ningun cliente

docker exec <backend> /opt/venv/bin/pytest tests/test_umbral_de_senal_por_empresa.py -q
# esperado: N passed — y el archivo tiene que existir; hoy no existe

# la guarda muere si se revierte: volver SENAL_MINIMA_DBM a -25.0 fijo
# y pegar el rojo
```

```
# 0.3 — el rol tiene la herramienta
py -3.13 cli/cargar_config.py --ver rapilink | grep -A 20 "supervisor_noc"
# esperado: consultar_topologia_ont aparece en puede_consultar
```

### Ola 1

```
# 1.1 — la herramienta devuelve datos reales, no un 200 vacio
py -3.13 cli/sondear_api.py   # o la llamada declarada
# esperado: la temperatura y el voltaje de cada OLT, pegados
```

### Todas

```
docker exec <backend> /opt/venv/bin/pytest campo/ operaciones/ -q --reuse-db --no-cov
# esperado: los 6 rojos preexistentes y ninguno mas
#   test_anonimizador x5 · test_despacho_pantalla::test_j x1
```

## Lo que ya se decidió y no se reabre sin medición nueva

`SPEC/auditorias/1.8-NETWORK.md` · `SPEC/objetivos/supervisor-pasa-a-despacho.md`
(*"Nadie sale a la calle por decisión de la IA"*, 14/10/2026) ·
`SPEC/objetivos/correcciones-al-diagnostico.md` (confirmó el -25 dBm **como
límite de la guía**, 18/10/2026 — no como constante del núcleo) ·
`SPEC/objetivos/entrenar-un-agente.md` (*"el carril de entrenar ya existía y es
`/habilidades`"*) · `operaciones/indicadores.py:1-40` (*"M11 NO lo reescribe: lo
LLAMA"*) · `operaciones/asistentes.py:1-45` (*"No hay cola nueva, no hay entidad
de recomendación"*).

## Riesgo abierto que esta especificación hereda

`SPEC/auditorias/1.8-NETWORK.md`, riesgo 2: el panel de red del Supervisor es
**histórico, no de estado** — *"Quien busque «¿está online?» no lo encuentra
acá"*. Ese hueco sigue vivo y es parte de lo que esta especificación pide.
