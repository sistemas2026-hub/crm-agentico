# Auditorías · La bandeja como WhatsApp (21/10/2026)

Ficha: [../objetivos/bandeja-como-whatsapp.md](../objetivos/bandeja-como-whatsapp.md).
Base: `b1c75518`. Cada hallazgo con lo que se hizo; lo que no se arregló dice
por qué.

## revisor-de-pii

Sin fugas de dato crudo al log, al modelo ni a un tercero. Corrió
`test_registro_sin_pii.py` (72 `[ok]`) y `test_bandeja_por_chat.py`.

| # | Gravedad | Hallazgo | Qué se hizo |
|---|---|---|---|
| 1 | MEDIA | Un número que cambió de dueño: los mensajes de una conversación anterior aparecían rotulados con el nombre del cliente de la actual (`MessageThread.svelte`, `nombreCliente` para todas las burbujas) | **Arreglado en dos capas.** El motor marca cada tramo verificado como otro cliente (`otro_cliente`, calculado contra el `id_cliente` del ancla; el id no viaja), y la marca de cierre dice «era otro cliente». La pantalla usa el nombre solo en la conversación actual; en las anteriores, la etiqueta neutra. Prueba: `test_bandeja_por_chat_base.py` («la conversación verificada como OTRO cliente se marca, sin mandar quién era») y `chat.test.js`. |
| 2 | BAJA | «Conservar» protege una conversación y la pantalla muestra el chat entero: se podía leer como «todo el chat» | **Arreglado el rótulo:** «Conservar esta conversación — no borrarla al vencer la retención (las anteriores del chat no)». Conservar el chat entero sería decisión de producto: cambia qué se retiene. |
| 3 | BAJA | La prueba de `desenlace_nota` afirmaba un nombre de clave, no el efecto | **Arreglado:** el cierre T17 de la prueba lleva `nota="CANARIO-NOTA-7731"` y se afirma que ese texto no aparece en el cuerpo de `/hilo`. |
| 4 | BAJA (previo) | El motor no comprueba que el `mensaje_id` de «marcar ejemplo» sea de la conversación de la URL (`db.marcar_ejemplo`) | **Anotado, no arreglado acá.** Viene de antes del cambio. Hoy la pantalla manda el `conversation_id` del propio mensaje (`MessageThread.svelte`, `item.m.conversation_id`) y la prueba base lo afirma. Endurecerlo en el motor (derivar el `conversation_id` del `mensaje_id`) es un cambio aparte de `marcar_ejemplo`. |

Frecuencia de números compartidos o reasignados: no medida. Consulta de solo
lectura que la mide (la corre una persona):
`select canal, usuario_externo, count(distinct id_cliente) from asistente.conversations where id_cliente is not null group by 1,2 having count(distinct id_cliente) > 1`.

## auditor-de-frontera

Midió con una sonda propia sobre una base efímera, con los envíos a Meta
sustituidos por dobles que cuentan cada POST.

