# Objetivo · El Supervisor sabe del oficio, y por eso nota cuando el reporte no cuadra con el ticket

> Abierto el **12/11/2026**. Estado: **abierto**.
>
> **Encuadre, corregido por el usuario el mismo día.** La primera versión de
> esta ficha leyó la especificación de 10 módulos FTTH como una lista de
> capacidades a construir. No es eso. El usuario:
>
> > *"el objetivo de la información que te pasé es porque el supervisor debe
> > tener el conocimiento de su trabajo y debe saber identificar y relacionar
> > lo que escribe el técnico. Debe haber relación entre el asunto, la
> > descripción del ticket y la respuesta del técnico. No puede haber una
> > respuesta correcta en un asunto que ni por ahí iba al caso."*
>
> Los 10 módulos **no son el producto: son el insumo**. Son lo que hay que
> saber de FTTH para poder juzgar si *"fibra partida antes del conector"*
> explica *"el cliente no tiene internet"* — y si *"cambié la clave del WiFi"*
> no explica *"LOS en la OLT"*.

## Qué significa terminado

Una orden no se cierra sola cuando **lo que el técnico escribió no explica el
problema que originó el ticket**, y la pantalla de revisión dice por qué, con
las dos cosas una al lado de la otra para que una persona decida.

## El hueco, medido el 12/11/2026

`campo/revision_del_cierre.py::revisar()` evalúa **ocho puntos**:

```
_checklist · _reporte · _servicio · _medicion · _material · _fotos ·
_potencia · _en_rango
```

**Ninguno mira el ticket.** `grep -n "resumen\|diagnostico_previo"` sobre
`revision_del_cierre.py` y `cierre_por_el_supervisor.py` devuelve cero
coincidencias de uso: el único hit es una palabra dentro de un comentario.

`OrdenTrabajo` **sí** tiene de dónde sacarlo — `resumen` (TextField),
`diagnostico_previo` (JSONField) y `origen_ref` (el ticket del ISP) — y la
revisión no los lee. El técnico puede escribir cualquier cosa coherente
consigo misma y los ocho puntos dan verde.

### Y este hueco ya se cerró una vez, con fotos

`revision_del_cierre.py:131-137`, del **06/11/2026**:

> *"el supervisor debe revisar si las fotos coinciden con lo pedido; si piden
> foto del router y manda el TV no debe pasar". Tenía razón y el hueco era de
> información, no de poder: el botón «Devolver al técnico» ya existía, pero
> esta lista mandaba solo el id y el título —sin las instrucciones y sin la
> imagen—, así que **no había con qué comparar**.*

Es el mismo hueco, con texto en vez de imagen. Y la solución fue la misma:
**darle con qué comparar**, no darle más poder.

## Cómo se resuelve sin invertir una decisión congelada

Hay una tensión real y hay que nombrarla antes de construir.

El usuario dice *"no puede haber una respuesta correcta en un asunto que ni
por ahí iba al caso"*. Y `campo/inspeccion_visual.py:24-36` decidió el
**31/10/2026** que **el punto de IA nunca puede valer `False`**, porque un
`False` se convierte en veredicto `NO_CERRAR` y eso le da a la IA el poder de
negar el trabajo de un técnico.

**No se invierte, y aun así se cumple lo que el usuario pide.** El punto nuevo
vale `True` o `None`, nunca `False`:

| Valor | Veredicto de la orden | Qué pasa |
|---|---|---|
| `True` — el reporte explica el ticket | no estorba | la orden puede cerrar sola |
| `None` — no cuadra, o no se pudo juzgar | **`REVISAR`** | **la orden NO cierra sola**: una persona la mira |

`None` ya produce `REVISAR` en `revisar():117`. Una orden en `REVISAR` no entra
al cierre automático. Eso es exactamente *"no puede pasar"*, **sin** que la IA
repruebe a nadie: la frena para que la mire un humano, y le muestra las dos
cosas juntas con el motivo escrito.

## Las tres piezas, en orden

### Pieza 1 — el ticket entra a la revisión (el hueco de información)

Hoy `revisar(orden)` no ve el problema que originó la orden. Hay que llevarle
el asunto, la descripción y el diagnóstico previo, y mostrarlos en la pantalla
al lado de lo que el técnico escribió. **Esto solo ya tiene valor sin ninguna
IA de por medio**: hoy quien revisa tampoco los ve juntos.

