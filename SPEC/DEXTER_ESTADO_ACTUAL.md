# DEXTER — ESTADO ACTUAL

Autoridad del estado. Quien empieza una sesión lee ESTO, no el historial.
Si contradice a una conversación, gana este archivo.

**Un gate no está cerrado hasta que este archivo lo refleje.** Y se poda cuando
se actualiza: una sección que quedó vieja no es inocua — la siguiente sesión la
lee como verdad. La historia detallada vive en `auditorias/`, no acá.

Última actualización: **28/09/2026 18:28 Bogotá** — la **custodia de materiales** queda
construida en sus TRES FASES y vista en la pantalla. Rama
`feat/inventario-custodia` (worktree `C:/tmp/dexter-inventario`), **sin
pushear**:

```
8851b5e  la bodega existe: el material puede salir y volver
4f70241  la API: despachar, recibir, historia de un aparato
79ee0c8  la pantalla /inventario
fe64c8c  la entrada del menú, y A4 medida con bloqueo real
56fff80  la diferencia al recibir se nombra; la existencia con su guarda
c3fdc10  Fase 2 y 3: reservas, conteo, traslados, compras y valorización
b8f264e  las dos fases en la pantalla: lo libre, lo contado y lo que vale
```

La **Fase 3 se construyó por decisión explícita del usuario**, que levantó la
restricción del brief (*«el modo de fallar de este trabajo es volverse un
ERP»*). Esa advertencia queda escrita en `campo/inventario_operacion.py`.

⚠️ Y una corrección de este mismo archivo: la actualización del 28/09 metió su
sección en `TRABAJO ACTIVO` pero **no cambió esta línea** — el reemplazo buscaba
un texto que otra sesión ya había editado y falló en silencio, así que la
cabecera afirmó el 25/09 durante todo el día 28. Es la tercera vez que este
archivo afirma algo que no verificó quien lo escribió. **Un reemplazo sobre un
documento que otra sesión puede tocar se comprueba después de hacerlo.**

La anterior fue el **25/09/2026 13:57 Bogotá** — la planta del centro de
mando pasa a **salas por área** (`8d9a3d7`) y entra una **propuesta** de planta
radial sin enchufar (`c660474`). Los dos **sin desplegar**. Se remide el mapa de
ramas: producción ya no está donde decía este archivo hace tres horas.

La anterior fue el **25/09/2026 13:44 Bogotá** — se abren dos fichas en
`TRABAJO ACTIVO`: la custodia de materiales, con su diseño congelado, y la
integración de Campo, que es su prerrequisito y está **bloqueada hasta cumplir su
contrato**. Ninguna arrancada; nada de código tocado. El detalle de por qué la
integración es el riesgo y no el diseño está en esa sección.

La actualización anterior fue el **24/09/2026 ~22:05 Bogotá** — deploy de la planta
de oficina (`0925a7e`), su ajuste tras verla (`0c98fa5`) y la remedición del
mapa de ramas. Esa versión es la
**FUSIÓN A MANO** de las dos copias que existían de este archivo — una en
`integrar-centro-mando` y otra en `feature/bandeja-relevo`, editadas las dos
el mismo día, divergidas 252 lineas. No se borró nada de ninguna: se importó
entera la sección `VALIDACIÓN DE PRODUCCION` que solo tenía bandeja-relevo, y
se remidió el mapa de ramas, que estaba mal en las dos.

**Desde hoy este archivo tiene un solo escritor.** La regla y su motivo están
al final, en `UN SOLO DUEÑO DEL ESTADO`. En una línea: dos sesiones arreglaron
el MISMO defecto el mismo día sin saberlo —`DECLARACION_NO_ALCANZA`, en
`6207b9a` y en `4ac7dfb`— y cada una lo anotó en su copia. Un documento de
autoridad con dos escritores no es autoridad: son dos borradores homónimos.

---

## DÓNDE VIVE CADA COSA

**REMEDIDO el 24/09/2026 ~16:30 Bogotá, por contenido y no por hash.**
Esta sección se equivocó dos veces hoy, en direcciones opuestas, y las dos
veces por medir mal. La primera versión decía que nada estaba desplegado
cuando el Centro de Mando ya estaba afuera. La corrección de la mañana dijo
que el upstream era la rama de despliegue y que el trabajo «ya estaba
afuera», y tampoco: el upstream es `origin/integrar-centro-mando`.

Lo que hay que medir es el **contenido**, no la ancestría. Otra sesión tomó
dos commits de esta rama y los puso en producción con otro hash, así que
`merge-base --is-ancestor` los contaba como ausentes estando presentes:

```
git log --format=%H origin/fix/integracion-wisphub..HEAD   -> 19 commits
   comparados por `git patch-id --stable` contra producción:
   2 YA ESTÁN afuera con otro hash   65c8f57 -> 790e185
                                     eb8f503 -> b7cfa90
   17 realmente fuera
git rev-list --left-right --count origin/fix/integracion-wisphub...HEAD -> 2  19
git rev-list --left-right --count origin/integrar-centro-mando...HEAD   -> 2  46
```

`origin/integrar-centro-mando` quedó **detrás** de la rama de despliegue: su
último push es del 23/09 (`5cd47e6`). Por eso los 46 «sin pushear» y los 19
«fuera de producción» no se contradicen — miden contra bases distintas.

~~**Lo que está REALMENTE fuera de producción son 17 commits.**~~
~~Además hay **2 commits en producción que no están acá** (`790e185`,
`b7cfa90`).~~

**Ya no. Remedido el 24/09 21:30: son 3, y están listados abajo.** Los 17
salieron esa misma tarde en dos tandas (`1a83886 → 8d1fbf4` y
`8d1fbf4 → 0925a7e`).

La medición de arriba queda tachada y no borrada a propósito: es la tercera
vez en el mismo día que esta sección afirma un número que deja de ser cierto
en cuestión de horas. **El número envejece; el método no.** Lo que hay que
conservar de este bloque es cómo se mide —`git patch-id --stable` contra la
rama de despliegue, nunca `merge-base --is-ancestor`, que no ve un commit
rebaseado por otra sesión— y no cuántos commits había una tarde cualquiera.

| Rama | Qué tiene | Estado medido |
|---|---|---|
| `integrar-centro-mando` | **Activa, es esta.** Centro de Mando, sistema de trabajo con IA, plataforma multi-ISP | 🟡 **3 commits fuera de producción** (remedido 24/09 21:30) |
| `feature/bandeja-relevo` | Bandeja Fase 1, batería de 41 flujos, validación de producción | 🟡 activa en `C:/tmp/dexter-bandeja`. **NO está congelada** pese a lo que dice la memoria: 3 commits hoy 16:12-16:14 |
| `feat/campo-diseno-stitch` | **Dexter Campo.** 101 archivos de prueba, 551 pruebas | 🟡 activa en `C:/wisphub/_wt_campo`. Una tercera sesión implementa ahí «refrescar ficha» (`test_refrescar_ficha.py`, sin commitear) |
| `fix/integracion-wisphub` | **Producción.** Push ahí ES deploy | `0c98fa5` (24/09 22:0x) — la planta de oficina, ajustada tras verla |

**Los 3 que siguen fuera, remedidos el 24/09 21:30.** No son deuda olvidada:
son trabajo de otra sesión, sin pushear a ninguna parte, y tocan config del
tenant y el motor. Por eso el deploy de la planta se hizo por **cherry-pick de
un solo commit** y no por push de la rama: publicar `tenants/rapilink.config.
yaml`, `cli/cargar_config.py` y `nucleo/modelo/motor.py` sin que nadie lo
decidiera habría sido un deploy de tres cosas disfrazado de uno.

```
78d20b8  Una copia mas vieja que produccion ya no puede escribir la config
f946d84  Un servicio puede decir de quien habla, y la sesion sigue mandando
afd721a  D1 cierra su parte: el CI queda en verde en las dos ramas
```

**REMEDIDO el 25/09/2026 13:57 Bogotá, por contenido (`git patch-id --stable`)
contra `origin/fix/integracion-wisphub`, que está en `8d37f70`.** De 16 commits
locales, **10 ya están afuera con otro hash** y 6 no:

```
FUERA (6):
   afd721a  D1 cierra su parte: el CI queda en verde en las dos ramas
   e957e06  El estado dice que la planta salio, y corrige lo que ya no era cierto
   c017bdb  Ver la pantalla encontro lo que las guardas no podian
   109a550  La integracion de Campo tiene contrato antes de que alguien la fusione
   8d9a3d7  Cada area es una oficina con paredes  (25/09 13:47)
   c660474  Propuesta de planta radial, sin enchufar  (25/09 13:48)

YA DESPLEGADOS, con otro hash (los publicó otra sesión):
   78d20b8 → e1080a1     f946d84 → 6b096af     bea9a8b → 0925a7e
   063d0fa → 0c98fa5     b8cbb85 → 2f14565     29fdb1e → 05ef873
   7566e0b → fab796b     a4985f4 → 76e29bf     c3ec175 → a60cb85
   ea483ed → 8d37f70
```

