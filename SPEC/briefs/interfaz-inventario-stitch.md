# Prompt para Google Stitch — la sección Inventario

**Para quién es este archivo:** para pegarlo en Google Stitch (IA de diseño de
interfaces). No es documentación del módulo — eso vive en
[inventario-de-bodega.md](inventario-de-bodega.md) y en los docstrings del código.

**Cómo usarlo.** Stitch trabaja mejor con un prompt de contexto y después una
pantalla por vez. Pegá el **Bloque 0** primero (fija producto, paleta y reglas), y
después uno de los bloques 1 a 10 por cada pantalla que quieras generar. Si Stitch
pierde el contexto entre generaciones, volvé a pegar el Bloque 0 arriba del que
sigue.

Todo está descrito sobre la pantalla que ya existe y funciona
(`django-crm/frontend/src/routes/(app)/inventario/`), así que lo que devuelva
Stitch se puede comparar contra algo real en vez de contra una idea.

---

## BLOQUE 0 — contexto, sistema visual y reglas duras

```text
Estás diseñando una sección de una aplicación web interna en español (Colombia)
que usan las oficinas de un proveedor de internet (un ISP). No es una app para
clientes ni una landing: es una herramienta de trabajo que una persona de bodega o
de coordinación tiene abierta ocho horas por día. Densidad alta, cero decoración,
nada de ilustraciones ni fondos degradados.

LA SECCIÓN: "Inventario". Responde tres preguntas y todo lo demás es secundario:
  1. ¿Tengo material con qué despachar hoy?
  2. ¿Qué tiene encima cada técnico en su camioneta?
  3. ¿Dónde está este aparato concreto, y por dónde pasó?

CONTEXTO DE LAYOUT: la sección vive dentro de una app que ya tiene navegación
lateral izquierda (no la diseñes). Diseñá solo el área de contenido, que empieza
con un encabezado de página:
  Título: "Inventario"
  Subtítulo: "Qué hay en bodega, qué tiene cada técnico y por dónde pasó cada aparato"

Debajo del encabezado va una BARRA DE PESTAÑAS horizontal, con subrayado en la
activa (no cápsulas, no botones), que se envuelve a dos filas en pantallas
angostas. Las diez pestañas, en este orden exacto:
  Existencias · Registrar entrada · Despachar · Recibir devolución · Trasladar ·
  Reservas · Conteo físico · Compras y valor · Reportes · Buscar un aparato

SISTEMA VISUAL (respetalo, la app ya lo usa):
  fondo de página     #f9fafb
  tarjetas            #ffffff, borde 1px #e5e7eb, radio 10px, padding 16px 18px
  texto principal     #111827
  texto secundario    #6b7280
  acento / botón      #2563eb con texto blanco, radio 7px
  tipografía          system-ui / Inter. Cuerpo 14px, títulos de tarjeta 16px
  números y códigos   fuente monoespaciada, alineados a la derecha en tablas,
                      con tabular-nums
  tablas              sin bordes verticales, solo línea inferior #f3f4f6 por fila,
                      encabezados en 600 y color secundario

TRES TIPOS DE AVISO, y los tres son distintos a propósito (esto es una decisión
de producto, no estética):
  ÉXITO     fondo #f0fdf4, borde #bbf7d0, texto #166534
  ERROR     fondo #fef2f2, borde #fecaca, texto #991b1b
  ATENCIÓN  fondo #fffbeb, borde #fde68a, texto #92400e
El tercero existe porque hay resultados que no son ni éxito ni error: "la
devolución entró pero faltan 3 conectores" en verde se lee como "todo bien" y en
rojo como "falló la operación", y ninguna de las dos es cierta. Necesita su propio
color y su propio lugar.

CINCO REGLAS QUE NO SE PUEDEN ROMPER:

1. NUNCA MOSTRAR UN CERO INVENTADO. Si un dato no se pudo leer, la pantalla dice
   "No se pudo leer el inventario. Lo que sigue puede estar incompleto: no se
   muestran ceros porque no sabemos si son ceros." Un "0 conectores" falso manda a
   un técnico a la calle sin material. Diseñá ese estado como una franja de ERROR
   arriba del contenido, no como un toast que desaparece.

2. LOS NÚMEROS NEGATIVOS SE MUESTRAN, no se ocultan ni se ponen en cero. Un
   negativo en una existencia es exactamente lo que alguien tiene que ver. Va en
   rojo #b91c1c y en negrita, con la fila marcada.

3. LOS MENSAJES DE ERROR LLEGAN COMPLETOS. Cuando un despacho choca, el sistema
   dice DÓNDE está el aparato: "La serie HWTCA6FB5263 figura en 'Custodia de
   Carlos Ramírez' y no en el origen de este despacho. Un aparato no puede estar
   en dos manos a la vez: primero hay que registrar su devolución." Ese texto va
   entero, sin truncar y sin reescribir por un "No se pudo completar la
   operación". Reservá espacio para mensajes de dos y tres líneas.

4. CADA TABLA TIENE SU ESTADO VACÍO CON TEXTO ÚTIL, que dice qué hacer y no solo
   "sin datos". Ejemplo real: "Todavía no hay ninguna ubicación con movimientos.
   Empezá registrando una entrada: hasta que el material entre al sistema, no hay
   nada que despachar."

5. LOS FORMULARIOS SON ANGOSTOS (máximo 34rem), de una sola columna, con la
   etiqueta arriba del campo y un texto de ayuda gris debajo cuando hace falta. No
   uses formularios de dos columnas: se llenan mal y acá cada campo importa.

TONO DE LOS TEXTOS: español rioplatense-neutro con voseo ("Elegí un material…",
"Anotá lo que vayas contando", "Reintentá"), directo, sin signos de admiración y
sin lenguaje de marketing. Los textos de ayuda explican POR QUÉ, no qué botón
apretar.

DATOS DE EJEMPLO (usá estos, son realistas para el dominio):
  Materiales:  CON-SC-APC · Conector SC/APC · Conectividad · unidades
               FIB-DROP · Fibra drop · Cableado · m (se cuenta con decimales)
               ONT-HG8145 · ONT Huawei HG8145V5 · Equipos · unidades (con serie)
               ROS-HAP · Router hAP lite · Equipos · unidades (con serie)
  Ubicaciones: "Bodega Central" (bodega) · "Bodega Norte" (bodega) ·
               "Camioneta 02" (vehículo) · "Custodia de Carlos Ramírez" (técnico)
  Series:      HWTCA6FB5263 · HWTCA6FB5271
  Personas:    Carlos Ramírez · Juan Pérez · Marta Salgado
  Documentos:  acta de entrega K-0412 · factura FAC-8891 · remisión R-2291
  Moneda:      pesos colombianos, formato 1.250.000
```

