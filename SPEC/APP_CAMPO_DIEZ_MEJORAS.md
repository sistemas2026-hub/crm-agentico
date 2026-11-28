# App de campo (Flutter) — diez mejoras pedidas por el usuario

Briefing para quien las desarrolle. Todo lo que dice "medido" se verificó leyendo
el código el 09/11/2026; lo que dice "no verificado" hay que comprobarlo antes.

Maqueta visual de cómo queda cada una:
https://claude.ai/artifact/MdDMTRFNuiJuBW6XBUrrFe
(es privada: si no abre, pedírsela al usuario. **Este documento se lee solo** —
la maqueta muestra la forma, pero el qué y el porqué están todos acá.)

---

## 0 · Antes de escribir una línea

Leé, del disco y completos, en este orden:

1. `CLAUDE.md` — manda sobre todo lo demás. Especialmente §3 (núcleo vs
   configuración), §6 (cómo se verifica), §7 (git) y §11 (protocolo).
2. `PRD.md` y `ARQUITECTURA.md`.
3. `SPEC/DEXTER_ESTADO_ACTUAL.md` — dónde estamos hoy.

Tres reglas del proyecto que aplican a este trabajo y que no son negociables:

- **Push a `fix/integracion-wisphub` es DEPLOY A PRODUCCIÓN.** No se empuja sin
  autorización explícita del usuario, dicha con esa palabra.
- **Afirmar sobre el efecto, nunca sobre la presencia del mecanismo.** Una prueba
  que dice que algo existe no prueba que funcione. Matá la mutación que restaura
  el código viejo; si no muere, la prueba no sirve.
- **Lo que varía por empresa es configuración, no código.** Antes de agregar un
  `if`, preguntarse si falta un campo en la configuración.

El repositorio se comparte con otras sesiones que empujan a la misma rama.
`git fetch` antes de afirmar cualquier estado, y rebase antes de empujar.

---

## 1 · Dónde está cada cosa

Raíz de la app: `apps/tecnicos-mobile/lib/`

| Qué | Archivo |
|---|---|
| Pantalla de inicio (1739 líneas) | `features/inicio/inicio_screen.dart` |
| Las tres cifras del inicio | `inicio_screen.dart::_avanceDiario` (~595-660) |
| Recibo del kit al arrancar | `features/inicio/arranque_de_jornada.dart` |
| Lista de trabajos | `features/trabajo/trabajo_screen.dart` |
| Distancia en línea recta | `features/trabajo/cercania.dart` |
| Materiales (1238 líneas) | `features/materiales/materiales_screen.dart` |
| Detalle de la orden | `features/detalle_orden/detalle_orden_screen.dart` |
| Los 3 botones de reporte | `features/detalle_orden/seguimiento_de_la_intervencion.dart:515` |
| Formulario de un reporte | `features/detalle_orden/hoja_de_reporte.dart` |
| Ejecución por pasos | `features/ejecucion/ejecucion_screen.dart` |
| Un campo del formulario | `features/ejecucion/campo_del_formulario.dart` |
| De dónde sale una foto | `features/ejecucion/de_donde_sale_la_foto.dart` |
| Resumen de cierre | `features/ejecucion/cierre_de_orden.dart` |
| Notificaciones (pantalla) | `features/notificaciones/notificaciones_screen.dart` |
| Encabezado con la campana | `core/widgets/dexter_app_header.dart` |
| Envío automático / red | `core/sync/envio_automatico.dart` |

Backend (Django), lo que toca este trabajo:

| Qué | Archivo |
|---|---|
| Plantillas del formulario, `permite_otro` | `django-crm/backend/campo/plantillas.py:517, 691` |
| Validación del formulario | `django-crm/backend/campo/services/validador.py:137` |
| Lectura de coordenadas del ISP | `django-crm/backend/campo/coordenadas_del_cliente.py` |

---

## 2 · Las diez mejoras

Orden sugerido de ejecución al final del documento.

### 1. Campana en vez de pantalla de avisos