**Tres de los seis que faltan son documentación de este archivo**; los otros tres
son el CI, el contrato de Campo y el trabajo de hoy.

Es la **quinta** vez que esta sección envejece en dos días. Producción se movió
otra vez: `a60cb85 → 61a7f74 → 8d37f70`, y los tres últimos saltos son de OTRA
sesión (bandeja rediseñada, nombre del cliente, referencia de Stitch). Por quinta
vez el método aguantó y el número no: lo que hay que conservar es la primera línea
de este bloque, no la lista.

### SIN DESPLEGAR — 25/09/2026 13:47 Bogotá — la planta pasa a salas por área

`8d9a3d7`, tres archivos. **No está en producción**: producción sigue mostrando
la planta de puestos sueltos de `a60cb85`.

El agrupamiento por color de piso **no se leía**: en una rejilla diagonal, dos
vecinos de la misma área se ven igual que dos de áreas distintas. Ahora cada área
es una sala con paredes, puerta y cuadros, con los puestos de sus agentes dentro,
y la puerta de entrada del tenant queda sola como principal.

**Lo que costó cada pieza** — todas salieron de mirar la pantalla, no del código:

```
el nombre del área flotaba y no decía de quién era: "FACTURACION" aparecía
  sobre la recepción. Va pintado en el SUELO de su oficina. Para que quepa,
  cada sala reserva una franja libre al frente -- sin ella caía bajo los
  escritorios y se leía "RECEP|ION" partido por un monitor
el cuerpo de letra sale del ANCHO DE SU SALA: con un número fijo (26),
  "ATENCION AL CLIENTE" cruzaba tres oficinas
el cartel del agente recortaba a "SOPORTE TECNICO CLIE..." TENIENDO la pared
  medio vacía al lado. La cuenta: zona útil 56, cuerpo 56/(23*0,72) = 3,4, por
  debajo del mínimo. A 1,24 L la zona útil es 88 y entra a cuerpo 5,3. El sitio
  lo dio mover la PUERTA a la pared izquierda
paredes a 46 y no más: a 62 la pared de la oficina de delante se come a la de
  atrás y "FACTURACION" quedaba en "ATURACION"
el color de área se reparte por POSICIÓN, no por hash del nombre: por hash,
  administración, ventas y atención al cliente salían del mismo gris azulado,
  y entonces el color deja de agrupar, que es para lo único que está
```

**Un archivo se perdió durante el trabajo y hubo que reescribirlo.** Una expresión
regular se comió 370 líneas de `planta.js`, que estaba sin commitear y sin copia.
Se restauró desde la versión commiteada y se reescribió `rejillaDeSalas` a mano.
Dos consecuencias reales, no cosméticas: `rejillaPorGrupos` desapareció (no la
importaba nadie, pero se fue por esto y no por decisión), y `colorDeArea` se
reescribió — de ahí el cambio de criterio del color. **Desde entonces se respalda
fuera del repo antes de tocar un archivo sin commitear.**

```
93 pruebas de src/lib/centro-mando          verdes
docker exec dexter-frontend-1 pnpm check    0 errores en los 3 archivos
                                            (39 del total, todos preexistentes)
que ningún nombre quede recortado           LEÍDO DEL DOM, no a ojo:
                                            cero ocurrencias de "…"
```

### SIN DESPLEGAR — propuesta de planta radial, sin enchufar — `c660474`

Dos archivos nuevos (`planta-radial.js`, `PlantaRadial.svelte`). **Nadie los
monta**: no están en ninguna ruta. Existen para mirarlos al lado de la planta en
uso y decidir.

La puerta de entrada del tenant va al centro y las áreas en anillo alrededor, que
es la topología real del motor: todo el que escribe por un canal público entra por
`rol_de_entrada` y de ahí se deriva. El radio se deriva de que dos salas contiguas
no se toquen, así que el anillo se adapta solo con tres áreas o con nueve.

Nacen de una imagen de referencia que trajo el usuario. **De ella se toman cuatro
cosas, y las cuatro con dato que el payload YA traía**: la ficha pegada a la
oficina, el número grande en la pared, el gráfico en el monitor (los 15 cubos de 2
minutos de `serie`, que no se dibujaban en ningún sitio) y el orquestador al
centro.

**Tres no se toman, y conviene que quede escrito por qué** — es el mismo criterio
que gobierna la animación de esta pantalla:

```
"Calidad 98%"        no existe ninguna métrica de calidad
"Conectado" en verde no hacemos healthcheck a ningún sistema externo. Lo que
                     sabemos es la tasa de fallo de las llamadas que HICIMOS:
                     un sistema caído al que no llamamos hace media hora se
                     vería "Conectado"
cintas de tráfico    el destino de cada derivación vive en tool_calls.parametros
                     y NO sale en el payload. Los pasillos radiales dicen POR
                     DÓNDE se deriva --estructura, que es cierta-- y no cuánto
```

Alguien recorre un pasillo **cuando el motor contó un evento** de un agente de esa
área. No hay figurantes: si en una ventana no pasó nada, los pasillos están
vacíos, y que estén vacíos ES la información.

**Lo que queda pendiente si esta propuesta avanza:** la franja de sistemas
externos no está montada en ella, y animar la derivación de verdad exige que el
motor exponga el área de destino desde `tool_calls.parametros`.

### DESPLEGADO el 24/09/2026 21:2x Bogotá — la planta de oficina

`8d1fbf4 .. 0925a7e`. Un solo commit, siete archivos, 1.273 líneas, todas
altas. Medido **por contenido y no por hash** (`git patch-id --stable`):
`d62a4df6be5f` a los dos lados.

El centro de mando gana una **segunda vista**: una planta isométrica donde
cada agente es un puesto de trabajo. El anillo de discos sigue siendo el de
por omisión y no se tocó — está medido en producción desde esta mañana, y
estrenar la planta como única vista sería cambiar algo que funciona por algo
que nadie miró todavía en la operación real.

**Lo que la planta muestra y el anillo no:** la estructura del tenant, que ya
viajaba en el panorama y no se pintaba en ningún lado — quién atiende al
cliente, quién trabaja para adentro, y por dónde entran las conversaciones.
Para lo último el motor ahora expone `rol_de_entrada`, que vivía en
`config/schema.py:2897` y no salía. **Si un tenant no lo declara, la pantalla
lo dice** en vez de deducirlo: tomar «el primer rol orientado al cliente» es
el error que el 07/09 dejó a un suscriptor sin internet hablando con ventas.

**Por qué se anima tan poco.** Los datos llegan por sondeo cada 12 s
(`lib/centro-mando/eventos.js`), así que no hay tiempo real que animar: lo
único honesto es la diferencia entre dos fotos. El color de estado vira en vez
de saltar, la carga cuenta de un número al otro, y un puesto que ENTRA en
alarma destella una vez — seguir en alarma no dispara nada, o el aviso se
repetiría cada 12 s hasta dejar de avisar. Un sello dice hace cuántos segundos
se leyó. Cero movimiento perpetuo: en un tablero, lo que se mueve siempre deja
de significar.

```
planta.test.js + PlantaOficina.test.js   43 verdes. Render REAL con
                                         svelte/server: no que el componente
                                         exista, sino que dibuje
motor local, reiniciado                  rol_de_entrada: 'cliente_final'
suite del frontend                       979 pasan (936 antes + 43 nuevas).
                                         63 rojos en los MISMOS 17 archivos
                                         de siempre: cero regresiones
docker exec pnpm check                   45 -> 40 errores; 0 de los archivos
                                         nuevos
test_nucleo_sin_tenants                  verde
test_registro_sin_pii                    verde (lo pidió el pre-commit)
test_timeouts_modelo · test_editor_config verde
```

**Dos defectos los encontraron las guardas, no mirar la pantalla.** Vale
anotarlos porque son el argumento entero a favor de correrlas:

```
{@const} suelto en el marcado NO COMPILA en Svelte. El componente no se
  habria renderizado nunca, y `pnpm check` lo caza; abrir la pantalla, no.
el nombre del area se recortaba TENIENDO SITIO: cuerpoQueCabe() devuelve el
  cuerpo exacto para que entre, y rehacer esa division en recortar() daba
  14,999 en vez de 15. Lo caza la prueba de render, no la vista.
```

### AJUSTADA el 24/09 22:0x tras VERLA en producción — `0925a7e .. 0c98fa5`

Se abrió la pantalla y salieron dos defectos que ninguna guarda podía cazar,
porque las dos eran sobre lo que se VE y no sobre lo que el código afirma.
Vale escribirlo así: el bloque de arriba dice que las guardas encontraron dos
defectos que mirar no habría encontrado; este dice lo contrario, y los dos son
ciertos. **Ninguna de las dos formas de verificar sustituye a la otra.**