---

## BLOQUE 1 — Existencias (la pestaña de entrada)

```text
Pantalla "Existencias", la primera y la que se abre por defecto.

Es una LISTA DE TARJETAS, una por ubicación, en una sola columna. Empieza por las
existencias y no por los formularios a propósito: la pregunta que trae a alguien
acá es "¿tengo con qué despachar?", y poner el formulario arriba obliga a bajar
para responderla y después subir.

Cada tarjeta:
  - Título: el nombre de la ubicación ("Bodega Central") seguido de una etiqueta
    pequeña tipo pill con su tipo: bodega / vehículo / técnico.
  - Una tabla con columnas: Código | Material | Categoría | Existencia | Unidad
    Código en monoespaciada. Existencia alineada a la derecha, monoespaciada.
    Categoría y Unidad en color secundario.
  - Si la ubicación no tuvo movimientos: "Sin movimientos todavía." en gris.

Mostrá cuatro tarjetas de ejemplo: Bodega Central con 4 materiales, Bodega Norte
con 2, Camioneta 02 con 1, y "Custodia de Carlos Ramírez" con 2 materiales, una de
ellas EN NEGATIVO (-6 conectores) para que se vea el tratamiento del negativo: fila
marcada, número en rojo y negrita.

Las cantidades se muestran distinto según el material: los conectores en entero
(94), la fibra con dos decimales (257.50). No inventes un formato único.

Arriba de todo, mostrá también cómo se ve la franja de ERROR de "No se pudo leer
el inventario" (regla 1 del bloque 0), como un segundo estado de la misma pantalla.
```

