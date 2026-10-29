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

/**
 * Cómo se marca la SIGUIENTE orden de una cuadrilla (29/10/2026): «Empieza por
 * esta» si la cuadrilla todavía no arrancó ninguna, «Sigue esta» si ya hay una
 * en camino, en sitio o terminada.
 *
 * @param {{ estado: string }[]} ordenes
 */
export function textoDeLaSiguiente(ordenes) {
  const arranco = (ordenes ?? []).some((o) =>
    ['en_camino', 'en_sitio', 'completada_campo', 'cerrada'].includes(o.estado)
  );
  return arranco ? 'Sigue esta' : 'Empieza por esta';
}

/**
 * Cuándo vence el compromiso de la orden (29/10/2026), contra el día que se
 * mira: «Vence hoy», «Vence mañana», «Vence el 31/10», «Venció el 28/10». Sin
 * fecha, «Sin vencimiento»: no se inventa.
 *
 * La fecha viene en el reloj de la empresa: se lee el día tal cual.
 *
 * @param {string | null | undefined} iso
 * @param {string} dia AAAA-MM-DD
 */
export function textoDelVencimiento(iso, dia) {
  return vencimiento(iso, dia).texto;
}

/**
 * Con qué tono se pinta el vencimiento en la tarjeta de la orden (29/10/2026):
 * «vencida» en rojo, «hoy» en ámbar, «proxima» y «sin» en gris. Sale de la misma
 * cuenta que el texto, para que el color y la frase no se contradigan.
 *
 * @param {string | null | undefined} iso
 * @param {string} dia AAAA-MM-DD
 */
export function tonoDelVencimiento(iso, dia) {
  return vencimiento(iso, dia).tono;
}

/**
 * @param {string | null | undefined} iso
 * @param {string} dia
 * @returns {{ texto: string, tono: 'vencida' | 'hoy' | 'proxima' | 'sin' }}
 */
function vencimiento(iso, dia) {
  const fecha = (iso ?? '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha) || !/^\d{4}-\d{2}-\d{2}$/.test(dia ?? '')) {
    return { texto: 'Sin vencimiento', tono: 'sin' };
  }
  const dias = Math.round((Date.parse(`${fecha}T00:00:00Z`) - Date.parse(`${dia}T00:00:00Z`)) / 86400000);
  const corta = `${fecha.slice(8, 10)}/${fecha.slice(5, 7)}`;
  if (dias < 0) return { texto: `Venció el ${corta}`, tono: 'vencida' };
  if (dias === 0) return { texto: 'Vence hoy', tono: 'hoy' };
  if (dias === 1) return { texto: 'Vence mañana', tono: 'proxima' };
  return { texto: `Vence el ${corta}`, tono: 'proxima' };
}