```
la planta usaba el 57% DEL ANCHO, con el lado derecho vacio y los nombres
  diminutos. No era el margen ni el reparto de columnas: un rombo isometrico
  tiene SIEMPRE la relacion de su elevacion --1.48:1 a 34 grados-- y un
  monitor ancho ronda 2:1. Ningun reparto lo arregla, porque el bounding box
  depende de (cols-1)+(filas-1) y 4x2 mide lo mismo que 3x3.
  -> la elevacion tambien se deriva del lienzo ahora. Medido sobre 1240x600
     con 8 agentes:   fija a 34  escala 1.18 -> 57% del ancho
                      derivada   escala 1.42 -> 74%  (elige 26 grados)
     El piso son 26 aunque 22 diera 86%: mas plano, los puestos se ven desde
     arriba y deja de leerse como una oficina.

la leyenda del ANILLO se mostraba en la planta, describiendo un dibujo que no
  estaba: "el grosor es la carga que pasa por esa via" y "punteada: sin
  trafico ahora" sobre una pantalla sin una sola via.
  -> solo sale con el anillo. La planta ya traia la suya: las zonas.
```

Verificado: 46 verdes en las pruebas de la planta (3 nuevas), 982 en la suite
(979 + 3), 63 rojos en los MISMOS 17 archivos, `pnpm check` 40 errores en 29
archivos y ninguno de los tocados.

⚠️ **LO QUE NO SE VERIFICÓ EN EL PRIMER DEPLOY, y se cerró en el segundo:** el
texto de abajo quedó obsoleto en una hora — la pantalla SÍ se vio, y de ahí
salieron los dos defectos de este bloque. Se conserva porque describe un
bloqueo que sigue vigente para la próxima pantalla que se construya.

⚠️ **LO QUE NO SE VERIFICÓ, y hay que cerrarlo mirando:** ningún píxel de esta
vista se vio renderizado en un navegador. El dev server redirige a `/login` y
entrar exige un JWT del backend — el mismo bloqueo que este archivo ya
registra como *QA visual 🔴 NO EJECUTABLE*. Se sustituyó por pruebas que
afirman sobre el HTML producido, que es más que compilar y menos que mirarlo.
Queda pendiente: abrir `/centro-mando` en producción y pulsar **Planta**.

**Saltado, diciéndolo:** los casos dorados (`cli/evaluar.py`) no corrieron —
este cambio no toca prompt, catálogo ni modelo. Tampoco pasó por
`auditor-independiente` ni `revisor-de-pii` como agentes; se corrió la guarda
de PII a mano en su lugar.

### DESPLEGADO el 24/09/2026 17:0x Bogotá — y verificado en la pantalla

`790e185 .. 1a83886`. Salieron los 28 commits del día: la plataforma multi-ISP,
el sistema de trabajo con IA (CLAUDE.md, 9 agentes, 4 comandos, `pre-commit`,
CI), el entorno local aislado, `DECLARACION_NO_ALCANZA` clasificado en los tres
guardas, la medición de TR-069 y el extracto en la ficha del agente.

**La verificación que cierra la plataforma multi-ISP, y por qué vale:**

```
Centro de Mando en produccion, tras iniciar sesion:
  insignia            RAPILINK
  panorama            126 activas, 8 agentes, 110 conversaciones hoy,
                      528 herramientas, grafo completo
```

No es «se ve lindo». `(app)/centro-mando/+page.server.js` tiene **una sola
fuente** para el tenant —`tenantDeLaSesion(locals, fetch)`— y si devuelve
`null` la pantalla no pinta el panorama: devuelve `panorama: null` y el texto
«Asistente no configurado». No hay default y no hay camino alternativo. Que se
vea el grafo prueba que el motor contestó `/tenant-de-organizacion/<org>` con
`rapilink`, o sea que **la empresa ya no sale de una variable de entorno: sale
de quién inició sesión**. Es la propiedad entera de PRD §8.13, medida en la
pantalla y no en una prueba.

**El riesgo de orden de contenedores no se materializó.** Se esperaba una
ventana en que el frontend levantara antes que el motor y las pantallas
salieran vacías (falla cerrada, sin fuga). No pasó.

**CERRADO el 24/09/2026 por la noche: ya no queda ninguna.** Los últimos 9
archivos que leían `env.PRIVATE_ASISTENTE_TENANT` resuelven la empresa con
`tenantDeLaSesion`, y el puente `tenantDeLaInstalacion()` se borró — existía
con fecha de vencimiento escrita en su propio docstring.

```
ningun archivo de src/ lee env.PRIVATE_ASISTENTE_TENANT
    guarda: src/lib/server/v2/tenant.test.js, hermana de
            tests/test_nucleo_sin_tenants.py. Recorre src/ y FALLA NOMBRANDO
            el archivo culpable. Comprobada al reves antes de darla por
            buena: se metio una violacion a proposito y la cazo por su ruta.
pnpm vitest run   936 pasan. Los 63 rojos son los MISMOS 17 archivos que ya
                  fallaban en produccion --medido contra un worktree en
                  790e185--: cero regresiones.
pnpm check        40 errores en 29 archivos. La linea base eran 43 en 30.
```

Lo caro no fue reemplazar la lectura: fue que `locals` llegue a donde hace
falta. La acción `invite` de `team` no lo recibía, y `guardia()` de los tres
proxies era síncrono llamando a `cfg()`, así que los dos cambiaron de firma.
Por eso se hizo a mano archivo por archivo: una sustitución por regex ya
rompió ocho archivos antes, exactamente por esto.

~~**Esta versión NO está desplegada.** Producción sigue en `1a83886`.~~
**Corregido el 24/09 21:30: SÍ está desplegada.** Producción pasó por
`1a83886 → 8d1fbf4 → 0925a7e` esa misma tarde. La frase tachada se quedó
vieja en cuestión de horas, que es exactamente el riesgo que este archivo
tiene por construcción — se deja tachada, y no borrada, porque la siguiente
sesión merece ver que se midió mal y cuándo.

⚠️ Ruido esperado y ya explicado, para que la próxima sesión no lo investigue
de nuevo: al reiniciar el frontend aparecen `Token refresh failed ... 401` en
su log. Es una cookie `jwt_refresh` ya gastada —`ROTATE_REFRESH_TOKENS` +
`BLACKLIST_AFTER_ROTATION`, o sea un solo uso por token— de una pestaña
abierta desde antes del despliegue. Ninguno de los 28 commits toca
autenticación, JWT ni `settings.py`; `hooks.server.js` no cambió una línea.
Solo preocupa si es continuo y para todos JUSTO DESPUÉS de iniciar sesión:
eso sería `SECRET_KEY` cambiada, que invalida todo lo emitido.

### El CI encontró tres defectos en su primer día, y los tres eran suyos

24/09/2026, primeras corridas reales de `.github/workflows/pruebas.yml`.
Ninguno era un bug del producto: los tres eran del andamiaje de pruebas, que
es exactamente lo que un CI nuevo tiene que sacar a la luz primero.

```
1  test_ledger_checksum preguntaba `shutil.which("docker")` -- "esta docker
   instalado" -- cuando lo que necesita es la IMAGEN. El runner de GitHub SI
   trae docker, asi que entraba al bloque y corria `docker run
   dexter-backend:latest`, que en CI nunca se construye. ROJO afirmando algo
   que no habia medido.

2  La misma prueba compara contra el blob de un commit FIJADO (f60beda) como
   referencia dorada. `actions/checkout` clona con profundidad 1, asi que ese
   commit no existia: `git show` devolvia vacio y decia "el hash no cuadra"
   cuando la verdad era "no hay con que compararlo".
   Arreglado por los DOS lados: `fetch-depth: 0` en el workflow, y la prueba
   salta ESA comprobacion --siguiendo con la del arbol, que si puede medir--.

3  cli/correr_pruebas.py tomaba la ultima linea no vacia como motivo del
   fallo. Estas pruebas cierran con una barra de separacion, asi que el CI
   reporto un fallo cuyo motivo era "=========". Ahora busca hacia atras la
   primera linea que explique algo.
```

**Los tres son la misma falta: «no se pudo medir» presentado como «fallo».**
Es un contrato congelado de este proyecto, incumplido dos veces en una tarde
por las propias guardas. Que lo encontrara el CI y no una persona es el
argumento entero a favor de haberlo construido.

Los tres se comprobaron **en los dos sentidos**: con la imagen y la historia
presentes siguen verdes; sin ellas saltan nombrando lo que falta. Una guarda
que solo se ve pasar no prueba que detecte nada.

**CI EN VERDE, en las dos ramas.** `92 en verde · 0 en rojo · 54 sin correr`
(local: 94 y 0 — la diferencia son dos que en el runner no se pueden medir).

Los 2 rojos que quedaban tampoco eran bugs del producto: eran pruebas
atrasadas respecto de mejoras reales.

