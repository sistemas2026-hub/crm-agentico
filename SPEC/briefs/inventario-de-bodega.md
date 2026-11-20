# Brief · Custodia de materiales y activos — de la bodega al cliente y de vuelta

> **Versión 3 · 25/09/2026.** Diseño **acordado** tras dos rondas de revisión. La
> v1 afirmaba que `MovimientoDeMaterial` estaba en producción; **no lo está** (§3),
> y esa corrección descartó la capa paralela que justificaba. La v3 cierra las tres
> decisiones que quedaban abiertas —el merge de migraciones, el puntero de
> ubicación y el lazo con WispHub— y ubica en fases las funciones que salieron de
> la revisión (§8). Lo que sigue abierto es **en qué rama se construye** (§14).
>
> Autocontenido a propósito: quien lo reciba no tiene el repositorio ni la
> conversación donde salió. Todo dato de código lleva su ruta para que lo
> **verifiques**, no para que me creas. Si algo de acá no coincide con el
> código, manda el código.
>
> Medido sobre la rama `feat/campo-diseno-stitch` (worktree
> `C:/wisphub/_wt_campo`), que es donde vive el módulo de campo. La rama de
> despliegue **no lo tiene**.

## 1 · El sistema, en cinco líneas

Dexter es un asistente de IA para ISPs (proveedores de internet), multi-empresa.
Tres piezas corren juntas:

| Pieza | Qué es | Tecnología |
|---|---|---|
| **Motor** (`nucleo/`) | El agente: habla con WispHub (el sistema del ISP) y SmartOLT | Python 3.13 · Flask |
| **CRM** (`django-crm/`) | Gestión y pantallas. Incluye el módulo `campo` | Django + DRF · SvelteKit |
| **App de campo** (`apps/tecnicos-mobile/`) | Lo que usa el técnico en el terreno | Flutter, con operación **sin señal** |

Una **orden de trabajo** (`campo.OrdenTrabajo`) es una visita que un técnico hace
a un cliente. En esa visita gasta material: conectores, metros de fibra, una ONT
(el equipo que va en la casa del cliente).

Todo cuelga de una **organización** (`Org`), que es la empresa. La base tiene RLS
por organización: una consulta sin el contexto fijado devuelve cero filas, nunca
todas.

## 2 · Lo que ya existe, y es mucho

El ciclo está construido **desde la mitad hacia adelante**: todo lo que pasa
después de que el técnico ya tiene el material en la camioneta.

Código: `django-crm/backend/campo/` — `models.py` (1.149 líneas),
`services/materiales.py` (394), `services/cierre_jornada.py` (430),
`materiales_views.py` (493). Cobertura: 30 archivos de prueba en `campo/tests/`
y 10 de los 47 de la app.

### Las ocho entidades

| Modelo | Qué es |
|---|---|
| `MaterialCatalogo` | Qué materiales maneja la empresa. Clases: `consumible`, `bobina`, `serializado`, `terminal`. `unidad` es texto ("unidades", "m", "kg") |
| `EntregaDeKit` | El acta de lo que la bodega le entregó a un técnico: `profile`, `despachado_por`, `acta`, `confirmado_en` |
| `ItemDeKit` | Una línea del acta: material + cantidad + `serie` |
| `ReglaDeConsumo` | Cuánto se suele usar por tipo de trabajo: `cantidad_habitual`, `maximo` |
| `MovimientoDeMaterial` | **Append-only.** Tipos `consumo`/`devolucion`/`ajuste`, estados `aceptado`/`descuadre`/`conflicto`, `idempotency_key`, y `ocurrido_en` (cuándo pasó en la calle) distinto de `created_at` |
| `IncidenciaDeMaterial` | Por qué lo que volvió no es lo que debía volver. Con evidencia fotográfica |
| `TransferenciaDeMaterial` | Material que pasa de un técnico a otro. `pendiente`/`aceptada`/`rechazada` |
| `ActaDeDevolucion` | El cierre de jornada. La única tabla del módulo que **guarda totales**, y solo al confirmarse: un acta es lo que dos personas acordaron ese día |

