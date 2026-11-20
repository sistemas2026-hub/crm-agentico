/**
 * A dónde se puede ir desde una conversación  --  12/11/2026
 *
 * POR QUÉ. La Bandeja era una isla (auditoría del menú §1.1 y §2): el único
 * `href` saliente de `lib/conversaciones` era el ticket del CRM. Para ir del
 * chat a la ficha del cliente, al ticket operativo o al agente que atendió
 * había que buscar a mano.
 *
 * SOLO CON LO QUE YA VIAJA EN LA APERTURA. Ningún enlace pide un dato nuevo
 * al abrir la conversación; cada uno sale de un campo que el motor ya manda
 * (GET /conversaciones/<id>/apertura, `conversacion`), y si el campo no está
 * el enlace no se dibuja — un enlace que lleva a una pantalla vacía enseña a
 * no usarlo.
 *
 *   ficha            `id_cliente` es el id_servicio del sistema del ISP
 *                    (api.py lee la ficha con `id_servicio = id_cliente`).
 *                    → /clientes/<id_servicio>
 *   ticketOperativo  `ticket_operativo` es el número del ticket en el sistema
 *                    del ISP; el CRM lo guarda como `external_ticket_id`, y la
 *                    búsqueda de /tickets lo encuentra por número exacto
 *                    (cases/views.py, `iexact`). `all=1` para que un ticket
 *                    ya cerrado también aparezca.
 *   agente           `rol_efectivo`: qué agente lleva la conversación.
 *                    → /agentes (la pantalla no tiene ancla por agente).
 *
 * LO QUE NO ESTÁ, Y POR QUÉ: la solicitud de instalación. Se ata a la
 * conversación por el Lead que creó Dexter (solicitudes/models.py), y ni el
 * Lead ni la solicitud viajan en la apertura.
 *
 * @param {any} conversacion
 * @returns {{ ficha: string | null, ticketOperativo: string | null, agente: string | null }}
 */
export function enlacesDeSalida(conversacion) {
  const texto = (/** @type {unknown} */ v) =>
    typeof v === 'string' || typeof v === 'number' ? String(v).trim() : '';
  const idServicio = texto(conversacion?.id_cliente);
  const ticket = texto(conversacion?.ticket_operativo);
  const agente = texto(conversacion?.rol_efectivo);
  return {
    ficha: idServicio ? `/clientes/${encodeURIComponent(idServicio)}` : null,
    ticketOperativo: ticket ? `/tickets?search=${encodeURIComponent(ticket)}&all=1` : null,
    agente: agente ? '/agentes' : null
  };
}
