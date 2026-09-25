# Restricción de implementación · el estado dinámico no toca el prefijo cacheado

> Escrito el 25/09/2026, **antes** de la ficha y a propósito. La ficha del cambio
> espera dos mediciones (abajo); esta restricción no, porque el riesgo que cubre
> es que alguien implemente la solución obvia sin conocer el dato que la
> desaconseja.
>
> No cierra la arquitectura. Acota **una** decisión.

## El defecto que motiva todo esto

Medido el 25/09/2026, con su guarda en
[tests/test_system_identidad_no_queda_obsoleto.py](../../tests/test_system_identidad_no_queda_obsoleto.py)
(en ROJO DECLARADO, defecto abierto):

Los mensajes `system` que el motor arma dentro de `if not historial`
([nucleo/modelo/motor.py:3144](../../nucleo/modelo/motor.py)) se escriben **una
vez, en el primer turno**, y nada los invalida cuando el estado que describen
cambia. Una conversación que arranca sin verificar y se verifica después arrastra
para siempre *"Este cliente TODAVIA NO esta verificado: no sabes quien es, no
tienes su cuenta ubicada y no conoces su servicio"* — con `sesion.verificado`
ya en `True`.

**Un `system` no es memoria: es una instrucción vigente.** Si afirma un estado
que puede cambiar, en algún momento se vuelve una mentira activa, y el modelo no
tiene con qué saber cuál de los dos mundos es el de hoy.

## La solución obvia, y por qué es media solución

La lectura natural del defecto lleva a:

> *"El estado cambia, entonces regeneremos el `system` en cada turno con el
> estado actual."*

Es correcta en el diagnóstico y peligrosa en el lugar. El `system` es el
**primer** mensaje del payload, y el caché de entrada del proveedor es **de
prefijo**: cualquier cambio arriba invalida todo lo que viene después.

### La restricción

```
El estado dinámico NO modifica el prefijo estable del prompt.

La vista del contexto se construye preservando:
  - instrucciones estables ARRIBA      (cacheables: identidad, rol, políticas)
  - estado operativo dinámico ABAJO    (zona variable, recalculado por turno)

No mover estado al prefijo sin medir el impacto de caché.
```

Y el corolario que arregla el defecto sin pagar el costo: **el mensaje del turno
1 deja de afirmar estado.** El estado viaja en la cola, que es la parte que
cambia de todos modos — y de paso es donde tiene más peso de atención.

## El número, que es lo que hace defendible la restricción

Está medido en el repo y nadie lo va a cruzar con este problema por su cuenta
— [nucleo/modelo/cliente.py](../../nucleo/modelo/cliente.py), sobre
`tokens_entrada_cache`:

```
un token de entrada cacheado sale ~30 veces mas barato que uno nuevo
   ($0.014 contra $0.44 por millon, DeepSeek)

medido sobre 30 dias reales de Rapilink:
   141.8 millones de tokens  ->  $7.48       ($0.053 por millon)
   la misma carga sin cache  ->  $30 a $60   (estimado)
```

Se cita el número no para cerrar el diseño sino porque sin él la restricción
suena a preferencia. **Ninguna guarda del proyecto mira el costo**: un cambio que
multiplique la factura por 4 a 8 pasa el CI entero en verde.

## Lo que esta restricción NO decide

- **Cómo se invalida** un `system` vencido: `pop` como el precedente que ya
  existe ([api.py:1754](../../nucleo/canales/api.py) lo hace para
  `INSTRUCCION_REENCAUZAR`), o no escribirlo nunca arriba. Las dos respetan la
  restricción.
- **Qué forma tiene** el bloque de estado.
- **Si hace falta un contrato por inyección** (`tipo: permanente | temporal`,
  `vence: cuando cambia X`). Probablemente sí, y es de la ficha.

## Precedente: el principio ya está en el proyecto, aplicado a otra cosa

*Cada parte del sistema ve la vista adecuada a su responsabilidad* no es nuevo
acá: es lo que hacen las **listas blancas por rol**, que deciden qué campos del
cliente llegan al modelo según el área que atiende, sobre datos que siguen
completos abajo.

```
datos del cliente        -> vista según responsabilidad   ✅ resuelto
contexto conversacional  -> vista según responsabilidad   ← esto
```

Mismo principio, y más delicado en el segundo caso: el lenguaje natural arrastra
más que un campo ausente. **La regla que se conserva es la misma: no se arregla
eliminando información.** La identidad de agosto queda, el historial queda, la
auditoría queda. Lo que cambia es qué vista recibe cada componente.

## Lo que falta antes de la ficha: **una sola medición**

```
A/B/C contra el modelo, N>=5             C:\tmp\abc_router_con_modelo.py
```

Hoy está probado que la contradicción **existe**; falta **cuánto mueve la
decisión**. La ficha tiene que poder distinguir las dos cosas:

```
contradicción de contexto   ≠   causa conductual del modelo
```

Mide sobre la traza —si el turno llamó a `derivar_a_area`— y no sobre la
redacción. Y repite N veces cada variante porque el modelo es probabilístico: el
proyecto ya pagó esa lección dos veces con el ping, donde el mismo equipo sano
devuelve `1 de 3`, `2 de 3` y `3 de 3` en corridas seguidas. Lecturas:

```
A 5/5 · B 0/5 · C 5/5    causalidad cerrada
A 5/5 · B 3/5 · C 5/5    hay efecto, falta muestra -- NO es una refutación
A 5/5 · B 5/5 · C 5/5    la contradicción existe y NO explica este caso
```

