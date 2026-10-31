/**
 * Quién atiende, y quién figura en el caso del CRM (D28).
 *
 * SON DOS COSAS DISTINTAS Y LA PANTALLA NO PUEDE MEZCLARLAS
 * ---------------------------------------------------------
 *   A cargo en Dexter    UNA persona. Es la autoridad: decide quién atiende
 *                        la conversación, y nada de lo que pase en el CRM la
 *                        cambia.
 *   Asignados en CRM     un CONJUNTO. `Case.assigned_to` es ManyToMany, así
 *                        que puede tener a varias personas, y las que no puso
 *                        Dexter son colaboración de alguien más.
 *
 * Por eso acá no se dice «dueño del caso» en ningún lado. Ese nombre promete
 * una sola persona y una autoridad que ese campo no tiene, y quien lo lea va a
 * intentar «corregirlo» borrando a los demás.
 *
 * LA DIFERENCIA SE MUESTRA, NO SE CORRIGE SOLA
 * --------------------------------------------
 * Si el operador de Dexter no está en el caso, eso es algo pendiente de
 * sincronizar — se agrega, aditivamente. Si hay otros, son colaboradores y se
 * quedan: el CRM no guarda quién creó cada asignación, así que nada distingue
 * una automática vieja de un segundo técnico que un supervisor sumó hoy.
 * Quitarlos sobre una suposición borra trabajo que no se recupera.
 */

/** Cómo se llama cada cosa. Fijo acá para que no se reinvente por pantalla. */
export const ETIQUETAS = {
  dexter: 'A cargo en Dexter',
  crm: 'Asignados en CRM',
  colaboradores: 'Colaboradores en el CRM'
};

/**
 * Lo que la pantalla necesita saber, ya resuelto por el backend
 * (nucleo/relevo/asignados_crm.py::diferencia).
 */
export function vistaDeAsignados(diferencia, nombreEnDexter = '') {
  const d = diferencia ?? {};
  const colaboradores = (d.colaboradores ?? []).map(nombreDePerfil);

  return {
    aCargoEnDexter: nombreEnDexter || '',
    colaboradores,
    // Pendiente, no error: el efecto está encolado y se reintenta solo.
    pendienteDeSincronizar: d.falta_agregar === true,
    // El operador no tiene perfil en esta organización del CRM. No es una
    // falla del sistema ni algo que se pueda arreglar reintentando.
    sinPerfilEnCrm: d.sin_perfil === true,
    hayAlgoQueMostrar:
      d.falta_agregar === true || d.sin_perfil === true || colaboradores.length > 0
  };
}

export function nombreDePerfil(perfil) {
  const detalles = perfil?.user_details ?? {};
  return detalles.name || detalles.email || '—';
}

/**
 * La línea que explica la diferencia, en palabras.
 *
 * Nunca dice que algo está mal: una asignación que todavía no se reflejó es
 * trabajo en curso, y un colaborador de más es información, no un defecto.
 */
export function explicacion(vista) {
  if (vista?.sinPerfilEnCrm) {
    return 'Quien atiende no tiene perfil en esta organización del CRM, así que el caso no lo puede mostrar.';
  }
  if (vista?.pendienteDeSincronizar) {
    return 'Todavía no figura en el caso. Se está sincronizando.';
  }
  if (vista?.colaboradores?.length) {
    return 'Otras personas también figuran en el caso. Dexter no las quita.';
  }
  return '';
}