### Las cinco decisiones que NO se reabren

Están fundamentadas en los docstrings del código, con su motivo. Son el activo
más valioso de este módulo:

**1 · El saldo se calcula, nunca se guarda.**

```python
# services/materiales.py::saldo_de
entregado − consumido − devuelto + ajustado
```

> *"Un contador guardado y un movimiento que llega ocho horas tarde —que es el
> caso normal de una cuadrilla sin señal— se desincronizan en cuanto alguien
> reintenta, y a partir de ahí nadie sabe cuál de los dos números es el bueno.
> Sumar es barato; explicar un contador que miente, no."*

Y **puede dar negativo a propósito**: un `max(0, ...)` haría desaparecer el
descuadre de la pantalla sin haberlo resuelto.

**2 · El servidor no valida para rechazar: valida para clasificar.**

> *"Un movimiento de material es un hecho que ya ocurrió en la calle, no una
> solicitud que el servidor pueda aprobar o negar. Cuando el teléfono lo manda,
> el conector ya está ponchado y los metros de fibra ya no están en la bobina."*

Un consumo que deja el saldo negativo **entra igual**, marcado `descuadre`.
Rechazarlo no devolvería el material a la camioneta: solo borraría el único
registro de que se usó. La única excepción es una serie que otro ya consumió →
`conflicto`.

**3 · Nada se edita. Corregir es registrar en sentido contrario.** Una devolución
no anula el consumo de ayer: son dos hechos, en ese orden, y los dos tienen que
poder explicarse después.

**4 · Lo que falta no se esconde: se nombra.** Una diferencia al devolver abre una
incidencia con su motivo, porque *"faltan 3 conectores"* y *"se dañaron 3
conectores al retirarlos"* son hechos distintos.

**5 · Lo que varía por empresa es configuración, no código.** Precedente escrito
en este mismo módulo (`ReglaDeConsumo`): *"«Una instalación usa dos conectores» es
verdad en una empresa y falso en la siguiente"*.

## 3 · El estado real: construido, no desplegado

Medido el 25/09/2026 comparando las ramas con git:

```
migraciones de campo en la rama de DESPLIEGUE:  0001 · 0002 · 0003_alter_asignaciontrabajo_rol
migraciones de campo en la rama de CAMPO:       0001 · 0002 · 0003_campos_de_despacho
                                                0004  ← las 8 tablas de materiales
                                                0005  ← reglas + motivo del técnico
                                                0006  ← acta, incidencia, transferencia
```

**Ninguna tabla de materiales existe en producción.** No hay un `MovimientoDeMaterial`
real, ni un `ItemDeKit`, ni un acta. Lo que sí hay es una app Flutter que consume
los cinco endpoints y 10 archivos de prueba que los afirman: eso es código a
rehacer, no datos a preservar.

**Consecuencia de diseño, y es la que gobierna este brief:** no hay contrato
desplegado ni historia que proteger. La pregunta no es *"cómo agrego bodega sin
romper lo que corre"* sino **"cuál es el diseño correcto antes del primer
despliegue"**.

### Y hay un conflicto de integración que va primero

Las dos ramas tienen un `0003` **distinto**, los dos con padre `0002`, y el `0004`
de materiales depende del de Campo:

```
despliegue:  0003_alter_asignaciontrabajo_rol     ← padre 0002
campo:       0003_campos_de_despacho              ← padre 0002
             0004_...materiales                   ← depende de 0003_campos_de_despacho
```

Django ve dos hojas en el grafo de la app `campo` y se niega a migrar hasta que
alguien escriba una migración de merge o renumere. **Es la primera tarea, antes
de una línea de inventario.** (Inferido del comportamiento estándar de Django, no
ejecutado: se confirma con `makemigrations --check` sobre las dos ramas
fusionadas.)

