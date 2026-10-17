# Inventario — qué hace y qué funcionalidad tiene

Descripción funcional de la sección Inventario de un CRM interno para proveedores
de internet (ISP). Sin nada sobre apariencia: solo qué hace, qué datos maneja, qué
reglas cumple y qué puede responder.

Medido sobre el código que está en producción (`campo/inventario_views.py`,
`campo/inventario_operacion_views.py`, `campo/services/inventario*.py`).

---

## 1 · Para qué existe

La sección responde tres preguntas, y todo lo demás está subordinado a ellas:

1. **¿Tengo material con qué despachar hoy?**
2. **¿Qué tiene encima cada técnico, en su camioneta o en su mochila?**
3. **¿Dónde está este aparato concreto, quién lo tuvo y por dónde pasó?**

Quien la usa es la oficina: coordinación, supervisión y bodega. **El técnico no
usa esta sección** — él consume y devuelve material desde una app móvil propia,
que escribe en el mismo libro por otra puerta.

---

## 2 · Vocabulario del dominio

**Ubicación.** Un lugar donde puede haber material. Tres tipos:
- `bodega` — un depósito físico. Puede haber varias.
- `vehiculo` — una camioneta cargada.
- `tecnico` — la **custodia** de una persona: lo que lleva encima. Se crea sola la
  primera vez que se le despacha algo.

Las tres son lo mismo para el sistema: la custodia de un técnico se consulta igual
que una bodega. No hay ubicación "proveedor" ni "cliente" — ver la regla 2.

**Material de catálogo.** Tiene código (`CON-SC-APC`), nombre, categoría, unidad, y
una **clase** que cambia cómo se comporta:
- `consumible` — se cuenta en enteros. Un conector y medio no existe: si llega
  2.7, se guarda 2 (se trunca hacia abajo, no se redondea).
- `bobina` — se cuenta con decimales. Fibra en metros: 257.500.
- `serializado` — cada unidad es un aparato con número de serie único. Una ONT, un
  router. La cantidad siempre es 1 y la serie es obligatoria.

**Movimiento.** Cada hecho que ocurrió con material. Tiene tipo (`entrada`,
`despacho`, `traslado`, `consumo`, `devolucion`, `ajuste`, `baja`), cantidad,
serie si aplica, ubicación de origen, ubicación de destino, quién, cuándo y por
qué. **Nunca se edita ni se borra.**

**Existencia.** Cuánto hay de un material en una ubicación. **No es un dato
guardado**: se calcula siempre como `suma de lo que entró − suma de lo que salió`.

**Activo serializado.** La identidad de un aparato concreto (material + serie), con
un puntero a dónde está ahora. Ese puntero es un atajo: siempre se puede
reconstruir desde los movimientos, y el sistema compara los dos y avisa si no
coinciden.

**Reserva.** Material comprometido para un trabajo que todavía no salió. No mueve
nada, pero descuenta de lo que se puede prometer.

---

## 3 · Las siete reglas que gobiernan todo el módulo

Son decisiones tomadas, no detalles de implementación. Cada funcionalidad las
cumple.

**1. Un solo libro, y la existencia se calcula.** No hay columna de "stock". La
existencia de una bodega y el saldo de un técnico salen de la misma resta sobre los
mismos movimientos. Un contador guardado y un movimiento que llega ocho horas tarde
—que es el caso normal de una cuadrilla sin señal— se desincronizan en cuanto
alguien reintenta, y a partir de ahí nadie sabe cuál de los dos números es bueno.

**2. Hay exactamente dos fronteras, y en cada una falta un lado.** Una **entrada**
no tiene origen (el material viene de afuera del sistema). Un **consumo** no tiene
destino (el material entró a la pared de la casa de un cliente, y de eso el dueño
es el sistema del ISP, no este). No se inventan ubicaciones falsas para tapar esos
dos huecos.

**3. Un hecho que ya ocurrió se registra, no se rechaza.** Cuando el técnico
sincroniza un consumo, el conector ya está ponchado. Si el consumo deja el saldo en
negativo, **entra igual** y queda marcado como descuadre, porque rechazarlo no
devuelve el material a la camioneta: solo borra el único registro de que se usó.

**4. La única excepción es el despacho.** Es el único acto del ciclo que todavía no
ocurrió —el material está sobre el mostrador—, así que sí se puede negar. Negar un
despacho imposible no borra ningún hecho: evita que nazca uno falso.

**5. Lo que falta se nombra, no se absorbe.** Cuando una devolución no cuadra, no
hay un ajuste silencioso que cierre la cuenta: se registra lo que llegó de verdad y
la diferencia queda como una incidencia abierta con su motivo. "Faltan 3
conectores" y "se dañaron 3 al retirarlos" son hechos distintos.