**Pedido.** Una campanita en el encabezado; al tocarla se despliegan las
notificaciones; al tocar afuera se recogen.

**Hoy (medido).** `notificaciones_screen.dart` es una pantalla completa. El
encabezado ya tiene `notificacionesSinLeer` (`dexter_app_header.dart:43, 61`),
**pero el número es de ejemplo**: `app_shell.dart:821` dice literalmente
"Dato de ejemplo: todavía no hay notificaciones de verdad". El contador real
existe: `app_shell.dart:282` llama a `contarNotificacionesSinLeer`.

**Qué hacer.** Panel desplegable anclado a la campana, cierre al tocar fuera,
punto solo en lo no leído, y "Ver todos" que abre la pantalla completa (que se
queda, como historial).

**No negociable:** el contador tiene que salir de `local_notificaciones`. Un 3
que no corresponde a nada enseña a ignorar la campana.

### 2. Las tres cifras del inicio

**Pedido.** "Asignadas" = las del día, diciendo con cuántas arrancó. "En curso"
igual que ahora. "Pendientes" = lo que va quedando por hacer, sin mezclar las
cerradas.

**Hoy (medido).** Las tres ya existen y ya suman: el código calcula
`sinEmpezar = total - completados - enCurso`, con un comentario que explica por
qué (`resumen.pendientes` incluye la que está en curso, y ponerlo al lado daba
"5 asignadas, 1 en curso, 5 pendientes", que se lee como app rota).

**Qué hacer.** Agregar "arrancó con N" debajo de Asignadas. **Mantener la regla
de que las tres sumen**: si se rompe, vuelve el síntoma que ya se corrigió una
vez.

### 3. "Mi Trabajo" cuenta de más — es un defecto

**Pedido.** Que muestre solo las asignadas hoy.

**Hoy (medido).** `trabajo_screen.dart:360`:

    final int total = widget.ordenes.trabajos.length;

y se rotula "$total órdenes asignadas para la jornada de hoy". Cuenta **todo**,
cerradas incluidas. El rótulo afirma algo que el número no dice.

**Qué hacer.** Contar solo lo asignado hoy y poner "N cerradas" aparte, en gris.

### 3b. Quitar los chips "Cerca mío" y "Todos"

**Pedido.** Quitarlos.

**Hoy (medido).** `trabajo_screen.dart:534`. "Cerca mío" tiene un comentario
largo explicando por qué va primero: al final de la fila quedaba fuera de la
vista a cualquier ancho y **el toque ni siquiera llegaba**. No es el orden por
omisión a propósito: una orden con ventana prometida se atiende cuando se
prometió, aunque quede lejos.

**Qué hacer.** "Todos" se va sin más. Para "Cerca mío": la propuesta aceptada en
la maqueta es sacarlo de la fila de filtros y mostrar la distancia ("a 1,2 km")
en cada tarjeta. **Confirmar con el usuario** antes de borrar el ordenamiento por
distancia: es la única forma que tiene de saber cuál le queda cerca.

### 4. El material se recibe dos veces

**Pedido.** Que no se repita el proceso.

**Hoy (medido).** `arranque_de_jornada.dart` ya dice "Revisá el material antes de
salir" / "Ya revisé, arrancar". `materiales_screen.dart` repite el recibo con su
propio botón.

**Qué hacer.** En "Mi Kit", el bloque pasa a decir **cuándo** se recibió y de qué
bodega, con el acta a un toque (no a la vista). Lo que se hace varias veces al
día —pedir, devolver, escanear— queda en una fila debajo del material.

### 5. Ticket desplegable, mapa, y coordenadas del cliente

**Pedido.** (a) El "Ticket #" como botón que despliega cliente, teléfono, IP,
puerto y niveles leídos, y esa información también en "para entender la falla".
(b) Texto técnico de validación en vez de la descripción larga del Supervisor.
(c) Que el mapa se vea. (d) Un botón que tome las coordenadas donde está el
técnico y las guarde **en el cliente**, visible solo cuando el cliente no las
tiene.