**Decidido: migración de merge, no renumerar** — conserva la historia de las dos
ramas. Y se midió que es viable, porque la pregunta que decide un merge es si las
dos hojas tocan lo mismo:

```
0003_alter_asignaciontrabajo_rol   AlterField  asignaciontrabajo.rol
0003_campos_de_despacho            AddField    ordentrabajo × 9 campos
                                               (prioridad, zona, resumen,
                                                ventana_inicio/fin, sla_vence_en,
                                                cliente_id_abonado,
                                                cliente_detalle_acceso,
                                                requisitos_seguridad)
```

**Modelos distintos, cero colisión.** El merge las conserva las dos y las aplica
en cualquier orden. La hoja de merge depende de `0003_alter_asignaciontrabajo_rol`
y de `0006`, no de las dos `0003`, porque el `0004` de materiales ya cuelga de
`0003_campos_de_despacho`.

## 4 · El agujero, y el diseño acordado

### Lo que falta, medido

```
entidades de bodega / almacén / existencia / stock / proveedor / compra    0
endpoints para CREAR una EntregaDeKit (KitView solo tiene `get`)          0
lugares del backend que instancien EntregaDeKit fuera de las pruebas      0
modelos de materiales registrados en el admin de Django                   0
   (admin.py registra 4 modelos: ninguno de materiales)
pantallas web de bodega, despacho o materiales                            0
   (31 rutas en routes/(app)/, ninguna de campo)
rol de bodeguero                                                          0
   (permissions.py:9 → ROLES_GESTION = {"ADMIN","SUPERVISOR","OPERACIONES"})
```

Nadie puede entregarle un kit a un técnico hoy. El material devuelto no vuelve a
ninguna parte: `saldo_de` se lo resta al técnico y ahí termina el rastro.

### Un solo libro, con origen y destino

Descartada la capa paralela (`InventarioBodegaMovimiento` junto a
`MovimientoDeMaterial`, con el despacho como puente): son dos libros, y cada
transferencia pasa a ser una reconciliación entre dos verdades. El día que una
escritura entre y la otra no —transacción cortada, reintento offline, error en la
segunda— bodega dice 10 y el técnico dice 9, con el agravante de que el puente es
el punto más concurrido del sistema.

`MovimientoDeMaterial` se extiende en su lugar:

```
MovimientoDeMaterial  (hoy)            →   (con ubicaciones)
  tipo: consumo|devolucion|ajuste          tipo: + entrada|despacho|traslado|baja|retiro
  profile  (el técnico)                    ubicacion_origen   → FK UbicacionInventario (nullable)
  orden    (en qué trabajo)                ubicacion_destino  → FK UbicacionInventario (nullable)
  material · cantidad · serie              (el resto igual: estado, idempotency_key,
  estado · idempotency_key                  ocurrido_en, motivo, motivo_tecnico)
  ocurrido_en · motivo · motivo_tecnico
```

Y una existencia sola, para cualquier ubicación:

```
existencia(ubicación, material) = Σ movimientos con destino = ubicación
                                − Σ movimientos con origen  = ubicación
```

`saldo_de(técnico)` pasa a ser un caso particular de esa función, no otro
cálculo. Un solo lugar donde puede estar mal.

`EntregaDeKit`/`ItemDeKit` dejan de ser la fuente del saldo y pasan a ser lo que
su nombre dice: **el acta** que agrupa un despacho y que alguien firma — igual que
`ActaDeDevolucion` agrupa el retorno. Los movimientos son la verdad; las actas
son el documento.

### Cuatro consecuencias que hay que decidir explícitamente

**1 · La entrada es el único movimiento sin origen.** No inventes una ubicación
`PROVEEDOR` para no admitir un `null`: el proveedor es de la Fase 3, y una
ubicación ficticia es una entidad creada para esquivar una frontera real. El
sistema tiene dos fronteras y las dos son nulls legítimos: **entra** material sin
origen interno, y **sale** material sin destino interno.