### Ya cerrado, y no se remide

**Dónde se decide qué vista recibe cada rol.** La capacidad de un rol la define
`puede_consultar`, y de ahí `atender_turno` puede derivar la vista. Cerrado en
otra sesión de la investigación — *reportado, no medido acá*: si hace falta
reabrirlo, la evidencia está en esa sesión, no en este brief.

## Cómo se formula el objetivo de la ficha, y cómo NO

Esto decide si el arreglo conserva o destruye una mejora de producto, así que va
escrito antes de que la ficha exista.

```
MAL   "eliminar los mensajes system de identidad"
BIEN  "evitar que un estado temporal o una señal operativa se presenten como
       contexto permanente cuando ya no representan el estado actual"
```

La primera formulación parece la misma y borra la mejora de agosto de 2026. Los
~45 renglones de comentario en `motor.py:3154-3210` no son decoración: son la
memoria de por qué esos mensajes existen, qué bug evitaron y qué conducta no se
quiere recuperar.

### Las cuatro regresiones que el arreglo no puede reintroducir

Medidas en producción, con fecha, y hoy solo vivas como comentario. **La ficha
las hereda como criterios de aceptación** — es la única forma de que mover el
bloque no pierda lo que el bloque protege:

```
R1  15/08/2026 · ante "¿vos sabes quien soy?" el modelo FABRICA la explicación:
      "tu chat esta asociado a tu cuenta porque escribis desde el WhatsApp que
       tenes registrado"  y  "el sistema me confirma que sos el titular"
      Las dos frases inventadas. Por eso el aviso lleva el nombre real.

R2  15/08/2026 · ante "¿sabes quien te habla?" contesta sobre el TRÁMITE
      ("tu identidad quedo verificada antes") a alguien que pregunta por su
      NOMBRE, teniéndolo a mano. Son dos preguntas y se contestan distinto.

R3  12/09/2026 · sin verificar, el cliente escribe su cédula y recibe "no
      necesito ese numero, ya tengo tu cuenta ubicada". Las dos mitades falsas:
      ni la tenía ubicada ni podía. Es el agujero simétrico de R1.

R4  agosto 2026 · en un rol SIN herramientas de datos --el router-- el modelo no
      podía deducir la verificación de ninguna señal, y volvía a pedir la cédula
      de alguien ya verificado en CADA conversación.
```

R4 importa doble: explica por qué el aviso existe justamente en el rol donde se
está investigando el defecto. El mensaje no está ahí por descuido.

## El criterio de la vista: **suficiente**, no mínima

La pregunta que cierra este trabajo no es *cuánto* contexto darle al modelo, sino
**qué tipo de contexto corresponde a la responsabilidad que está ejerciendo**. Y
de ahí sale el criterio, que hay que fijar **antes** de leer los resultados o los
resultados eligen mal:

```
MÍNIMA        solo los mensajes del cliente.
              Puede alcanzar para UNA intención y perder identidad, estado y
              lo que evita repetir preguntas ya contestadas.

SUFICIENTE    el prompt del rol (estable, cacheable)
            + el hilo conversacional necesario
            + el estado actual, recalculado
              SIN: narrativa de herramientas · historial administrativo ·
                   escaladas previas como relato · procesos internos
```

### Por qué el criterio va antes del resultado

`30_solo_user` **puede ganar el experimento y ser inaceptable.** Si da 5/5 en la
decisión, la lectura tentadora es «la vista mínima alcanza». Pero esa vista quita
el aviso de verificación, y eso es exactamente **R4**: en un rol sin herramientas
de datos —el router— el modelo volvía a pedir la cédula de alguien ya verificado,
en cada conversación.

Una vista sirve si cumple **las dos** condiciones, y por eso el arnés mide dos
preguntas sobre el **mismo** contexto:

```
deriva como la referencia     Y     pide documento 0/N
```

`deriva 5/5 · pide documento 3/5` no es una solución: decide bien y reintroduce
la regresión de agosto. Es la trampa de optimizar una sola métrica.

**La segunda pregunta se mide sobre el TEXTO**, y es la excepción justificada a la
regla de medir sobre la traza: R4 se define como *le pide la cédula a alguien ya
verificado*, y eso no deja rastro en ninguna herramienta — el router tiene
`deriva_verificacion` y no verifica él mismo. Es un proxy por patrones y se
declara como tal: un falso negativo es posible si el modelo lo pide con otras
palabras, así que las respuestas de los casos en `0/N` se leen antes de darlos
por limpios.

## Fuera de alcance, con su motivo

**La auditoría de integridad de herramientas queda como deuda aparte.** Son tres
preguntas distintas, todas legítimas y ninguna de este trabajo:

```
1  herramienta declarada en puede_consultar que NO existe en el catálogo
     -> el rol cree poder algo que no puede
2  herramienta que existe y está declarada pero falla siempre
     (credencial, endpoint, parámetro)  -> declarada y muerta
3  herramienta ejecutable cuya lista blanca de campos deja la respuesta vacía
     -> la llama y no obtiene nada
```

Las tres dan resultados distintos y la 1 y la 3 se miden sin base ni red,
leyendo la config. **No se mezclan acá**: abren otro frente, y este trabajo es
sobre qué vista del contexto recibe cada rol, no sobre la salud del catálogo.
