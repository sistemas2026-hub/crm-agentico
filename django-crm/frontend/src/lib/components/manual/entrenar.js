/**
 * LA LÓGICA DE «CORREGIR AL AGENTE», FUERA DEL COMPONENTE  --  02/11/2026
 * =======================================================================
 *
 * Vive acá y no dentro de los `.svelte` por una razón concreta y medida: el
 * harness de pruebas del frontend (`vitest.config.js`) **no compila
 * `.svelte`** y no resuelve `$env/dynamic/private`, así que nada que viva en
 * un componente o en un `+server.js` se puede probar. Dejar estas tres
 * funciones adentro habría sido escribirlas sin guarda y decir que están
 * probadas porque la pantalla "se ve bien".
 *
 * Las tres son puras: entran cadenas, salen cadenas.
 */

/**
 * El código estable de una habilidad, derivado de su nombre.
 *
 * No se le pide a la persona: quien está corrigiendo una respuesta mala no
 * quiere pensar en identificadores. El sufijo de tiempo evita el choque con
 * una que ya exista — el motor rechaza el código repetido con «¿ya existe
 * ese código?», que desde una burbuja no es accionable.
 *
 * @param {string} texto
 * @param {() => number} [ahora] inyectable para poder probarlo
 * @returns {string}
 */
export function codigoDesde(texto, ahora = Date.now) {
  const base =
    (texto || 'correccion')
      .toLowerCase()
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/^_+|_+$/g, '')
      .slice(0, 40) || 'correccion';
  return `${base}_${ahora().toString(36).slice(-4)}`;
}

/**
 * La señal de un hueco, en palabras.
 *
 * Las tres las define `nucleo/habilidades/analista.py::detectar`, y cada una
 * significa algo distinto para quien va a corregir. La tercera es la única
 * que responde «¿mejoró?»: dice que ya se le enseñó algo y escaló igual.
 *
 * @param {{senal?: string, motivo?: string, codigo_habilidad?: string|null}} h
 * @returns {string}
 */
export function textoDelHueco(h) {
  const motivo = (h?.motivo || '').replaceAll('_', ' ');
  if (h?.senal === 'habilidad_insuficiente') {
    return `se le enseñó «${h.codigo_habilidad ?? motivo}» y escaló igual`;
  }
  if (h?.senal === 'sin_procedimiento') {
    return 'dijo no tener el procedimiento';
  }
  return `escaló por ${motivo || 'el mismo motivo'}`;
}

/**
 * Los huecos de UN agente, de lo que vino agrupado por rol.
 *
 * @param {Record<string, any[]> | undefined | null} porRol
 * @param {string} nombre
 * @returns {any[]}
 */
export function huecosDe(porRol, nombre) {
  return (porRol ?? {})[nombre] ?? [];
}