**2 · El cliente NO es una ubicación de inventario.** La cadena «técnico →
cliente» es tentadora y es una trampa: si `CLIENTE` es una ubicación con
existencias, alguien va a preguntar *"¿qué hay en el cliente 1001?"* y eso es una
pregunta de WispHub (§6), no de Dexter. `MovimientoDeMaterial` **ya tiene** el
campo `orden`, y una orden apunta al cliente: el consumo con su orden ya es la
salida de custodia, con más información que una ubicación. Las existencias se
calculan solo para ubicaciones internas (bodega, vehículo, técnico).

El retiro de una ONT en un cliente que canceló es el caso simétrico: **una entrada
sin origen, con la orden de retiro como justificación**. No una salida del cliente.

**3 · El ajuste deja de tener signo ambiguo.** Hoy `saldo_de` lo suma (`+ ajustado`),
lo que obliga a que un ajuste negativo se guarde con cantidad negativa. Con
origen/destino el signo lo da la dirección del movimiento y la cantidad es
siempre positiva. Es menos lugar donde equivocarse.

**4 · Un despacho de 12 líneas son 12 movimientos, y cada uno necesita su clave
idempotente estable.** El invariante del proyecto es explícito: *"una clave nueva
por intento es un identificador único, no una clave idempotente"*. La clave se
deriva del acta y la línea, nunca de un uuid generado al enviar.

## 5 · El activo serializado, y la única garantía que la base no puede dar

Una ONT no es un texto: es un activo con historia. Hoy `serie` es un `CharField`
en tres tablas distintas y no hay ninguna entidad que represente *ese aparato*.

La entidad correcta es **solo identidad**:

```
ActivoSerializado
  org · material · serie      (único)
  fecha_alta · garantia
```

Nada de `estado` ni `ubicacion_actual`: los dos son función del último movimiento
de esa serie, y guardarlos repite exactamente el error que la decisión §2.1 ya
descartó — con el agravante de que una ONT instalada sin señal es justo el
movimiento que llega ocho horas tarde.

### La parte difícil, y es la más importante del diseño

El criterio **A4 — una serie no puede estar en dos manos a la vez** no se puede
expresar como un `UniqueConstraint` de Postgres. El constraint actual lo intenta y
falla en la dirección contraria (§7). La propiedad real es temporal: *una serie no
puede tener dos salidas consecutivas sin una entrada en medio*, y eso es una
invariante sobre una secuencia, no sobre una fila.

Hay dos caminos:

| Camino | Qué da | Qué cuesta |
|---|---|---|
| Validar en código dentro de la transacción, con `SELECT FOR UPDATE` sobre el activo | Correcto, y nada se guarda de más | La garantía sale de la base y pasa al código. Una escritura por otro camino la saltea |
| Una tabla **`UbicacionDeActivo`**: un registro por activo, con `UNIQUE(activo)`, escrita en la misma transacción que el movimiento | La base garantiza A4 de forma declarativa | Hay un dato derivado guardado |

**DECIDIDO: el segundo, con la reconciliación como condición.** No es opcional: sin
la prueba de reconciliación, la tabla es un contador guardado con otro nombre.

Sobre el nombre: se descartó `CustodiaActual` porque *custodia* arrastra
responsabilidad legal y posesión, que son otra discusión. `UbicacionDeActivo` sigue
además el patrón de nombres del módulo —`MovimientoDeMaterial`, `EntregaDeKit`,
`ActaDeDevolucion`, `IncidenciaDeMaterial`— y por eso se prefirió a `PosicionActivo`.

```
UbicacionDeActivo
  activo          → FK ActivoSerializado, UNIQUE
  ubicacion       → FK UbicacionInventario (o null = fuera de custodia)
  movimiento      → FK MovimientoDeMaterial, el que la justifica
  actualizada_en
```