```
test_asignacion_escritores   exigia que 'resolver' escribiera la asignacion.
                             Existe, pero desde 4251dfd es un envoltorio de
                             una linea sobre cerrar(): ya no escribe. Exigirlo
                             era exigir lo contrario de lo que la prueba
                             defiende. Y marcaba un print de revision_g8 como
                             escritura: falso positivo anotado ANCLADO AL
                             TEXTO de la linea, no perdonado por ruta.

test_guarda_alineacion_git   los 17 casos fallaban por UNA causa: la guarda
                             gano una tercera condicion (avisar si falta
                             RAMA_DESPLIEGUE) despues de que la prueba se
                             escribiera con dos. Hasta "0 adelante y 0 atras
                             -> sin problemas" salia rojo.
                             Se aislo la logica Y se escribio el escenario que
                             faltaba: arreglar los 17 sin cubrir esa condicion
                             habria cambiado 17 falsos rojos por un verde que
                             tampoco significaba nada.
                             Siete casos mas exigian frases literales que
                             habian cambiado; ahora afirman sobre el DATO
                             --cuantos commits--, que es la regla de §6 que
                             estaban incumpliendo.
```

**El patron del dia: cinco defectos encontrados, los cinco del andamiaje y
ninguno del producto.** Tres eran «no se pudo medir» presentado como «fallo»;
dos eran pruebas afirmando sobre la redaccion o sobre expectativas vencidas.
Es lo que saca a la luz un CI recien encendido sobre un proyecto que corria
sus guardas a mano: primero, el estado de las guardas.

**Lo que sigue abierto de D1:** las 54 que piden Postgres no corren en CI.
Falta un servicio de base en el workflow.

### 25/09/2026 — el CI gana una tercera categoría: ROJO DECLARADO

```
MEDIDO el 25/09/2026 15:30 Bogotá, local, `--sin-base --sin-red`, 127s:
   92 en verde · 2 en rojo · 1 en ROJO DECLARADO · 54 sin correr · exit 1
```

⚠️ **Los 2 en rojo NO son el declarado y no son de este trabajo.** Esta sección
decía «CI EN VERDE, 0 en rojo» y con esta medición deja de ser cierto:

```
test_centro_mando.py         TypeError: '>' not supported between instances of
                             'NoneType' and 'int'
test_m06e_consolidacion.py   FaltaIdentidadEnSesion: 'ping_cliente' necesita
                             ['id_servicio'] de la sesion verificada
```

### `test_centro_mando.py` — ROJO REAL, y el Centro de Mando está desplegado

⚠️ La primera versión de este bloque dijo que era *probablemente «no se pudo
medir» presentado como fallo, por estar mal clasificada*. **Esa hipótesis se
midió y es falsa**, y se corrige acá en vez de borrarse porque el error de
razonamiento vale más que la conclusión: la prueba **no toca la base** — define
sus `totales` a mano (línea 113) y golpea el endpoint con el cliente de test. Que
esté mal clasificada es cierto como hecho y **no** es la causa de su rojo.

Lo que de verdad falla, corrido a mano:

```
[FALLA] el agente con error nombra la herramienta que fallo
[FALLA] el que procesa nombra la herramienta en curso
[FALLA] el disponible lo dice sin inventar actividad
[FALLA] 'agentes con trabajo' cuenta los mismos que muestran las tarjetas
        la franja dice None y hay 0: []
TypeError: '>' not supported between 'NoneType' and 'int'   (linea 214)
```

`totales.get("agentes_activos")` llega **`None`**: el endpoint dejó de devolver
ese campo. Y el comentario de la propia prueba dice que ese contador ya se rompió
una vez, por lo mismo:

> *"Nace de un error real: al renombrar los estados, este conteo se quedo
> buscando 'procesando' y 'atendiendo'. Nadie lo vio hasta abrir la pantalla en
> produccion y leer '0 agentes con trabajo' sobre tres tarjetas activas."*

**El Centro de Mando está en producción, y el código que falla es EL MISMO que
está afuera.** Medido contra la rama de despliegue:

```
tests/test_centro_mando.py     0 líneas de diff
nucleo/canales/api.py          0 líneas de diff
```

No es una regresión de esta rama ni de nadie que trabajara hoy: es un defecto que
ya estaba cuando esta sección declaró «CI EN VERDE, 0 en rojo». **Hay que mirarlo
con la pantalla delante**, porque el síntoma que la prueba nació para cazar es
justamente el que no se ve solo: un cero falso no obliga a investigar como lo
haría un «no disponible».

Lo que la prueba dice y **no** se terminó de diagnosticar: la respuesta llega sin
`agentes` ni `totales` —de ahí el `None`—, o sea que la petición falla antes de
armarlos. El endpoint SÍ calcula `agentes_activos` (`api.py:3666`), así que el
problema está aguas arriba, en la resolución del pedido. Queda ahí a propósito:
seguir era abrir otro frente, y este trabajo era otra cosa.

`test_m06e_consolidacion.py` queda sin diagnosticar: no importa `db` y su
`FaltaIdentidadEnSesion` no se investigó.

**Y aparte, `clasificar()` sí tiene un defecto propio**, aunque no explique estos
rojos: decide leyendo el texto del archivo, así que una prueba que llega a la
base por un import (`test_centro_mando.py` importa `nucleo.persistencia.db`) se
clasifica como aislada. Mirar los imports, no solo el texto.

Ninguno de los dos se arregló acá: son de otra familia, y confundirlos con el
rojo declarado es lo que esta sección existe para evitar.

El exit 1 de la corrida viene de esos dos, **no** del rojo declarado: el
declarado da exit 0 por sí solo, medido.

Commit `29ddcf4`. `cli/correr_pruebas.py` distinguía **FALLO** de **NO SE PUDO
CORRER**; sin esta tercera, una guarda que caza un defecto **abierto** entraba al
resumen como rojo puro, indistinguible de una prueba que alguien olvidó
actualizar — y un CI donde no se sabe cuál rojo es el conocido deja de ser una
señal: la sesión siguiente aprende a ignorarlo entero.

La regla de entrada es estrecha a propósito, para que no se vuelva un cajón:
**solo entra un rojo que señala un defecto real con su ficha.** Una prueba
atrasada respecto del código no entra — esa se arregla. Comprobada en las tres
direcciones, y la tercera es la que importa: cuando un rojo declarado **pasa**, el
corredor avisa que hay que sacarlo de la lista. Sin eso, la anotación envejece —
que es exactamente el defecto que la prueba de abajo persigue, un nivel arriba.

**El rojo declarado de hoy:** `tests/test_system_identidad_no_queda_obsoleto.py`.

Los cuatro mensajes `system` que el motor arma dentro de `if not historial`
(`nucleo/modelo/motor.py:3144`) se escriben **una vez, en el primer turno**, y
nada los invalida cuando el estado que describen cambia. Medido: una conversación
que arranca sin verificar y se verifica después arrastra para siempre *"Este
cliente TODAVIA NO esta verificado: no sabes quien es, no tienes su cuenta
ubicada y no conoces su servicio"* — con `sesion.verificado` ya en `True`. Dos
conversaciones que desde afuera están las dos verificadas reciben instrucciones
**opuestas**. Corre sin base y sin red.

**Un `system` no es memoria: es una instrucción vigente.** Si afirma un estado
que puede cambiar, en algún momento miente, y el modelo no tiene con qué saber
cuál de los dos mundos es el de hoy.

Lo que está **medido** y lo que está **reportado**, que no es lo mismo:

```
MEDIDO acá    la contradicción existe (exit 1, sin base ni red)
              el patrón de invalidación YA existe en el código: api.py:1754
              hace `pop` de INSTRUCCION_REENCAUZAR, y el comentario de al lado
              describe el defecto general sin saberlo
              inventario de los 14 puntos que inyectan un system, congelado en
              la prueba: uno nuevo la hace fallar y obliga a declarar si
              envejece
REPORTADO     que este tipo de señal degrade el RUTEO. Viene de otra sesión de
              la investigación y NO se midió acá. La contradicción de estado y
              la degradación del router son dos fenómenos distintos
```

**Falta una sola medición para la ficha:** A/B/C contra el modelo con N≥5
(`C:\tmp\abc_router_con_modelo.py`), sobre la traza y no la redacción. Hoy está
probado que la contradicción **existe**; falta **cuánto mueve la decisión**.
`B 3/5` sería efecto con muestra corta, no refutación.

El diseño ya acordado y su restricción económica están en
[briefs/restriccion-estado-vs-prefijo-cacheado.md](briefs/restriccion-estado-vs-prefijo-cacheado.md)
(`493444e`, `ef26b32`, `cac3bdc`): instrucciones estables arriba y cacheables,
estado operativo abajo y recalculado. **Regenerar el `system` en cada turno
invalida el caché de prefijo**, y eso cuesta entre 4 y 8 veces la factura —
ninguna guarda del proyecto mira el costo, así que ese cambio pasaría el CI
entero en verde. Ese brief lleva también las **cuatro regresiones de producción**
que el bloque de identidad evita (R1–R4, agosto y septiembre 2026), como
criterios que la ficha hereda: el objetivo **no** es «eliminar los mensajes
system de identidad» sino que dejen de afirmar un estado vencido.

### Qué hay en producción, con fecha

Importado de la copia de `feature/bandeja-relevo`, que lo tenía y esta no.
Es la evidencia de los despliegues del 23/09 — no se pierde en la fusión.

