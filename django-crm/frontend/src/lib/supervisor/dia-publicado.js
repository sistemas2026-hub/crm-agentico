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
 * Lo que la app de UNA persona debería tener (28/10/2026), EN PASTILLAS desde
 * el 07/11/2026.
 *
 * La tarjeta cuenta las órdenes de toda la cuadrilla; la app, las de la cuenta
 * con que se entró. Lo que publica el Supervisor va a todos los de la
 * cuadrilla; lo que se despacha a mano, a uno solo.
 *
 * Era UNA frase gris con todo pegado —«JEIDER AMELL: 2 órdenes · sin teléfono
 * registrado · última conexión 10:15»— que en una tarjeta de 300 px ocupaba
 * dos renglones y dejaba el nombre y el problema con el mismo peso: en la
 * captura del usuario, tres personas por cuadrilla eran seis renglones grises
 * donde no se distinguía quién estaba mal. Ahora el nombre va aparte y cada
 * estado es una pastilla, y `falta` dice cuál de ellas es un problema —el
 * color lo elige la pantalla, acá se escribe el texto.
 *
 * `sin_bajar` entra como una pastilla más y no como un párrafo aparte: es otro
 * estado de la misma persona.
 *
 * @param {{ nombre: string, ordenes: number, telefono: boolean, ultimo_contacto: string | null, sin_bajar?: number }} p
 * @param {string} dia AAAA-MM-DD
 * @returns {{ nombre: string, pastillas: { texto: string, falta: boolean }[] }}
 */
export function pastillasDePersona(p, dia) {
  /** @type {{ texto: string, falta: boolean }[]} */
  const pastillas = [
    { texto: `${p.ordenes} ${p.ordenes === 1 ? 'orden' : 'órdenes'}`, falta: false }
  ];
  if (p.sin_bajar) pastillas.push({ texto: textoSinBajar({ sin_bajar: p.sin_bajar }), falta: true });
  if (!p.telefono) pastillas.push({ texto: 'sin teléfono registrado', falta: true });
  pastillas.push(
    p.ultimo_contacto
      ? { texto: `última conexión ${momento(p.ultimo_contacto, dia)}`, falta: false }
      : { texto: 'nunca se conectó', falta: true }
  );
  return { nombre: p.nombre, pastillas };
}

/**
 * CUÁNTAS ÓRDENES TIENE Y CUÁNTAS LE CABEN (07/11/2026). El usuario, con la
 * captura: «qué otro arreglo se puede hacer para que no se vea tan maluco».
 *
 * La cabecera decía `${cuantas} de ${tope} órdenes` sin mirar los números, y
 * con una cuadrilla pasada de cupo salía **«20 de 10 órdenes»**: se lee como
 * una pantalla rota, y lo que de verdad pasa —que tiene el doble de lo que le
 * cabe— queda escondido en una forma que nadie asocia con un problema.
 *
 * `pasada` lo deja decidir a la pantalla: acá se escribe el texto, no el color.
 *
 * @param {number} cuantas las órdenes publicadas de la cuadrilla
 * @param {number} [tope] su tope del día; 0 o ausente = sin tope
 * @returns {{ texto: string, pasada: boolean }}
 */
export function cupoDeLaCuadrilla(cuantas, tope) {
  const n = cuantas ?? 0;
  const plural = n === 1 ? 'orden' : 'órdenes';
  if (!tope) return { texto: `${n} ${plural}`, pasada: false };
  if (n > tope) {
    return { texto: `${n} ${plural} · ${n - tope} sobre el tope de ${tope}`, pasada: true };
  }
  //  El plural va con el TOPE, no con la cantidad: «1 de 10 orden» está mal.
  return { texto: `${n} de ${tope} ${tope === 1 ? 'orden' : 'órdenes'}`, pasada: false };
}

/**
 * Lo único que se afirma sobre la app: lo asignado DESPUÉS de su última
 * conexión todavía no puede estar en el teléfono. Vacío si no hay.
 *
 * CORTO A PROPÓSITO desde el 07/11/2026. Decía la frase entera —«N asignadas
 * después de su última conexión: su app todavía no las tiene. Que abra la
 * app.»— en CADA tarjeta, y en la captura del usuario eran cuatro párrafos
 * rojos idénticos de dos renglones. Cuatro avisos iguales no avisan: el rojo
 * deja de marcar nada y la pantalla se vuelve un muro. El porqué y qué hacer
 * se dicen UNA vez arriba, con `resumenDeLoSinBajar`; acá queda la marca de a
 * quién le pasa.
 *
 * @param {{ sin_bajar: number }} p
 */