El campo `movimiento` es lo que la hace auditable: cada posición dice de qué hecho
salió. Una fila sin movimiento que la respalde es un defecto detectable.

Guardar un derivado parece contradecir la decisión §2.1, y no la contradice: **un
puntero al presente no es un contador acumulado**. La diferencia importa y conviene
dejarla escrita, porque es la que distingue un diseño consistente de una excepción
conveniente:

```
contador guardado   acumula N operaciones. Un error viejo es invisible y no hay
  (prohibido)       forma de saber cuál de los dos números es el bueno.
puntero al presente guarda UNA referencia: dónde está este activo ahora.
  (aceptable)       Es reconstruible desde el libro, y por lo tanto VERIFICABLE:
                    una prueba recalcula la custodia de cada activo desde sus
                    movimientos y compara. Si difiere, hay un defecto y se ve.
```

Esa prueba de reconciliación es la que hace aceptable el puntero. Sin ella, es un
contador guardado con otro nombre.

## 6 · La frontera con WispHub

El reparto ya rige de hecho, y en la dirección correcta. Medido: `sn_onu` **entra**
al snapshot de la orden (`services/despacho.py:424`) y la app lo muestra
(`trabajo_vista.dart:319` → `serialOnu`). **Nada escribe hacia WispHub.**

```
Dexter controla          material → custodia → técnico → salida de custodia
WispHub controla         cliente → servicio → equipo instalado confirmado
```

Dexter no debe volverse un segundo registro de lo instalado. Pero el reparto tiene
dos casos que no cubre, y los dos son frecuentes:

- **Una instalación nueva llega con `sn_onu` vacío.** No hay contra qué comparar, y
  el único que sabe qué serie quedó en esa casa es el técnico. Ese dato **nace en
  Dexter** y tiene que llegar a WispHub, o el ISP queda con el campo vacío para
  siempre. (`sn_onu` es escribible en la API de WispHub, verificado.)
- **El técnico instaló una serie distinta a la registrada.** Pasa al cambiar un
  equipo dañado. Dos fuentes, dos valores, y ninguna es obviamente la buena.

Para el tránsito entre *"el técnico dice que la instaló"* y *"el ISP lo confirma"*
este proyecto ya tiene el patrón y el nombre — `ACCION_CONFIRMADA`: *el equipo hizo
lo pedido ≠ el cliente tiene internet*. Aplicado acá:

```
la serie salió de la custodia del técnico   ≠   la serie está registrada en el ISP
```

Son dos hechos, se muestran distinto, y el segundo puede fallar sin que el primero
deje de ser cierto. Un estado intermedio —*instalada según el técnico, no
confirmada en el ISP*— no es deuda: es lo que de verdad pasa.

### Cuánto vale este lazo, medido

`sn_onu` **lo tiene solo el 68% de los clientes activos.** Medido el 14/08/2026
sobre los 4.163 activos, con la paginación verificada: 2.864 traen serial y **1.299
lo tienen vacío**. Importa doble, porque `sn_onu` es además la llave contra SmartOLT:
**1 de cada 3 clientes no se puede diagnosticar por ahí.**

O sea que el lazo no es prolijidad de inventario: cada instalación en la que el
técnico registre la serie y Dexter la escriba en el ISP es un cliente que pasa a ser
diagnosticable. Es la justificación más fuerte de todo este módulo.

### Y NO se construye una cola nueva para esto

La tentación es una entidad tipo `CambioEquipoPendiente` con estados
pendiente/confirmada/rechazada. **Ese mecanismo ya existe y está cerrado en código**
—`asistente.operaciones_externas` + `nucleo/relevo/reconciliador.py` + su worker,
con idempotencia por clave, estado `desconocida` y reintento con regla—. Una segunda
cola es un segundo reconciliador que se desincroniza del primero.

Lo que hay que hacer es **un tipo nuevo en la cola que ya está**, y cuesta una
migración de una línea: hoy el esquema tiene el check cerrado
(`202609201000_sincronizaciones_externas.sql:35`):

