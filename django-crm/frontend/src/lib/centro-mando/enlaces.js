/**
 * A DÓNDE SE VA DESDE LA FICHA DE UN PUESTO  --  12/11/2026
 *
 * La auditoría del menú (§2, Centro de mando) midió cero enlaces salientes:
 * la ficha decía «qué puede hacer» un agente —la misma lectura que /agentes—
 * sin el botón para cambiarlo, y no llevaba a la conversación ni al tablero.
 * Tres pantallas para dos preguntas. Esto las une: desde el puesto se va a
 * configurarlo, a lo que atiende y, si es el Supervisor NOC, a su tablero.
 *
 * El Supervisor se reconoce por el nombre de su rol, `supervisor_noc`, que es
 * del PRODUCTO y no de una empresa: lo declara la organización por defecto
 * del motor (nucleo/config/organizacion.py). No es un slug de tenant.
 *
 * Mismo criterio que el menú: el tablero del Supervisor solo se ofrece a los
 * roles que su servidor deja pasar. No es control de acceso (la ruta se
 * defiende sola); es no mandar a nadie a rebotar.
 */
import { ROLES_GESTION } from '$lib/v2/menu.js';

export const AGENTE_SUPERVISOR = 'supervisor_noc';

/**
 * @param {{ agente?: string | null } | null | undefined} puesto
 * @param {string | null | undefined} rol  de quien mira, leído en el servidor
 * @returns {{ href: string, texto: string }[]}
 */
export function enlacesDelPuesto(puesto, rol) {
  const agente = puesto?.agente;
  if (!agente) return [];
  if (agente === AGENTE_SUPERVISOR) {
    const enlaces = [];
    if (rol && ROLES_GESTION.includes(rol)) {
      enlaces.push({ href: '/supervisor-noc', texto: 'Abrir su tablero' });
    }
    // Su tarjeta está en /agentes, entre los operativos: qué hace solo hoy.
    enlaces.push({ href: '/agentes', texto: 'Ver qué hace solo' });
    return enlaces;
  }
  return [
    // El ancla apunta a la tarjeta del agente; si la pantalla todavía no la
    // tiene, se llega igual a /agentes, arriba.
    { href: `/agentes#agente-${encodeURIComponent(agente)}`, texto: 'Configurar este agente' },
    { href: '/conversaciones', texto: 'Ver las conversaciones' }
  ];
}