---

## BLOQUE 2 — Registrar entrada

```text
Pantalla "Registrar entrada": material que ENTRA al sistema por primera vez — una
compra sin factura cargada, o un equipo retirado de la casa de un cliente.

Una sola tarjeta, título "Material que entra", con un formulario de una columna:
  - Material: desplegable con "Elegí un material…" y opciones "CON-SC-APC —
    Conector SC/APC".
  - Cantidad: numérico, admite decimales (paso 0.001).
  - Número de serie: campo de texto que APARECE SOLO si el material elegido es un
    equipo serializado, y entonces la cantidad se fija en 1 y se oculta.
    Placeholder: HWTCA6FB5263.
  - Ubicación de destino: desplegable de bodegas y vehículos.
  - Referencia de origen (opcional): texto, placeholder "FAC-001", con ayuda
    debajo: "El número de la remisión o la factura. Con referencia, registrar la
    misma entrada dos veces no la duplica; sin ella, no hay forma de saber que es
    la misma."
  - Botón primario: "Registrar entrada".

Mostrá además, arriba del formulario, el aviso de ÉXITO ya resuelto: "La entrada
quedó registrada."
```

---

## BLOQUE 3 — Despachar a un técnico

```text
Pantalla "Despachar": la bodega le entrega material a un técnico y las dos partes
firman un acta. Es la única operación del módulo que el sistema puede NEGAR, porque
es la única que todavía no ocurrió: el material está sobre el mostrador.

Tarjeta "Despachar a un técnico", formulario de una columna:
  - Bodega de origen: desplegable (bodegas y vehículos).
  - Técnico que recibe: desplegable de personas.
  - Material: desplegable.
  - Cantidad, o Número de serie si el material es serializado (mismo
    comportamiento que en Registrar entrada).
  - Número de acta (opcional): texto, placeholder "K-0412", con ayuda: "El acta es
    lo que hace que despachar dos veces por un doble clic no descuente dos veces.
    Sin acta, el segundo intento sí descuenta otra vez."
  - Botón primario: "Despachar".

Diseñá DOS estados de resultado arriba del formulario:
  a) ÉXITO: "Despachado. Acta: K-0412"
  b) ERROR de conflicto, con el mensaje largo completo: "La serie HWTCA6FB5263
     figura en 'Custodia de Carlos Ramírez' y no en el origen de este despacho. Un
     aparato no puede estar en dos manos a la vez: primero hay que registrar su
     devolución." Tiene que caber sin truncarse ni romper el diseño.
```

---

## BLOQUE 4 — Recibir devolución

```text
Pantalla "Recibir devolución": el técnico trae material de vuelta a la bodega.

Tarjeta "Recibir una devolución", formulario de una columna:
  - Técnico que devuelve: desplegable.
  - Bodega a la que vuelve: desplegable.
  - Material · Cantidad · Serie (igual que las otras pantallas).
  - "Cuánto se esperaba" (opcional): numérico, con ayuda debajo: "Solo si esto es
    un cierre de jornada y sabés cuánto debía volver. Si vuelve menos, la
    diferencia NO se absorbe: queda como una incidencia con su motivo. Vacío
    significa 'no sé cuánto debía volver', y entonces no se abre ninguna."
  - Notas (opcional): texto, placeholder "el cliente canceló, vuelve sin instalar".
  - Botón primario: "Registrar devolución".

EL ESTADO MÁS IMPORTANTE DE ESTA PANTALLA es el aviso de ATENCIÓN (ámbar) cuando
la devolución no cuadra. Diseñalo con cuidado:

  Título en negrita: "Quedó una diferencia abierta."
  Texto: "La devolución se registró por lo que llegó, y lo que falta quedó como
  incidencia — no se absorbió en un ajuste:"
  Lista:
    · CON-SC-APC · faltan 3 · Al recibir se esperaban 18 y volvieron 15. Falta por
      explicar: 3.

No es un error (la devolución entró) ni un éxito (falta material). Es lo que hay
que mirar.
```

