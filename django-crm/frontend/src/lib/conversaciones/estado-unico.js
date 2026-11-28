/**
 * EL ESTADO DE UNA CONVERSACIÓN, EN UNA SOLA LÍNEA (04/11/2026).
 *
 * POR QUÉ EXISTE
 * --------------
 * Una conversación cerrada mostraba a la vez cinco indicadores: el chip
 * «cerrada» de la cabecera, la caja «Control humano · Sin asignar», la franja
 * «Respondida por el equipo · IA no responde», el motivo «Información a
 * confirmar» y la marca verde «Resuelta». Varios se contradecían: ¿cómo está
 * cerrada y resuelta, y a la vez sin asignar y esperando a una persona?
 *
 * No era un error de los datos sino de lectura: al cerrar, el motor no toca
 * las banderas de legado ni `control` (transiciones.py lo explica), así que
 * `control_efectivo` sigue diciendo 'humano' en una legada cerrada. Para la
 * persona que mira, en cambio, cerrada es el estado: lo demás es historia.
 *
 * Y había un segundo caso, al revés: la franja se dibujaba también en una
 * conversación que lleva la IA sin escalar, y caía en la rama «Escalada · el
 * asistente sigue respondiendo». Era falso: nadie la había escalado.
 *
 * NO DECIDE NADA DEL RELEVO. Quién controla lo resuelve el motor y llega como
 * props, igual que en HandoffControls. Esto solo elige cuál de esas verdades
 * ya resueltas es LA que se dice primero.
 *
 * @typedef {'neutro'|'alerta'|'aviso'|'humano'|'ia'} Tono
 * @typedef {{ clave: string, tono: Tono, texto: string, detalle: string|null }} Estado
 */
import { QUIEN_CERRO } from './chat.js';

/**
 * Quién cerró la conversación y cuándo, de lo que consta.
 *
 * El evento 'cerrada' del relevo es la fuente: trae el camino (`datos.por`),
 * el nombre de la persona si fue una, y la hora. Una legada sin eventos solo
 * conserva `atendida_por`, sin fecha confiable (`actualizado_en` cambia por
 * cualquier cosa): se nombra a la persona y no se inventa el día.
 *
 * @param {any[]|null|undefined} relevo  eventos del relevo, en orden
 * @param {any} conversacion
 * @returns {{ por: string|null, quien: string|null, en: string|null }|null}
 */
export function cierreDe(relevo, conversacion) {
  const eventos = Array.isArray(relevo) ? relevo : [];
  for (let i = eventos.length - 1; i >= 0; i--) {
    const ev = eventos[i];
    if (ev?.tipo !== 'cerrada') continue;
    const por = ev?.datos?.por ?? null;
    const quien = por === 'operador' ? (ev?.actor_nombre || '').trim() || null : null;
    return { por, quien, en: ev?.creado_en ?? null };
  }
  const atendidaPor = (conversacion?.atendida_por || '').trim();
  return atendidaPor ? { por: 'operador', quien: atendidaPor, en: null } : null;
}

/** «31/10 a las 13:43», en la hora local de quien mira. */
function cuando(/** @type {string} */ iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const dia = new Intl.DateTimeFormat('es', { day: '2-digit', month: '2-digit' }).format(d);
  const hora = new Intl.DateTimeFormat('es', { hour: '2-digit', minute: '2-digit' }).format(d);
  return `${dia} a las ${hora}`;
}

/**
 * La línea de estado.
 *
 * @param {{
 *   estado: string|null|undefined,
 *   iaEnPausa?: boolean, escalada?: boolean, atendida?: boolean,
 *   esMia?: boolean, asignadaA?: string|null,
 *   cierre?: ReturnType<typeof cierreDe>
 * }} c
 * @returns {Estado}
 */
export function estadoDeLaConversacion(c) {
  if (c.estado === 'cerrada') {
    const partes = [];
    const cierre = c.cierre ?? null;
    if (cierre?.quien) partes.push(`la resolvió ${cierre.quien}`);
    else if (cierre?.por && QUIEN_CERRO[/** @type {keyof typeof QUIEN_CERRO} */ (cierre.por)]) {
      partes.push(QUIEN_CERRO[/** @type {keyof typeof QUIEN_CERRO} */ (cierre.por)]);
    }
    const momento = cierre?.en ? cuando(cierre.en) : null;
    if (momento) partes.push(`el ${momento}`);
    return {
      clave: 'cerrada',
      tono: 'neutro',
      texto: partes.length ? `Cerrada · ${partes.join(' ')}` : 'Cerrada',
      // Lo que importa a quien está por escribir. Reemplaza al aviso gris que
      // repetía lo mismo debajo del hilo.
      detalle: 'Un mensaje nuevo, tuyo o del cliente, abre una conversación nueva.'
    };
  }
  if (c.iaEnPausa && c.atendida) {
    return { clave: 'respondida', tono: 'humano', texto: 'Respondida por el equipo', detalle: 'la IA no responde' };
  }
  if (c.escalada && c.esMia) {
    return { clave: 'mia', tono: 'humano', texto: 'Asignada a mí', detalle: 'la IA no responde' };
  }
  if (c.escalada && c.asignadaA) {
    return { clave: 'de-otro', tono: 'humano', texto: `La atiende ${c.asignadaA}`, detalle: 'la IA no responde' };
  }
  if (c.iaEnPausa) {
    return { clave: 'espera', tono: 'alerta', texto: 'Espera a una persona', detalle: 'la IA no responde' };
  }
  if (c.escalada) {
    // Escaló, pero no hay a quién esperar (agendada, o el CRM no tomó el
    // caso): el asistente SIGUE contestando. Ámbar y no rojo: está en riesgo,
    // pero el cliente no está esperando sin respuesta.
    return { clave: 'escalada', tono: 'aviso', texto: 'Escalada', detalle: 'el asistente sigue respondiendo' };
  }
  return { clave: 'ia', tono: 'ia', texto: 'La atiende la IA', detalle: 'Dexter responde solo' };
}
