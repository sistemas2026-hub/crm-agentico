/**
 * La logica del formulario de agentes, aparte de la pantalla (02/11/2026).
 *
 * El usuario: "que la persona que cree un agente se le haga facil... la
 * grilla de herramientas, el prompt, mas entendible". El formulario mostraba
 * las 84 herramientas en una sola lista, cada una con su instruccion entera
 * para el modelo ("LLAMA A ESTA HERRAMIENTA (no sugieras...") y su tipo
 * tecnico, sin distinguir mirar de actuar ni las que dispara el sistema.
 *
 * Aca: una linea por herramienta, agrupadas por lo que HACEN (con las marcas
 * que manda el motor: nucleo/config/editor.py::catalogo_herramientas, nunca
 * adivinadas del texto), y los avisos de lo que va a pasar ANTES de guardar.
 */

/** Sin tildes y en minusculas, para buscar y para armar identificadores. */
const plano = (/** @type {string} */ t) =>
  (t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

const MAXIMO_RESUMEN = 140;

/**
 * La primera oracion de la descripcion, o el comienzo cortado sin partir una
 * palabra. La descripcion entera es una instruccion para el modelo; esto es
 * para la persona que elige.
 * @param {string} descripcion
 */
export function resumenDe(descripcion) {
  const texto = (descripcion || '').replace(/\s+/g, ' ').trim();
  if (!texto) return '';
  const fin = texto.search(/[.!?](\s|$)/);
  const oracion = fin > 0 ? texto.slice(0, fin + 1) : texto;
  if (oracion.length <= MAXIMO_RESUMEN) return oracion;
  const corte = oracion.slice(0, MAXIMO_RESUMEN);
  const espacio = corte.lastIndexOf(' ');
  return (espacio > 40 ? corte.slice(0, espacio) : corte).replace(/[,;:\s]+$/, '') + '…';
}

/** Los grupos, en el orden en que se muestran, y como se le explica cada uno. */
export const GRUPOS = [
  { clave: 'consulta', titulo: 'Consulta', ayuda: 'Mira datos. No cambia nada.' },
  { clave: 'actua', titulo: 'Actúa', ayuda: 'Cambia algo real: crea, registra, reinicia.' },
  { clave: 'deriva', titulo: 'Pasa la conversación', ayuda: 'Deriva a otro agente o a una persona.' },
  { clave: 'sistema', titulo: 'Del sistema', ayuda: 'Las dispara el código, no el agente. Normalmente no se le dan.' }
];

/** @param {any} h */
const grupoDe = (h) => (h.de_sistema ? 'sistema' : h.deriva ? 'deriva' : h.escribe ? 'actua' : 'consulta');

/**
 * El catalogo agrupado por lo que hace cada herramienta, filtrado por el
 * buscador (nombre o descripcion, sin tildes ni mayusculas). Los grupos
 * vacios no aparecen.
 * @param {any[]} catalogo
 * @param {string} busqueda
 */
export function agrupar(catalogo, busqueda) {
  const q = plano(busqueda).trim();
  const visibles = (catalogo ?? []).filter(
    (h) => !q || plano(h.nombre).includes(q) || plano(h.descripcion).includes(q)
  );
  return GRUPOS.map((g) => ({ ...g, items: visibles.filter((h) => grupoDe(h) === g.clave) })).filter(
    (g) => g.items.length
  );
}

/**
 * Un identificador valido a partir del cargo (o del area): minusculas, sin
 * tildes, con guion bajo, empezando con letra, hasta 30. El mismo formato que
 * exige el motor (nucleo/config/editor.py::_validar_nombre_rol).
 * @param {string} texto
 */
export function sugerirIdentificador(texto) {
  return plano(texto)
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^[^a-z]+/, '')
    .replace(/_+$/, '')
    .slice(0, 30)
    .replace(/_+$/, '');
}

/**
 * Lo que va a pasar si se guarda asi, dicho antes de guardar. Cada aviso
 * tiene una clave estable (para probarlo) y el texto para la persona.
 * @param {{ orientadoA: string, descripcion: string, atiende: string, conectar: boolean,
 *   seleccion: Record<string, boolean>, campos: Record<string, string[] | Set<string>>,
 *   catalogo: any[] }} f
 */
export function avisosDelAgente(f) {
  /** @type {{ clave: string, texto: string }[]} */
  const avisos = [];
  if (!(f.descripcion || '').trim()) {
    avisos.push({ clave: 'sin_instrucciones', texto: 'No tiene instrucciones: el modelo no sabe qué hacer ni qué evitar.' });
  }
  if (f.orientadoA === 'cliente_final') {
    if (!f.conectar) {
      avisos.push({ clave: 'sin_router', texto: 'Atiende clientes pero no está conectado al router: nunca le va a llegar una conversación.' });
    } else if (!(f.atiende || '').trim()) {
      avisos.push({ clave: 'sin_atiende', texto: 'Está conectado al router pero no dice qué temas atiende: el router no sabe cuándo mandarle algo.' });
    }
  }
  const porNombre = Object.fromEntries((f.catalogo ?? []).map((h) => [h.nombre, h]));
  for (const [nombre, elegida] of Object.entries(f.seleccion ?? {})) {
    if (!elegida) continue;
    const h = porNombre[nombre];
    if (!h) continue;
    if (h.de_sistema) {
      avisos.push({ clave: `de_sistema:${nombre}`, texto: `«${nombre}» la dispara el sistema, no el agente: dársela puede hacer que la llame cuando no corresponde.` });
      continue;
    }
    const campos = f.campos?.[nombre];
    const cuantos = campos instanceof Set ? campos.size : (campos ?? []).length;
    if (!h.escribe && !h.deriva && !h.verifica_identidad && cuantos === 0) {
      avisos.push({ clave: `sin_campos:${nombre}`, texto: `«${nombre}» no tiene ningún dato elegido: el agente la va a usar y no va a ver nada de la respuesta.` });
    }
  }
  return avisos;
}

/** Lo que un buen texto de instrucciones tiene que decir, para no arrancar en blanco. */
export const PLANTILLA_INSTRUCCIONES = `Qué hace:
(En una o dos frases: para qué existe este agente.)

Con quién habla:
(Clientes por WhatsApp, o compañeros del equipo. En qué tono.)

Qué NO debe hacer:
(Lo que nunca promete, nunca inventa, nunca decide solo.)

Cuándo pasa a una persona:
(Qué situaciones no resuelve y a quién las deriva.)`;