| # | Gravedad | Hallazgo (medido) | Qué se hizo |
|---|---|---|---|
| 1 | ALTA | I22/X26 se miraba en la LECTURA de la guarda pero no en la ESCRITURA: un cierre (barrido T16, otra persona T17, un «listo, gracias» T15) entre la guarda y el insert dejaba el mensaje guardado en la cerrada y salía a Meta (sonda S6: 201, 1 POST, mensaje `enviado` en una `cerrada`). En `/plantilla` la ventana incluye un GET a Meta | **Arreglado.** `agregar_mensaje_humano` bloquea la fila (`FOR UPDATE`) y vuelve a mirar `estado` en la misma transacción del insert; una cerrada levanta `ConversacionCerrada` y las tres rutas (texto, plantilla, media) responden 409 `conversacion_cerrada` sin guardar ni enviar. Prueba: `test_bandeja_por_chat_base.py` §C («I22: cerrada entre la guarda y el guardado»). Mutación M5 (quitar la comprobación). |
| 2 | ALTA | La misma clave después del cierre abría una conversación fantasma; con plantilla, un SEGUNDO POST a Meta (S1: el cliente la recibía dos veces). También desde otra cerrada del mismo chat (S3), y por «Reintentar» en una cerrada (S2b) | **Arreglado.** T21 busca la clave en TODO el chat antes de crear nada: si ya tiene su mensaje, 409 `clave_usada` con el id de esa conversación, sin crear ni enviar. «Reintentar» no se dibuja si la conversación actual está cerrada. Pruebas §C: misma clave tras el cierre (texto y plantilla) y desde otra cerrada. Mutación M6. |
| 3 | MEDIA | T21 y un mensaje del cliente a la vez pueden dejar dos abiertas (límite 3, ya declarado en el contrato); medido: además los turnos siguientes los atiende la IA (la abierta que creó `registrar_mensaje` tiene control `ia`) | **Anotado, no arreglado.** El arreglo es que `registrar_mensaje` tome el mismo lock consultivo al crear; tocar `registrar_mensaje` exige correr la evaluación del modelo (criterio 9 de la ficha), y la ventana es de milisegundos. La bandeja muestra las dos abiertas (§4.5, regla 2). Queda como decisión para una sesión aparte. |
| 4 | BAJA | `esta_de_baja` sin `try`: una falla de la base daba un 500 sin forma (fallaba cerrado). Además: la baja por BSUID y por teléfono son dos identidades; el texto dentro de 24 h no mira la baja; la plantilla de la conversación ABIERTA nunca la miró (previo) | **Arreglado el 500:** 503 `baja_desconocida` con mensaje, como `/avisos`. El resto, **anotado**: la doble identidad es el mismo hueco de `/avisos`; que el texto dentro de 24 h no mire la baja coincide con la regla de `esta_de_baja` («bloquea la interrupción, no la atención»); la plantilla en una abierta es previa a este cambio. |

Notas del auditor que no son de frontera:

