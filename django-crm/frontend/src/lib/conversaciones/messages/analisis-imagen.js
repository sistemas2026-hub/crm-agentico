/**
 * ════════════════════════════════════════════════════════════════════════════
 *  ANÁLISIS DE IMAGEN — partir el mensaje y resumirlo, sin tocar lo guardado
 * ════════════════════════════════════════════════════════════════════════════
 *
 * POR QUÉ EXISTE
 * --------------
 * Cuando el cliente manda una foto, el motor NO guarda "una foto": guarda un
 * mensaje de texto que arma `nucleo/canales/vision.py::texto_para_el_agente`
 * y que se ve así:
 *
 *     [Foto que envio el cliente]
 *
 *     [Texto que escribio junto con la imagen]
 *     Mira como esta mi modem
 *
 *     [Analisis automatico de la foto, no verificado]
 *     Se ve un equipo blanco con rejillas y dos antenas verticales, montado
 *     en una pared clara. En la parte superior tiene una fila de…
 *
 * Eso es lo que el modelo necesita leer, y está bien que sea así. Pero en la
 * bandeja ocupa una burbuja de 600 caracteres por cada foto, y quien revisa
 * un hilo para entender qué pasó tiene que saltearla a mano.
 *
 * ESTO ES PRESENTACIÓN, Y NADA MÁS
 * ---------------------------------
 * No se modifica lo almacenado, no se vuelve a llamar al modelo y no se
 * cambia una coma del análisis. Se parte el texto que YA llegó y se muestra
 * en dos niveles: una línea arriba, el resto a un clic.
 *
 * EL RESUMEN NO INVENTA
 * ---------------------
 * Esta es la parte delicada. Un resumen que "interpreta" sería un segundo
 * análisis sin modelo, y diría cosas que el original no dice — justo lo que
 * todo el diseño de visión evita.
 *
 * Así que sólo EXTRAE, nunca deduce:
 *   · si el texto nombra un equipo conocido, lo nombra;
 *   · si menciona luces de un color, lo dice con el color que usó;
 *   · si dice que algo NO se ve o NO se distingue, lo arrastra como tal;
 *   · y si no encuentra nada de eso, muestra el principio del original en
 *     vez de fabricar una frase.
 *
 * La última regla es la que importa: ante la duda, el resumen degrada a una
 * cita literal. Nunca a una interpretación.
 */

// Los rótulos que pone `vision.py::texto_para_el_agente`. Si cambian allá,
// cambian acá: son el contrato entre el motor y esta pantalla.
//
// El tercero, '[Foto que envio el cliente]', no hace falta leerlo — es el
// encabezado y lo que se busca son los dos cortes de abajo.
const R_PIE = '[Texto que escribio junto con la imagen]';
const R_ANALISIS = '[Analisis automatico de la foto, no verificado]';

/**
 * ¿Este mensaje es una foto analizada?
 *
 * Se pregunta por el rótulo del análisis y no por el de la foto: un mensaje
 * puede traer el primero sin el segundo (visión apagada, o falló), y en ese
 * caso no hay nada que colapsar.
 */
export function esAnalisisDeImagen(contenido) {
  return typeof contenido === 'string' && contenido.includes(R_ANALISIS);
}

/**
 * El contenido crudo → `{ pie, analisis }`, o `null` si no aplica.
 *
 * Devuelve `null` —y no un objeto a medias— cuando el mensaje no tiene la
 * forma esperada. Quien llama dibuja entonces la burbuja de siempre, que es
 * exactamente el comportamiento que había antes de que esto existiera.
 */
export function partirMensaje(contenido) {
  if (!esAnalisisDeImagen(contenido)) return null;

  const corte = contenido.indexOf(R_ANALISIS);
  const encabezado = contenido.slice(0, corte);
  const analisis = contenido.slice(corte + R_ANALISIS.length).trim();
  if (!analisis) return null;

  // El pie es lo que escribió LA PERSONA, así que se muestra como texto suyo
  // y no se resume ni se esconde: son sus palabras.
  let pie = '';
  const iPie = encabezado.indexOf(R_PIE);
  if (iPie !== -1) pie = encabezado.slice(iPie + R_PIE.length).trim();

  return { pie, analisis };
}

/**
 * Equipos que el vocabulario del ISP reconoce, del más específico al menos.
 * @type {[RegExp, string][]}
 */
