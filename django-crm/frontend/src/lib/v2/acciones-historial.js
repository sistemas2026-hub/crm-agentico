/**
 * Los verbos de la linea de tiempo, en español.
 *
 * El CRM guarda el verbo en ingles y su propia etiqueta tambien lo esta
 * ("Created", "Assigned", "Status Changed"), asi que la linea de tiempo era el
 * unico lugar de la pantalla que hablaba en otro idioma.
 *
 * La clave es el CODIGO (`action`), no la etiqueta que manda el servidor: el
 * codigo es lo estable -- esta en `ACTION_CHOICES` del modelo y no cambia --
 * mientras que la etiqueta se puede reescribir sin que nadie avise.
 *
 * Un verbo que no este aca cae a su propio codigo, legible pero sin traducir.
 * Preferible a esconderlo: un evento que ocurrio y no se ve es peor para
 * auditar que uno que se ve en ingles.
 */
export const ACCION_LABEL = {
  CREATE: 'Ticket creado',
  UPDATE: 'Ticket modificado',
  DELETE: 'Ticket eliminado',
  VIEW: 'Ticket visto',
  COMMENT: 'Respuesta agregada',
  ASSIGN: 'Asignado',
  STATUS_CHANGED: 'Estado cambiado',
  PRIORITY_CHANGED: 'Prioridad cambiada',
  ROUTED: 'Derivado',
  ESCALATED: 'Escalado',
  REOPENED: 'Reabierto',
  MERGED: 'Unido a otro ticket',
  MERGE_TARGET: 'Recibió otro ticket',
  UNMERGED: 'Separado',
  UNMERGE_TARGET: 'Separación recibida',
  LINKED_SOLUTION: 'Artículo enlazado',
  UNLINKED_SOLUTION: 'Artículo desenlazado',
  WATCHED: 'Alguien lo sigue',
  UNWATCHED: 'Dejó de seguirse',
  MENTIONED: 'Mención',
  APPROVAL_REQUESTED: 'Aprobación pedida',
  APPROVED: 'Aprobado',
  REJECTED: 'Rechazado',
  APPROVAL_CANCELLED: 'Aprobación cancelada',
  LINKED_ASSET: 'Equipo enlazado',
  UNLINKED_ASSET: 'Equipo desenlazado',
  LINKED_JIRA: 'Jira enlazado',
  LINKED_PARENT: 'Ticket padre enlazado',
  UNLINKED_PARENT: 'Ticket padre desenlazado',
  PARENT_CLOSED_CASCADE: 'Cerrado con su ticket padre',
  TIME_LOGGED: 'Tiempo registrado'
};

/**
 * @param {{ action?: string, label?: string }} evento
 * @returns {string}
 */
export function accionLegible(evento) {
  const codigo = evento?.action ?? '';
  if (ACCION_LABEL[codigo]) return ACCION_LABEL[codigo];
  // Sin traduccion: el codigo crudo, pero sin los guiones bajos.
  const crudo = (codigo || evento?.label || '').replace(/_/g, ' ').toLowerCase().trim();
  return crudo ? crudo[0].toUpperCase() + crudo.slice(1) : 'Actividad';
}