```
23/09/2026, push a fix/integracion-wisphub (= deploy):
  00407ac  el aviso del reencauzamiento no llegaba al modelo
  0b27263  el embudo de identidad se puede medir  (+ migracion 202609231445)
  969e7b9  privacidad de la observabilidad del frontend
  49d9318  la pestaña abierta antes del deploy se recupera sola
  055d1a2  franja horaria en el prompt, y motivo de escalada obligatorio
  ee4563f  Centro de Mando (12:29)

y en la base de producción ese mismo día:
  config v150 -> v154   descripcion de derivar_a_area, por el editor versionado
                        (nucleo/config/editor.py), UN CAMPO POR VEZ. Nunca con
                        --forzar: ese sube el documento completo.
  migracion             202609231445_identidad_eventos.sql aplicada. Ledger en
                        0 pendientes, 0 checksums distintos.

24/09/2026:
  b7cfa90  el tablero se mira de lejos y se lee de un vistazo   (11:55)
  790e185  el tablero no cabia donde de verdad se mira          (15:35)
                        ^ los dos son commits de `integrar-centro-mando`
                          rebaseados y pusheados por otra sesion.
```

⚠️ **Tres frentes activos a la vez, y hoy se cruzaron tres veces:**

1. Dos sesiones arreglaron **el mismo defecto** sin saberlo —
   `DECLARACION_NO_ALCANZA`, en `6207b9a` (esta rama) y en `4ac7dfb`
   (bandeja-relevo). Dos arreglos del mismo bug, en dos ramas.
2. Dos sesiones editaron **este archivo** el mismo día, y las dos copias
   divergieron 252 líneas. Esta versión es la fusión a mano de las dos.
3. Una sesión **rebaseó y pusheó** dos commits de esta rama sin avisar. El
   trabajo salió bien, pero el hash local ya no existe afuera, y eso es
   exactamente lo que hizo fallar la medición por ancestría.

Ninguno de los tres es un error de código. Los tres son el mismo error de
coordinación, y la regla del final existe para eso.

### Cómo se resuelve el cruce de `DECLARACION_NO_ALCANZA` al fusionar

Medido el 24/09 comparando las dos ramas archivo por archivo: **los dos
arreglos son semánticamente idénticos.** No hay que elegir cuál está bien;
hay que deshacer un conflicto de texto. Va escrito acá para que quien
fusione no lo decida a ojo:

```
nucleo/modelo/motor.py          ambos agregan "DECLARACION_NO_ALCANZA" al
                                MISMO frozenset (CODIGOS_DE_BLOQUEO), en la
                                misma posicion. Conflicta el COMENTARIO, no el
                                codigo. -> quedarse con uno, da igual cual.
nucleo/seguimiento/forzado.py   ambos lo agregan al MISMO set
                                (CODIGOS_MOTOR_GUARD). Verificado leyendo a
                                que set pertenece cada linea, no por cercania
                                visual. -> idem.
+page.svelte  (linea 138)       aca SI hay una decision: el texto que ve el
                                usuario es distinto.
                                  integrar-centro-mando:
                                    "lo que el cliente reporto no corresponde
                                     a esa accion"
                                  bandeja-relevo:
                                    "la accion no corresponde a lo que el
                                     cliente dijo que le pasaba"
                                Dicen lo mismo. -> elegir uno y borrar el otro;
                                dejar los dos duplica la clave del objeto.
tests/test_escalada_forzada.py  SOLO integrar-centro-mando. Agrega el codigo
                                al set GATES de la prueba. No conflicta, y es
                                el lado que hay que conservar: es la guarda.
```

La prueba de que el lado de esta rama queda verde:

```
py -3.13 tests/test_escalada_forzada.py     -> exit 0
   "Todo en orden: lo que obliga a escalar no depende del modelo."
```


## TRABAJO ACTIVO

### Abierto el 25/09/2026 — custodia de materiales, y su prerrequisito

Dos fichas nuevas. El diseño está cerrado, y la primera **ya está construida**.

```
Custodia de materiales   🟢 CONSTRUIDA Y VISTA EN LA PANTALLA (28/09/2026).
                            Rama feat/inventario-custodia, worktree
                            C:/tmp/dexter-inventario. SIN PUSHEAR.
                            8851b5e  la bodega existe
                            4f70241  la API: despachar, recibir, historia
                            79ee0c8  la pantalla /inventario
                            fe64c8c  la entrada del menú y A4 en Postgres
                            56fff80  la diferencia al recibir se nombra, y la
                                     existencia queda defendida por su guarda
                            Ficha: objetivos/custodia-de-materiales.md
                            Brief del diseño (v3): briefs/inventario-de-bodega.md
                            Lo que la motivó, medido: el módulo de materiales de
                            Campo tenía 8 entidades y 5 endpoints y NO tenía
                            bodega -- 0 entidades de existencia, 0 endpoints para
                            crear una EntregaDeKit, 0 pantallas, 0 rol de
                            bodeguero. Nadie podía despachar material.
                            Ahora el ciclo cierra: entrada → bodega → técnico →
                            devolución → bodega, con UN libro de movimientos que
                            lleva origen y destino. La existencia de cualquier
                            ubicación sale de la misma resta, así que el saldo de
                            un técnico es un caso particular y no otro cálculo.
                            EL BLOQUEO SE QUITÓ SIN TOCAR LA RAMA DE CAMPO: el
                            worktree salió de producción al día y se trajo sólo el
                            módulo `campo/`. La otra sesión siguió con su rama
                            intacta. Ver la ficha de integración, abajo.

                            LO QUE ENCONTRÓ AL CONSTRUIRSE, y ninguna prueba
                            había cazado -- todos medidos, todos arreglados:
                              el constraint de ItemDeKit hacía IMPOSIBLE
                                re-despachar una serie devuelta. Estaba anotado
                                como "inferido de leer el esquema"; ahora está
                                EJECUTADO: IntegrityError reproducido por la
                                prueba A3
                              la clave idempotente no cabía en su varchar(128)
                                --cuatro UUID, ~134 caracteres-- y las pruebas
                                pasaban porque corren sobre SQLite, que no impone
                                la longitud. PostgreSQL real: DataError
                              A4 se comprobaba SECUENCIALMENTE, y depende de un
                                select_for_update que SQLite no implementa: la
                                suite podía estar verde con la carrera abierta
                              tres defectos del frontend que sólo se vieron
                                ABRIENDO la pantalla: endpoints con /api doble
                                (404), `locals` en vez de `{cookies}` (token
                                vacío, toda lectura fallaba en silencio), y el
                                nombre de una custodia saliendo como UUID
                            Dos veces el mismo patrón: EL MOTOR DE LA PRUEBA NO ES
                            EL MOTOR DE PRODUCCIÓN. Por eso hay una prueba que
                            afirma sobre el LÍMITE del campo y no sobre el motor,
                            y otra que se SALTA nombrando el motivo cuando no hay
                            Postgres.

                            Verificado:
                              34 pasan contra PostgreSQL real (ciclo 17 + api 12
                                 + una-sola-verdad 4 + concurrencia 1), con
                                 TEST_DATABASE_URL
                              273 pasan · 6 skipped · 0 fallan, campo/tests/
                                 entero sobre SQLite
                              la pantalla, MIRADA con JWT contra el backend local:
                                 Bodega Central   960 conectores · 6 ONT ·
                                                  3700.75 m de fibra
                                 Custodia de Marcador   40 · 0 · 300.25
                                 Camioneta 1      sin movimientos
                                 la ONT devuelta volvió a la bodega, y la consulta
                                 de su serie da cuadra_con_el_libro: true
                              la entrada en el menú: Instalaciones · INVENTARIO ·
                                 Base de conocimiento

                            FASE 2 Y 3, construidas el 28/09 (`c3fdc10`,
                            `b8f264e`). La 3 por decisión explícita del
                            usuario, que levantó la restricción del brief --
                            «el modo de fallar de este trabajo es volverse un
                            ERP»--; la advertencia queda en el módulo.
                              Fase 2  reservas con plazo que se vence solo ·
                                      traslados entre ubicaciones · conteo
                                      físico que produce AJUSTES y no
                                      reescribe el saldo · tres reportes
                              Fase 3  proveedores · compras con costo ·
                                      valorización por promedio PONDERADO,
                                      declarado porque FIFO/LIFO/promedio dan
                                      números distintos sobre los mismos datos
                            Ninguna de las cuentas nuevas es una columna:
                            reservado, libre y valorización salen de sumas.
                            Y el total de la valorización DICE lo que no
                            incluye: se vio en vivo pasar de 0.00 con «3
                            material(es) sin costo conocido» a 1752000.00 con
                            el aviso en 2, al registrar una compra con costo.
                            LA GUARDA DE F2 CAZÓ A SU AUTOR dos horas después
                            de escribirse: el servicio nuevo sumaba cantidades
                            sin estar declarado. Se agregó a la lista CON SU
                            MOTIVO, que es el procedimiento que la guarda pide.
                              34 pasan contra PostgreSQL real
                              318 pasan · 6 skipped · 0 fallan sobre SQLite
                              svelte-check  0 errores en los archivos nuevos

                            LO ÚNICO DE FASE 2 QUE NO SE CONSTRUYÓ: el lazo con
                            WispHub --escribir `sn_onu` del equipo instalado--.
                            Motivo: toca `nucleo/`, que es el motor DESPLEGADO,
                            y pasa por la frontera de autorización de 8 pasos;
                            y exige `verificador-de-api` contra WispHub real,
                            que necesita credenciales de producción. Lo medido
                            que lo justifica sigue en pie: `sn_onu` está vacío
                            en 1.299 de 4.163 clientes activos, y es la llave
                            contra SmartOLT. La cola donde va ya existe
                            (`asistente.operaciones_externas`, reconciliador
                            cerrado en código y APAGADO), y hace falta ampliar
                            su `check` de tipos: hoy admite cuatro y ninguno es
                            éste. `actualizar_sn_onu` sería el primer efecto
                            externo de WispHub naturalmente idempotente --pone
                            un valor, no crea nada-- y eso cambia su
                            clasificación en el gate Q2.

                            LO QUE FALTA, dicho: la pasada adversarial (F14 --
                            los 9 agentes siguen sin cargarse), `flutter test`
                            en este worktree (la app consume los 5 endpoints
                            viejos y ninguno cambió de contrato, pero eso está
                            INFERIDO), y el `revisor-de-pii` sobre qué se dibuja
                            junto a un movimiento que trae `orden`: una orden
                            arrastra nombre y dirección del cliente.

                            LO QUE NO SE HIZO, dicho: Fase 2 (varias bodegas con
                            traslados, conteo físico, reservas, reportes) y Fase 3
                            (proveedores, compras, costos). Y el lazo con WispHub
                            --escribir `sn_onu` del equipo instalado-- sigue en
                            Fase 2: es una escritura a un sistema externo y pasa
                            por la frontera de autorización del motor.

Integración de Campo     🔴 SIGUE ABIERTA, y ya no bloquea al inventario.
                            Ficha: objetivos/integracion-campo.md
                            El 28/09 se resolvió de otra forma: en vez de esperar
                            la rama, el inventario se construyó en un worktree
                            desde PRODUCCIÓN al día, trayendo sólo `campo/`. Eso
                            quitó el bloqueo sin tocar la rama que otra sesión
                            edita, y de paso resolvió dos conflictos que la
                            integración completa va a encontrar igual:
                              las DOS migraciones 0003 de `campo`, unidas con un
                                merge (0007). Se midió que era seguro antes de
                                escribirlo: tocan modelos distintos
                              las DOS migraciones 0039 de `common`. Las de campo
                                dependían de la que NO está en producción; se
                                apuntaron a 0038, que existe en las dos ramas, y
                                la dependencia real son Org y Profile, que están
                                desde 0001
                            Lo que sigue siendo de esta ficha: los 190 archivos
                            que difieren en los dos lados.
                            feat/campo-diseno-stitch está 59 commits adelante del
                            destino y 297 ATRÁS. 948 archivos difieren:
                            548 faltan en Campo · 210 son solo de Campo ·
                            190 difieren en los dos lados.
                            El riesgo NO son los 548: son los 190, que es donde
                            git pide decisiones. Entre ellos los CUATRO monolitos
                            de §2, los cuatro documentos de autoridad,
                            tenants/rapilink.config.yaml y cli/cargar_config.py
                            --o sea la guarda que protege de esta misma rama--.
                            Antecedente real: `452e6bb` frenó que la config de
                            esta copia dejara al motor desplegado ejecutando
                            acciones irreversibles sin la frontera. Ese commit
                            declara el resto pendiente: "12 archivos en
                            conflicto". Este objetivo es ese trabajo.
                            NO INICIAR MERGE hasta: ficha leída · línea base de
                            las guardas medida y pegada · los rojos clasificados.
                            Y J1: otra sesión está editando esa rama ahora
                            (12 archivos sin commitear, 3 en el camino).
```