Es la pieza más barata y la que desbloquea las otras dos. Nada se puede juzgar
sin ella.

### El caso real que la pieza 2 tiene que atrapar — capturado el 12/11/2026

Apenas la pieza 1 salió a producción, la primera tarjeta que el usuario miró
ya mostraba el problema entero. **No hay que inventar un caso de prueba: este
es.**

| | |
|---|---|
| **Se pidió** | *"Soporte en campo · Según el Supervisor: El cliente pide el cambio de router wifi como gestión comercial/técnica, **no por una falla**: el equipo está **en línea y con señal buena**. El único indicio técnico es un desajuste de configuración respecto a su perfil en la OLT (confianza baja). Recomienda: Va a Soporte Técnico / agenda de instalaciones con trabajo pedido, **no como correctivo**."* |
| **Qué hizo** | *"Potencia al llegar: **-50.0 dBm**. Qué encontró: **fibra partida antes del conector**. Qué hizo: se prepara nuevamente el conector y se restablece el servicio. Potencia al salir: -21.0 dBm. Servicio probado con el cliente: Hecho"* |

**Las dos cosas no pueden ser ciertas a la vez.** Un equipo en línea y con
señal buena no tiene la fibra partida ni recibe -50.0 dBm; un equipo con la
fibra partida no está en línea. Una de las dos lecturas está mal, o pasaron
cosas distintas en momentos distintos y nadie lo escribió.

**Y los ocho puntos estaban en verde.** *"El checklist está completo"*, *"El
técnico afirma que el servicio quedó funcionando"*, *"Registró 1 material"*,
*"La medida al salir (-21 dBm) está dentro de lo que la empresa considera
bueno"*. El único amarillo era de fotos. La orden se podía cerrar.

Lo que la pieza 2 tiene que devolver acá es `None` —no `False`— con el motivo
escrito: *"el ticket dice que el equipo estaba en línea y sin falla; el
reporte describe una fibra partida y -50 dBm al llegar"*. Y la orden queda en
`REVISAR` para que una persona decida cuál de las dos es la buena.

**Qué NO puede hacer:** afirmar que el técnico mintió. Puede que el
diagnóstico del Supervisor estuviera viejo, que el cliente tuviera dos
problemas, o que la fibra se partiera entre el diagnóstico y la visita. El
punto noveno nombra la contradicción; no la resuelve.

### Pieza 2 — el punto noveno: ¿el reporte explica el ticket?

El juicio es de lenguaje, no de cuenta, así que lo hace el modelo — y aquí
**no** rige *"el código calcula"* (§4): no hay nada que sumar. Lo que sí rige:

- El modelo **no inventa el veredicto final**. Devuelve si el reporte explica
  el problema y por qué; el código convierte eso en `True`/`None` y nunca en
  `False`.
- Un modelo que no contesta, o contesta algo que no se puede leer, da `None`,
  no `True`. **Fail-closed**: la duda frena, no pasa.
- Lo que el técnico escribió es **texto libre de una persona**. Antes de ir al
  proveedor pasa por lo mismo que el resto (§5), y el revisor de PII mira este
  camino antes de que salga.

### MEDIDO EN PRODUCCION EL 12/11/2026: la pieza 2 funciona, y la 3 puede no hacer falta

Encendido `cotejo_reporte_campo` para Rapilink (version 214 de `tenant_config`)
y cotejadas cuatro ordenes reales de la base, sin escribir nada:

| OT | Se pidio | Que hizo | Veredicto |
|---|---|---|---|
| 215 | cambio de clave de wifi, *"no una falla del enlace"* | conector dañado, se cambia APC | **no** |
| 200 | cambio de router, *"el servicio esta sano"* | conector dañado | **no** |
| 213 | problema del router, *"la ONU esta en linea"* | conector dañado | **no** |
| **210** | *"verifique y reemplace el conector optico"* | se cambia conector APC | **si** |

**4 de 4**, con el control negativo incluido — la #210 es el caso donde el
trabajo SI corresponde, y si hubiera salido `no` el cotejo no serviría para
nada.

**Lo que el modelo usó como evidencia, y es mejor de lo que se esperaba.** No
comparó palabras: comparó el dato técnico.

