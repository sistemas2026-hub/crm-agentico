/**
 * Cómo se dice en Programación quién asignó una orden y si al técnico le llegó
 * el aviso (28/10/2026). Fuera del componente para poder probarlo: es justo lo
 * que una persona lee para saber qué hizo el Supervisor solo.
 */

/**
 * «Supervisor · 09:07», «Mayra · 08:15», o con la fecha si fue otro día
 * («Supervisor · 27/10 18:07»). Sin evento, «Sin registro»: no se adivina.
 *
 * @param {{ asignada_por?: string, asignada_por_nombre?: string, asignada_en?: string | null }} fila
 * @param {string} dia AAAA-MM-DD, el día que se está mirando
 */
export function quienLaAsigno(fila, dia) {
  if (!fila?.asignada_por) return 'Sin registro';
  const quien = fila.asignada_por_nombre || (fila.asignada_por === 'supervisor' ? 'Supervisor' : 'Una persona');
  const iso = fila.asignada_en ?? '';
  //  La hora viene en el reloj de la empresa (con su desfase): se lee tal cual,
  //  sin pasarla por el reloj del navegador.
  const hora = iso.slice(11, 16);
  if (!hora) return quien;
  const fecha = iso.slice(0, 10);
  if (fecha && fecha !== dia) return `${quien} · ${fecha.slice(8, 10)}/${fecha.slice(5, 7)} ${hora}`;
  return `${quien} · ${hora}`;
}

/**
 * «Enviado al teléfono» y no «Avisado»: Google lo aceptó para un teléfono, que
 * no es lo mismo que leído. «No llegó al teléfono»: había teléfono y el envío
 * no salió (rechazado, o el teléfono se registró después del aviso).
 *
 * @param {string} aviso
 */
export function textoDelAviso(aviso) {
  switch (aviso) {
    case 'avisado':
      return 'Enviado al teléfono';
    case 'no_llego':
      return 'No llegó al teléfono';
    case 'sin_telefono':
      return 'Sin teléfono registrado';
    case 'sin_aviso':
      return 'Sin aviso';
    default:
      return '';
  }
}

/** @param {string} prioridad */
export function textoDePrioridad(prioridad) {
  return { alta: 'Alta', media: 'Media', baja: 'Baja' }[prioridad] ?? (prioridad || '—');
}