---

**Tres frentes avanzaron el 24/09**, cada uno en su propio árbol. Ninguno está
bajo los pies de los otros.

```
Centro de Mando        🟢 EN PRODUCCIÓN desde el 24/09 09:31 Bogotá (468f575).
                          El estado anterior decía ee4563f: ese commit es del
                          23/09 12:29 y producción avanzó 20 commits desde ahí.
                          Quedan dos entradas de menú que se pisan, y E2E-001
                          fuera por el choque en el serializer de campo
Dexter Campo           🟡 FASE 2 · PULIDO desde el 24/09/2026: datos reales,
                          los modulos ausentes del contrato §2, la deuda del §6,
                          diseño, y 2.E prioridad dual (decidida el 24/09, sin
                          implementar). Se permiten cambios de funcionalidad y
                          arquitectura; los seis invariantes del §3 NO se
                          relajan. Ficha: objetivos/campo-release-candidate.md
                          LÍNEA BASE de la Fase 1, medida el 23/09 sobre
                          cf4684e: 536 pruebas verdes en las dos compilaciones,
                          APK de release 53.2 MB. ⚠ esa rama avanzó 4 commits
                          desde entonces (evidencias con geolocalización, sello
                          de hora de fotos, filtro de localidad, siembra de
                          carga) y NO se remidió: el 536 es de antes, no de hoy
Batería de evaluación  🟡 viva en C:/tmp/dexter-bandeja (feature/bandeja-relevo),
                          5 commits fuera de producción. 20 conversaciones
                          completas que se juzgan solas, y la auditoría del
                          bloque: tres falencias arregladas, nueve anotadas.
                          Hallazgo propio: la batería daba verde con el sistema
                          caído — su garantía era falsa
Sistema de trabajo IA  ✅ CLAUDE.md como enrutador, 9 agentes, 4 comandos,
                          pre-commit activo y corregido (3 hallazgos). Falta CI
                          del lado del servidor (D1). ⚠ los agentes NO se
                          cargan en la sesión: los 9 están en disco
                          (.claude/agents/) y solo `verificador-de-api` queda
                          invocable — medido por TERCERA vez el 24/09
```

## TRABAJO SIN COMMITEAR — no se limpia sin preguntar

Alguien lo dejó ahí a propósito. Medido el 24/09.

**En `C:/wisphub/_wt_campo`** (Campo, el árbol vivo) — probablemente 2.E en curso:

```
M  apps/tecnicos-mobile/lib/features/trabajo/trabajo_vista.dart
M  apps/tecnicos-mobile/lib/features/trabajo/widgets/tarjeta_trabajo.dart
M  (3 registrants generados de macos/ y windows/)
?? compose.puerto-8001.yml
```

**En `C:/tmp/dexter-bandeja`** (la batería):

```
M  SPEC/CONTRATO_RELEVO_IA_HUMANO.md   arrastre ajeno sobre G9, sin destino propio
```

**En este árbol** (`integrar-centro-mando`) — **remedido el 25/09 13:57**: el
trabajo del centro de mando **ya está commiteado** (`8d9a3d7`, `c660474`); lo que
queda no es suyo ni va al repositorio:

```
M  cli/revision_g8.py                 arrastre ajeno, sin destino propio
?? apps/tecnicos-mobile/{docs,test}   copias de B2, 5 archivos
?? django-crm/frontend/banco-tmp/     banco local de la sesión: NO se versiona
?? documentos/command-center/*.png    ~30 capturas de trabajo, artefacto de sesión
?? documentos/command-center/*.html   los dos prototipos sueltos
?? documentos/command-center/avatares/  8 webp
```

El banco (`banco-tmp/`) monta las dos plantas con un conmutador y es la forma de
compararlas; se levanta con vite y no depende de nada del repositorio.

⚠️ **Stage por rutas explícitas siempre, también para documentación**:
prohibidos `git add .`, `git add -A`, `commit -a` y **`git add SPEC/`**. El
último se coló en el cierre de 1.8 y metió un arrastre ajeno en el commit
documental. Un directorio entero es el mismo gesto que un `add .`: basta con que
alguien deje un archivo ajeno adentro. Verificar siempre con
`git diff --cached --name-only` antes de commitear.

⚠️ **Hay 21 worktrees registrados** (`git worktree list`), la mayoría de bloques
ya cerrados (`dexter-d17`, `dexter-d19d23`, `dexter-hotfix`, `dexter-ledger`…).
No se podan acá: es decisión de una persona, no de una sesión.

## VALIDACIÓN DE PRODUCCIÓN — abierta, y ahora se sabe en qué

Objetivo `SPEC/objetivos/endurecer-validacion-de-produccion.md`. **NO está
cerrado.** La versión anterior de esta sección decía «cerrado con una
salvedad»; estaba mal contada y se corrige acá.

Lo que quedó funcionando y medido el 24/09:

```
cli/bateria_flujos.py    41 conversaciones que entran por atender_turno y se
                         juzgan solas contra la traza. 36/38 en LOCAL; 3
                         necesitan el CRM (backend:8000, red del compose).
                         Cierra el hueco de que cli/evaluar.py llama a
                         motor.responder() directo.
casos dorados            el inestable partido en dos: 10/10 y 10/10.
                         'sin el serial cargado' dejó de afirmar sobre la
                         redacción: 10/10.
cli/evaluar.py           afirmaciones 'bloquea_con' / 'no_bloquea_con'.
diferencias_config       exit 0. Las 3 diferencias son las sincronizadas
                         (localidades, localidades_actualizado_en,
                         parrilla_canales).
test_bloqueos_en_traza   VERDE (7/7). Estaba rojo en la rama.
```

