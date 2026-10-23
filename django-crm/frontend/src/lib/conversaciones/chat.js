/**
 * El CHAT de un número: sus conversaciones anteriores y la actual, en un solo
 * hilo, como WhatsApp.
 *
 * POR QUÉ EXISTE  --  21/10/2026 (contrato §4.5, C19)
 * ---------------------------------------------------
 * Reportado: "cuando uno escribe desde el mismo numero de telefono se crea una
 * nueva conversacion como si fuera otro numero nuevo". Es la conducta del
 * contrato --una conversación cerrada no se reabre y lo siguiente que escribe
 * ese número abre otra--, pero la pantalla mostraba cada una suelta. El motor
 * entrega las anteriores (GET /conversaciones/<id>/hilo); esto las encadena.
 *
 * Vive fuera del componente para poder probarse: la marca de cierre dice SOLO
 * lo que quedó registrado, y esa regla se rompe sin que la pantalla se vea
 * rota.
 */

/** Quién cerró, en palabras. Las claves son las de `cerrada_por_tipo`. */
const QUIEN_CERRO = {
  operador: 'la cerró una persona',
  ia_cliente: 'el cliente confirmó con la IA',
  cliente: 'el cliente confirmó',
  plazo: 'cerrada por plazo sin respuesta',
  inactividad: 'cerrada por inactividad'
};

/**
 * El texto de la marca entre una conversación y la siguiente.
 *
 * Sin hora ni motivo si el cierre no los dejó: el cierre por inactividad de
 * hoy (T18) no escribe quién cerró ni su evento, y afirmar algo que no se
 * sabe es peor que no decirlo.
 *
 * @param {{por?: string|null, en?: string|null}|null|undefined} cierre
 * @param {(iso: string) => string} [formatoHora]
 */
export function textoDeCierre(cierre, formatoHora) {
  const partes = ['Conversación cerrada'];
  if (cierre?.en && formatoHora) partes.push(formatoHora(cierre.en));
  const quien = cierre?.por ? QUIEN_CERRO[/** @type {keyof typeof QUIEN_CERRO} */ (cierre.por)] : null;
  if (quien) partes.push(quien);
  return partes.join(' · ');
}

/**
 * Los elementos del hilo: {tipo:'mas'} si hay más atrás, después cada
 * conversación anterior con sus separadores de día y su marca de cierre, y al
 * final la actual. Los mensajes de las anteriores llevan `deOtraConversacion`
 * (no se reintentan desde acá) y su `conversation_id`.
 *
 * @param {any[]} tramos              lo que devuelve /hilo, del más viejo al más nuevo
 * @param {any[]} mensajes            los de la conversación actual
 * @param {{diaDe: (iso: string) => string, etiquetaDia: (iso: string) => string,
 *          formatoHora?: (iso: string) => string, hayAnteriores?: boolean}} opciones
 */
export function itemsDelChat(tramos, mensajes, { diaDe, etiquetaDia, formatoHora, hayAnteriores = false }) {
  /** @type {any[]} */
  const salida = [];
  if (hayAnteriores) {
    salida.push({ tipo: 'mas', clave: 'mas', texto: 'Ver conversaciones anteriores' });
  }
  /** @type {string|null} */
  let dia = null;
  /** @param {any} m @param {boolean} deOtra */
  const poner = (m, deOtra) => {
    const d = diaDe(m.creado_en);
    if (d !== dia) {
      salida.push({ tipo: 'dia', clave: `d-${d}-${salida.length}`, texto: etiquetaDia(m.creado_en) });
      dia = d;
    }
    salida.push({ tipo: 'msg', clave: `m-${salida.length}`, m: deOtra ? { ...m, deOtraConversacion: true } : m });
  };
  for (const t of tramos || []) {
    for (const m of t.mensajes || []) poner(m, true);
    const c = t.conversacion || {};
    const base = c.estado === 'cerrada'
      ? textoDeCierre(c.cierre, formatoHora)
      : 'Esta conversación del mismo número sigue abierta';
    salida.push({
      tipo: 'cierre',
      clave: `c-${c.id}`,
      // Una que sigue abierta se atiende en ella: la marca lleva a ella.
      enlace: c.estado === 'cerrada' ? null : c.id ?? null,
      // I17: una sincronización que no terminó (un ticket que no se pudo
      // cerrar en el sistema del ISP) tiene que seguir viéndose aunque el chat
      // ya tenga otra conversación. Antes se veía en «Resueltas»; agrupado, la
      // conversación vieja ya no es una fila.
      texto: [base,
              // Un número que cambió de dueño: lo de arriba lo escribió otro
              // cliente verificado. El motor solo dice que es otro, no quién.
              c.otro_cliente ? 'era otro cliente' : null,
              c.sincronizacion_pendiente ? 'con una sincronización sin terminar' : null]
        .filter(Boolean).join(' · ')
    });
    // Después de una marca, el día se vuelve a decir: la conversación
    // siguiente empieza, y "HOY" sin ficha arriba se lee como la anterior.
    dia = null;
  }
  for (const m of mensajes || []) poner(m, false);
  return salida;
}
