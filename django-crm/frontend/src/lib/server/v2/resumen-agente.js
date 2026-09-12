/**
 * Lee la descripcion de un caso escalado por el asistente y la separa en sus
 * partes.
 *
 * POR QUE UN PARSER Y NO UN RESUMEN NUEVO
 * ---------------------------------------
 * La tentacion obvia era pedirle a un modelo que resumiera el ticket al
 * abrirlo. Seria inventar: el resumen ya existe y se escribio UNA vez, en el
 * momento de escalar, con la traza real delante (nucleo/seguimiento/
 * escalamiento.py). Volver a generarlo desde el texto ya resumido produce una
 * interpretacion de una interpretacion, que puede contradecir lo que de
 * verdad midieron las herramientas -- y quien lee no tiene como notarlo.
 *
 * Asi que esto NO resume: reconoce los bloques que el motor ya escribio y los
 * devuelve separados para que la pantalla los muestre como tarjetas. Todo lo
 * que sale en la pantalla estuvo antes en la descripcion, literal.
 *
 * LOS MARCADORES SON UN CONTRATO
 * ------------------------------
 * Son exactamente los que escribe `escalamiento.py::escalar`. Si alguien los
 * cambia alla, esto deja de reconocerlos -- y por eso el caso de "no
 * reconozco nada" no rompe la pantalla ni muestra secciones vacias: devuelve
 * null y quien llama muestra la descripcion tal cual, como se hacia antes.
 * Un ticket cargado a mano por una persona cae por el mismo camino.
 */

// Una sola definicion, usable desde el servidor y desde la pantalla.
export { nombreLegible } from '$lib/v2/nombre-herramienta.js';

/** Separador entre el encabezado y la transcripcion: 40 guiones. */
const SEPARADOR = '-'.repeat(40);

const MARCAS = {
  resumen: 'RESUMEN:',
  probado: 'QUE YA SE PROBO (no hace falta repetirlo):',
  noComprobado: 'NO SE PUDO COMPROBAR (empezar por aca):',
  siguientePaso: 'SIGUIENTE PASO:',
  adjuntos: 'ADJUNTOS:'
};

/**
 * Corta un bloque que empieza en `marca` y termina donde empieza el siguiente
 * marcador conocido (o el separador). No se corta por linea en blanco: un
 * resumen de dos parrafos es normal y se partiria al medio.
 *
 * @param {string} texto
 * @param {string} marca
 * @returns {string}
 */
function bloque(texto, marca) {
  const i = texto.indexOf(marca);
  if (i < 0) return '';
  const desde = i + marca.length;
  const finales = [...Object.values(MARCAS), SEPARADOR]
    .map((m) => texto.indexOf(m, desde))
    .filter((p) => p > -1);
  const hasta = finales.length ? Math.min(...finales) : texto.length;
  return texto.slice(desde, hasta).trim();
}

/**
 * Las llamadas a herramientas, tal como quedaron en la traza.
 *
 * Cada linea es "  - <herramienta>: <json>" o "  - <herramienta>: no se pudo
 * -- <error>". Se separa el nombre del resultado y se marca si fallo, pero NO
 * se interpreta el contenido: que significa cada campo lo sabe el catalogo de
 * la empresa, no esta pantalla. El mismo criterio que ya tomo el nucleo al
 * escribirlas (ver `_que_se_probo`), y por el mismo motivo -- una pantalla que
 * traduzca `{"verificado": false}` a "Identidad verificada" estaria diciendo
 * lo contrario de lo que midio la herramienta.
 *
 * @param {string} texto
 * @returns {{ herramienta: string, resultado: string, fallo: boolean }[]}
 */
function herramientas(texto) {
  if (!texto) return [];
  return texto
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l.startsWith('- '))
    .map((l) => {
      const linea = l.slice(2);
      const corte = linea.indexOf(': ');
      const herramienta = corte > 0 ? linea.slice(0, corte) : linea;
      const resultado = corte > 0 ? linea.slice(corte + 2) : '';
      return {
        herramienta,
        resultado,
        // El texto exacto que escribe el nucleo cuando la herramienta devolvio
        // un error, en vez de un dato.
        fallo: resultado.startsWith('no se pudo -- ')
      };
    });
}

/**
 * La conversacion, como turnos.
 *
 * Las etiquetas ('Cliente'/'Asistente') las fija `_ROL_LEGIBLE` en el nucleo.
 * Una linea sin etiqueta es continuacion del turno anterior -- un mensaje con
 * saltos de linea adentro -- y se pega ahi en vez de perderse.
 *
 * @param {string} texto
 * @returns {{ quien: 'cliente' | 'asistente', texto: string }[]}
 */