**6. Los negativos se muestran.** Una existencia negativa es exactamente lo que
alguien tiene que ver. No se corrige a cero.

**7. Si un dato no se pudo leer, se dice — nunca se muestra un cero.** Una bodega
que dice "0 conectores" porque la consulta falló manda a un técnico a la calle sin
material, y desde afuera no se distingue de una bodega realmente vacía.

---

## 4 · Las diez áreas funcionales

### 4.1 Existencias
**Qué hace:** lista todas las ubicaciones con movimientos y, en cada una, una fila
por material: código, nombre, categoría, existencia y unidad. Incluye los
materiales que quedaron en cero, porque "hubo y se acabó" es información distinta
de "nunca hubo".

**Qué devuelve:** todas las ubicaciones a la vez, bodegas y custodias de técnicos
por igual. Es la vista que contesta la pregunta 1 y la 2.

---

### 4.2 Registrar una entrada
**Qué hace:** da de alta material que entra al sistema por primera vez sin factura
—un equipo retirado de la casa de un cliente, un lote sin papeles.

**Datos:** material, cantidad (o serie si es serializado), ubicación de destino, y
una **referencia de origen** opcional (número de remisión o factura).

**Qué valida:** que la ubicación de destino exista; que el material esté en el
catálogo (se acepta el código o el identificador); que la cantidad sea un número.

**Qué significa la referencia:** con ella, registrar la misma entrada dos veces no
la duplica. Sin ella no hay forma de saber que es la misma, y la segunda entra
igual —porque el material está sobre la mesa— pero queda marcada como no
protegida.

---

### 4.3 Despachar a un técnico
**Qué hace:** la bodega le entrega material a una persona. Produce dos cosas a la
vez: el **acta de entrega** (el documento que las dos partes firman) y los
**movimientos** (la verdad de la que sale la existencia).

**Datos:** bodega de origen, técnico que recibe, número de acta (opcional), y una o
más líneas de material con cantidad o serie.

**Qué valida —y es el único que puede negar:**
- Un material serializado sin número de serie no se despacha: sin el número no se
  sabe qué aparato se entregó.
- Una línea sin cantidad no se despacha.
- **Una serie no puede estar en dos manos a la vez.** Si el aparato figura en otra
  custodia, el despacho se niega y el mensaje dice **dónde está**: "la serie
  HWTCA6FB5263 figura en 'Custodia de Carlos Ramírez' y no en el origen de este
  despacho: primero hay que registrar su devolución". Ese dato resuelve el caso; un
  "no se pudo despachar" obliga a investigar de cero.

**Qué hace además, sin que se pida:** libera las reservas que cubrían ese material
en esa bodega. Lo despachado deja de estar comprometido.

**Idempotencia:** el número de acta es lo que hace que un doble clic o el reintento
de un proxy no despache dos veces. El mismo acta es el mismo hecho: el segundo
intento devuelve la entrega que ya existía, sin descontar de nuevo. Sin acta no hay
esa protección.

---

### 4.4 Recibir una devolución
**Qué hace:** el técnico trae material de vuelta y la bodega lo recibe. El material
sale de la custodia y entra a la bodega.

**Datos:** técnico que devuelve, bodega que recibe, líneas de material con cantidad
o serie, notas opcionales, y un campo opcional **"cuánto se esperaba"**.

**Por qué ese campo es opcional y qué cambia:** devolver 12 de 18 es legítimo —al
técnico le quedan 6 y sigue trabajando—, así que el sistema **no adivina un
faltante**. Solo cuando quien recibe declara cuánto debía volver, la diferencia
abre una **incidencia** con su motivo. Quien recibe es el único que sabe si esto es
un cierre de jornada o una entrega parcial.

**Qué devuelve:** la confirmación, y si se abrieron incidencias, cuáles y por
cuánto. Ese resultado no es un éxito limpio ni un error: la devolución entró y
además falta material. Las dos cosas tienen que verse.

---

### 4.5 Trasladar entre ubicaciones
**Qué hace:** mueve material entre ubicaciones internas —bodega a bodega, o bodega
a camioneta. Es lo que hace útil tener más de una bodega: sin traslado, dos bodegas
son dos sistemas separados.

**Datos:** origen, destino, líneas de material, motivo opcional.

**Qué valida:** que origen y destino existan y **sean distintos**; que haya
cantidad; y la misma regla de la serie que el despacho (un aparato no sale de donde
no está), porque el traslado tampoco ocurrió todavía.

