# Objetivo · El contexto que recibe una IA depende de lo que puede hacer

> Abierto el 25/09/2026. Estado: **propuesto, sin implementar.**
>
> Entrada: `SPEC/auditorias/2026-09-25-degradacion-por-contexto.md` — seis
> hipótesis descartadas, una causa sostenida y su control.

## Qué significa terminado

El rol que decide destino deja de recibir el expediente de lo que Dexter ya
hizo, y los roles que ejecutan lo siguen recibiendo entero. Sin listas de
nombres de rol, y sin que ninguna guarda del motor pierda lo que necesita.

## El problema, en una línea

```
la MISMA información, en dos formas, da resultados opuestos

  sesion.verificado = True          (estado)      ->  el router deriva 6/6
  "identidad verificada, 9 herra-
   mientas, escalada previa"        (narrativa)   ->  el router deriva 0/12
```

Un cliente que escribe *"quiero cancelar"* sobre una conversación con gestión
previa **no llega a ninguna parte**: ni se deriva ni se escala. Medido: 0 de 84
corridas con el historial cargado, 20 de 20 con el historial vacío.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| A1 | El turno que solo puede derivar recibe contexto ligero | `py -3.13 tests/test_contexto_del_router.py` → 16 verdes. **Ya existe y ya pasa** |
| A2 | Ninguna guarda del motor pierde lo que necesita | Las pruebas 1 y 2 del mismo archivo: `exige_previas` y `limite_por_conversacion` siguen contando con el historial completo |
| A3 | La regla no depende de ningún nombre de rol | Prueba 4: tres roles inventados (`ventas_entrada`, `cobranzas_whatsapp`, `soporte_l1`) dan el mismo criterio |
| A4 | El caso que lo motivó se arregla | `py -3.13 cli/cortes_historial.py rapilink --corridas 6` → la condición `A_completo` pasa de 0/12 a derivar |
| A5 | No se rompe lo que hoy funciona | `py -3.13 cli/bateria_flujos.py rapilink` → los 38 casos, sin regresiones contra el baseline |
| A6 | La señal de agosto sigue viva | `py -3.13 cli/tension_identidad.py rapilink` → el router **no** vuelve a pedir la cédula de alguien verificado (0/6) |
| A7 | **La trazabilidad no pierde nada** | La vista NO muta la fuente: tras construirla, el historial original queda idéntico, y `asistente.tool_calls` / `relevo_eventos` registran lo mismo que antes. Prueba unitaria, sin modelo |

**A7 faltaba, y es el criterio que protege todo lo demás.** Si la vista se
construye mutando el historial en vez de derivando una copia, el expediente
desaparece también de la auditoría, del Command Center y de la traza que usan
los casos dorados — y eso no se notaría hasta que alguien necesite reconstruir
qué pasó en una conversación. La regla es una sola: **se deriva una vista, no
se filtra la fuente.**

**A6 es la que protege un arreglo ajeno.** Es fácil "arreglar" el ruteo quitando
la inyección de identidad y reintroducir el bug de agosto sin notarlo — medido:
esa señal no daña la derivación, así que quitarla no gana nada y pierde algo.

## El contrato, antes que la regla

> **La vista del router nunca reemplaza ni modifica el historial fuente.**

Dos implementaciones se ven iguales desde afuera y solo una es correcta:

```python
# INCORRECTA -- borrado silencioso
historial = limpiar(historial)
router(historial)
#   el sistema sigue andando, y se perdieron la auditoria, la reconstruccion
#   de conversaciones, los casos dorados y el analisis posterior. Sin error,
#   sin log, sin alerta.

# CORRECTA -- la fuente intacta, cambia la vista de cada consumidor
fuente = obtener_historial()
router(vista_de_router(fuente))
guardar_auditoria(fuente)
```

**Y ojo con la version "correcta" de arriba en ESTE motor**, porque tal como
esta escrita produce el otro bug: `responder()` MUTA su argumento in-place y el
llamador lo conserva entre turnos. Pasarle una vista le entrega un cuaderno
descartable -- lo que escriba durante el turno no vuelve a la sesion.