**Lo que se descubrió al medir, y es lo importante de esta sección:** la
batería comiteada **nunca se había corrido**. El commit `d9733df` está escrito
como un arreglo de una línea del cliente simulado y además agrega 20 casos —de
21 a 41—, entre ellos los de seguridad. El 19/19 que esta sección declaraba se
midió sobre `81677b4`, con 21 casos. O sea: la evidencia no describía el código
comiteado, que es el error cardinal de este proyecto.

Corrida ya la batería completa, los cinco casos de seguridad que nunca se
habían medido **pasan**: inyección de instrucciones, técnico falso, lista de
morosos, cédula de un tercero, amenaza de cancelar.

**Un hallazgo de conducta, determinista, fuera del objetivo:**

```
una falla de barrio     0/10. El agente dice "puede ser algo de la zona" y acto
no se diagnostica       seguido diagnostica una sola casa: consulta el incidente
como una casa           de red en el paso 9, DESPUÉS de haber propuesto el
                        reinicio en el 8. Arreglarlo es cambiar el orden del
                        diagnóstico, o sea conducta: se anota, no se toca.
                        El caso queda ADENTRO de la batería y en rojo.
```

**Lo que falta para cerrar el objetivo:**

```
docker exec <contenedor-motor> python cli/bateria_flujos.py rapilink --todos
```

Y no basta un contenedor local: los 3 casos de CRM llaman a
`http://backend:8000` con las credenciales de la config de producción. Un
`backend` levantado desde un worktree no las tiene y responde 403; en el
intento del 24/09 eso fue exactamente lo que pasó. El 41/41 literal solo sale
en la red de producción, y antes hay que desplegar `cli/bateria_flujos.py`.

**Lo que la auditoría dejó abierto** (`SPEC/auditorias/2026-09-23-bateria-de-flujos.md`):

```
AUTONOMIA_2_NO_ACTIVA  sigue sin clasificar como bloqueo. No se arregla con un
                       renglón en una lista: llega por el except genérico, así
                       que hay que hacer que ese camino preserve e.codigo.
                       (DECLARACION_NO_ALCANZA SÍ se arregló: commit 4ac7dfb.)
traza incompleta       la batería juzga contra la traza de la base y hubo dos
                       ConnectionTimeout al escribirla. Hoy nada distingue "la
                       herramienta no se llamó" de "la llamada no se pudo
                       escribir": un caso puede salir verde por el error.
franja horaria         REFUTADO el 23/09: medido dentro de la imagen,
                       ZoneInfo('America/Bogota') funciona.
```

## CERRADO

```
Fase 0 (componentización)     ✅
D29 · D30                     ✅
G9 recibo punta a punta       ✅ verde en producción 16/09/2026
Fase 1.1–1.4B (visual)        ✅
FASE 1.4C  backend + UI de T6 ✅
FASE 1.5   Case + Tools       ✅
FASE 1.6   Activity           ✅  el relevo se lee por primera vez
FASE 1.7   Customer           ✅  lo que sabe del cliente, y lo que no
FASE 1.8   Network            ✅  qué se le hizo al equipo, sin botones
FASE 1.9   cierre visual      ✅  utilidades de panel unificadas
FASE 1     Bandeja rediseñada ✅  COMPLETA
```

## ABIERTO al cerrar la Fase 1

```
G6 sobre messages poblada   🔒 gate de DESPLIEGUE. La migración aplica limpia
                               desde cero y el ledger la anota sola, pero no se
                               midió sobre una tabla con datos. No bloquea
                               desarrollo; sí bloquea cualquier push.
                               ✅ 24/09: el push de hoy NO lo violó, medido.
                               El deploy ee4563f..468f575 llevó UNA sola
                               migración, 202609231445_identidad_eventos.sql, y
                               es `create table if not exists` sobre una tabla
                               NUEVA + índices + RLS: no hay tabla poblada que
                               medir. Las tres migraciones que sí tocan
                               `messages` (202609071000, 202609072000,
                               202609161600) son del 07 y 16/09 y ya estaban
                               afuera desde antes. El gate NO se salteó:
                               no era el caso. Sigue vigente para el próximo
                               push que sí toque `messages`.
QA visual multi-viewport    🔴 NO EJECUTABLE con los medios disponibles, y no
                               por falta de intento: el dev server levanta pero
                               hooks.server.js:373 redirige a /login antes de
                               montar el layout, así que ni el estado de error
                               dentro de .mesa.bandeja se dibuja. Entrar exige
                               un JWT del backend de producción; una ruta de
                               prueba con datos falsos está prohibida.
                               NINGÚN píxel de 1.4C a 1.9 se vio renderizado.
D28                         ⏭ abierto para B4. La pantalla lo MUESTRA (1.5): el
                               dueño del CRM es informativo, el de Dexter manda.
                               No se reconcilian — no comparten identidad de
                               usuario, y por eso se comparan nombres.
hot path ③a/③c              ⏭ idempotencia del outbound automático del canal,
                               retirado y preservado en
                               auditorias/1.4C-hotpath-diferido.md
T7 endpoint                 ⏭ «devolver sin responder»: capacidad distinta, NO
                               el recovery de T6
semánticos ember/clay/      ⏭ resueltos en context/ (1.5); los consumidores de
rust/moss                      otras pantallas, en la fase de cada una
```

## B4 — CERRADO EN CÓDIGO. Falta encenderlo (G7)

```
migración    202609201000_sincronizaciones_externas.sql   aplica limpia
T20          nucleo/relevo/reconciliador.py               la regla de reintento
worker       nucleo/relevo/worker_reconciliador.py        proceso propio, 5 min
ejecutor     nucleo/relevo/efectos_externos.py            crear_caso real
panel        «Sincronización externa», read-only, sin botón de reintentar
commits      b5bfb84 · 62487db
```

**G7 es ahora sólo activar**, y en este orden: declarar `busca_caso` en el
catálogo del tenant → comprobar que funciona → recién entonces
`RECONCILIADOR_HABILITADO=1` y desplegar el servicio. El mecanismo existe entero. El reloj general sigue en ~60 min y **no
se tocó**: el worker tiene interruptor propio, para que encender uno no encienda
el otro por descuido.

Lo que sigue sin conectar, y es deliberado:

```
crear_ticket sin ejecutor      y no lo tendrá mientras Q2 siga rojo. Uno que
                               llegue hoy a la cola termina en
                               fallida_definitiva con 'sin_ejecutor', visible
sólo crear_caso se encola      los otros tres tipos existen en esquema y panel,
                               sin productor
falta declarar `busca_caso`    ningún tenant declara la herramienta de búsqueda.
en el catálogo                 Sin ella todo reintento intentaría crear — no es
                               inseguro (el 400 se maneja) pero conviene tenerla
                               antes de encender el worker
```

## B4 — lo que Q2 ya decidió

```
Q2                    🔴 ROJO, cerrado el 20/09/2026 (auditorias/B4-Q2-WISPHUB.md)
crear_ticket WispHub  NO es reintentable automáticamente: la API no acepta
                      clave de idempotencia, no hay filtro para buscar el
                      ticket, WispHub reescribe el asunto y el histórico se
                      recorta sin rango de fecha (tope 2 meses)
fallo incierto        → estado 'desconocida'. NUNCA se crea otro ticket
                      automáticamente: un ticket pendiente de revisión es
                      preferible a dos visitas técnicas al mismo cliente
crear_caso (CRM)      SÍ reintentable: el nombre incluye el conversation_id y
                      es único por organización; un repetido da 400 y se adopta
```

**La cola de B4 no puede diseñarse homogénea.** Los dos tipos de efecto tienen
estrategias distintas, y `desconocida` deja de ser un caso teórico del esquema
para ser el camino normal de la mitad de la cola. Eso arrastra dos cosas a
decidir antes de escribir la migración: dónde se muestra un pendiente de
revisión en la conversación, y que el reintento automático de `crear_ticket`
**no se escribe**, ni detrás de una bandera.

## G3 — VERDE. El camino de ejecución está cerrado

```
36 acciones de legado en 'pendiente' (34 create_ticket · 2 promise_payment),
sin conversation_id. SIGUEN pendientes: cancelarlas es trabajo de una persona
con la pantalla delante, y ese es el punto.
```

Cerrado en `5055c20` (motor) y `e67875b` (pantalla). Detalle en
`auditorias/G3-CIERRE.md`.

```
1. aprobar responde 409 y no llega al ejecutor. La guarda corre ANTES del
   chequeo de estado y de leer la config.
2. 'cancelada' es estado declarado, con motivo obligatorio y evento durable
   en la misma transacción (I12). Tabla nueva acciones_eventos: el
   conversation_id de relevo_eventos es NOT NULL y estas 36 no tienen.
3. /acciones-legado lista las pendientes. Sin botón de aprobar —ausente, no
   deshabilitado— y sin 'argumentos' (valores reales sin enmascarar).
```