> *"el ticket afirma servicio operativo y que no hay falla del enlace,
> mientras el reporte da **-50 dBm al llegar** y un conector dañado
> reemplazado"*

En las tres contradicciones se apoyó en la potencia. **Ya sabe que -50 dBm
contradice «señal buena»** sin que nadie le cargara un manual de FTTH.

**Consecuencia para la pieza 3:** la evidencia apunta a que el conocimiento
FTTH no es necesario para ESTE juicio. Cuatro casos no lo cierran, y la pieza
queda abierta — pero baja de prioridad hasta que aparezca un caso que el
modelo no sepa juzgar.

**Y valida una decisión de diseño que podría haber sido al revés:** se mandan
TODOS los campos del reporte, no solo `solucion`. Con solo la solución el
`-50 dBm` no habría viajado y las tres contradicciones se habrían apoyado
únicamente en las palabras.

**Costo medido:** ~1.100 tokens y 1-7 segundos por cotejo, una vez por cierre.

**Lo que esta medición NO dice:** cuántas órdenes REALES tienen el problema.
Las 30 últimas de producción son pruebas — todas del servicio 5832, el mismo
técnico, y *"se cambia conector APC"* palabra por palabra en ~20 de 30. El
número de frecuencia se mide cuando entren clientes de verdad, con
`python manage.py cuantas_no_cuadran`.

### Pieza 3 — el conocimiento que hace bueno el juicio

Sin saber de FTTH, el modelo acepta cualquier par de frases que suenen
técnicas. Los 10 módulos del usuario son exactamente este contenido, y el
carril **ya existe y ya se decidió** — `SPEC/objetivos/entrenar-un-agente.md`:
*"el carril de entrenar ya existía y es `/habilidades`, no `/manual`"*.

| Qué cargar | Dónde | Por qué ahí |
|---|---|---|
| Qué causa explica qué síntoma (fibra partida → sin servicio; LOS → ambiguo) | `asistente.habilidades` | Es un procedimiento, y `habilidades/catalogo.py:21-26`: el disparador lo escribe una persona, no lo calcula un coseno |
| Manuales de OLT y ONT, planos, tabla de potencias | `corpus/<tenant>/` → `cli/cargar_corpus.py` | Material de consulta, no procedimiento. Hoy `corpus/` solo tiene un `README.md` |
| Rangos de potencia de esa empresa | `TenantConfig.umbral_rx_dbm` | Ya existe. Ver la ola 0 |

**Nada de esto es código.** Si se escribe en `nucleo/`, es un `if` por cliente
con otro nombre.

## Ola 0 — el defecto que apareció buscando esto (en curso)

**El umbral de potencia estaba fijo en el núcleo.** `SENAL_MINIMA_DBM = -25.0`
en `nucleo/herramientas/diagnostico_servicio.py:109`, mientras
`nucleo/config/schema.py` declara en dos lugares que ese dato es del tenant, y
`TenantConfig.umbral_rx_dbm` ya existía sin que nadie lo leyera.

**El efecto, en producción, el 12/11/2026.** La pantalla de revisión de una
orden real dijo *"La medida al salir (-21 dBm) está dentro de lo que la empresa
considera bueno **(-27 a -8)**"*. Rapilink editó su plantilla de campo a **-27**;
el motor seguía en **-25**. Una ONT a **-26 dBm** era *débil* para el
diagnóstico y *buena* para la revisión de campo, el mismo día y en la misma
empresa.

`test_nucleo_sin_tenants.py` pasó en verde todo ese tiempo, y tiene razón
según lo que mide: busca slugs, ramas por tenant y URLs. **Un número no se
parece a ninguna de las tres.**

| # | Qué | Estado |
|---|---|---|
| 0.1 | El piso sale de `umbral_rx_dbm`, con respaldo histórico | **hecho** |
| 0.1b | `tests/test_umbral_de_senal_por_empresa.py`, 15 afirmaciones | **hecho** |
| 0.2 | Que la guarda de arquitectura cace un umbral numérico declarado del tenant | pendiente |
| 0.3 | `consultar_topologia_ont` al catálogo de `supervisor_noc` — la herramienta existe y el rol no la tiene | pendiente, **config** |