```python
# INCORRECTA TAMBIEN -- la fuente deja de RECIBIR
motor.responder(config, rol, mensaje, vista_de_router(fuente), sesion)
#   los turnos 'tool', el system del area nueva y la respuesta caen en la
#   copia. El turno siguiente arranca sin nada de lo que paso en este.

# CORRECTA ACA -- la fuente se sigue pasando entera; la vista se aplica en el
# unico punto donde el historial se convierte en lo que el modelo VE
resp = cliente.chat(referencia_decision, vista_de(historial, rol_cfg), ...)
```

## La regla

> La vista de contexto se decide según las herramientas declaradas en
> **`cfg_rol.puede_consultar`**. No se usa `roles_permitidos`: representa
> permisos potenciales y puede incluir capacidades que no forman parte del
> contexto operativo del rol.

```
si el rol tiene UNICAMENTE derivar_a_area dentro de puede_consultar
    -> vista ligera: el hilo conversacional, sin señales de gestión
si tiene cualquier herramienta ejecutable
    -> vista completa
sin herramientas, o ante la duda
    -> vista completa (FALLA CERRADO)
```

Falla cerrado porque los dos errores no son comparables: pasar de más degrada
una derivación; pasar de menos puede repetir una acción irreversible.

**La formulación anterior decía "capacidad efectiva del turno" y era
imprecisa.** No hay variación por turno: medido el 25/09, el conjunto que ve el
modelo es `puede_consultar` ∩ catálogo, sin filtro posterior por identidad ni
por estado, y es el mismo en todos los turnos de un mismo rol. La distinción que
importa nunca fue turno-contra-config: fue **cuál de los dos campos de la
config**.

La función de referencia ya está escrita y probada en
`tests/test_contexto_del_router.py::contexto_ligero`. Vive ahí y no en
`nucleo/` a propósito: **no hay decisión de implementarla todavía**, y este
repositorio ya conoce el costo del código sin llamador.

## Restricciones

- **No tocar `sesion.verificado` ni su inyección.** Medido: ayuda y no daña.
- **No borrar del historial los turnos `tool`.** El motor los lee para
  `exige_previas` y `limite_por_conversacion`. Se construye una **vista**, no se
  muta la fuente.
- **No decidir por nombre de rol ni por `roles_permitidos`.** Medido:
  `cliente_final` declara nueve herramientas, una irreversible — por config no
  es un router puro, y decidir por ahí da el resultado contrario.
- **No servirle la intención ya clasificada.** Es lo que el rol tiene que
  decidir; dársela mueve el problema a quien la calcule.
- **No escribir `tenant_config`** mientras siga abierta la medición Q3.
- **El filtro tiene que ser estable entre turnos, y el motivo es económico.**
  El caché de entrada de DeepSeek es **de prefijo**, y un token cacheado sale
  ~30 veces más barato ($0.014 contra $0.44 por millón). Medido sobre 30 días
  reales de Rapilink: 141,8 millones de tokens costaron **$7,48** — una cifra
  que solo es posible si casi todo pega en caché; cobrados como nuevos serían
  $30 a $60. Ver `nucleo/modelo/cliente.py:90`.

  Consecuencia: si la vista del router quita mensajes del medio, el prefijo
  diverge desde el primero que falte. Mientras el filtro sea **determinista y
  el mismo en todos los turnos de ese rol**, la vista del turno N+1 tiene como
  prefijo a la del turno N y el caché se conserva. Un filtro que dependiera del
  estado del turno reescribiría el prefijo en cada turno y **haría pagar el
  historial entero a precio completo, siempre**.

  Esto es un argumento de costo a favor de la regla que ya quedó elegida
  —`puede_consultar` del rol, fija— y en contra de la formulación que se
  descartó ("capacidad efectiva del turno"). El 30× y la factura están
  medidos; el efecto sobre el prefijo es razonamiento sobre cómo funciona un
  caché de prefijo, **no está medido en este motor**, y se comprueba mirando
  `tokens_entrada_cache` antes y después.