```sql
check (tipo in ('crear_caso', 'crear_ticket', 'cerrar_caso', 'cerrar_ticket'))
```

**Y hay un hallazgo que mejora su clasificación.** El gate Q2 del proyecto decidió
que `crear_ticket` de WispHub **no es reintentable**: la API no acepta clave de
idempotencia, así que un reintento con resultado incierto crea un segundo ticket.
`crear_caso` sí lo es, pero de forma *artificial* — mete el `conversation_id` en el
nombre para que el duplicado choque.

Escribir `sn_onu` no crea nada: **pone un valor**. Reintentarlo dos veces deja el
mismo estado que una. Es el primer efecto externo de WispHub **naturalmente
idempotente**, y por eso es el caso más seguro de la cola, no uno más:

```
crear_ticket        POST que crea      → no reintentable (Q2, cerrado)
crear_caso          POST que crea      → reintentable por un nombre único forzado
actualizar_sn_onu   escribe un campo   → reintentable por naturaleza
```

Lo único que sigue sin poder prometerse es lo de siempre: si la llamada salió y la
respuesta se perdió, nadie sabe si el tercero la aplicó. Pero acá eso da igual —
volver a escribir el mismo serial es inocuo.

## 7 · El defecto que la falta de bodega ya dejó en el esquema

**Una ONT devuelta no se puede volver a entregar. Nunca.** `ItemDeKit`
(models.py:695):

```python
models.UniqueConstraint(
    fields=["material", "serie"],
    condition=models.Q(serie__gt=""),
    name="unique_serie_entregada_por_material",
)
```

Su propio comentario dice *"una serie no se entrega dos veces **sin haber
vuelto**"*, pero la condición no modela el "haber vuelto": es absoluto. Una serie
puede aparecer en **un solo `ItemDeKit` en toda la historia de la base**. Se le
despacha una ONT a un técnico, el cliente cancela, la ONT vuelve intacta; al
despacharla a otro técnico → `IntegrityError`.

> Inferido de la lectura del esquema, no ejecutado: hoy no hay camino que cree dos
> `ItemDeKit`, precisamente porque no hay despacho. Confirmarlo con una prueba es
> parte del trabajo.

El constraint hermano de `MovimientoDeMaterial` **sí** acotó su condición y por eso
no tiene el problema — `condition=Q(serie__gt="", tipo="consumo", estado="aceptado")`.
Con el diseño del §5 el problema desaparece de raíz: la unicidad pasa a ser
*un activo, una custodia*, que es lo que el comentario siempre quiso decir.

## 8 · Orden de construcción

### Fase 1 — Núcleo de custodia

Cierra el ciclo físico completo, **serializados incluidos**:

```
entrada → bodega → técnico → consumo/instalación → devolución → bodega
```

Incluye: migración de merge (§3), `UbicacionInventario`, `ActivoSerializado`,
`UbicacionDeActivo` con su reconciliación, movimiento único con origen/destino,
despacho con su acta, recepción de la devolución, existencias calculadas, rol de
bodeguero, y **A3/A4**.

La serialización **no** queda para después: la ONT es el activo donde más duele
equivocarse, y una Fase 1 que cierre el ciclo solo para consumibles es una
promesa distinta de la que dice cerrarlo.

Y dos funciones más, que entran en Fase 1 porque el libro único las vuelve casi
gratis y son el valor del módulo:

**La historia de una serie, como pantalla.** Con un solo libro es una consulta
ordenada por `ocurrido_en`:

```
ONT Huawei ABC123
  25/09  entrada a Bodega Central
  26/09  despachada a Juan Pérez        acta K-0412
  27/09  instalada en OT-4521           salida de custodia
  28/09  registro en el ISP: pendiente
```

Es la pregunta que justifica el módulo entero —*"¿quién la tuvo, dónde está, cuándo
salió y por qué?"*— y responderla es la diferencia entre esto y un contador de
conectores.