- **Alcance:** cualquier usuario con sesión puede usar T21 sobre cualquier chat cerrado de la empresa, también los que solo atendió la IA. La validación sigue en código (plantilla aprobada, baja, ventana): es alcance, no autonomía. `/casos/<id>/mensajes` (la pantalla del ticket) también llega a T21, si el chat no tiene una abierta (ver auditor-independiente #1).
- **Arreglado:** el proxy `/api/conversaciones/[id]/humano` perdía el `codigo` y el `conversation_id` del 409; ahora viajan.
- **Previo, anotado:** reintentar un texto `fallido` no vuelve a hacer el POST (la salida `humano:K` ya quedó tomada) y responde 201 sin aviso. Falla cerrado, pero el resultado engaña.

## auditor-independiente

Pasada adversarial sobre el bloque entero. Midió con sondas propias sobre una
base efímera, comparando cada una contra `b1c75518` (extraído con
`git archive`), y con los conteos de la bandeja pasados por `estado.js` y
`ordenamiento.js` reales. Confirmó limpio: el layout de producción pide
`por_numero=1`, la página usa el hilo, ningún otro consumidor lee
`GET /conversaciones`, no hace falta migración ni `tenant_config`, y C20, T21,
X26 e I22 coinciden con el motor.

| # | Gravedad | Hallazgo (medido) | Qué se hizo |
|---|---|---|---|
| 1 | ALTA | Responder desde la pantalla del TICKET a un caso cuya conversación se cerró: la primera respuesta abría una nueva por T21 **sin copiar al ticket del ISP**, la segunda daba 409 `hay_conversacion_abierta` y **no salía**, y la pantalla del ticket trataba todo lo que no fuera 2xx como «no había a quién» (`sent: true`, sin aviso). En `origin`: dos envíos y dos copias | **Arreglado en dos lados.** `/casos/<id>/mensajes` escribe en la abierta del chat si existe (con sus guardas: si la atiende la IA, 409 `control_ia`, X25) y si no por T21; la copia va al ticket de ESE caso aunque se escriba en otra conversación del chat. La pantalla del ticket muestra cualquier rechazo que no sea el 404 `sin_conversacion`. Prueba: `test_bandeja_por_chat_base.py` §D (dos respuestas desde el caso → 2 envíos y 2 copias al mismo ticket, en una sola conversación nueva; con la IA atendiendo → 409, nada sale). Mutación M9. |
| 2 | ALTA si hay chats con dos abiertas | La fila copiaba solo la banda de la urgente: una escalada de 8 días detrás de una conversación nueva de la IA se veía «Por atender» con 0 críticas, espera de 0,6 h, sin plazo de toma, fuera de «solo escaladas», del filtro por motivo y de la búsqueda; al abrirla no había forma de llegar a la escalada | **Arreglado.** La fila lleva el estado ENTERO de la urgente (escalada, quién la tomó, asignación, espera) y conserva el enlace de la actual (D2); copiar campo por campo mezclaba la escalada de una con el `tomada_por` de la otra. `abiertas` pasa a ser «las que no son la urgente», así cada abierta cuenta una vez. En la ventana, un aviso con enlace «Abrirla» y la marca de la abierta también enlaza. Pruebas: `test_bandeja_por_chat.py` §1 y §1b, base §A, `chat.test.js`. Mutación M2c. |
| 3 | MEDIA | «Devolver a la IA», adjuntos y audio aparecían en un chat cerrado; con texto, «Devolver» mandaba por T21 sin devolver. Sin texto, sobre una cerrada de legado, daba 200 y le borraba `escalada_a_humano` (la métrica la contaba distinto) | **Arreglado.** El compositor recibe `chatCerrado` y no dibuja «Devolver» ni adjuntos. `devolver_a_ia` rechaza una cerrada también de legado (E3 terminal). Prueba base §D. Mutación M11. |
| 4 | MEDIA | Una cerrada creada DESPUÉS de la abierta que representa al chat desaparecía: la fila mostraba su último mensaje y la ventana no lo tenía | **Arreglado con aviso.** `/hilo` devuelve `posteriores`; la ventana dice «Este chat tiene una conversación más reciente, ya cerrada · Verla». No se dibuja dentro del hilo: lo que se escribe va a la actual, y una cerrada debajo se leería como su respuesta. Prueba base §A. Mutación M12. |
| 5 | MEDIA-BAJA | La búsqueda miraba solo la conversación representante: un cliente que vuelve y todavía no se identificó dejaba de encontrarse por su nombre | **Arreglado.** La fila trae `buscable` (nombres, motivos y caso manual de todas las conversaciones del chat) y la búsqueda lo incluye. No se pinta en la fila: si el número cambió de dueño, rotularía a otra persona. |
| 6 | MEDIA-BAJA | T21 corría en el canal simulado y dejaba el número de batería en manos de una persona: la próxima corrida no la contestaba la IA (D9) | **Arreglado.** T21 solo en `canales.REALES` (409 `conversacion_cerrada` como antes); `/hilo` dice `agrupa`, y la pantalla no ofrece escribir si el chat no agrupa o no se pudo leer. Prueba base §D. Mutación M10. |
| 7 | MEDIA-BAJA | Dos garantías de S37 sin prueba que las vigile: quitar el `FOR UPDATE` del guardado o el lock consultivo de T21 dejaba la suite en verde (el lock sí hace falta: sin él, dos T21 a la vez dejan dos abiertas) | **Arreglado.** Dos pruebas de carrera en la base §D: dos T21 a la vez sobre el mismo chat dejan UNA abierta; un guardado durante un cierre que tarda en confirmar espera y ve la cerrada. Mutaciones M7 y M8. |
| 8 | BAJA | La ventana de una cerrada no se enteraba de lo nuevo del cliente (cae en otra conversación), y un 409 `hay_conversacion_abierta` dejaba la burbuja como enviada | **Arreglado.** Con un chat cerrado a la vista y la caja vacía, el sondeo relee el mapa del chat (`/hilo?limite=1`). Con un 409 así, la burbuja se va, el texto vuelve a la caja y un aviso lleva a la conversación actual. |
| 9 | BAJA | D7 a medias: el Centro de mando no decía que cuenta conversaciones; la cabecera «Por atender» no decía que cuenta chats; el comentario «cuatro estados que se excluyen» ya no era cierto | **Arreglado.** Rótulos «Conversaciones activas (24 h)» y «Conversaciones que esperan…» en el Centro de mando; la cabecera lleva el mismo `title` que las pestañas; el comentario dice que un chat con dos abiertas cuenta en la pestaña de cada una. |

Previos que el auditor anotó y no son de este bloque: `test_errores_http`
(api.py:3488-3585) y las 7 fallas de `test_relevo_transiciones_base` (D24/D25)
están igual en `origin`. Un cliente que llega a veces con teléfono y a veces
con BSUID sigue partido en dos chats (`whatsapp.py`), como antes.

Frecuencia en producción de chats con dos abiertas (de ella dependen 2 y 4):
no medida. La consulta de solo lectura, para que la corra una persona:
`select canal, usuario_externo, count(*) from asistente.conversations where estado = 'abierta' group by 1,2 having count(*) > 1`.