## Qué NO hacer

- **No construir un "Context Manager" general, y el nombre importa.** Esto no
  administra memoria: decide qué VISTA del contexto corresponde a cada
  responsabilidad. Llamarlo "manager" invita a construir una capa que guarde,
  resuma y decida — tres cosas que no hacen falta. El hallazgo es acotado: un
  rol, una clase de dato, una función de diez líneas que ya está escrita y
  probada. Este proyecto ya evitó esa trampa dos veces en esta misma
  investigación.
- **No resumir el historial.** Medido: un resumen de UN turno que conserva las
  señales hace el mismo daño que diez turnos completos. El problema no es el
  tamaño.
- **No tocar el prompt.** Refutado con A/B en memoria: idéntico en los 4 casos.

## Bloqueos

**B1 · Dónde se construye el contexto. CERRADO, REABIERTO Y RECERRADO EN OTRO
PUNTO el 25/09/2026.**

Primero se cerró en `api.atender_turno`, antes de llamar al motor, sin tocar
`responder()`. **Esa respuesta era incorrecta, y la refuta la propia firma del
motor:**

```python
def responder(config, nombre_rol, mensaje, historial: list[dict], sesion, ...):
    """
    'historial' se muta in-place -- el llamador lo conserva entre turnos.
    """
```

`api.py:1708` pasa `estado["historial"]` **por referencia**, y el motor le hace
`append` durante todo el turno: los turnos `tool`, el `system` del área nueva al
derivar, el empujón de `sugerir_cuando_disponible`. El mismo parámetro es
entrada y salida.

Construir la vista en `api.atender_turno` significaría entonces que todo lo que
el turno escribe cae en la **copia** y no llega a la sesión: el turno siguiente
arrancaría sin nada de lo que pasó en este. A7 protege contra que la vista mute
la fuente; esto es el problema inverso —**la fuente deja de recibir**— y A7 no
lo cubre. Un filtro de lectura se vuelve una pérdida de escritura porque el
parámetro hace las dos cosas.

**Dónde va, entonces: `motor.py:3477`**, el único punto donde el historial se
convierte en lo que el modelo ve.

```python
while iteraciones < config.llm.limite_iteraciones_agente:
    iteraciones += 1
    resp = cliente.chat(referencia_decision, historial,     # <- aca
                        tools=catalogo_openai or None, ...)
```

La vista se aplica al argumento de esa llamada. El historial sigue mutándose
in-place para todo el resto del motor, la fuente queda intacta sin necesidad de
copiarla, y la auditoría no pierde nada.

Sí toca `responder()`, al revés de lo que decía el cierre anterior. Pero toca
**una línea**, en el borde exacto entre el sistema y el modelo — que es donde el
hallazgo dice que está el problema.

**Y hay un tercer argumento, de cobertura, que apareció el 25/09 al leer
`decision_del_router`:**

> *"el corredor de casos dorados (`cli/evaluar.py`) llama a `motor.responder()`
> DIRECTO y no pasa por `atender_turno`, así que nada de lo que se agregue
> alrededor del modelo lo ven los casos dorados."* — `api.py:1122`

Verificado en `cli/evaluar.py:191`: llama `motor.responder()`. Entonces una
vista construida en `api.atender_turno` **no la habrían ejercitado nunca los 56
casos dorados** — la guarda principal del repositorio, ciega justo sobre el
cambio. Dentro de `responder()` sí la ven, sin replicar nada.

Es la falla que §6 llama *código construido no es código que corre*, y acá
habría entrado por la puerta de al lado: el código corre en producción, pero
la prueba que debía cuidarlo no lo toca.

La medición que lo cierra — `puede_consultar` contra el conjunto que de verdad
recibe el modelo, en los ocho roles:

```
cliente_final              1  ->  1     SOLO deriva
soporte_tecnico_cliente   21  -> 21
facturacion_cliente        7  ->  7
ventas                    15  -> 15
soporte                   28  -> 28
facturacion               11  -> 11
administracion             9  ->  9
configuracion_guiada       2  ->  2
```

Coincide en los ocho, y no por casualidad:

```python
def herramientas_del_rol(config, rol_cfg):
    return [catalogo[n] for n in rol_cfg.puede_consultar if n in catalogo]

herramientas    = herramientas_del_rol(config, rol_cfg)     # motor.py:3198
catalogo_openai = [_esquema_openai(h) for h in herramientas]
```

Es determinista y conocible antes de armar el historial. Se descartó calcular
la capacidad en un punto nuevo: no hay nada que calcular.

**B4 · El rol cambia a mitad de turno, y ahí la vista ya está construida.**
Encontrado al verificar las líneas citadas arriba: `herramientas_del_rol` se
llama en **dos** puntos, no en uno.

```python
# motor.py:3198  -- al entrar al turno
herramientas = herramientas_del_rol(config, rol_cfg)

# motor.py:4072  -- DESPUES de que derivar_a_area cambio el rol activo
if sesion is not None and getattr(sesion, "rol_siguiente", None):
    ...
    herramientas = herramientas_del_rol(config, rol_cfg)
```

El comentario de ese bloque dice que el prompt del área nueva **entra al final
del mismo historial**, a propósito, para no empezar de cero. Consecuencia: en el
turno en que se deriva, el rol ejecutor hereda la vista que se construyó para el
router — la ligera.

El comentario de `motor.py:4051` lo dice sin ambigüedad: *"el especialista
atiende ACÁ, no en el próximo mensaje del cliente"*, y explica por qué —sin eso,
derivar le cuesta al cliente un intercambio entero sobre turnos que ya tardan
20-40s—. Así que la unidad no es el turno: es **cada llamada al modelo**.

**B4 no necesita una decisión propia: la resuelve el punto que cierra B1.** Como
`cliente.chat` está DENTRO del `while`, la vista se recalcula en cada vuelta. Y
`catalogo_openai` es exactamente la variable que 4072 rearma al cambiar el rol:
cuando el bucle vuelve a girar, el rol ya cambió, y la vista sale del rol nuevo
sin que haya que acordarse de reconstruirla en ningún lado.

Las dos opciones que se consideraron antes eran peores, y por el mismo motivo:

| | Dónde | Por qué no |
|---|---|---|
| vista por turno | `api.atender_turno` | rompe la escritura in-place, y el ejecutor hereda la del router |
| vista por transición | `api` + un rearme en 4072 | dos puntos de construcción; el día que aparezca un tercer camino que cambie de rol, nadie se acuerda |
| **vista por llamada** | **3477** | **un punto, y el que cambia de rol ya pasó por él** |

Esto se apoya en lectura de código, no en una corrida: es determinista y no
necesita el modelo. Lo que **no** está medido es qué borra exactamente la vista
ligera — eso es B2, y B4 no se puede terminar de escribir antes que B2.

**B2 · Qué cuenta como "señal de gestión". Tiene DOS mitades, y la segunda
apareció el 25/09 al revisar qué contenía el historial del experimento.**

*B2a — cuál de las tres.* Identidad verificada, herramientas ejecutadas y
escalada previa entraron **juntas** en el resumen que dio 0/12. Lo medido es que
*alguna* rompe, no cuál. Una vista que borre las tres cuando bastaba con una
borra de más, y en este objetivo el error caro es pasar de menos. El
experimento: `py -3.13 cli/senales_de_gestion.py rapilink --corridas 6`, cada
condición agrega UNA frase sobre el neutro que ya deriva 12/12.

*B2b — los turnos `tool` nunca estuvieron en la medición.* El historial del
laboratorio sale de `relevo/historial.py::construir`, y medido el 25/09 sobre
las dos conversaciones que dieron 0/12:

```
24d60d9d  no_internet · 9 herramientas ejecutadas -> {'user': 5, 'assistant': 5}
10929479  consulta_saldo · 4 herramientas         -> {'user': 4, 'assistant': 4}
```

Ni un turno `tool`, ni un `system`. Entonces **el texto conversacional basta
para romper el ruteo** —eso queda medido—, pero *que los `tool` sean inocuos no
se midió nunca*: no estaban ahí. La ficha lo daba por bueno y era una suposición.

Importa porque el historial **caliente** sí los tiene: `responder()` los appendea
in-place durante el turno. Si también rompen, la vista ligera choca de frente
con `exige_previas` y `limite_por_conversacion`. Si no rompen, la vista es
puramente textual y no toca nada de lo que leen las guardas — que es lo que
`tests/test_contexto_del_router.py` defiende.

**Medido el 25/09**, `cli/senales_de_gestion.py rapilink --corridas 6`, 96
turnos. Los dos controles reproducen, así que la tanda es comparable:

| Condición | 24d60d9d `no_internet` | 10929479 `consulta_saldo` | Total |
|---|---|---|---|
| `00_neutro` control | 6/6 | 6/6 | **12/12** |
| `01_completo` control | 0/6 | 0/6 | **0/12** |
| `10_identidad` | 5/6 | **0/6** | 5/12 |
| `11_herramientas` | 6/6 | 6/6 | **12/12** |
| `12_escalada` | 6/6 | 6/6 | **12/12** |
| `13_las_tres` | 0/6 | 0/6 | **0/12** |
| `20_tool_una` | 6/6 | 6/6 | **12/12** |
| `21_tool_varias` | 6/6 | 6/6 | **12/12** |

**B2b CERRADO: los turnos `tool` no rompen el ruteo.** Con el formato real del
motor, una llamada o dos, sobre un contexto que deriva: sigue derivando 12/12.
Consecuencia de diseño — **la vista ligera no necesita tocarlos**, así que no
hay conflicto con `exige_previas` ni `limite_por_conversacion`, que es el riesgo
que motivó `tests/test_contexto_del_router.py`. Ese test sigue valiendo: protege
contra una implementación que los borre por descuido, no contra una necesidad.

*Lo que esta medición NO dice:* los resultados inyectados son limpios
(`{"saldo": 0, "estado": "activo"}`). Un resultado de herramienta cuyo **texto**
narre gestión en curso no está probado, y por lo medido acá el daño lo hace el
texto.

**B2a NO está cerrado, y el total agregado engaña.** `10_identidad` da 5/12
sumado, pero desagregado son **5/6 y 0/6**: no es variabilidad del modelo, son
dos comportamientos distintos. Promediar por grupo es exactamente el error que
esta investigación ya cometió una vez.

Lo que sí queda firme:

- **`herramientas ejecutadas` y `escalada previa` no rompen solas** — 12/12 las
  dos, en las dos conversaciones.
- **`identidad verificada` es la señal activa**, y es la única que mueve la
  aguja.
- **Sola no basta, y las tres juntas sí** (0/12, igual que el historial
  completo).

**B2a CERRADO el 25/09 con la segunda tanda: 120 turnos, cuatro
conversaciones, dos de un tema que cae en el área de destino y dos que no.**

| Condición | `no_internet` | `consulta_saldo` | `validacion_de_pago` | `internet_lento` | Total |
|---|---|---|---|---|---|
| `00_neutro` control | 6/6 | 6/6 | 6/6 | 6/6 | **24/24** |
| `10_identidad` | 2/6 | 0/6 | 0/6 | 0/6 | **2/24** |
| `14_id_mas_herr` | 1/6 | 1/6 | 0/6 | 0/6 | **2/24** |
| `15_id_mas_esc` | 0/6 | 0/6 | 0/6 | 0/6 | **0/24** |
| `13_las_tres` | 0/6 | 0/6 | 0/6 | 0/6 | **0/24** |

