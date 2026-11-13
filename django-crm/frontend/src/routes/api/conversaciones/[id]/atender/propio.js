/**
 * Quién es «yo» entre los responsables posibles de un ticket del CRM.
 *
 * QUÉ SE COMPARA, Y POR QUÉ NO ERA «name === email»  (12/11/2026)
 * La auditoría del menú leyó `o.name === locals.user.email` como un
 * emparejamiento de nombre contra correo. No lo es: `owners[].name` es
 * `user__email` (lib/server/v2/tickets.js, cases/views.py), así que se
 * compara correo contra correo, y el correo es el USERNAME_FIELD de Django,
 * único por usuario (common/models.py). El perfil del CRM no trae el
 * `user_id` del JWT, así que el correo es el identificador real que hay.
 *
 * Lo que sí era frágil y se cierra acá: un correo vacío en la sesión
 * emparejaba con el primer perfil sin correo (`'' === ''`). Ahora un correo
 * vacío no empareja con nadie, y si por algún dato sucio aparecieran dos
 * perfiles con el mismo correo, tampoco: asignarle el ticket a la persona
 * equivocada es peor que no asignarlo y decirlo.
 *
 * @param {{ id: string, name?: string }[]} owners
 * @param {unknown} email
 * @returns {{ propio: { id: string, name?: string } | null, motivo: '' | 'sin_correo' | 'sin_perfil' | 'ambiguo' }}
 */
export function perfilPropio(owners, email) {
  const yo = typeof email === 'string' ? email.trim().toLowerCase() : '';
  if (!yo) return { propio: null, motivo: 'sin_correo' };
  const coinciden = (owners ?? []).filter(
    (o) => typeof o?.name === 'string' && o.name.trim().toLowerCase() === yo
  );
  if (coinciden.length === 1) return { propio: coinciden[0], motivo: '' };
  return { propio: null, motivo: coinciden.length ? 'ambiguo' : 'sin_perfil' };
}

/** Lo que se le dice a quien tomó la conversación cuando el ticket no quedó a su nombre. */
export const AVISO_TICKET = {
  sin_correo:
    'Tomaste la conversación, pero tu sesión no tiene correo: el ticket del CRM quedó sin asignarte.',
  sin_perfil:
    'Tomaste la conversación, pero tu usuario no figura entre los responsables de tickets del CRM: el ticket quedó sin asignarte.',
  ambiguo:
    'Tomaste la conversación, pero tu correo aparece en más de un perfil del CRM: el ticket quedó sin asignarte para no dárselo a otra persona.',
  fallo_crm:
    'Tomaste la conversación, pero el CRM no aceptó asignarte el ticket. Asignalo desde la pestaña Caso.'
};
