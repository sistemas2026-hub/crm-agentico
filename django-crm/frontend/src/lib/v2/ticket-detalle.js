/**
 * Lo que el detalle de un ticket lee de su encabezado y de su linea de tiempo.
 * Funciones puras: sin red, sin Svelte, probadas en ticket-detalle.test.js.
 */
import { accionLegible } from './acciones-historial.js';

/**
 * El nombre del caso viene como "Asunto · Cliente · #id8" cuando lo escribio
 * el asistente al escalar (nucleo/seguimiento/nombres.py), o con el formato
 * viejo "WhatsApp <numero> - <id8>". Misma regla que `partirAsunto` de la
 * cola: el ultimo tramo que empieza con '#' es el identificador.
 *
 * @param {string | null | undefined} nombre
 * @returns {{ asunto: string, cliente: string, id: string }}
 */
export function partirNombreDelTicket(nombre) {
  const limpio = (nombre ?? '').trim();
  const tramos = limpio.split(' · ');
  if (tramos.length > 1 && tramos[tramos.length - 1].startsWith('#')) {
    return {
      asunto: tramos[0],
      cliente: tramos.slice(1, -1).join(' · '),
      id: tramos[tramos.length - 1]
    };
  }
  const viejo = limpio.match(/^WhatsApp\s+(\S+)\s+-\s+(\S+)$/);
  if (viejo) return { asunto: `Conversación de ${viejo[1]}`, cliente: '', id: `#${viejo[2]}` };
  return { asunto: limpio || 'Sin asunto', cliente: '', id: '' };
}

/**
 * QUIEN hizo un evento de la linea de tiempo: una persona, la IA o el sistema.
 *
 * El CRM guarda `user` vacio para todo lo que no hizo una persona, asi que lo
 * que ejecuto el asistente y lo que hizo un automatismo llegan iguales. Se
 * separa SOLO donde el dato lo permite, y lo demas se dice como es:
 *
 *   persona  el evento tiene usuario.
 *   sistema  ROUTED y ESCALATED: el propio CRM los escribe con user=None
 *            (cases/routing.py, cases/tasks.py). Es verificable en el codigo.
 *   ia       la CREACION sin usuario de un ticket que vino de una
 *            conversacion del asistente: lo creo el asistente al escalar.
 *   ambos    cualquier otro evento sin usuario. "IA o sistema" -- poner "IA"
 *            adivinando seria inventar justo en la parte de la pantalla que
 *            existe para poder auditar.
 *
 * Limite conocido: si el asistente le habla al CRM con una clave de API, el
 * CRM registra al administrador que esa clave representa (common/
 * external_auth.py) y el evento llega como de una persona. Desde aca no hay
 * forma de distinguirlo.
 *
 * @param {{ action?: string, by?: string | null }} evento
 * @param {{ delAsistente?: boolean }} [contexto]
 * @returns {{ clave: 'persona'|'ia'|'sistema'|'ambos', rotulo: string }}
 */
export function actorDelEvento(evento, { delAsistente = false } = {}) {
  if (evento?.by) return { clave: 'persona', rotulo: 'Persona' };
  const accion = evento?.action ?? '';
  if (accion === 'ROUTED' || accion === 'ESCALATED') return { clave: 'sistema', rotulo: 'Sistema' };
  if (accion === 'CREATE' && delAsistente) return { clave: 'ia', rotulo: 'IA' };
  return { clave: 'ambos', rotulo: 'IA o sistema' };
}

/**
 * Nombres para una lista de ids de perfil. Un id que ya no esta en la
 * organizacion no se muestra crudo: se cuenta.
 *
 * @param {unknown} ids
 * @param {Record<string, string>} nombrePorId
 */
function nombres(ids, nombrePorId) {
  const lista = Array.isArray(ids) ? ids.map(String) : [];
  const conocidos = lista.map((id) => nombrePorId[id]).filter(Boolean);
  const faltan = lista.length - conocidos.length;
  if (faltan > 0) conocidos.push(faltan === 1 ? 'una persona que ya no está' : `${faltan} personas que ya no están`);
  return conocidos.join(', ');
}

/**
 * El texto de un evento, con NOMBRES donde el evento trae ids de perfil.
 *
 *   ASSIGN  metadata {"added": [ids]} o {"removed": [ids]} (cases/signals.py)
 *   ROUTED  metadata {"target_profile_id": id}             (cases/routing.py)
 *
 * @param {{ action?: string, label?: string, metadata?: any }} evento
 * @param {Record<string, string>} [nombrePorId]
 */
export function textoDelEvento(evento, nombrePorId = {}) {
  const base = accionLegible(evento);
  const m = evento?.metadata ?? {};
  if (evento?.action === 'ASSIGN') {
    if (Array.isArray(m.added) && m.added.length) return `Asignado a ${nombres(m.added, nombrePorId)}`;
    if (Array.isArray(m.removed) && m.removed.length) return `Se quitó a ${nombres(m.removed, nombrePorId)}`;
  }
  if (evento?.action === 'ROUTED' && m.target_profile_id) {
    return `${base} a ${nombres([m.target_profile_id], nombrePorId)}`;
  }
  return base;
}
