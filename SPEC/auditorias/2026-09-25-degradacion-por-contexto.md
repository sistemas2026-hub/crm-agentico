# Hallazgo: degradación de decisión por contexto no filtrado

> Medido el 25/09/2026 con `cli/varianza_contexto.py`, base aislada
> `dexter_local`, motor real (DeepSeek) por el camino de `atender_turno`.
> No se tocó producción.

**No es un defecto de DeepSeek.** Es de arquitectura de contexto, y por eso se
escribe así: cualquier modelo que reciba el mismo historial hereda el problema.
Jev tampoco es inmune — su propia página de fallos lista el estado grande y
ruidoso como modo de degradación (ver la skill `typesafe-jev`).

---

## La regla que sale de esto

> **El historial de conversación no debe pasar completo al modelo sin una capa
> de selección o resumen operativo.**

---

## ✅ CAUSA IDENTIFICADA (25/09/2026) — las señales de proceso, no el contexto

Cinco condiciones, dos conversaciones cargadas, seis corridas cada una. Mensaje:
`"quiero cancelar"`. Esperado: `facturacion_cliente` (lo que decide con el
historial vacío, 20/20).

```
A  historial completo                        0/12
B  resumen CON actividad      (1 turno)      0/12
C  resumen NEUTRO             (1 turno)     12/12
D  resumen minimo             (1 turno)     12/12
E  historial completo + otro fraseo         12/12
```

**B y C son la prueba.** Los dos son UN turno, misma forma, longitud
equivalente. Lo único que cambia es el contenido:

```
B  "Conversacion previa sobre no_internet. Identidad: verificada.
    9 herramientas ya ejecutadas. Hubo una escalada previa.
    Esa gestion NO sigue activa."                              ->  0/12

C  "Conversacion previa sobre no_internet. El intercambio abarco
    varios turnos. Se trataron temas del servicio contratado.
    Esa gestion NO sigue activa."                              -> 12/12
```

**No es la cantidad de contexto: son las señales de proceso.** Identidad
verificada, herramientas ejecutadas y escalada previa suprimen la derivación.
Sin ellas, el mismo formato y el mismo largo derivan siempre.

Y el control de longitud era imprescindible: sin él, C se habría atribuido a
"menos texto", que es la explicación equivocada y la que lleva a construir un
resumidor en vez de un filtro.

### Dos consecuencias que cambian el diseño

**1 · Comprimir no sirve si se conserva la señal.** B tiene UN turno y hace el
mismo daño que A, que tiene diez. Un Context Manager que resuma fielmente
—"hubo escalada, corrieron 9 herramientas"— reproduce el defecto en versión
corta. La decisión de diseño no es *cómo resumir* sino **qué no reportarle al
router**.

**2 · Decirlo explícitamente no alcanza.** B termina con *"Esa gestion NO sigue
activa"* y aun así da 0/12. Negar la continuidad en una frase no contrarresta
tres datos que la sugieren.

### Lo que E deja abierto, y no lo arregla ninguna capa de contexto

`E` mantiene el historial ENTERO y solo cambia el fraseo del cliente:

```
"quiero cancelar"                      ->  0/12
"necesito informacion para cancelar"   -> 12/12
```

**El fraseo lo escribe el cliente.** No hay Context Manager que lo controle.
Esto no es una vía de solución: es evidencia de que el ruteo es frágil ante la
forma del pedido, y eso solo lo cubre una guarda de código.

### D deriva, pero no es replicable

`D` dice *"No hay gestion activa asignada"* y da 12/12 — pero eso es servirle
la conclusión. En producción nadie sabe de antemano si hay gestión activa: si
lo decidiera el modelo, volveríamos al problema inicial con un paso más.

---

## FASE DE HIPÓTESIS: CERRADA. Cinco descartadas, con su evidencia

Se cierra el 25/09/2026 sin causa determinada, y eso **no es un fracaso**: cada
descarte costó una tanda y dejó al siguiente experimento más barato. Lo que sí
sería un fracaso es construir una solución para cualquiera de estas cinco.

| Hipótesis | Veredicto | Evidencia |
|---|---|---|
| El **largo** del historial | descartada | no hay umbral: errático desde 2 mensajes, y con 6, 15 y 20 vuelve a acertar |
| La **ambigüedad** del mensaje | descartada | `"necesito ayuda"` es igual de ambiguo y da 100 % en los nueve largos — pero su base ya era `None`: no tenía nada que perder |
| El **tema** del historial | descartada | historial de soporte 0/12 y de facturación 0/12: da igual de qué hable |
| La **identidad verificada** | descartada **como causa directa** | correlacionaba 0/84, pero el mismo grupo dio **15/15 en una muestra y 0/6 en otra**. La etiqueta contenía comportamientos distintos |
| El **prompt** (`"vos no verificas a nadie"`) | **refutada** | A/B en memoria, mismas conversaciones, misma tanda: **idéntico en los 4 casos** (0/6→0/6, 3/3→3/3, 2/6→2/6) |
| La **señal de identidad inyectada** (`motor.py:3138`, arreglo de agosto 2026) | **descartada** | Sin historial, cambiando **solo** `sesion.verificado`: el router deriva **6/6 con señal y 6/6 sin ella**, y con la señal deja de pedir la cédula (6/6 → 0/6). No hay tensión entre el arreglo de agosto y el hallazgo de septiembre: **la señal ayuda y no daña** |