**Hoy (medido).** `detalle_orden_screen.dart:1619` dibuja "Cliente & Ubicación";
~1845 pinta `lat, lng` como texto, o "Sin coordenadas en la orden"; al tocar
abre una app externa (`_navegar`). **No hay mapa.**

**ATENCIÓN — (d) no es trabajo de UI.** `campo/coordenadas_del_cliente.py` solo
**lee** el texto que manda el ISP y lo parte en `gps_lat` / `gps_lng`. La fuente
de verdad del campo `coordenadas` es **WispHub**. Entonces:

- Guardar en el cliente = **mutación en un sistema externo**. Cae bajo la
  frontera de autorización (`CLAUDE.md` §5) y bajo la decisión congelada de
  idempotencia (§12): clave `origen|herramienta|hash(argumentos resueltos)`.
- **No verificado:** que la API de WispHub acepte escribir `coordenadas`. Hay que
  medirlo con el método del valor imposible antes de prometerlo. Cargar la skill
  `wisphub-api` y pasar por el agente `verificador-de-api`.
- Hay una alternativa mucho más barata: guardar solo en la orden local
  (`gps_lat`/`gps_lng`) sin escribir al ISP. **Es una decisión del usuario**, no
  del desarrollador: con la alternativa, el cliente sigue sin coordenadas la
  próxima vez.
- Ese módulo es **fail-closed a propósito**: lo que no reconoce devuelve
  `(None, None)` y la pantalla dice "sin ubicación". No agregarle heurísticas.
- La acción necesita confirmación ("vas a guardar esta ubicación para X"), cola
  offline como todo lo demás, y registro de quién y cuándo. No es lo mismo cargar
  una coordenada parado en la casa que a seis cuadras.

### 6. Galería en la evidencia fotográfica

**Pedido.** Poder entrar a la galería para elegir fotos o capturas.

**Hoy (medido).** `de_donde_sale_la_foto.dart:39`:

    ImageSource fuenteDeLaEvidencia(requisito) =>
        esUnaCaptura(requisito) ? ImageSource.gallery : ImageSource.camera;

**Esto es una decisión escrita, no un olvido.** El encabezado del archivo dice:
"una de la galería puede ser de otro día o de otra casa, y la orden la
guardaría". La foto es lo único que prueba que alguien estuvo en la casa.

**Propuesta acordada:** los dos botones, y la foto de galería se guarda
**marcada** ("no tomada en sitio") para que el Supervisor decida. No quitar la
distinción en silencio.

### 7. El bloqueo, más fácil de llenar

**Pedido.** Los tres botones de reporte con sus preguntas; "mirá qué le puede
mejorar" al bloqueo.

**Hoy (medido).** Ya existen: `seguimiento_de_la_intervencion.dart:515` dibuja
"Registrar inicio" / "Registrar avance" / "Bloqueo". El bloqueo ya tiene sus dos
casillas ("Hace falta que el NOC haga algo", "Detener el trabajo") y foto
opcional (`hoja_de_reporte.dart:213-228`).

**Qué hacer.**
- Motivo **primero y como botones** (falta material / sin acceso / daño en red /
  otro) y el texto libre debajo. Hoy arranca en un campo vacío, parado en la
  calle.
- Cada casilla explica qué pasa si se deja: "Detener el trabajo" para el reloj de
  la orden, y ese reloj decide después si la orden se pasó de tiempo.
- Los tres botones dicen en un renglón qué piden.
- **La foto sigue opcional.** Obligarla deja a alguien sin poder avisar que está
  trabado.

### 8. "Qué encontraste" con texto libre — ES CONFIGURACIÓN, NO CÓDIGO

**Pedido.** Que las opciones predeterminadas tengan un "Otro" con texto libre.