---

## BLOQUE 5 — Trasladar

```text
Pantalla "Trasladar": mover material entre ubicaciones internas — de una bodega a
otra, o de la bodega a una camioneta.

Una tarjeta, "Trasladar entre ubicaciones", formulario de una columna:
  - Origen: desplegable · Destino: desplegable
  - Material · Cantidad o Serie
  - Motivo (opcional): texto, placeholder "reparto semanal"
  - Botón primario: "Trasladar"

Estado de error a mostrar: "El origen y el destino son la misma ubicación: eso no
es un traslado."

Es la pantalla más simple del módulo; no le agregues nada que las otras no tengan.
```

---

## BLOQUE 6 — Reservas (la pantalla con la tabla más importante)

```text
Pantalla "Reservas": material comprometido para trabajos que todavía no salieron.

Arriba, un selector de ubicación en línea (desplegable + botón "Ver"), porque todo
lo de esta pantalla es sobre UNA bodega concreta: un "comprometido" global no se
puede despachar desde ningún lado.

PRIMERA TARJETA — "Lo comprometido"
Texto de ayuda: "La pregunta que importa no es cuánto hay, sino cuánto queda LIBRE
después de lo ya prometido. Sin esto dos despachadores prometen el mismo equipo y
el segundo técnico llega a la bodega y no está."

Una tabla con SEIS columnas y LAS TRES CIFRAS JUNTAS — esto es deliberado:
  Código | Material | Hay | Comprometido | Libre | Unidad
"Hay" y "Comprometido" en color secundario; "Libre" en negrita y color principal,
porque es la que se usa para decidir. "Quedan 70" sin mostrar el 100 y el 30 no se
entiende.
Ejemplo: CON-SC-APC · Conector SC/APC · 100 · 30 · 70 · unidades
         ONT-HG8145 · ONT Huawei HG8145V5 · 4 · 6 · -2 · unidades  ← negativo en rojo

SEGUNDA TARJETA — "Comprometer material"
  - Material · Cantidad, o Serie si es serializado (ahí la ayuda dice "Reservar un
    aparato concreto.")
  - "Vence (opcional, pero recomendado)": selector de fecha y hora, con ayuda:
    "Sin plazo, una orden que se cae deja el material comprometido para siempre y
    quien lo reservó ya se fue a su casa."
  - "Para qué (opcional)": texto, placeholder "instalaciones de mañana"
  - Botón primario: "Reservar"

TERCERA TARJETA — "Reservas activas"
Tabla: Material | Cantidad | Serie | Vence | (acción)
La última columna lleva un campo de texto pequeño con placeholder "por qué se
libera" y un botón secundario "Liberar", en la misma fila.
Pie de tarjeta, en gris: "Liberar no borra la reserva: queda con su motivo y su
desenlace. Es lo que permite contestar después «por qué faltaron ONT el martes»."

Estado de error a mostrar arriba: "No alcanza: en 'Bodega Central' quedan 10
libres de CON-SC-APC y se piden 30. Hay 100 en total, 90 ya comprometidos."
```

---

## BLOQUE 7 — Conteo físico

