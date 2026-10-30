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
 * Los tiempos de una orden (30/10/2026, «¿cuánto han demorado?»): «28 min en
 * camino · 40 min en sitio», o «en sitio hace 35 min» si sigue ahí. Si llegó
 * OTRO día y nadie la cerró, «en sitio desde el 15/10 18:43»: no «21159 min».
 * Vacío si todavía no salió. Lo calcula el servidor (`campo/tiempos_del_dia.py`).
 *
 * @param {{ traslado_min?: number | null, en_sitio_min?: number | null, en_sitio_hace_min?: number | null, en_sitio_desde?: string | null } | null | undefined} t
 */
export function textoDeTiempos(t) {
  if (!t) return '';
  const partes = [];
  if (t.traslado_min != null) partes.push(`${t.traslado_min} min en camino`);
  if (t.en_sitio_min != null) partes.push(`${t.en_sitio_min} min en sitio`);
  else if (t.en_sitio_hace_min != null) partes.push(`en sitio hace ${t.en_sitio_hace_min} min`);
  else if (t.en_sitio_desde) partes.push(`en sitio desde el ${t.en_sitio_desde}`);
  return partes.join(' · ');
}

/**
 * El día de una cuadrilla en una línea (30/10/2026): «Salió 07:42 · 3 de 6
 * hechas · en sitio en OT #12 desde 09:10», o «Todavía no sale · 0 de 6».
 *
 * @param {{ salio?: string | null, hechas: number, total: number, en_curso?: { numero: number, estado: string, desde?: string | null } | null } | null | undefined} r
 */
export function textoDelDiaDeLaCuadrilla(r) {
  if (!r) return '';
  const partes = [r.salio ? `Salió ${r.salio}` : 'Todavía no sale', `${r.hechas} de ${r.total} hechas`];
  if (r.en_curso) {
    const donde = r.en_curso.estado === 'en_sitio' ? 'en sitio en' : 'en camino a';
    partes.push(`${donde} OT #${r.en_curso.numero}${r.en_curso.desde ? ` desde ${r.en_curso.desde}` : ''}`);
  }
  return partes.join(' · ');
}

/**
 * La regla de los 30 minutos de una orden, como la calcula el servidor
 * (`services/salud_seguimiento.py`): «Sin reporte hace 38 min» si venció, o
 * por qué no corre. Vacío si está al día o no aplica.
 *
 * @param {{ tipo: string, minutos_desde_la_referencia?: number | null } | null | undefined} s
 */
export function textoDeSeguimiento(s) {
  if (!s) return '';
  if (s.tipo === 'vencido') return `Sin reporte hace ${s.minutos_desde_la_referencia ?? '?'} min`;
  if (s.tipo === 'pausado_noc') return 'Pausado: espera al NOC';
  if (s.tipo === 'pausado_novedad') return 'Pausado por la novedad de la cuadrilla';
  return '';
}

/**
 * Cuándo fue una novedad de la cuadrilla (30/10/2026, novedad-de-cuadrilla.md):
 * «desde las 10:12 · hasta las 10:42», «desde las 10:12 · el resto del día», y
 * si ya terminó, «de 10:12 a 10:40» (lo que llegue antes: «Ya seguí» o su
 * hora). Las horas vienen en la de la empresa (`campo/novedades.py::a_json`).
 *
 * @param {{ avisada_en: string, hasta?: string | null, resuelta_en?: string | null, vigente?: boolean }} n
 */
export function textoDeNovedad(n) {
  /** @param {string | null | undefined} iso */
  const hm = (iso) => (iso ?? '').slice(11, 16);
  const desde = hm(n.avisada_en);
  if (n.vigente) {
    return n.hasta ? `desde las ${desde} · hasta las ${hm(n.hasta)}` : `desde las ${desde} · el resto del día`;
  }
  const fin = n.resuelta_en && (!n.hasta || n.resuelta_en < n.hasta) ? n.resuelta_en : n.hasta;
  return fin ? `de ${desde} a ${hm(fin)}` : `desde las ${desde}`;
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