**La señal que rompe el ruteo es `identidad verificada`, y basta sola.** Las
otras dos no aportan nada medible: agregarlas mueve 2/24 → 2/24 → 0/24, dentro
del ruido.

Tres cosas que esta tanda corrige, y las tres eran mías:

1. **"Identidad sola no basta, hace falta la combinación" era falso** — un
   artefacto de n=2 y una sola tanda. Con cuatro conversaciones, la identidad
   sola baja las cuatro.
2. **La hipótesis del tema queda refutada por su propia medición.** Si el tema
   modulara, los dos temas de facturación se comportarían distinto de los dos de
   soporte. No pasa: `internet_lento` (soporte) da 0/6 y `no_internet` (soporte)
   es el único que aguanta algo. El tema no separa nada.
3. **El laboratorio tiene ruido entre tandas que antes no se había medido.** La
   misma conversación, la misma condición `10_identidad`: **5/6 en la primera
   tanda, 2/6 en la segunda.** Las diferencias chicas entre condiciones no son
   interpretables; la que sí lo es, es la grande — 24/24 contra ≤2/24.

**Y esto confirma la tesis del objetivo con precisión.** La bandera
`sesion.verificado`, medida sin historial, deja al router derivando 6/6
(`cli/tension_identidad.py`). La frase *"Identidad: verificada."* dentro del
historial lo baja a 2/24. **Es el mismo dato**: como estado ayuda, como
narrativa rompe. Por eso la restricción de no tocar `sesion.verificado` sigue
en pie — el problema nunca fue la información, fue la forma.

*Sin medir todavía:* si hay otras señales — promesas de pago, acciones
pendientes, devoluciones.

**B5 · Cómo se reconoce la señal en un historial REAL. Abierto, y es ahora el
bloqueo principal.**

Lo medido dice qué señal quitar. No dice cómo encontrarla: en el historial real
no hay ninguna línea `"Identidad: verificada."` — hay un cliente que escribió su
cédula y un asistente que la confirmó, en lenguaje libre. Esa frase existía
solo en el resumen sintético del laboratorio.

Tres formas, con lo que cada una tiene medido:

| | Qué es | Estado |
|---|---|---|
| (a) resumen neutro derivado | tema + "esa gestión no sigue activa" | **24/24 medido**, pero depende de `caso_manual`, que sale del **evaluador de escalamiento en el post-proceso** (`api.py:2186`): no existe en el primer turno y cuesta una llamada al modelo |
| (b) historial menos los turnos que narran identidad | detectar la señal en texto libre | **sin medir.** Detección por patrón sobre lenguaje natural: frágil, y el proyecto ya sabe cómo termina eso |
| (c) solo los turnos `user` | el hilo de lo que el cliente pidió, sin las respuestas | **sin medir**, y es la más barata de medir: determinista, sin clasificación de por medio, y la narrativa de gestión la escribe el asistente |

**MEDIDO el 25/09, y (c) queda refutada.** 96 turnos, las mismas cuatro
conversaciones, los dos controles en la misma tanda:

| Condición | `no_internet` | `consulta_saldo` | `validacion_pago` | `internet_lento` | a facturación | salió del limbo |
|---|---|---|---|---|---|---|
| `00_neutro` control alto | 6/6 | 6/6 | 6/6 | 6/6 | **24/24** | 24/24 |
| `01_completo` control bajo | 0/6 | 0/6 | 0/6 | 0/6 | **0/24** | 0/24 |
| `30_solo_user` | 0/6 | 5/6 | 5/6 | 0/6 | **10/24** | 14/24 |
| `31_user_y_estado` | 0/6 | 4/6 | 4/6 | 3/6 | **11/24** | 14/24 |

**Quitar lo que escribe Dexter no alcanza.** Ni con la métrica exigente
(10-11/24) ni con la generosa (14/24), contra 24/24 del control. Y `31` no
supera a `30` —empatan en 14/24—, así que **la hipótesis del antecedente
tampoco se confirma**: lo que falta no es la pregunta que el `"sí"` contestaba.