**Hoy (medido).** La app **ya lo soporta**. `campo_del_formulario.dart` lee
`permite_otro`, dibuja la opción "Otro", guarda en `{id}_otro` y valida con
"Elegiste «Otro»: contá qué fue." El backend también:
`plantillas.py:517` y `:691`, `validador.py:137`, y hay pruebas
(`campo/tests/test_opcion_otro.py`).

**Qué hacer.** Marcar `permite_otro` en la definición de la plantilla de ese tipo
de trabajo. **Primero producir la lista** de todos los campos de selección de
todas las plantillas que **no** lo tienen, y pasársela al usuario: si a uno le
faltó, probablemente a varios. Esto sale sin release de la app.

### 9. El material, en un solo lugar

**Pedido.** "Registrar material" (debajo de las fotos) y "Material en esta orden"
(más abajo) están duplicados; que quede arriba.

**Qué hacer.** Un solo bloque: la lista, con "Agregar" como botón adentro, y
**cuánto queda** después de cargarlo (el dato ya está en el kit del día).
Propuesta: que el material sea su propio paso, entre evidencia y solución; hoy
cuelga debajo de las fotos, que es donde nadie lo busca.

### 10. Finalizar muestra un resumen

**Pedido.** Al finalizar, un resumen de lo realizado; el técnico revisa, corrige
o finaliza; queda esperando al Supervisor y le llega un aviso al confirmarse el
cierre.

**Hoy (medido).** La misma pregunta aparece tres veces: el paso "Solución" pide
en texto libre qué se hizo; el botón Finalizar abre otro formulario para
escribirlo otra vez; y `cierre_de_orden.dart` ya arma su propio resumen (fotos,
material, firma, "Falta 1 foto obligatoria", etc.) por separado.

**Qué hacer.** Un solo resumen antes de finalizar, con las dos potencias (llegada
y salida), evidencia, material y firma. **Cada bloque se corrige en el paso donde
se escribió** — si hay dos lugares para escribir lo mismo, lo que se guarda
depende de cuál se llenó último.

**Lo que no se puede prometer:** que el Supervisor confirme "enseguida". Lo
aprueba una persona. Lo que sí hay que garantizar es que el aviso llegue a la
campana **tanto si aprueba como si devuelve**, con el motivo. Hoy una devolución
se descubre solo volviendo a abrir la orden.

---

## 3 · Dos fallas reportadas que NO son de pantalla

No se arreglan a ojo. Hay que medir primero y dejar la medición escrita.

**a) "Los cambios tardan en enviarse."** `core/sync/envio_automatico.dart` espera
a que la cola tenga algo y reintenta por tiempo. Hay tres tramos que desde afuera
se ven iguales ("todavía dice pendiente"): esperar el turno, subir las fotos, y
que el servidor tarde. Instrumentar los tres por separado.

**b) "Dice sin red teniendo wifi con internet."** `alCambiarLaRed(bool)` se
alimenta del estado del adaptador, que dice "hay wifi", no "hay internet": un
router sin salida o un portal cautivo reportan conectado. Y al revés, el cartel
puede decir sin red cuando el envío funcionaría. La señal correcta es si **la
última llamada al servidor respondió**, no si la antena está prendida.

---

## 4 · Cómo se verifica este trabajo

La app es Flutter; la tabla de disparadores de `CLAUDE.md` §6 cubre el motor
Python, no esto. Para este trabajo:

- Toda decisión (qué se cuenta, qué se muestra, qué habilita un botón) va en
  **lógica pura, fuera del widget**, como ya se hace en
  `features/inicio/resumen_de_inicio.dart` y `features/trabajo/cercania.dart`.
  Esos archivos son el modelo a seguir: se prueban sin emulador, sin red y sin
  base.
- Pruebas en `apps/tecnicos-mobile/test/`. Correr `flutter test`.
- **Mutación obligatoria antes de dar algo por cerrado**: restaurar el código
  viejo tal cual y comprobar que la prueba muere. Una mutación que muere por un
  error de compilación no prueba nada — tiene que morir por una aserción.
