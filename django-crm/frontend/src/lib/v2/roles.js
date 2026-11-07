/**
 * Quien reparte el trabajo: los roles de gestion.
 *
 * Es el espejo de `cases/access.py::reparte_tickets` (backend), que es el que
 * de verdad decide: la pantalla solo deja de ofrecer lo que el backend negaria.
 * Mismo conjunto que ya usan campo y el Supervisor NOC (ROLES_GESTION).
 *
 * 23/10/2026: hasta ese dia, en Tickets solo ADMIN veia la cola entera y
 * asignaba; un supervisor que despacha cuadrillas no podia ver un ticket sin
 * asignar.
 */
export const ROLES_QUE_REPARTEN = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @param {string|null|undefined} rol */
export const reparteTickets = (rol) => ROLES_QUE_REPARTEN.has(rol ?? '');
