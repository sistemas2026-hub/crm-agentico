/**
 * Las acciones de la paleta ⌘K, antes de escribir nada  --  12/11/2026
 *
 * Hasta hoy eran «Nueva negociación», «Ir a Hoy», «Ir a Tareas» e «Ir a
 * Facturas»: los atajos de un CRM de ventas. Las pantallas donde trabaja un ISP
 * —la Bandeja, el Supervisor NOC, Instalaciones, Agentes— no estaban.
 *
 * Mismo criterio que el menú (`lib/v2/menu.js`): una acción a una pantalla que
 * el rol no puede abrir no se ofrece, y una a un módulo que la empresa ocultó
 * tampoco. No es control de acceso: cada ruta lo sigue haciendo en su servidor.
 */
import { ROLES_GESTION } from './menu.js';
import { ocultosConocidos } from './modulos.js';

/**
 * @typedef {{ kind: string, id: string, title: string, meta: string, href: string,
 *             icono: string, roles?: string[], modulo?: string }} Accion
 */

/** @type {Accion[]} */
export const ACCIONES = [
  { kind: 'Acciones', id: 'act-hoy', title: 'Ir a Hoy', meta: '', href: '/', icono: 'Sun' },
  { kind: 'Acciones', id: 'act-bandeja', title: 'Abrir la Bandeja', meta: 'Conversaciones', href: '/conversaciones', icono: 'MessageCircle' },
  { kind: 'Acciones', id: 'act-por-atender', title: 'Clientes que esperan a una persona', meta: 'Conversaciones', href: '/conversaciones?pestana=por-atender', icono: 'MessageCircle' },
  { kind: 'Acciones', id: 'act-supervisor', title: 'Ir al Supervisor NOC', meta: '', href: '/supervisor-noc', icono: 'Activity', roles: ROLES_GESTION },
  { kind: 'Acciones', id: 'act-instalaciones', title: 'Instalaciones por decidir', meta: 'Instalaciones', href: '/instalaciones', icono: 'ClipboardCheck' },
  { kind: 'Acciones', id: 'act-agentes', title: 'Configurar los agentes', meta: 'Agentes', href: '/agentes', icono: 'Bot' },
  { kind: 'Acciones', id: 'act-ticket', title: 'Nuevo ticket', meta: 'Tickets', href: '/tickets/new', icono: 'Plus' },
  { kind: 'Acciones', id: 'act-tareas', title: 'Ir a Tareas', meta: '', href: '/tasks', icono: 'CircleCheck', modulo: 'tasks' },
  { kind: 'Acciones', id: 'act-facturas', title: 'Ir a Facturas', meta: '', href: '/invoices', icono: 'Receipt', modulo: 'invoices' }
];

/**
 * @param {{ role?: string, ocultos?: unknown }} contexto
 * @returns {Accion[]}
 */
export function accionesDePaleta({ role = 'USER', ocultos = [] } = {}) {
  const fuera = ocultosConocidos(ocultos);
  return ACCIONES.filter(
    (a) => (!a.roles || a.roles.includes(role)) && (!a.modulo || !fuera.has(a.modulo))
  );
}