El criterio de legado es **la falta de `conversation_id`**, nunca la edad ni el
tipo. Cuando B5 traiga la columna, la misma función deja pasar las que la
tengan sin tocarla.

**Lo que este gate NO hizo, a propósito:** tocar las 36 filas. El contrato pide
revisión humana una por una, no un `UPDATE` en lote. Las 2 de promesa de pago
quedan para revisión: si el cliente pagó no se puede saber sin consultar
producción, y no se consultó.

Migración `202609201400_acciones_legado.sql` **sin aplicar en producción** — ver
la nota de abajo sobre *estar en el repo ≠ estar aplicada*.

B5 queda desbloqueado.

## B5 — CERRADO EN CÓDIGO. Falta la config del tenant (Q3)

Commits `1bad6f3` (motor), `f779d07` (pantalla) y `155bb15` (barrido T20).
Detalle en
`auditorias/B5-ACCIONES.md`.

```
aprobar = reservar -> revalidar -> ejecutar -> resolver  (§9.3)
          los dos del medio FUERA de transaccion (X23)
```

La revalidacion tiene **tres** desenlaces y no dos: «no se pudo comprobar» no
ejecuta y devuelve la accion a `pendiente`. Tratarlo como «cumple» ejecutaria a
ciegas con la API externa caida; como «no cumple» mataria una accion valida.

Dos aprobaciones concurrentes producen **un** efecto: probado con dos peticiones
reales compitiendo.

**Lo que falta, y no es codigo:** la config de Rapilink no declara
`vigencia_minutos` ni `revalidar`, y no puede hacerlo hasta que cierre la
medicion ON vs OFF (Q3). Hasta entonces las acciones nacen sin plazo y se
aprueban sin revalidar, con las guardas que no dependen de config. El validador
esta en modo **advertencia** a proposito.

Las cuatro revalidaciones de §3.7 tampoco estan escritas: el contrato exige
confirmarlas con la skill `wisphub-api` contra la API real antes de escribirlas.

T20 cierra lo que queda a medias: `ejecutando` vieja -> `desconocida` a los
10 min (§14.1 Q4), `pendiente` pasada de plazo -> `vencida`. Nunca reejecuta
(X21). Una de legado `pendiente` no se vence jamas, por construccion.

Migracion `202609201800_acciones_b5.sql` **sin aplicar en produccion**.
Verificado sobre base limpia (`b5_limpia`): 51 archivos, 0 checksum distinto.

## ESTAR EN EL REPO ≠ ESTAR APLICADA

Distinción que el 24/09 casi se pierde al medir. Son dos hechos distintos y solo
uno se puede comprobar desde una sesión:

```
en el repositorio   se mide con git, desde acá        ✅ medido el 24/09
aplicada en la base  se mide con el ledger, contra    ❌ NO se midió: consultar
                     producción                          producción desde una
                                                         sesión está prohibido
```

Medido el 24/09 con git: las **64** migraciones `.sql` de `supabase/` son
**idénticas** entre este árbol y la rama de despliegue — las tres de B4, G3 y B5
incluidas. Eso significa que sus archivos **sí viajaron a producción**, y no
dice nada sobre si el ledger las aplicó. Los «sin aplicar» de arriba siguen
vigentes tal como se escribieron; nadie los remidió.

Lo mismo vale para Campo: producción tiene **3** migraciones de `campo` en el
repo y `feat/campo-diseno-stitch` tiene **6**, mientras la anotación anterior
hablaba de **2 aplicadas** en la base. No es una contradicción: son dos cuentas
distintas, y confundirlas es el error que esta sección existe para frenar.

```
py -3.13 cli/migrar_asistente.py --estado    # lo único que responde la pregunta
```

## SIGUIENTE GATE DE LA BANDEJA *(en pausa — pero su rama NO está congelada)*

```
Branding   pantalla de ajustes, FUERA de la Fase 1
```

No es la Bandeja: es «Settings · Appearance & Branding», con subida de archivo,
almacenamiento de assets y alcance por organización. Hoy existe `Marca.logo_url`
en el esquema del tenant **sin ningún consumidor**, y nada más. Necesita su
propio scope.

Entrada: `SPEC/FASE_1_CHECKPOINT.md`.

**No es lo que sigue hoy**, y el motivo cambió. Hasta el 23/09 este gate estaba
en pausa *porque su rama estaba congelada*. Medido el 24/09, eso ya no es cierto:
`feature/bandeja-relevo` recibió 5 commits el 23–24/09 en el worktree
`C:/tmp/dexter-bandeja`, sobre la batería de evaluación y la auditoría del
bloque — no sobre la Bandeja.

Lo que sigue en pausa es **Branding**, no la rama. Quien lo retome ya no tiene
que descongelar nada: tiene que decidir que Branding es lo que toca. Lo que
sigue hoy está en TRABAJO ACTIVO, arriba, y en las fichas abiertas de
[objetivos/](objetivos/).

## CONTRATOS CONGELADOS DE ESTA RAMA

No se reauditan sin evidencia nueva.

```
T6 · control = ia     sólo con wamid + estado_entrega='enviado' durables
T6 · sin optimismo    el control cambia sólo con devuelto_al_asistente === true
rechazado             ≠ incierto / sin_id / aceptado_sin_registro
unknown               conserva el control humano y NO ofrece reintentar
clave idempotente     una por intento; viaja con la burbuja junto a la intención
T7                    no es el recovery de T6
D28                   dueño del ticket CRM ≠ dueño durable de Dexter;
                      nombres iguales NO prueban identidad
ficha del cliente     Dexter guarda identidad + equipo y nada más (RNF-01);
                      no se consulta el ISP en vivo desde la Bandeja
acciones sobre el     no se ejecutan desde la Bandeja: reiniciar corta el
equipo                servicio y pasa por la cola con confirmación (PRD §7.4)
ACCION_CONFIRMADA     el equipo hizo lo pedido ≠ el cliente tiene internet
NO_VERIFICABLE        «no se pudo medir» ≠ «se midió y el efecto no está»
el ping               no es veredicto: medido, un equipo sano da 1/3, 2/3 y 3/3
bloqueo               ≠ error: el código frenando la acción es la protección
                      funcionando, y no ensucia la tasa de error
```


---

## UN SOLO DUEÑO DEL ESTADO

*Regla nueva del 24/09/2026. No nace de una preferencia: nace de que hoy tres
sesiones se cruzaron tres veces en un día.*

### La regla

**Este archivo lo escribe la sesión que trabaja en `integrar-centro-mando`.**
Las demás sesiones **no lo editan**. Si tienen algo que anotar, lo entregan en
su respuesta —hash del commit y una línea de qué cerró— y la sesión dueña lo
escribe acá.

Es la misma forma que ya funciona para producción (ver la memoria «Un solo
dueño de producción»: solo la IA de Plataforma pushea, las demás entregan
hashes). Se extiende al estado por el mismo motivo y con la misma evidencia.

### Por qué, y lo que costó

Un documento de autoridad con dos escritores **deja de ser autoridad**: pasa a
ser dos borradores con el mismo nombre. Lo que pasó hoy, medido:

- Las dos copias divergieron **252 líneas** en un solo día. Ninguna era «la
  buena»: cada una tenía secciones que la otra no.
- El mismo defecto se arregló **dos veces** (`DECLARACION_NO_ALCANZA` en
  `6207b9a` y en `4ac7dfb`) porque cada sesión leía su propia copia del estado,
  y en ninguna de las dos figuraba que la otra ya lo estaba mirando.
- La sección del mapa de ramas afirmó **lo contrario de la realidad dos veces
  el mismo día** —una en cada dirección— y la segunda corrección también estaba
  mal, porque medir por ancestría no ve un commit rebaseado.

El costo no es el desorden. Es que este archivo existe para que una sesión nueva
no tenga que reconstruir el estado, y un archivo que miente cuesta **más** que
no tenerlo: la sesión que lo lee no sospecha.

### Las tres cosas que se hacen distinto desde hoy

1. **Se mide por contenido, no por hash.** Para saber si algo está en
   producción: `git patch-id --stable`, no `merge-base --is-ancestor`. Un
   commit rebaseado por otra sesión es invisible para el segundo.

2. **Antes de arreglar un defecto, se mira si otra rama ya lo está
   arreglando.** `git log --all --oneline --since=<ayer> -- <archivo>` cuesta
   dos segundos y hoy habría ahorrado un arreglo duplicado.

3. **Nadie rebasea ni pushea commits de una rama ajena sin decirlo.** Si pasa,
   se anota acá cuál fue el hash viejo y cuál el nuevo — como quedó anotado
   arriba con `65c8f57 -> 790e185` y `eb8f503 -> b7cfa90`.

### Lo que esta regla NO dice

No dice que las otras sesiones trabajen menos ni que pidan permiso para
codificar. Cada rama sigue siendo dueña de su trabajo y de sus commits. Lo
único centralizado es **el relato de qué está hecho** — porque de eso hay uno
solo por definición, y hoy había tres.