```text
Pantalla "Conteo físico": alguien cuenta la bodega a mano y anota lo que encuentra.

Texto de ayuda arriba: "«El sistema dice 50 y tengo 48» no es un error del
sistema: es un hecho que alguien tiene que explicar. Cerrar el conteo NO reescribe
el saldo — escribe un ajuste por cada diferencia, con su motivo."

PRIMERA TARJETA — abrir: selector "Ubicación a contar" en línea + botón "Abrir
conteo". Error posible: "Ya hay un conteo abierto de 'Bodega Central' desde
2026-09-28. Cerralo o descartalo antes de abrir otro: dos conteos abiertos
producen dos verdades sobre lo mismo."

SEGUNDA TARJETA — "Conteos": tabla Ubicación | Estado (pill: borrador / cerrado) |
Abierto (fecha y hora) | Líneas.

TERCERA TARJETA — aparece por cada conteo en borrador, con título "Anotar en el
conteo de Bodega Central":
  - Material: desplegable
  - "Cuánto hay de verdad": numérico
  - "Motivo de la diferencia (si hay)": texto, placeholder "faltaban cinco en el
    estante", con ayuda: "Sin motivo, el ajuste queda marcado como diferencia sin
    explicar."
  - Botón primario "Anotar"
  - Separado abajo, un botón secundario: "Cerrar el conteo y escribir los ajustes"

CUARTA TARJETA — "Resultado del conteo", después de cerrar:
Tabla: Material | Contado | Decía el sistema | Diferencia | Ajuste
  CON-SC-APC · 93 · 100 · -7 · se escribió     ← fila marcada, diferencia en rojo
  FIB-DROP   · 300 · 300 · 0 · cuadró          ← fila normal
Pie en gris: "Las líneas que cuadraron aparecen también: un conteo que solo
muestra diferencias no deja ver cuánto se revisó."
```

---

## BLOQUE 8 — Compras y valor

```text
Pantalla "Compras y valor": el único lugar por donde entra un costo al sistema, y
cuánto vale lo que hay.

PRIMERA TARJETA — "Registrar una compra"
  - Bodega de destino: desplegable
  - Proveedor: desplegable (opcional)
  - Referencia: texto, placeholder "FAC-8891", con ayuda: "El número de la
    factura. Es lo que hace que registrar la misma compra dos veces no duplique el
    material."
  - Moneda: desplegable, COP por defecto
  - Material · Cantidad · Serie · Costo unitario
  - Botón primario: "Registrar compra"
Error a mostrar: "La factura FAC-8891 ya se registró para este proveedor."

SEGUNDA TARJETA — "Proveedor nuevo": Nombre · Identificación · Contacto + botón
"Crear proveedor".

TERCERA TARJETA — "Cuánto vale lo que hay"
  - Un número grande arriba (1.7rem, negrita, tabular-nums): 1.250.000
  - Debajo, un aviso de ATENCIÓN cuando hay material sin costo conocido:
      "El total no incluye todo." + "2 material(es) sin costo conocido no entran
      en el total." + "Un total que se come en silencio lo que no sabe valorizar es
      la forma más rápida de decidir con un número que parece completo."
      Lista: · ONT-HG8145 ONT Huawei HG8145V5 · 3 unidades · sin costo conocido
  - Tabla: Código | Material | Cantidad | Costo unit. | Valor
  - Pie en gris: "El costo es un promedio ponderado de lo que costó al entrar. Se
    dice cuál es el método porque FIFO, LIFO y promedio dan números distintos
    sobre los mismos datos."
```

---

## BLOQUE 9 — Reportes

```text
Pantalla "Reportes", con una sub-navegación de tres enlaces de texto (no pestañas,
más chicos, el activo subrayado y en negrita):
  "En qué se fue" · "Por técnico" · "Descuadres abiertos"

REPORTE 1 — "En qué se fue": tabla Código | Material | Consumido | Unidad.

REPORTE 2 — "Por técnico": NO es una tabla. Es una lista de fichas, una por
persona: nombre como título y debajo una lista simple de "CON-SC-APC · 48".
Pie en gris, que explica una ausencia deliberada: "Sin «eficiencia» calculada, a
propósito: dos técnicos con distinto tipo de trabajo no son comparables por metros
de fibra, y un número que parece comparable se usa como si lo fuera."
No agregues gráficos de barras, rankings, medallas ni comparaciones entre
personas. Esa ausencia es una decisión tomada.

REPORTE 3 — "Descuadres abiertos": tabla Cuándo | Estado (pill) | Material |
Cantidad | Persona | Motivo. TODAS las filas van marcadas en rojo, porque todas
son cosas sin resolver.
Pie en gris: "Una lista y no un contador: un número en un tablero se mira una vez
y se ignora; esto se puede resolver."

En las tres, el estado vacío dice: "Nada que mostrar todavía en este reporte."
```

