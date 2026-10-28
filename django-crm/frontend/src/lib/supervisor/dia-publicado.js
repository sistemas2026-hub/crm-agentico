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
  const cuando = momento(fila.asignada_en, dia);
  return cuando ? `${quien} · ${cuando}` : quien;
}

/**
 * «09:07», o «27/10 18:07» si no es el día que se mira. Vacío sin hora.
 *
 * La hora viene en el reloj de la empresa (con su desfase): se lee tal cual,
 * sin pasarla por el reloj del navegador.
 *
 * @param {string | null | undefined} iso
 * @param {string} dia AAAA-MM-DD
 */
function momento(iso, dia) {
  const texto = iso ?? '';
  const hora = texto.slice(11, 16);
  if (!hora) return '';
  const fecha = texto.slice(0, 10);
  if (fecha && fecha !== dia) return `${fecha.slice(8, 10)}/${fecha.slice(5, 7)} ${hora}`;
  return hora;
}

/**
 * Lo que la app de UNA persona debería tener (28/10/2026): «Jeider Amell: 2
 * órdenes · sin teléfono registrado · última conexión 10:15».
 *
 * La tarjeta cuenta las órdenes de toda la cuadrilla; la app, las de la cuenta
 * con que se entró. Lo que publica el Supervisor va a todos los de la
 * cuadrilla; lo que se despacha a mano, a uno solo.
 *
 * @param {{ nombre: string, ordenes: number, telefono: boolean, ultimo_contacto: string | null }} p
 * @param {string} dia AAAA-MM-DD
 */
export function lineaDePersona(p, dia) {
  const partes = [`${p.nombre}: ${p.ordenes} ${p.ordenes === 1 ? 'orden' : 'órdenes'}`];
  if (!p.telefono) partes.push('sin teléfono registrado');
  partes.push(p.ultimo_contacto ? `última conexión ${momento(p.ultimo_contacto, dia)}` : 'nunca se conectó');
  return partes.join(' · ');
}

/**
 * Lo único que se afirma sobre la app: lo asignado DESPUÉS de su última
 * conexión todavía no puede estar en el teléfono. Vacío si no hay.
 *
 * @param {{ sin_bajar: number }} p
 */
export function textoSinBajar(p) {
  if (!p.sin_bajar) return '';
  return p.sin_bajar === 1
    ? '1 asignada después de su última conexión: su app todavía no la tiene. Que abra la app.'
    : `${p.sin_bajar} asignadas después de su última conexión: su app todavía no las tiene. Que abra la app.`;
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