**Decisión, contestada por la captura del 12/11/2026:** el rango efectivo de
Rapilink es **-27 a -8** — lo dice la propia pantalla de revisión de una orden
real: *"La medida al salir (-21 dBm) está dentro de lo que la empresa
considera bueno (-27 a -8)"*. Ese es el número que hay que cargar en
`umbral_rx_dbm`; el -25 del motor es el que estaba mal. Falta **cargarlo en
producción**, que es acción de una persona (`cli/cargar_config.py` o el editor),
no de una sesión.

## Lo que NO se construye, porque ya existe

Mapeado por `arquitecto-dexter` el 12/11/2026, con la guarda de arquitectura
en verde como base (129 archivos, 1 tenant).

**El rol `supervisor_noc` ya corre en producción** —
`tenants/rapilink.config.yaml:1939-2026` — con prompt, 11 herramientas, listas
blancas, 13 campos en `nunca_revelar`, pantalla y backend propios. Su prompt ya
dice *"NO EJECUTA NINGUNA ACCION"*, *"SEPARA LO QUE SABES DE LO QUE DEDUCIS"* y
*"VAS MAS ALLA DE LA SENAL"*.

| La especificación pide | Ya es |
|---|---|
| 5 especialistas coordinados | Un rol = prompt + catálogo + lista blanca. `motor.py:17-23`: *"un «coordinador + subagentes» no es mas que «un modelo, un prompt y un catalogo de tools distintos segun quien pregunta»"* |
| Correlación de alarmas | `operaciones/correlacion.py`, jerarquía PON > OLT > zona |
| Microcortes | `nucleo/herramientas/estabilidad.py` |
| MTTR, FRT, SLA | `cases/analytics.py` vía `operaciones/indicadores.py` |
| Topología OLT/PON/zona/caja | `consultar_topologia_ont`, `rapilink.config.yaml:5946` |
| Vecinos en LOS del mismo puerto | `diagnostico_servicio.py:195-269` |
| Análisis de fotos | `nucleo/canales/vision.py` + `campo/inspeccion_visual.py` |
| Fallas masivas | `nucleo/herramientas/incidentes.py` + `operaciones/deteccion.py` |

## Capacidad pagada y sin usar

Dos contratos **verificados en vivo** en `.claude/skills/smartolt-api/SKILL.md`
con **cero llamadores** (0 en `tenants/*.yaml`, 0 en `nucleo/`):

| Qué | Evidencia |
|---|---|
| Temperatura, voltaje y uptime de OLT | `get_olts_uptime_and_env_temperature`, `SKILL.md:920` (OLT 4: `normal`, 53,22 V) |
| Stream de eventos de alarma | `get_event_stream?events=pon.outage_started`, HTTP 200, `SKILL.md:918`. La URL lleva token y expira en 900 s: **no se loguea**, y eso exige código |

## Las dos decisiones del usuario del 12/11/2026

**1. Entra un inventario de planta externa** (CTO, splitters, puertos, qué
cliente cuelga de dónde). Llave de tres cosas que hoy **ningún dato existente
permite calcular**: CTO saturada, presupuesto óptico y sectores con
concentración de daños. Dos preguntas a resolver antes de la primera
migración: de dónde salen los datos iniciales, y quién los mantiene cuando un
técnico mueve a un cliente de puerto.

**2. El Supervisor pasa a poder ejecutar, con la frontera de por medio.**
Tomada después de que esta sesión advirtiera que choca con
`SPEC/FUERA_DE_ALCANCE.md` §3 y con el propio prompt del rol. Se aplica así, y
no de otra forma:

- Toda acción nueva entra como `irreversible` y sale **solo** por
  `frontera.critica()`.
- `FUERA_DE_ALCANCE.md` §3 se actualiza **en el mismo commit** que la primera
  acción, con fecha y motivo.
- El techo de autonomía sube por decisión registrada, nunca como efecto
  lateral de agregar una herramienta.
- El prompt deja de decir *"NO EJECUTA NINGUNA ACCION"* cuando la primera
  acción exista, no antes.

Ninguna de las dos bloquea las tres piezas de arriba. Van después.

## Las trampas, con su evidencia

1. **El ping no prueba que algo funcione.** §12, y ya rechazó un botón:
   `SPEC/auditorias/1.8-NETWORK.md:36-40`. El mismo equipo sano devuelve
   `1 de 3` y `3 de 3` en corridas seguidas. Sirve para descartar, no para
   afirmar.