function turnos(texto) {
  /** @type {{ quien: 'cliente' | 'asistente', texto: string }[]} */
  const salida = [];
  for (const linea of (texto ?? '').split('\n')) {
    if (linea.startsWith('Cliente: ')) salida.push({ quien: 'cliente', texto: linea.slice(9) });
    else if (linea.startsWith('Asistente: '))
      salida.push({ quien: 'asistente', texto: linea.slice(11) });
    else if (salida.length && linea.trim()) salida[salida.length - 1].texto += '\n' + linea;
  }
  return salida;
}

/**
 * @param {string} descripcion
 * @returns {null | {
 *   resto: string,
 *   situacion: string,
 *   ticketOperativo: string,
 *   verificado: { herramienta: string, resultado: string, fallo: boolean }[],
 *   noComprobado: string,
 *   siguientePaso: string,
 *   adjuntos: string,
 *   turnos: { quien: 'cliente' | 'asistente', texto: string }[]
 * }}
 */
export function leerResumenDelAgente(descripcion) {
  const texto = (descripcion ?? '').trim();
  // Con que reconozca UNO alcanza: los bloques son opcionales cada uno (un
  // caso puede escalar sin nada pendiente por comprobar, por ejemplo), asi
  // que exigirlos todos dejaria afuera casos perfectamente validos.
  const esDelAgente = Object.values(MARCAS).some((m) => texto.includes(m));
  if (!texto || !esDelAgente) return null;

  const sep = texto.indexOf(SEPARADOR);
  const encabezado = sep > -1 ? texto.slice(0, sep) : texto;
  const transcripcion = sep > -1 ? texto.slice(sep + SEPARADOR.length) : '';

  const resumenCrudo = bloque(encabezado, MARCAS.resumen);
  // El numero del ticket operativo se escribe DENTRO del resumen, en su propio
  // parrafo. Se separa para poder mostrarlo como dato y no como prosa.
  const conTicket = resumenCrudo.match(/^(Ticket operativo #\d+[^)]*\)\.)$/m);

  // Lo que quedo del encabezado despues de sacar todo lo que SI se reconocio.
  //
  // Existe para no perder texto en silencio. La descripcion completa se
  // mostraba abajo del detalle tecnico, pero repetia la pantalla entera --
  // las mismas herramientas de la tabla de arriba y la misma conversacion que
  // ya esta en burbujas. Sacarla del todo, en cambio, hacia que un bloque con
  // un marcador cambiado (o uno nuevo que este parser todavia no conoce)
  // desapareciera sin dejar rastro.
  //
  // Con esto pasan las dos cosas: si todo encajo en una tarjeta no sobra nada
  // y no se muestra nada; si sobro algo, se muestra ESO y solo eso.
  // Se recorta por POSICION, no buscando el texto del bloque: `bloque()`
  // devuelve el contenido ya recortado (sin el salto de linea ni la sangria
  // que traia), asi que buscar esa cadena dentro del original no encuentra
  // nada y el bloque quedaba entero en el sobrante. Con los indices se saca
  // exactamente el tramo que se reconocio.
  const tramos = Object.values(MARCAS)
    .map((marca) => {
      const desde = encabezado.indexOf(marca);
      if (desde < 0) return null;
      const finales = [...Object.values(MARCAS), SEPARADOR]
        .map((m) => encabezado.indexOf(m, desde + marca.length))
        .filter((pos) => pos > -1);
      return { desde, hasta: finales.length ? Math.min(...finales) : encabezado.length };
    })
    .filter((t) => t !== null)
    .sort((a, b) => b.desde - a.desde);

  let resto = encabezado;
  for (const t of tramos) resto = resto.slice(0, t.desde) + resto.slice(t.hasta);

  // Un bloque que este parser no conozca, escrito ENTRE dos marcadores
  // conocidos, no aparece en el sobrante calculado arriba: queda dentro del
  // tramo del marcador anterior. Y si ese anterior es el de herramientas, se
  // pierde del todo, porque ahi solo sobreviven las lineas que empiezan con
  // '- '. Asi que las demas lineas de ese bloque se recuperan aca.
  const crudoHerramientas = bloque(encabezado, MARCAS.probado);
  const sueltas = crudoHerramientas
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith('- '))
    .join('\n');
  if (sueltas) resto = (resto + '\n' + sueltas).trim();

  // Los guiones del separador no son contenido perdido.
  resto = resto.replace(/-{3,}/g, '').trim();

  return {
    resto,
    situacion: (conTicket ? resumenCrudo.replace(conTicket[0], '') : resumenCrudo).trim(),
    ticketOperativo: conTicket ? conTicket[1] : '',
    verificado: herramientas(bloque(encabezado, MARCAS.probado)),
    noComprobado: bloque(encabezado, MARCAS.noComprobado),
    siguientePaso: bloque(encabezado, MARCAS.siguientePaso),
    adjuntos: bloque(encabezado, MARCAS.adjuntos),
    turnos: turnos(transcripcion.trim())
  };
}