**El despacho sí se valida antes, y eso no rompe la decisión §2.2.** Antes de
entregar una serie: ¿está libre? ¿está en otra ubicación? ¿tiene un conflicto
abierto? La distinción que lo hace consistente:

```
un consumo   ya pasó en la calle  → se clasifica, nunca se rechaza
un despacho  todavía no pasó: el material está sobre el mostrador
             → es el ÚNICO acto del ciclo que se puede impedir a tiempo
```

Rechazar un despacho imposible no borra ningún hecho: evita que nazca uno falso. Y
sigue siendo cierto que **nada de lo ya ocurrido se bloquea jamás**.

**El inventario por técnico no es una tabla:** es `existencia(ubicación)` con la
ubicación de tipo `TECNICO`. Ya sale del §4 sin código nuevo, y eso es justamente la
prueba de que el libro único era el diseño correcto.

### Fase 2 — Operación

Varias bodegas y traslados · conteo físico con ajuste identificado · reservas
(derivadas de movimientos, nunca un contador) · reportes · el lazo con WispHub
del §6, por la cola que ya existe.

### Fase 3 — Gestión empresarial

Proveedores · compras · costos · valorización. **No antes**: el mismo brief lo
advierte y el riesgo es real — el modo de fallar de este trabajo es volverse un
ERP y perder la filosofía que ya está bien resuelta.

## 9 · Trampas

**1 · `ActaDeDevolucion` congela sus totales al confirmarse, y es deliberado.** Si
el inventario recalcula hacia atrás, va a discrepar con actas viejas — y **el acta
gana**, porque es lo que dos personas firmaron. El inventario tiene que poder
explicar la diferencia, no borrarla.

**2 · `ocurrido_en` ≠ `created_at`.** Un movimiento sin señal llega horas después.
Cualquier corte de inventario "a fecha" tiene que elegir cuál usa, y las dos
respuestas son correctas para preguntas distintas.

**3 · La app trabaja sin señal, y eso alcanza al despacho.** Si la entrega se
confirma en el teléfono del técnico en la bodega, entra a la misma cola offline y
necesita su idempotencia. Si se confirma solo en la web, el técnico puede empezar
la jornada con un kit que su teléfono no conoce.

**4 · Reescribir `services/materiales.py` toca las 10 pruebas de materiales de la
app.** Son el contrato con el teléfono. El §3 dice que no hay datos en producción;
no dice que no haya trabajo.

## 10 · Reglas del proyecto que no se rompen

- **Fail-closed.** Ante la duda, no hay dato. Nunca se inventa un valor por
  defecto ni se rellena un hueco con algo plausible.
- **`django-crm` no habla con WispHub ni con SmartOLT.** No tiene las credenciales
  y no debe tenerlas. Todo dato externo se le pide al motor.
- **RLS por organización.** Toda escritura necesita el contexto fijado
  (`common.tasks.set_rls_context`), o Postgres la rechaza.
- **El motor (`nucleo/`) nunca conoce a un cliente concreto.** Si aparece la
  necesidad de un `if` por empresa, falta un campo de configuración.
- **Idempotencia por clave estable**, derivada de algo durable.
- **Guardar primero, entregar después.** Ninguna transacción de base abierta
  mientras se espera una llamada de red.
- **Afirmar sobre el efecto, nunca sobre la presencia del mecanismo.** Una prueba
  que comprueba que una función existe no prueba que funcione.
- **Distinguir "no se pudo medir" de "se midió y falló".**

## 11 · Qué NO hacer

- **No agregar `disponible` ni `stock_actual`.** El saldo se calcula. La única
  excepción discutida es el puntero de custodia del §5, con su prueba de
  reconciliación.
- **No permitir que un movimiento se edite o se borre.** Corregir es registrar en
  sentido contrario.
- **No rechazar un hecho que ya ocurrió en la calle** para que el inventario
  cuadre. El descuadre visible es el producto, no el error.