*Defecto de métrica encontrado en esta tanda, y corregido.* `deriva_a` distinto
de `facturacion_cliente` contaba como fallo, mezclando **el limbo** (`None`, el
problema que originó todo) con **derivar a otra área**. `internet_lento` con
`31` dio `{soporte: 3, facturacion: 3}`: cero limbo, y la métrica lo anotaba
2/6. Recalculadas las tres tandas, **B2 y B2a dan idéntico con las dos
métricas** —ahí el fallo siempre fue limbo— así que sus conclusiones quedan en
pie sin cambios.

**Lo que aparece y no estaba previsto: `no_internet` es resistente a todo.**
0/6 en las cuatro condiciones salvo el control — ni siquiera con los mensajes
del cliente solos deriva. Es la conversación más cargada (10 turnos, 9
herramientas). Si el texto del propio cliente ya basta para bloquear el ruteo,
**ninguna vista que filtre el historial va a arreglar ese caso**: lo único que
lo mueve es reemplazarlo por un estado neutro.

Eso emparenta B5 con B3 y refuerza la misma conclusión: **la guarda anti-limbo
no es un complemento de la vista, es la que cubre lo que la vista no puede.**

**Dónde queda B5:** (a) es la única con evidencia a favor (24/24), y carga dos
costos explícitos — depende de `caso_manual`, que sale del evaluador en el
post-proceso, y rehace el prefijo en cada turno, que es el peor caso para el
caché (ver Restricciones). (b) sigue sin medir y sin razón para intentarla: si
filtrar por autor —que quita *toda* la narrativa de Dexter— no alcanza, filtrar
solo las menciones de identidad alcanza menos.

**Esto no invalida lo cerrado.** B1 (dónde), B2a (qué señal) y B2b (los `tool`
no molestan) siguen en pie. B5 es *con qué regla se construye la vista*, y sin
él no hay implementación posible.

**B3 · El fraseo del cliente queda fuera.** `"quiero cancelar"` da 0/12 y
`"necesito informacion para cancelar"` 12/12, con el mismo contexto. Eso no lo
arregla ninguna capa de contexto, y es el argumento a favor de hacer **primero**
la guarda anti-limbo: *si la intención requiere un área y no hubo derivación ni
escalamiento, no dejar la conversación detenida.* Es determinista, cubre el caso
aunque cambie el modelo, y no depende de que esta causa siga siendo válida.

## Bitácora

| Fecha | Qué avanzó | Qué falta |
|---|---|---|
| 25/09/2026 | Causa aislada con control de longitud. Seis hipótesis descartadas. Regla propuesta y probada (16 afirmaciones). Laboratorio completo | Decidir B1, y si se hace primero la guarda anti-limbo |
| 25/09/2026 | B1 cerrado en `api.atender_turno` con la medición de `puede_consultar` (8/8) | B2, B3 |
| 25/09/2026 | B2b cerrado: los turnos `tool` no rompen el ruteo (12/12), así que la vista ligera no choca con las guardas. B2a cerrado en una segunda tanda de 120 turnos: la señal es `identidad verificada` y basta sola (2/24 contra 24/24 del control); herramientas y escalada no aportan. Refutada la hipótesis del tema, y medido el ruido entre tandas (5/6 y 2/6 en la misma celda) | **B5**: con qué regla se construye la vista sobre un historial real |
| 25/09/2026 | **B1 reabierto el mismo día.** La firma de `responder()` dice que el historial se muta in-place: una vista en `api` haría que la fuente dejara de recibir lo que el turno escribe. Recerrado en `motor.py:3477`, el único punto donde el historial se vuelve lo que el modelo ve. Eso resuelve B4 de paso: el `cliente.chat` está dentro del bucle, y el rol nuevo ya cambió cuando el bucle gira | B2 (qué borra la vista), B3 (el fraseo), y la guarda anti-limbo |