const EQUIPOS = [
  [/\bONT\b/i, 'ONT'],
  [/\bONU\b/i, 'ONU'],
  [/\bOLT\b/i, 'OLT'],
  [/\brouter\b/i, 'router'],
  [/\bm[oó]dem\b/i, 'módem'],
  [/\bcaja\s+(nap|de\s+empalme)\b/i, 'caja de red'],
  [/\bantenas?\b/i, 'equipo con antenas'],
  [/\broseta\b/i, 'roseta'],
  [/\bequipo\b/i, 'equipo de red']
];

// Cada color EN SUS DOS GÉNEROS, y no es un detalle de estilo.
//
// La primera versión buscaba sólo `/rojas?/`, y el análisis real de una ONT
// dice "la luz LOS en rojo": el resumen salía "ONT · luz verde visible" y se
// comía la luz roja. Perder el rojo invierte el diagnóstico en la dirección
// que hace daño — quien lee la bandeja ve un equipo sano donde hay una señal
// de falla. En plural y singular, masculino y femenino.
//
/** @type {[RegExp, string, string][]}  patron, singular, plural. */
const COLORES = [
  [/\bverdes?\b/i, 'verde', 'verdes'],
  [/\broja?s?\b|\brojos?\b/i, 'roja', 'rojas'],
  [/\bnaranjas?\b|\b[aá]mbar(es)?\b/i, 'naranja', 'naranjas'],
  [/\bazul(es)?\b/i, 'azul', 'azules']
];

/**
 * Una frase corta a partir del análisis. Nunca más de lo que el texto dice.
 *
 * Devuelve siempre una cadena no vacía: si no puede extraer nada, cita el
 * principio del original. Un resumen vacío dejaría la línea en blanco y
 * obligaría a abrir el detalle siempre, que es justo lo que se evita.
 */
export function resumir(analisis, limite = 110) {
  if (typeof analisis !== 'string' || !analisis.trim()) return '';
  const t = analisis.trim();
  const partes = [];

  // --- qué equipo, si lo nombra -------------------------------------------
  for (const [patron, nombre] of EQUIPOS) {
    if (patron.test(t)) {
      partes.push(nombre.charAt(0).toUpperCase() + nombre.slice(1));
      break;
    }
  }

  // --- las luces, con el color que usó el análisis -------------------------
  // Se mira si el texto NIEGA ese color antes de afirmarlo: "no se observan
  // luces rojas" no puede resumirse como "luces rojas". Es el error que haría
  // peligroso este resumen, porque invertiría el diagnóstico.
  const encendidas = [];
  const ausentes = [];
  for (const [patron, singular, plural] of COLORES) {
    if (!patron.test(t)) continue;
    const niega = new RegExp(
      `no\\s+(se\\s+)?(observan?|ven?|hay|aprecian?|distinguen?)[^.]{0,60}(${patron.source})`,
      'i'
    ).test(t);
    (niega ? ausentes : encendidas).push({ singular, plural });
  }
  if (encendidas.length) {
    partes.push(
      encendidas.length === 1
        ? `luz ${encendidas[0].singular} visible`
        : `luces ${encendidas.map((c) => c.plural).join(' y ')} visibles`
    );
  }
  if (ausentes.length) {
    // "sin luces rojas ni naranjas" — en plural, que es como se dice.
    partes.push(`sin luces ${ausentes.map((c) => c.plural).join(' ni ')}`);
  }

  // --- lo que el análisis dice que NO pudo determinar ----------------------
  // Se arrastra tal cual porque es la parte más valiosa y la más fácil de
  // perder al resumir: un resumen que se come las dudas convierte una lectura
  // parcial en una certeza.
  if (/no\s+se\s+(distingue|lee|leen|alcanza|puede|logra|aprecia)/i.test(t)) {
    partes.push('hay detalles que no se distinguen');
  }

  const resumen = partes.join(' · ');
  if (resumen && resumen.length <= limite) return resumen;
  if (resumen) return resumen.slice(0, limite - 1).trimEnd() + '…';

  // --- no se pudo extraer nada: se cita, no se inventa ---------------------
  const primera = t.split(/(?<=\.)\s/)[0] || t;
  return primera.length <= limite
    ? primera
    : primera.slice(0, limite - 1).trimEnd() + '…';
}