2. **`LOS` es ambiguo; `dying gasp` concluye.** `SKILL.md:352-358`: fibra
   cortada y equipo desenchufado *"desde la OLT se ven identicos"*. **Esto es
   justamente lo que la pieza 3 tiene que enseñarle**: si el ticket dice LOS y
   el técnico reporta "estaba desenchufado", eso **sí** cuadra.
3. **`ACCION_CONFIRMADA` ≠ problema resuelto** (§12).
4. **La IA puede pedir atención, nunca negar un cierre** (31/10/2026). Resuelto
   arriba con `None` → `REVISAR`.
5. **Un proveedor de visión distinto no es decisión técnica** (§5, Ley 1581
   art. 26).
6. **Nada predice.** `operaciones/gobierno.py:460`: *"La coincidencia es el
   dato; el diagnostico es de quien sabe."*
7. **Traceroute, DNS, jitter, saturación** son integraciones externas nuevas.
   `FUERA_DE_ALCANCE.md` §8 exige autorización antes de código.
8. **"Reincidencia" ya nombra dos cosas** (`db.py:1046` conversaciones,
   `gobierno.py:448` situaciones) y ninguna es "fallas repetidas del mismo
   servicio".
9. **`cli/evaluar.py` no mide esto** (§6): no pasa por `atender_turno`, y la
   revisión del cierre es un tercer camino. Lo que la mide son las suites de
   `campo/` y `operaciones/`, que piden Postgres y **no corren en CI** (D1).
10. **D5 aplica**: cada pantalla nueva suma una aparición de
    `PRIVATE_ASISTENTE_TENANT` (70 archivos / 80 apariciones al 24/09/2026).

## Criterios de aceptación

Comando y salida pegada. Un criterio que no se puede pegar no es un criterio.

### Pieza 1 — el ticket llega

```
docker exec <backend> /opt/venv/bin/pytest campo/tests/test_el_ticket_entra_a_la_revision.py -q --reuse-db --no-cov
# el archivo hoy NO existe
# esperado: N passed — y que revisar() devuelva el asunto, la descripcion y
#           el diagnostico previo junto a lo que el tecnico escribio
```

### Pieza 2 — el punto noveno

```
# que NUNCA valga False, aunque el modelo diga que no cuadra
docker exec <backend> /opt/venv/bin/pytest campo/tests/test_la_respuesta_cuadra_con_el_ticket.py -q --reuse-db --no-cov
# esperado, en la misma corrida:
#   - reporte que no explica el ticket  -> punto None, veredicto REVISAR
#   - el modelo no contesta             -> punto None (fail-closed)
#   - reporte que si explica            -> punto True, no estorba
#   - en NINGUN caso ok is False
```

### Ola 0

```
py -3.13 tests/test_umbral_de_senal_por_empresa.py
# esperado: [OK] El piso de potencia lo pone cada empresa, y sin configurar
#           nadie se queda sin veredicto.

py -3.13 tests/test_nucleo_sin_tenants.py
# esperado: [OK] El nucleo no conoce a ningun cliente.
```

### Todas

```
docker exec <backend> /opt/venv/bin/pytest campo/ operaciones/ -q --reuse-db --no-cov
# esperado: los 6 rojos preexistentes y ninguno mas
#   test_anonimizador x5 · test_despacho_pantalla::test_j x1
```

## Lo que ya se decidió y no se reabre sin medición nueva

`SPEC/auditorias/1.8-NETWORK.md` (rechazó el botón de ping y el de reinicio) ·
`SPEC/objetivos/supervisor-pasa-a-despacho.md` (*"Nadie sale a la calle por
decisión de la IA"*, 14/10/2026) · `SPEC/objetivos/correcciones-al-diagnostico.md`
(el -25 dBm como límite **de la guía**, 18/10/2026) ·
`SPEC/objetivos/entrenar-un-agente.md` (*"el carril de entrenar ya existía y es
`/habilidades`"*) · `operaciones/indicadores.py:1-40` (*"M11 NO lo reescribe: lo
LLAMA"*) · `campo/inspeccion_visual.py:24-36` (la IA no niega un cierre).

## Riesgo abierto que esto hereda

`SPEC/auditorias/1.8-NETWORK.md`, riesgo 2: el panel de red del Supervisor es
**histórico, no de estado** — *"Quien busque «¿está online?» no lo encuentra
acá"*.