**El patrón del error, repetido cinco veces:** elegir una etiqueta, agrupar por
ella y atribuirle el efecto. Una etiqueta que contiene comportamientos
distintos no explica nada — los esconde. Por eso la fase siguiente **no
agrupa**: caracteriza conversación por conversación y busca la variable sobre
los datos, no antes.

## LA CAUSA SOSTENIDA, y la frontera que deja

**El rol de entrada recibe señales de gestión previa como narrativa
conversacional.** Eso, y no el estado que el código mantiene.

```
contexto CON señales de gestión (texto)    ->  0/12 derivaciones
contexto neutro, mismo largo               -> 12/12
la bandera sesion.verificado (estado)      ->  6/6  — no rompe
```

La última línea es el control que lo separa todo: **la misma información, en
dos formas, da resultados opuestos.** Como dato de estado ayuda; como historia
de gestión, rompe.

### La frontera

```
quién es el cliente        ->  ESTADO      (la bandera, el id, el servicio)
qué hizo Dexter            ->  AUDITORÍA   (herramientas, escaladas, eventos)

y ninguno de los dos se le cuenta al rol de entrada COMO CONVERSACIÓN
```

Lo que sí recibe el rol de entrada es **el hilo** —qué dijo el cliente, qué se
le respondió— porque sin eso no se entienden los mensajes de continuación
("sí", "sigue igual", "ya lo hice"), que son la mitad de cualquier conversación
real.

**Lo que NO recibe es la intención ya clasificada.** Servirle "intencion:
cancelacion" sería o bien redundante —es lo que tiene que decidir— o bien
haberla decidido en otro lado, moviendo el problema un casillero. Es el mismo
defecto que tuvo la condición `D` del experimento, que derivaba 12/12 porque el
texto decía "no hay gestión activa": funciona en el laboratorio y no es
replicable, porque en producción nadie sabe eso de antemano.

---

## ⚠️ CORREGIDO el 25/09/2026 con 180 corridas — tres afirmaciones se cayeron

La primera versión de este documento se escribió con **3 puntos de medición**
(0, 10, 30) y 2 mensajes. Al ampliar a **9 largos × 4 mensajes × 5 corridas =
180 corridas**, más un control de 20 corridas, tres cosas resultaron falsas:

| Decía | Medido con 180 corridas |
|---|---|
| "Diez mensajes alcanzan para romperlo" | **Dos alcanzan.** Con 2 previos ya cambia 2 de 5 |
| "La latencia sube 57 % con el largo" | **No hay tendencia.** Los nueve largos dan entre 6,8 y 8,2 s, sin patrón. Los tres puntos de la primera tanda fueron casualidad |
| "Un mensaje ambiguo se diluye; uno específico resiste" | **Refutado.** `"necesito ayuda"` es igual de ambiguo y aguantó **100 % en los nueve largos**. La ambigüedad no es la variable |

Lo que sobrevivió, y ahora con control: **el historial sí cambia la decisión.**
`"quiero cancelar"` sin historial da la misma área **20 de 20 veces**; con
historial oscila. El caso no es inestable por sí mismo.

Se deja escrito porque es el punto: con tres mediciones parecía una
degradación proporcional al largo, y con nueve se ve que no lo es.

---

## Qué se midió

El mismo mensaje, con distinto historial encima, cinco corridas por condición.
El historial se inyecta en la sesión y es **relleno neutro**: cortesías que no
mencionan internet, facturas ni planes. Lo único que cambia entre condiciones
es cuánto texto hay antes, no de qué habla.

```
                 0    2    4    6    8   10   15   20   30   ← mensajes previos
cancelar       100   60   80  100   80   80  100  100   60   %  de acuerdo
ayuda          100  100  100  100  100  100  100  100  100
comprobante    100  100  100  100  100  100  100  100  100
sin_internet   100  100  100  100  100  100  100  100  100

control: cancelar con 0 previos, 20 corridas -> 20/20 la misma area
```

**Dos mensajes de cortesías vacías alcanzan** para que la decisión cambie. No
hace falta que el historial hable de otra cosa ni que compita semánticamente.