---

## BLOQUE 10 — Buscar un aparato

```text
Pantalla "Buscar un aparato": la que justifica todo el módulo. Un equipo con
número de serie no puede quedar "en algún lado".

Texto de ayuda: "Quién lo tuvo, dónde está, cuándo salió y por qué. Es la pregunta
que este módulo existe para responder."

Arriba: un buscador en línea, campo "Número de serie" (placeholder HWTCA6FB5263) +
botón "Buscar".

RESULTADO — una ficha por aparato encontrado:
  - Título: la serie en monoespaciada, y al lado en gris el nombre del material
    ("ONT Huawei HG8145V5").
  - Una línea destacada: "Ahora está en: Custodia de Carlos Ramírez" (el lugar en
    negrita). Cuando el aparato ya se instaló en la casa de un cliente, dice
    "fuera de custodia".
  - Un aviso de ERROR, solo cuando corresponde: "Atención: el índice de posición y
    el libro de movimientos no coinciden para este aparato. Lo que manda es el
    libro, que está abajo. Hay que revisarlo."
  - LA HISTORIA, como una lista ordenada vertical tipo línea de tiempo, de lo más
    viejo a lo más nuevo. Cada paso en una línea:
      2026-09-20 08:14  entrada   → Bodega Central
      2026-09-24 07:30  despacho  desde Bodega Central → Custodia de Carlos Ramírez
      2026-09-28 11:05  consumo   desde Custodia de Carlos Ramírez → fuera de custodia
    La fecha en gris, el tipo de movimiento en negrita, los lugares en texto
    normal, y "→ fuera de custodia" en gris. Si un paso tiene un estado que no es
    "aceptado", se marca con un pill (descuadre / conflicto).

ESTADO SIN RESULTADO, y es distinto de un error — el texto importa: "No hay ningún
aparato con la serie HWTCA6FB5263 en esta empresa. No es un error de consulta:
nunca entró al sistema."
```

---

## Lo que Stitch NO debe inventar

Pegá esto si la primera generación se va de tema:

```text
No agregues a esta sección:
  - Gráficos, dashboards, KPIs ni tarjetas de "métricas" arriba de la pantalla.
    Este módulo no tiene tablero; tiene tablas para trabajar.
  - Rankings o comparaciones entre técnicos (decisión tomada: no son comparables).
  - Un botón de "eliminar" en ningún movimiento. Nada se borra nunca: corregir es
    registrar otro movimiento en sentido contrario, como en cualquier libro
    contable.
  - Semáforos de "stock bajo", alertas de reposición ni mínimos y máximos: hoy no
    existen en el sistema y no deben aparecer como si existieran.
  - Iconos decorativos, ilustraciones, fondos con degradado o modo oscuro.
  - Modales para los formularios: las operaciones viven en su propia pestaña a
    propósito, porque quedan en la URL y se pueden compartir por link.
```

---

## Qué comparar cuando Stitch devuelva algo

La pantalla real ya existe, así que la revisión no es de gusto:

1. ¿Están las tres cifras juntas en Reservas (hay / comprometido / libre)?
2. ¿Los negativos se ven, en rojo, sin taparse?
3. ¿El aviso ámbar de la devolución que no cuadra es visualmente distinto del
   verde y del rojo?
4. ¿Cabe un mensaje de error de tres líneas sin romper el diseño?
5. ¿Los estados vacíos dicen qué hacer, o solo "sin datos"?
6. ¿El resultado del conteo muestra también las líneas que cuadraron?