- Si se toca el backend (plantillas, coordenadas): las pruebas de
  `django-crm/backend/campo/tests/` contra **PostgreSQL real**, nunca SQLite.
- Cambios en `django-crm/frontend/`: `npx vitest run` y `npx svelte-check`
  comparando contra la base, que hoy **no está en cero** (hay rojos previos).

---

## 5 · Orden sugerido

1. **La 8** (texto libre). Es configuración: no espera release de la app y
   desbloquea al técnico hoy mismo. Empezar por la lista de campos sin
   `permite_otro`.
2. **La 3** (el conteo de "Mi Trabajo"). Es un defecto claro, de una línea, con
   su guarda.
3. **La 10 y la 9** (resumen de cierre y material). Son las que más tiempo le
   ahorran al técnico en cada orden.
4. **La 1, 2, 4, 6, 7** (campana, cifras, kit, galería, bloqueo).
5. **La 5** al final, y partida en dos: el mapa y el desplegable del ticket son
   UI; guardar coordenadas en el cliente es una acción con efecto sobre un
   sistema externo y necesita que antes se mida si WispHub acepta la escritura.

Lo que haga falta decidir —"Cerca mío", coordenadas en el ISP o solo locales—
se pregunta al usuario. No se decide en el código.

---

## 6 · El encargo, listo para entregar

Este es el texto con el que se le pasa el trabajo a quien lo vaya a hacer. Va
acá, dentro del mismo documento, para que el encargo y su contexto no se
separen: un prompt suelto en un chat se pierde, y entonces el que recibe el
trabajo no tiene de dónde leer el porqué de cada decisión.

```
Vas a desarrollar diez mejoras en la app de campo (Flutter) de este
repositorio, en apps/tecnicos-mobile/.

Leé primero, del disco y completos: CLAUDE.md, PRD.md, ARQUITECTURA.md y
SPEC/DEXTER_ESTADO_ACTUAL.md. Mandan sobre cualquier cosa que diga este
prompt.

El briefing del trabajo es SPEC/APP_CAMPO_DIEZ_MEJORAS.md. Tiene, para cada
mejora, el archivo y la línea donde está hoy, qué se midió y qué no, y qué
decisión ya escrita no hay que romper.

Tres cosas antes de empezar:

1. Empezá por la mejora 8. Es configuración, no código: la app y el backend YA
   soportan permite_otro. Tu primera entrega es la LISTA de campos de selección
   de todas las plantillas que no lo tienen. No cambies ninguno hasta que el
   usuario vea la lista.

2. La mejora 5 (guardar coordenadas en el cliente) NO es trabajo de UI: es una
   mutación en WispHub y pasa por la frontera de autorización. Nadie verificó
   todavía que esa API acepte escribir ese campo. Medilo con el método del
   valor imposible antes de prometer nada, y decile al usuario qué encontraste.

3. Hay tres puntos donde el pedido choca con una decisión ya tomada y escrita
   en el código: el chip «Cerca mío», la galería en la evidencia fotográfica, y
   el «enseguida» del cierre. El briefing explica cada una. Preguntá al usuario
   en vez de resolverlas vos.

Reglas del proyecto para este trabajo:
- Push a fix/integracion-wisphub es DEPLOY A PRODUCCIÓN: no empujes sin que el
  usuario lo autorice explícitamente.
- Toda decisión va en lógica pura fuera del widget, como resumen_de_inicio.dart
  y cercania.dart, y se prueba sin emulador.
- Antes de dar algo por cerrado, restaurá el código viejo tal cual y comprobá
  que la prueba muere. Si muere por error de compilación, no probaste nada.
- Afirmá sobre el efecto, nunca sobre la presencia del mecanismo.

Entregá de a una mejora, con lo que verificaste y cómo, distinguiendo medido de
inferido.
```

---

*Escrito el 09/11/2026 a partir de los pedidos del usuario sobre capturas de la
app en uso. Todo lo marcado como "medido" se verificó leyendo el código ese día;
lo marcado como "no verificado" sigue abierto.*