La latencia **no** muestra tendencia: los nueve largos caen entre 6,8 y 8,2 s
sin patrón. (La primera versión afirmaba +57 %; eran tres puntos y era ruido.)

---

## Lo que las 180 corridas sí muestran

**1 · No es inestabilidad: es SUPRESIÓN de la derivación.**

⚠️ Esto se leyó al revés durante unas horas, y la causa fue la métrica. La
tabla original medía **consistencia** —si las cinco corridas coinciden entre
sí— y no **acierto** —si coinciden con la decisión sin historial—. Son cosas
distintas: una condición puede ser 100 % consistente y 0 % acertada, o sea
decidir siempre lo mismo y siempre distinto de la base.

Recalculado contra la decisión de 0 previos (`facturacion_cliente`):

```
cancelar   0: 5/5   2: 3/5   4: 1/5   6: 0/5   8: 1/5
          10: 4/5  15: 0/5  20: 0/5  30: 3/5
```

**Con 6, 15 y 20 mensajes previos, las cinco de cinco corridas deciden algo
distinto.** Eso con la métrica vieja figuraba como "100 % estable", y se leyó
como "el historial no lo afecta". Era exactamente lo contrario.

En total: **sin historial acierta 5 de 5; con historial, 12 de 40 (30 %).**

**2 · De los cuatro mensajes, dos resisten y uno no deriva nunca.**

```
comprobante    5/5 en los nueve largos   (base: facturacion_cliente)
sin_internet   5/5 en los nueve largos   (base: soporte_tecnico_cliente)
ayuda          5/5 ... pero su base ya es None: NUNCA derivó, ni sin historial
cancelar       12/40 con historial
```

`"necesito ayuda"` no "aguanta": no tiene nada que perder. Eso también corrige
lo anterior — no son "3 de 4 estables", son **2 que resisten de verdad**.

La ambigüedad sigue descartada como explicación (`ayuda` es igual de ambiguo y
no se puede comparar), pero ahora la pregunta es más precisa: **por qué el
historial suprime una derivación a facturación y no las otras dos.**

**3 · El fallo es de enrutamiento, no de comprensión.** Contra la base de 0
previos:

| | cambió área | perdió intención | cambió herramientas | escaló distinto |
|---|---:|---:|---:|---:|
| 2 previos | 2/5 | **0/5** | 2/5 | **0/5** |
| 6 previos | 5/5 | **0/5** | 5/5 | **0/5** |
| 10 previos | 1/5 | **0/5** | 1/5 | **0/5** |

**La intención nunca se pierde y el escalamiento nunca cambia.** Lo que cambia
es a qué área manda y qué herramientas llama — y las dos cosas se mueven
siempre juntas, porque el área decide el catálogo disponible.

Eso acota mucho dónde intervenir: el modelo sigue entendiendo qué quiere el
cliente; lo que se desestabiliza es la elección del destino.

---

## Con historiales REALES: la variable es la identidad, y el mecanismo es el texto

Se repitió con conversaciones reales de la base de laboratorio, agrupadas por
lo que el motor ya registra. Mensaje: `"quiero cancelar"`. Acierto = coincide
con la decisión sin historial (`facturacion_cliente`):

```
CONTROL sin historial      5/5  = 100 %
CONTROL sintetico (10)     1/5  =  20 %
sin_id                     8/10 =  80 %
sin_id+escalada            3/15 =  20 %
id_ok                      0/15 =   0 %
id_ok+escalada             0/15 =   0 %
id_ok+fallo                0/15 =   0 %
id_ok+fallo+escalada       0/15 =   0 %
                        ─────────────────
CON identidad verificada   0/60 =   0 %
SIN identidad verificada  11/25 =  44 %
```

**Los cuatro grupos con identidad verificada dan 0 de 15 cada uno**, tengan o no
herramienta fallida y escalada previa. Esas dos **no** son la variable. La
identidad sí.

### No es el estado, es el texto — y eso está probado

La sospecha obvia era que el estado `verificado` de la sesión cambiara el
catálogo del router. **Falso, medido:**

```
78 corridas · identidad=sin_verificar · 1 herramienta disponible · NO derivó
17 corridas · identidad=sin_verificar · 1 herramienta disponible · SÍ derivó
```

El router ve exactamente lo mismo en los dos casos. Lo único que cambia es qué
dice el historial.

Y como el experimento inyectaba el historial sin restaurar el estado —cosa que
producción sí hace— se corrió el control que lo decide: **con la identidad
restaurada como en producción, el resultado es idéntico (None en 6/6).** El
hallazgo no es un artefacto del arnés.

### Descartada la interferencia semántica

El grupo `id_ok` resultó estar **dominado por conversaciones de soporte**
(37 de 60: `no_internet`, `internet_lento`, `cambio_wifi`), así que el efecto
podía ser el TEMA del historial y no la identidad. Se separó:

```
"quiero cancelar"  (base sin historial: facturacion_cliente)

historial de SOPORTE     + identidad verificada  ->  0/12   (None)
historial de FACTURACION + identidad verificada  ->  0/12   (None)
```

**Da igual de qué hable el historial.** Si fuera interferencia semántica, un
historial de facturación debería *ayudar* a derivar a facturación; no lo hace.
La variable es la identidad verificada, no el tema.

Acumulado: **0 aciertos en 84 corridas** con identidad verificada en el
historial, contra 5/5 sin historial.

### Pero NO rompe todos los ruteos

```
"no tengo internet desde ayer…"   id_ok -> 15/15   INTACTO
"ya pague ayer…comprobante"       id_ok -> parcial (algunas van a soporte)
"quiero cancelar"                 id_ok ->  0/84
```

Así que no es "la identidad rompe el enrutamiento". Es más fino, y todavía sin
explicación: **rompe el de cancelación, degrada el de pagos y no toca el de
soporte técnico.**

### La segunda mitad: el escalamiento tampoco compensa

En esas corridas el log repite:

```
[escalamiento] se pospone: el asistente todavia no habia hecho nada
               motivo=informacion_a_confirmar / frustracion_detectada
```

O sea: el evaluador **sí quiere** pasar el caso a una persona, y se pospone
porque el asistente no hizo nada todavía. El resultado combinado es el peor de
los tres posibles: **ni deriva, ni escala.** Un cliente que escribe *"quiero
cancelar"* sobre una conversación con identidad ya verificada no llega a
ninguna parte.

---

## Dos correcciones que el propio experimento se hizo

Quedan escritas porque las dos cambiaron la conclusión:

**1 · La primera corrida comparaba dos variables a la vez.** Para los largos > 0
la sesión se creaba mandando un turno real (`"hola"`) y después se le pisaba el
historial, así que la condición de 0 previos era la única sin una conversación
ya abierta detrás. El 0-vs-10 medía largo **y** existencia de conversación
previa. Corregido: las tres condiciones construyen la sesión igual.

**2 · Con la corrida sesgada se concluyó que el desestabilizador era el
contenido y no la cantidad.** Con la mecánica igualada resultó lo contrario: la
cantidad sola ya rompe el caso ambiguo, con relleno vacío.

---

## Qué NO se midió

- **La interferencia semántica**: un historial que hable de otra área y arrastre
  la decisión hacia allá. Es otro experimento y necesita relleno con contenido.
- **Por qué `cancelar` y no los otros tres.** Es la pregunta abierta más
  importante. La ambigüedad quedó descartada; falta saber qué lo distingue.
  Cuatro mensajes no alcanzan — con quince o veinte empezaría a verse.
- **Si el efecto aparece con historial REAL.** Todo se midió con relleno
  sintético. Una conversación de verdad trae identidad verificada, herramientas
  ya llamadas y una escalada abierta, y nada de eso está en estas 180 corridas.

---

## De dónde venía la pista

Ya estaba escrita como advertencia en `cli/bateria_flujos.py`, sin medir:

> *"Reusar un numero arrastra la conversacion anterior --historial, identidad ya
> verificada, escalada abierta-- y el caso mide otra cosa. Es la leccion de la
> conversacion de produccion del 22/09: **con 27 mensajes encima, el mismo
> mensaje da otro resultado**."*

Se había anotado para no ensuciar las pruebas. Nunca se había tratado como un
fenómeno del sistema.

---

## El patrón que se repite en el proyecto

| Bloque | La forma del defecto |
|---|---|
| Campo | el dato correcto viajaba mal |
| Bandeja | la regla correcta estaba en el lugar incorrecto |
| **Conversacional** | **el modelo correcto recibe el contexto incorrecto** |

Las tres veces el componente estaba bien y el problema era lo que lo rodeaba.

---

## Qué sigue, en orden

1. ~~Medir el umbral~~ — **hecho: no hay umbral.** El efecto es errático desde
   2 mensajes y no crece con el largo. Eso cambia la estrategia: no sirve
   "resumir solo conversaciones largas".
2. **Un gestor de contexto**, y no necesariamente con IA: primero reglas. Que
   conserve identidad confirmada, intención actual, datos relevantes, decisiones
   previas y herramientas usadas; que descarte saludos, cortesías y ruido.
3. **Recién después, volver a evaluar modelos.** Hoy la comparación que se hizo
   fue *Dexter con contexto malo* contra *Jev*. La pregunta que importa es
   *Dexter con contexto correcto* contra *Jev*, y no se ha hecho.

Un modelo nuevo puede mejorar un porcentaje; si se le sigue entregando contexto
ruidoso, el problema sigue ahí.