export function textoSinBajar(p) {
  if (!p.sin_bajar) return '';
  return p.sin_bajar === 1 ? '1 sin bajar a su app' : `${p.sin_bajar} sin bajar a su app`;
}

/**
 * El aviso de las apps, UNA sola vez y arriba de las tarjetas: a cuántas
 * cuadrillas les pasa, cuántas órdenes son y qué hay que hacer. Vacío si no le
 * pasa a nadie.
 *
 * Se cuenta por CUADRILLA y por ÓRDENES, no por persona: lo que el Supervisor
 * decide con esto es a quién llamar, y llama a la cuadrilla.
 *
 * @param {{ personas?: { sin_bajar?: number }[] }[]} [cuadrillas]
 */
export function resumenDeLoSinBajar(cuadrillas) {
  let conCuantas = 0;
  let ordenes = 0;
  for (const c of cuadrillas ?? []) {
    const suyas = (c.personas ?? []).reduce((n, p) => n + (p.sin_bajar ?? 0), 0);
    if (suyas) {
      conCuantas += 1;
      ordenes += suyas;
    }
  }
  if (!conCuantas) return '';
  const cuales = conCuantas === 1 ? '1 cuadrilla no abrió la app' : `${conCuantas} cuadrillas no abrieron la app`;
  const cuantas = ordenes === 1
    ? '1 orden todavía no está en el teléfono'
    : `${ordenes} órdenes todavía no están en los teléfonos`;
  return `${cuales}: ${cuantas}. Que abran la app para recibirlas.`;
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

/*
 *  AQUÍ VIVÍA `textoDelDiaDeLaCuadrilla` (30/10/2026 – 07/11/2026). Escribía
 *  el día de una cuadrilla en una línea —«Salió 07:42 · 3 de 6 hechas · en
 *  sitio en OT #12 desde 09:10»— dentro de su tarjeta de Programación.
 *
 *  Se fue porque desde el 30/10 el cuadro de «Seguimiento de las cuadrillas»
 *  está arriba, en la MISMA pantalla y con la misma condición, y dice las tres
 *  cosas mejor: el estado y la OT como título, los minutos en grande, y
 *  «3 de 6 · salió 07:42» con su barra de avance. La línea de la tarjeta
 *  repetía eso en gris chico, cuatro veces, y era el renglón que más se
 *  parecía a relleno en la captura del usuario (07/11/2026).
 *
 *  No se reemplaza por nada: la pregunta «¿cómo va esta cuadrilla?» ya tiene
 *  su lugar. Si vuelve a hacer falta, está en el historial de git — pero
 *  entonces hay que decidir también qué deja de decir el cuadro de arriba.
 */

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
 * Los pasos del progreso de una orden, como en la app (30/10/2026).
 */
export const PASOS = ['Asignada', 'En camino', 'En sitio', 'Completada', 'Cerrada'];

/**
 * En qué paso está una orden (0-4), o -1 si no tiene progreso (cancelada).
 * Bloqueada y devuelta para corregir siguen «en sitio»: hay trabajo en la casa.
 *
 * @param {string} estado `estado_operativo` de la orden
 */
export function pasoDelProgreso(estado) {
  switch (estado) {
    case 'asignada':
      return 0;
    case 'en_camino':
      return 1;
    case 'en_sitio':
    case 'bloqueada':
    case 'correccion_requerida':
      return 2;
    case 'completada_campo':
      return 3;
    case 'cerrada':
      return 4;
    default:
      return -1;
  }
}

/**
 * Las que esperan cuadrilla, agrupadas por el motivo que dio el servidor, de
 * la más numerosa a la menos (30/10/2026: «que se puedan contraer»).
 *
 * @param {{ id: string, por_que?: string, motivo?: string }[]} esperan
 * @returns {{ motivo: string, ordenes: any[] }[]}
 */
export function gruposQueEsperan(esperan) {
  /** @type {Map<string, any[]>} */
  const grupos = new Map();
  for (const o of esperan ?? []) {
    const motivo = (o.por_que || o.motivo || 'Sin motivo').trim();
    if (!grupos.has(motivo)) grupos.set(motivo, []);
    /** @type {any[]} */ (grupos.get(motivo)).push(o);
  }
  return [...grupos].map(([motivo, ordenes]) => ({ motivo, ordenes }))
    .sort((a, b) => b.ordenes.length - a.ordenes.length);
}

/**
 * Cómo quedó el ticket del ISP de una orden cerrada (30/10/2026).
 *
 * @param {{ estado: string, detalle?: string } | null | undefined} t
 */
export function textoDelTicket(t) {
  switch (t?.estado) {
    case 'cerrado':
      return 'Cerrado en el sistema del ISP';
    case 'no_cerrado':
      return `No se pudo cerrar en el sistema del ISP${t.detalle ? `: ${t.detalle}` : ''}`;
    case 'sin_ticket':
      return 'La orden no tiene ticket del ISP';
    default:
      return 'Sin registro de cómo quedó el ticket';
  }
}

/**
 * Quién cerró una orden (30/10/2026).
 *
 * @param {{ de: string, nombre?: string } | null | undefined} q
 */
export function textoDeQuien(q) {
  if (q?.de === 'persona') return `${q.nombre} la aprobó y la cerró`;
  if (q?.de === 'supervisor') return 'El Supervisor la aprobó y la cerró';
  return 'Se cerró sin una aprobación registrada';
}

/**
 * Los días de la pestaña Cerradas: hoy, ayer o los últimos 7 (hoy incluido).
 *
 * @param {string} rango 'hoy' | 'ayer' | '7d'
 * @param {string} hoy AAAA-MM-DD, el día de la empresa
 */
export function rangoDeCerradas(rango, hoy) {
  /** @param {number} n */
  const menos = (n) => new Date(Date.parse(`${hoy}T12:00:00Z`) - n * 86400000).toISOString().slice(0, 10);
  if (rango === 'ayer') return { desde: menos(1), hasta: menos(1) };
  if (rango === '7d') return { desde: menos(6), hasta: hoy };
  return { desde: hoy, hasta: hoy };
}

/**
 * El porqué de una devolución, ya escrito (30/10/2026, revision-del-cierre.md):
 * lo que el Supervisor encontró que no está bien o no se sabe, una línea por
 * punto. Si todo estaba bien, vacío: quien devuelve igual tiene que decir por
 * qué.
 *
 * @param {{ puntos?: { ok: boolean | null, texto: string }[] } | null | undefined} r
 */
export function motivosDeLaRevision(r) {
  return (r?.puntos ?? [])
    .filter((p) => p.ok !== true)
    .map((p) => p.texto)
    .join('\n');
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

/**
 * LAS ALERTAS DEL DÍA (31/10/2026). Lo que necesita que alguien actúe, junto y
 * ordenado por gravedad. No pide nada nuevo al servidor: se arma con lo que la
 * pantalla ya cargó (`del_dia` y el material), así que no puede decir algo que
 * las tarjetas no digan.
 *
 * Cada alerta: `{ clave, tono, texto, donde }`. `tono` manda el orden —
 * 'grave' antes que 'avisa' antes que 'dato'— y dentro de un tono se respeta
 * el orden en que se descubrieron.
 *
 * @param {any} publicado lo que devuelve `campo/dia_publicado.py::del_dia`
 * @param {any} material lo del material del día, o null si no se pudo leer
 * @returns {{ clave: string, tono: 'grave'|'avisa'|'dato', texto: string, donde: string }[]}
 */
export function alertasDelDia(publicado, material) {
  /** @type {{ clave: string, tono: 'grave'|'avisa'|'dato', texto: string, donde: string }[]} */
  const salida = [];
  for (const c of publicado?.cuadrillas ?? []) {
    const donde = c.cuadrilla ?? '';
    //  DEJÓ DE REPORTAR: lo más grave, porque nadie sabe qué pasa.
    if (c.sin_reporte) {
      salida.push({
        clave: `sin_reporte|${c.jornada}`,
        tono: 'grave',
        texto: `OT #${c.sin_reporte.numero} sin reporte hace ${c.sin_reporte.minutos} min`,
        donde
      });
    }
    //  SIN APP: no recibe órdenes ni recordatorios. Se nombra a quién.
    const sinApp = (c.personas ?? []).filter((p) => !p.telefono || !p.ultimo_contacto);
    if (sinApp.length) {
      salida.push({
        clave: `sin_app|${c.jornada}`,
        tono: 'grave',
        texto: sinApp.length === 1
          ? `${sinApp[0].nombre} no tiene la app: no le llegan las órdenes ni los avisos`
          : `${sinApp.length} técnicos sin la app: no les llegan las órdenes ni los avisos`,
        donde
      });
    }
    //  SOBRECARGADA: más órdenes que su tope del día.
    const cuantas = (c.ordenes ?? []).length;
    if (c.tope && cuantas > c.tope) {
      salida.push({
        clave: `sobrecarga|${c.jornada}`,
        tono: 'grave',
        texto: `${cuantas} órdenes para un tope de ${c.tope}`,
        donde
      });
    }
    //  NOVEDAD VIGENTE: la cuadrilla avisó algo y el reloj no corre. Solo las
    //  vigentes: una resuelta hace tres horas no es algo que atender.
    for (const n of c.novedades ?? []) {
      if (!n.vigente) continue;
      salida.push({
        clave: `novedad|${n.id ?? `${c.jornada}|${salida.length}`}`,
        tono: 'avisa',
        texto: [n.tipo_texto || 'Avisó una novedad', textoDeNovedad(n)].filter(Boolean).join(' · '),
        donde
      });
    }
  }
  //  MATERIAL: una sola línea, no una por bodega.
  const faltan = material?.cuentas?.con_faltantes ?? 0;
  if (faltan) {
    salida.push({
      clave: 'material',
      tono: 'avisa',
      texto: faltan === 1 ? '1 cuadrilla sale con material faltante'
        : `${faltan} cuadrillas salen con material faltante`,
      donde: 'Material del día'
    });
  }
  //  TERMINADAS SIN CERRAR: esperan que alguien las apruebe.
  const porRevisar = (publicado?.por_revisar ?? []).length;
  if (porRevisar) {
    salida.push({
      clave: 'por_revisar',
      tono: 'avisa',
      texto: porRevisar === 1 ? '1 orden terminada espera que la aprueben'
        : `${porRevisar} órdenes terminadas esperan que las aprueben`,
      donde: 'Por revisar'
    });
  }
  //  ESPERAN CUADRILLA: no es una falla, es trabajo sin repartir.
  const esperan = publicado?.cuentas?.esperan ?? 0;
  if (esperan) {
    salida.push({
      clave: 'esperan',
      tono: 'dato',
      texto: `${esperan} ${esperan === 1 ? 'orden espera' : 'órdenes esperan'} cuadrilla`,
      donde: 'Sin repartir'
    });
  }
  const rango = { grave: 0, avisa: 1, dato: 2 };
  return salida
    .map((a, i) => ({ a, i }))
    .sort((x, y) => rango[x.a.tono] - rango[y.a.tono] || x.i - y.i)
    .map(({ a }) => a);
}

/**
 * SI SE DIBUJA EL MAPA (01/11/2026): solo cuando lo que se mira es HOY.
 *
 * Una fecha pasada no tiene posiciones --no se guarda el recorrido-- y
 * mostrar las de ahora bajo otra fecha sería mentir sobre dónde estuvo
 * alguien. Sin saber cuál es el día de la empresa tampoco se dibuja: adivinar
 * con el reloj del navegador fue justo el defecto que dejó el mapa invisible.
 *
 * Es una función y no una condición escrita en la plantilla porque una
 * condición dentro de un `{#if}` no la mira ninguna prueba: la mutación que
 * la borraba sobrevivía.
 *
 * @param {string | null | undefined} dia el día que se está mirando
 * @param {string | null | undefined} hoy el día de la empresa, del servidor
 */
export function seDibujaElMapa(dia, hoy) {
  return Boolean(hoy) && dia === hoy;
}