---

### 4.6 Reservas y material libre
**Qué hace:** deja comprometido material para un trabajo futuro, y muestra **las
tres cifras juntas** por material: cuánto **hay**, cuánto está **comprometido**, y
cuánto queda **libre**.

**Por qué las tres y no solo la última:** la pregunta que la operación hace de
verdad no es "cuánto hay" sino "cuánto puedo prometer para mañana". Y "quedan 70"
sin saber que hay 100 con 30 comprometidos no se puede interpretar.

**Datos para reservar:** ubicación, material, cantidad (o serie, para comprometer un
aparato concreto), **fecha de vencimiento** opcional y motivo.

**Qué valida:** que haya material libre suficiente. Si no alcanza, se niega y el
mensaje trae los tres números: "en 'Bodega Central' quedan 10 libres y se piden 30.
Hay 100 en total, 90 ya comprometidos". Una serie ya reservada no se reserva dos
veces.

**Por qué conviene la fecha de vencimiento:** sin plazo, una orden que se cae deja
el material comprometido para siempre y quien lo reservó ya se fue a su casa.

**Liberar una reserva:** se marca, **no se borra**. Queda con su motivo y su
desenlace (liberada, vencida, o consumida por un despacho). Es lo que permite
contestar después "por qué faltaron ONT el martes".

**Todo esto es sobre una ubicación concreta**: un "comprometido" global no se puede
despachar desde ningún lado.

---

### 4.7 Conteo físico
**Qué hace:** alguien cuenta la bodega a mano y registra lo que encontró. El ciclo
tiene tres pasos: **abrir** un conteo sobre una ubicación, **anotar** cuánto hay de
cada material, y **cerrar**.

**Qué pasa al cerrar —y esto es el punto:** el conteo **no reescribe el saldo**.
Escribe un movimiento de ajuste por cada diferencia, con su motivo y su
responsable, y deja la diferencia visible. "El sistema dice 50 y tengo 48" no es un
error del sistema: es un hecho nuevo que alguien tiene que explicar, y un conteo que
sobreescribiera el saldo perdería lo único interesante que tiene.

**Qué devuelve al cerrar:** una línea por material contado, con lo contado, lo que
decía el sistema, la diferencia, y si generó ajuste. **Incluye las líneas que
cuadraron**: un conteo que solo muestra diferencias no deja ver cuánto se revisó.

**Qué valida:** un solo conteo abierto por ubicación a la vez (dos conteos abiertos
producen dos verdades sobre lo mismo); un conteo sin líneas no se puede cerrar
(dejaría constancia de que se contó cuando no); un conteo cerrado no se puede
modificar (sus números ya produjeron ajustes).

**Advertencia funcional:** si quien cuenta no escribe el motivo de la diferencia, el
ajuste queda marcado como *diferencia sin explicar*. Eso se registra tal cual.

---

### 4.8 Compras, proveedores y valorización
**Qué hace:** registrar una compra es la **única vía por la que entra un costo** al
sistema. Crea la compra y una entrada de material por cada línea, con su costo
unitario.

**Datos de la compra:** bodega de destino, proveedor (opcional), referencia de la
factura, moneda, y líneas con material, cantidad, serie y costo unitario.

**Idempotencia:** la referencia de la factura. La misma factura dos veces no
duplica el material.

**Proveedores:** nombre, identificación y contacto. Crear uno que ya existe no
falla: devuelve el que había y lo dice.

**Valorización de una ubicación:** cuánto vale lo que hay. El costo de cada
material es un **promedio ponderado** de lo que costó al entrar —se declara el
método a propósito, porque promedio, FIFO y LIFO dan números distintos sobre los
mismos datos.

**Lo que no se puede valorizar se nombra:** un material sin costo conocido **no se
cuenta como cero** —cero diría que es gratis, que es distinto de no saberlo. Queda
listado aparte, con su cantidad, y el total avisa que no los incluye. Un total que
se come en silencio lo que no sabe valorizar es la forma más rápida de que alguien
decida con un número que parece completo.

---

### 4.9 Reportes
Tres, y cada uno contesta una pregunta distinta:

**"En qué se fue el material":** consumo agrupado por material sobre una ventana de
tiempo. Código, nombre, cantidad consumida, unidad.

**"Por técnico":** qué consumió cada persona, agrupado por material. **No trae
ninguna métrica de eficiencia ni comparación entre personas, a propósito:** dos
técnicos con distinto tipo de trabajo no son comparables por metros de fibra, y un
número que parece comparable se usa como si lo fuera.

