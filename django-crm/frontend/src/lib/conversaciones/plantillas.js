/**
 * Los huecos de una plantilla de WhatsApp: cómo se rotulan y cómo se ven
 * llenos, antes de mandarla.
 *
 * POR QUÉ ESTO NO ES COSMÉTICO
 * ----------------------------
 * El texto de una plantilla lo aprueba Meta y no se puede corregir después de
 * enviada. La vista previa es la única oportunidad de ver lo que el cliente va
 * a leer — así que si la previa y el envío no reparten los valores igual, el
 * operador aprueba una cosa y el cliente recibe otra.
 *
 * EL REPARTO ES CONTRACTUAL, y viene del backend:
 *
 *     primero los del ENCABEZADO, después los del CUERPO
 *
 * Es el mismo orden que usan `whatsapp.componentes_de_plantilla` (el envío) y
 * `api._armar_plantilla` (el texto que queda en el hilo). Los tres leen
 * `variables_encabezado` y `variables_cuerpo` de la misma ficha: acá no se
 * vuelve a deducir nada del texto, justamente para que no puedan separarse.
 *
 * LOS DOS FORMATOS DE META
 * ------------------------
 *     posicional   {{1}}, {{2}}        el hueco es un número
 *     nombrado     {{customer_name}}   el hueco es el nombre, y ES la etiqueta
 *
 * En posicional cada componente numera desde 1 por su cuenta: el {{1}} del
 * encabezado y el {{1}} del cuerpo son dos valores distintos. Por eso la
 * etiqueta dice de qué parte es — sin eso, dos campos seguidos dirían
 * «reemplaza {{1}}» y no habría forma de saber cuál es cuál.
 */

/** Los huecos de cada componente, en el orden en que se piden. */
export function huecosDe(plantilla) {
  return {
    encabezado: plantilla?.variables_encabezado ?? [],
    cuerpo: plantilla?.variables_cuerpo ?? []
  };
}

/**
 * Un rótulo por campo, en el mismo orden que los valores.
 *
 * Para un nombrado el rótulo es el nombre que puso quien diseñó la plantilla
 * ({{customer_name}}), que es lo más cerca de una etiqueta semántica que Meta
 * entrega hoy. Para un posicional no hay nada que decir salvo dónde va.
 */
export function etiquetasDe(plantilla) {
  const { encabezado, cuerpo } = huecosDe(plantilla);
  const hayDosPartes = encabezado.length > 0 && cuerpo.length > 0;

  const rotular = (hueco, parte) => {
    const nombrado = !/^\d+$/.test(hueco);
    return {
      hueco,
      parte,
      // El nombre ya dice qué es; el número sólo dice dónde va.
      titulo: nombrado ? hueco : `Dato ${hueco}`,
      // Se aclara la parte sólo cuando hay de las dos: si toda la plantilla
      // es cuerpo, decirlo en cada campo es ruido.
      donde: hayDosPartes ? (parte === 'encabezado' ? 'encabezado' : 'cuerpo') : '',
      reemplaza: `{{${hueco}}}`
    };
  };

  return [
    ...encabezado.map((h) => rotular(h, 'encabezado')),
    ...cuerpo.map((h) => rotular(h, 'cuerpo'))
  ];
}

/** Cuántos valores hay que pedir. Sale de los huecos, no de un campo aparte. */
export function cuantosValores(plantilla) {
  const { encabezado, cuerpo } = huecosDe(plantilla);
  return encabezado.length + cuerpo.length;
}

function rellenar(texto, huecos, valores) {
  let salida = texto ?? '';
  huecos.forEach((hueco, i) => {
    const valor = valores[i];
    // Un campo vacío deja el hueco a la vista: es más honesto que mostrar un
    // espacio en blanco donde va a ir el nombre del cliente.
    salida = salida.replaceAll(`{{${hueco}}}`, valor || `{{${hueco}}}`);
  });
  return salida;
}

/**
 * El texto tal como lo va a leer el cliente.
 *
 * Reparte la lista plana igual que el envío, y rellena CADA componente con los
 * suyos. El encabezado no se concatena crudo: si tiene variables, también se
 * llenan.
 */
export function vistaPrevia(plantilla, valores = []) {
  if (!plantilla) return '';
  const { encabezado: huecosEnc, cuerpo: huecosCuerpo } = huecosDe(plantilla);
  const corte = huecosEnc.length;

  const encabezado = rellenar(
    plantilla.encabezado, huecosEnc, valores.slice(0, corte)
  ).trim();
  const cuerpo = rellenar(
    plantilla.cuerpo, huecosCuerpo, valores.slice(corte, corte + huecosCuerpo.length)
  );
  return encabezado ? `${encabezado}\n\n${cuerpo}` : cuerpo;
}

/**
 * Si se puede enviar. Una mixta no: el backend la rechaza, y ofrecer el botón
 * sería ofrecer un envío que va a fallar.
 */
export function sePuedeEnviar(plantilla, valores = []) {
  if (!plantilla) return false;
  if (plantilla.formato_variables === 'mixto') return false;
  const cuantos = cuantosValores(plantilla);
  return valores.length === cuantos && valores.every((v) => (v ?? '').trim().length > 0);
}

/** Por qué no se puede, cuando el motivo no es «falta llenar un campo». */
export function motivoDeBloqueo(plantilla) {
  if (plantilla?.formato_variables === 'mixto') {
    return 'Esta plantilla mezcla variables numeradas y con nombre. Hay que corregirla en Meta antes de poder enviarla.';
  }
  return '';
}
