# Objetivo · Dexter avisa antes de que el cliente pregunte

> Abierto el 30/10/2026. Estado: **abierto**.
> El **qué** y el **por qué** viven en [PRD.md §8.17](../../PRD.md) (Ola 2) y no se
> repiten acá. Si difieren, manda el PRD.

## Qué significa terminado

Cuando ocurre un hecho que el cliente va a preguntar —su visita es hoy, se le
abrió un ticket, hay una caída en su zona—, Dexter le escribe primero por
WhatsApp, una sola vez, solo si la empresa encendió ese aviso, y nunca a quien
pidió la baja.

## Lo medido que define el orden (30/10/2026)

```
El envio ya existe y es robusto: nucleo/seguimiento/mensajes_automaticos.enviar
  interruptor por aviso, modo prueba por numeros, baja (Ley 1581), plantilla
  aprobada, reserva por (evento, clave) antes de mandar.
Solo la encuesta tiene disparador. Patron: post_save del Case en el CRM ->
  tarea Celery -> POST al motor -> enviar.
El telefono de un cliente sin chat sale de WispHub CRUDO: sin indicativo y con
  varios numeros en el 55% de los casos. Sin normalizar, la baja no lo reconoce.
```

## Orden

| # | Qué | Por qué en este lugar |
|---|---|---|
| 1 | Resolver el destino: conversación del caso, o WispHub normalizado con `autenticacion.indicativo_pais` | Prerrequisito de todo aviso a quien no está chateando, y de que la baja funcione |
| 2 | `visita_programada`: al publicar el día, al cliente con su franja | "¿A qué hora viene el técnico?" es de las preguntas que más entran |
| 3 | `ticket_creado_cliente` desde "Nuevo ticket" de Dexter | El cliente no está en el chat cuando una persona le abre el ticket |
| 4 | Caída masiva, con aprobación humana antes de mandar, en lotes | Mayor reducción de volumen; ya estaba decidido que la apruebe una persona |
| 5 | Confirmación y promesa de pago (en la aprobación de la acción) | |
| 6 | Recordatorio de pago y suspensión (diario) | Necesita un lector de facturas de WispHub que hoy no existe |

## Qué NO hacer

- **No avisar el cierre del ticket aparte.** Al cerrar ya sale la encuesta: serían dos plantillas seguidas al mismo cliente.
- **No avisar los tickets importados de WispHub.** Los abrió una persona en el sistema del ISP; avisarlos duplicaría lo que el ISP ya hace o no hace a propósito.
- **No encender ningún aviso desde el código.** Todos nacen apagados; los enciende la empresa, primero en modo prueba.

## Criterios de aceptación

| # | Evidencia | Cómo se comprueba |
|---|---|---|
| A1 | El resolvedor saca el número de WhatsApp de un campo crudo con varios números, y sin indicativo declarado no inventa uno | `py -3.13 tests/test_destino_de_aviso.py` |
| A2 | La baja se respeta sobre el número normalizado | misma prueba |
| A3 | Publicar el día dispara `visita_programada` una sola vez por orden y fecha | `campo/tests/test_aviso_de_visita.py` (SQLite; falta correrla contra Postgres) |
| A4 | `auditor-de-frontera` y `revisor-de-pii` corrieron | hallazgos resueltos o anotados |

## Restricciones

- **NO push** — es deploy.
- **NO escribir `tenant_config`** fuera de la base efímera de las pruebas.

## Bitácora

| Fecha | Qué avanzó | Qué falta | Commit |
|---|---|---|---|
| 30/10/2026 | Mapa de disparadores; orden decidido | 1 a 6 | — |
| 30/10/2026 | **1 y 2 en código.** Resolvedor de destino (`indicativo_pais`, sin default), puerta común `POST /avisos/evento` con horario de la empresa, evento `visita_programada` disparado al publicar el día. Auditorías de frontera y PII corridas: 3 hallazgos altos y 2 medios resueltos (BSUID, empresa de la org, visita que ya no existe, ruta abierta a cualquier aviso, dirección de más) | 3 a 6; medir cuántos avisos caerían en "primero del ISP" antes de encender; la asignación a mano desde Despacho todavía no avisa | 555e16df (antes del rebase) |
| 30/10/2026 | **3 en código.** `ticket_creado_cliente` lo pide el CRM al atar el caso de "Nuevo ticket" a su ticket del ISP; el motor lee nombre y móvil de la ficha del ISP solo si le faltan, y reagenda si el ISP no contesta. Sin descripción en el aviso. 6 mutaciones del motor cazadas | 4 a 6; lo mismo de arriba | 103e85bd |
| 31/10/2026 | **Auditorías de 3 resueltas.** Frontera: 2 medios (el motor creía servicio, contexto y clave del pedido; la ficha no se comprobaba) y 4 bajos. PII: 2 medios (asunto releído y editable; cliente ficticio de instalaciones) y 1 bajo. Ahora el CRM manda solo el número de ticket y el motor lo confirma en el ISP; contrato por evento en `PROACTIVOS` | Verificar en vivo que el detalle del ticket trae `servicio.id_servicio` | 4bbaa67f |
| 31/10/2026 | **4 en código: caída masiva.** Pestaña Supervisor NOC → Fallas de red: vista previa (a cuántos, quiénes quedan afuera, si el aviso puede salir) y aprobación de una persona; tandas con pausa; el motor recalcula la falla en cada tanda (solo el grupo que cayó junto, clientes activos) y descarta a quien ya volvió; se detiene si la situación se resuelve | 5 y 6; el aviso «restablecido» al cerrar una caída avisada | 01e06fd5, 1361a1a9 |
| 31/10/2026 | **«Ya quedó restablecido».** Segunda fase del mismo envío: solo a quien recibió el aviso de la falla y cuyo equipo ya no está en LOS. Y lo que encontró el auditor independiente: «en verificación» solo pausa (antes descartaba pendientes), arranca con la situación resuelta, cerrada o descartada, un envío detenido después de mandar también avisa la vuelta, la pantalla sigue mostrando la caída 24 h, sin indicativo del país la vista previa lo dice, y las esperas de visita y ticket se parten bajo el `visibility_timeout` de Redis | 5 y 6 (pagos: falta verificar el lector de facturas) | 770b7000 y el siguiente |