**"Descuadres abiertos":** la lista de movimientos que quedaron en descuadre o en
conflicto, con fecha, estado, material, cantidad, persona y motivo. Es una lista y
no un contador: un número en un tablero se mira una vez y se ignora; una lista se
puede resolver.

---

### 4.10 Buscar un aparato por su serie
**Qué hace:** es la funcionalidad que justifica todo el módulo. Con el número de
serie devuelve:

- **Dónde está ahora**, en palabras: una bodega, la custodia de una persona, o
  "fuera de custodia" cuando ya se instaló en la casa de un cliente.
- **Toda su historia en orden**: cada movimiento con su fecha, su tipo, de dónde
  salió, hacia dónde fue, su motivo y su estado. Desde que entró al sistema hasta
  hoy.
- **Un aviso si el atajo y el libro no coinciden.** El puntero de posición es un
  derivado, y el sistema lo compara contra los movimientos. Si difieren, lo dice y
  aclara que manda el libro. Un dato guardado que nadie puede verificar es
  exactamente lo que este módulo evita.

**Cuando no hay resultado, la respuesta es específica:** "no hay ningún aparato con
esa serie en esta empresa; no es un error de consulta: nunca entró al sistema".

---

## 5 · Quién puede hacer qué

Dos niveles, y la diferencia importa:

**Mover inventario** (entrada, despacho, devolución, traslado, reservar, liberar,
contar, comprar, crear proveedores) lo pueden los roles de gestión —administración,
supervisión, operaciones— **más el rol de bodega**. Un bodeguero despacha y recibe,
y **no** valida órdenes de trabajo ni cierra casos: son dos permisos distintos que
se veían iguales porque el primero no existía.

**Consultar** (existencias, catálogo, ubicaciones, libre, reservas, valorización,
reportes, buscar un aparato) lo puede cualquier persona autenticada de la empresa,
técnicos incluidos. Saber en qué se fue el material no mueve nada.

**Aislamiento entre empresas:** el módulo es multiempresa. Una ubicación, un
material o una reserva de otra empresa **no existe** para quien consulta: no es un
error de permiso, simplemente no aparece.

---

## 6 · Qué significa cada respuesta

La distinción no es decorativa: es lo que permite que un mensaje sirva.

| Respuesta | Qué significa | Qué tiene que hacer quien la recibe |
|---|---|---|
| **Creado / registrado** | El hecho quedó escrito | Nada |
| **Registrado con diferencia** | La operación entró **y** quedó algo abierto (una incidencia, un descuadre) | Mirarlo. No es éxito ni error |
| **400 — dato mal escrito** | Una cantidad que no es un número, un material que no está en el catálogo | Corregir el dato |
| **409 — el inventario no lo permite** | El dato está bien, pero el estado del material lo impide: no alcanza lo libre, la serie está en otra custodia, ya hay un conteo abierto, esa factura ya se registró | Mirar el número o el aparato, no el formulario |
| **403** | El rol no puede mover inventario | Pedir el permiso |
| **404** | No existe en esta empresa | — |

Con 400 para las dos primeras cosas, quien usa la pantalla no puede distinguir
"escribiste mal la cantidad" de "no queda material libre", y todo termina siendo
"no se pudo".

---

## 7 · Lo que el módulo deliberadamente NO hace

Cada ausencia es una decisión, no un pendiente:

- **No borra ni edita nada.** Corregir es registrar un movimiento en sentido
  contrario, como en cualquier libro contable.
- **No guarda ningún contador de existencia**, disponible ni saldo.
- **No calcula eficiencia por técnico** ni los compara entre sí.
- **No tiene mínimos, máximos ni alertas de reposición.** Hoy no existen.
- **No sigue el material dentro de la casa del cliente.** Cuando se instala, sale
  de este sistema; quién es el cliente y qué equipo tiene lo sabe el sistema del
  ISP.
- **No corrige un saldo negativo** ni esconde un descuadre.

---

## 8 · Límites conocidos hoy

Para que no se diseñe funcionalidad sobre algo que no está resuelto:

- Una devolución que el técnico declara desde su app y la recepción que registra la
  bodega son **dos hechos separados**, y hoy las dos descuentan de la custodia. Si
  se registran las dos por el mismo material, se resta dos veces. Falta
  conciliarlas.
- Las reservas con plazo vencido **no se liberan solas**: hace falta un proceso que
  las barra, y todavía no está en marcha.
- La valorización **suma montos sin distinguir la moneda** de cada compra.
- Los movimientos de ajuste que ya estaban en la base antes del 28/09/2026 no
  tienen dirección y no cuentan en ninguna existencia: su sentido no quedó
  registrado y no se puede deducir.