- **No absorber una diferencia en un ajuste automático.** Se nombra con su motivo.
- **No crear una ubicación `PROVEEDOR` ni `CLIENTE`** para evitar un `null`
  legítimo (§4).
- **No construir una segunda cola de efectos externos** para el lazo con WispHub.
  Existe una, cerrada en código, con su reconciliador (§6).
- **No bloquear un hecho que ya ocurrió.** La validación previa es del despacho y
  solo del despacho, por el motivo del §8.
- **No convertir esto en un ERP.** Fase 3 existe para eso, y existe al final.

## 12 · Cómo se verifica

```
docker exec <backend> python -m pytest campo/tests/ -q --no-cov
cd apps/tecnicos-mobile && flutter test          # referencia: 536 verdes
py -3.13 cli/correr_pruebas.py --sin-base --sin-red
py -3.13 tests/test_nucleo_sin_tenants.py        # si se toca el motor
```

Las tres pruebas que más importan, en orden:

1. **A4 por reconciliación** — recalcular la custodia de cada activo desde sus
   movimientos y compararla con el puntero. Es la que hace legítimo el §5.
2. **A3** — una serie devuelta se puede volver a entregar. Hoy falla.
3. **Existencia = una sola función** — que bodega y técnico se calculen con el
   mismo código. Es la propiedad que motivó descartar los dos libros, y la única
   forma de que no vuelva por la ventana.

## 13 · El reparto acordado, en una tabla

Dos rondas de revisión lo dejaron acá, y esta es la parte que no se reabre sin una
medición nueva:

| Pieza | Qué es | Qué NO es |
|---|---|---|
| `MovimientoDeMaterial` | La verdad histórica. Append-only, con origen y destino | Nunca se edita ni se borra |
| `ActivoSerializado` | La identidad del aparato: `(org, material, serie)` | No guarda estado ni ubicación |
| `UbicacionInventario` | Bodega, vehículo, técnico. Interna siempre | El cliente y el proveedor **no** son ubicaciones |
| `existencia(ubicación, material)` | Un cálculo, una sola función | No hay columna `disponible` |
| `UbicacionDeActivo` | Un índice verificable del presente | No es fuente de verdad; se reconcilia contra el libro |
| `EntregaDeKit` · `ActaDeDevolucion` | Documentos que dos personas firman | Ya no son la fuente del saldo |
| WispHub | Dueño del equipo instalado confirmado | Dexter no lleva un segundo registro de lo instalado |
| `asistente.operaciones_externas` | La cola del lazo con el ISP, ya construida | No se construye otra |

## 14 · La rama — resuelto: se integra Campo primero

No es una decisión de diseño y por eso está al final. **Decidido el 25/09/2026:**
`feat/campo-diseno-stitch` se integra a la rama de despliegue **antes** de construir
inventario, y la Fase 1 se levanta después sobre un solo terreno. El diseño de este
brief no depende de la rama, así que esperar no cuesta nada.

Los números que llevaron ahí, medidos el 25/09/2026:

```
feat/campo-diseno-stitch  (donde vive el módulo de materiales)
    59 commits adelante de la rama de despliegue
   297 commits ATRÁS
   948 archivos difieren
   y otra sesión está editándola ahora: 12 archivos sin commitear, entre ellos
   campo/urls.py, campo/despacho_views.py y campo/serializers.py
   — los tres que el despacho de inventario necesita tocar
```

Construir ahí choca con esa sesión en los tres archivos exactos. Construir en otra
rama obliga a traer el módulo a una base 297 commits más nueva, y eso es *la
integración de Campo*, que es un trabajo con nombre propio.

Los dos caminos terminaban pagando la misma integración, y uno de ellos sin
decirlo. Por eso se eligió nombrarla y hacerla primero: **la integración de Campo es
ahora un prerrequisito declarado de este trabajo, no una deuda que aparece a mitad
de camino.**
