/**
 * Despacho a campo: decidir que un caso merece una visita.
 *
 * `POST /campo/trabajos/crear/` existía desde siempre y **nadie lo llamaba** —
 * verificado el 09/10/2026 en frontend, app móvil, motor y scripts, sin una
 * sola referencia. Las órdenes solo se podían crear por API directa, así que el
 * circuito estaba cortado justo al principio: el ciclo de la madrugada reparte
 * órdenes y la clasificación propone su tipo, y nada de eso se ejercita si no
 * hay por dónde decir «este caso va a campo».
 *
 * Server-only, por el mismo `apiRequest` que el resto del módulo.
 */
import { createHash } from 'node:crypto';
import { apiRequest } from '$lib/api-helpers.js';

/**
 * Con qué se puede despachar: las plantillas PUBLICADAS, con su labor.
 *
 * Una borrador puede cambiar debajo del técnico y el backend ya la rechaza;
 * ofrecerla acá sería dejar elegir algo que va a fallar al enviar.
 *
 * @param {{ cookies: any }} ctx
 */
export async function leerPlantillasDeTrabajo(ctx) {
  try {
    const d = await apiRequest('/campo/plantillas-de-trabajo/', {}, ctx);
    return {
      plantillas: d?.plantillas ?? [],
      labores: d?.labores ?? [],
      sinClasificar: d?.sin_clasificar ?? 0,
      error: false
    };
  } catch {
    // Forma vacía Y error aparte: «no hay plantillas cargadas» y «no se pudo
    // leer» se dibujan distinto.
    return { plantillas: [], labores: [], sinClasificar: 0, error: true };
  }
}

/**
 * Los casos abiertos que podrían ir a campo.
 *
 * `conFicha` pide además la evidencia de cada uno, y cuesta: es una llamada al
 * motor POR CASO, que a su vez habla con WispHub y SmartOLT. Abrir la lista no
 * puede costar veinticinco viajes de red, así que por defecto no se piden.
 *
 * FILTRA Y PAGINA EL BACKEND (18/10/2026), no el navegador: la lista llega
 * de a `tope` casos, y filtrar o contar solo esos dejaría afuera, sin
 * decirlo, todo lo que está en la página siguiente.
 *
 * LO QUE YA TIENE TÉCNICO NO VIENE (28/10/2026): está en Programación. El
 * backend lo cuenta (`conTecnico`) y `filtro.conTecnico` lo vuelve a traer,
 * para una segunda visita al mismo caso.
 *
 * @param {{ cookies: any }} ctx
 * @param {boolean} conFicha
 * @param {{ q?: string, asunto?: string, pagina?: number, conTecnico?: boolean }} [filtro]
 */
export async function leerCasosDespachables(ctx, conFicha = false, filtro = {}) {
  const p = new URLSearchParams();
  if (conFicha) p.set('ficha', '1');
  if (filtro.conTecnico) p.set('con_tecnico', '1');
  if (filtro.q) p.set('q', filtro.q);
  if (filtro.asunto) p.set('asunto', filtro.asunto);
  if (filtro.pagina && filtro.pagina > 1) p.set('pagina', String(filtro.pagina));
  const consulta = p.toString();
  try {
    const d = await apiRequest(
      `/campo/casos-despachables/${consulta ? `?${consulta}` : ''}`, {}, ctx
    );
    const casos = d?.casos ?? [];
    return {
      casos,
      tope: d?.tope ?? 0,
      // «Todavía nadie aprobó ninguno» y «no se pudo leer» se dibujan
      // distinto: la primera dice qué hacer, la segunda que algo falló.
      sinAprobados: d?.sin_aprobados === true,
      //  Un backend anterior a la paginación no los manda: se cae a lo que
      //  llegó, que es lo único que se sabe con certeza.
      total: d?.total ?? casos.length,
      totalSinFiltro: d?.total_sin_filtro ?? d?.total ?? casos.length,
      pagina: d?.pagina ?? 1,
      paginas: d?.paginas ?? 1,
      asuntos: d?.asuntos ?? [],
      conTecnico: d?.con_tecnico ?? 0,
      error: false
    };
  } catch {
    return {
      casos: [], tope: 0, sinAprobados: false, total: 0, totalSinFiltro: 0,
      pagina: 1, paginas: 1, asuntos: [], conTecnico: 0, error: true
    };
  }
}

/**
 * Lo que hace falta para despachar UN caso, ya cargado: el barrio de la ficha
 * del ISP, la lectura del Supervisor y la descripción del ticket TAPADA.
 *
 * Una consulta para el caso que se está mirando, en vez de «Traer el
 * diagnóstico de cada uno» para los veinticinco. `null` si no se pudo: el
 * formulario se llena a mano como antes, no se rompe.
 *
 * @param {{ cookies: any }} ctx
 * @param {string} id
 */
export async function leerFichaDespachable(ctx, id) {
  try {
    return await apiRequest(`/campo/casos-despachables/${encodeURIComponent(id)}/ficha/`, {}, ctx);
  } catch {
    return null;
  }
}

/**
 * Crea la orden de trabajo.
 *
 * La `Idempotency-Key` la exige el backend y es lo que evita que un doble clic
 * —o un reintento de red— cree dos órdenes para el mismo caso. Se arma con el
 * caso y la plantilla: el mismo despacho repetido es la misma clave, y una
 * segunda visita deliberada al mismo caso lleva otra plantilla u otro momento.
 *
 * @param {{ cookies: any }} ctx
 * @param {Record<string, any>} cuerpo
 * @param {string} idempotencia
 */
/**
 * La clave de idempotencia de un despacho: el caso, y la huella del cuerpo.
 *
 * POR QUE VIVE ACA Y NO EN `+page.server.js` (06/11/2026). Estuvo alla, y
 * exportarla para poder probarla ROMPIO EL BUILD: SvelteKit solo acepta
 * `load`, `actions`, `prerender`, `csr`, `ssr`, `trailingSlash`, `config` y
 * `entries` en un `+page.server.js`. El deploy fallo en produccion porque
 * `vite build` --la unica guarda que lo detecta-- no se habia corrido: ni
 * vitest ni svelte-check lo ven. Aca ademas esta su lugar: al lado de
 * `despacharACampo`, que es quien la consume.
 *
 * EL CASO VA EN TEXTO PLANO para que la fila se lea cuando alguien mire la
 * tabla de mutaciones buscando que paso. La huella cubre todo el cuerpo; 32
 * caracteres de SHA-256 alcanzan de sobra y la columna del backend
 * (`MutacionIdempotente.idempotency_key`) acepta 128.
 *
 * LAS CLAVES SE ORDENAN antes de serializar: `JSON.stringify` respeta el orden
 * de insercion, asi que sin ordenar, el mismo contenido escrito en otro orden
 * daria otra huella y un doble clic crearia dos ordenes.
 *
 * `undefined` desaparece en `JSON.stringify`, que es justo lo que se quiere:
 * un campo ausente y uno que nunca se mando son el mismo despacho.
 *
 * @param {string} caseId
 * @param {Record<string, any>} cuerpo
 */
export function claveDeDespacho(caseId, cuerpo) {
  const ordenado = Object.fromEntries(
    Object.keys(cuerpo).sort().map((k) => [k, cuerpo[k]])
  );
  const huella = createHash('sha256')
    .update(JSON.stringify(ordenado))
    .digest('hex')
    .slice(0, 32);
  return `despacho:${caseId || 'manual'}:${huella}`;
}


export async function despacharACampo(ctx, cuerpo, idempotencia) {
  return apiRequest('/campo/trabajos/crear/', {
    method: 'POST',
    body: cuerpo,
    headers: { 'Idempotency-Key': idempotencia }
  }, ctx);
}


/**
 * A qué ZONA va un barrio y qué CUADRILLA la cubre ese día con esa labor
 * (13/10/2026). Es lo que el supervisor tiene que ver al despachar. La regla
 * es la del reparto (`campo/reparto.py::cobertura`): acá no se recalcula nada.
 *
 * @param {{ cookies: any }} ctx
 * @param {{ barrio: string, fecha?: string, labor?: string }} q
 */
export async function leerCobertura(ctx, { barrio, fecha = '', labor = '' }) {
  const p = new URLSearchParams({ barrio, fecha, labor });
  try {
    return await apiRequest(`/campo/despacho/cobertura/?${p}`, {}, ctx);
  } catch {
    return null;
  }
}

/**
 * Qué órdenes crearía el Supervisor ahora en la cola de Despacho, y por qué no
 * las otras (23/10/2026). No crea nada: ver
 * `operaciones/ordenes_de_despacho.py::decidir`.
 *
 * @param {{ cookies: any }} ctx
 */
export async function leerVistaPreviaDeLasOrdenes(ctx) {
  return apiRequest('/operaciones/ordenes/vista-previa/', {}, ctx);
}

/**
 * El día entero como lo dejaría el Supervisor: cuadrillas, órdenes y reparto,
 * sin guardar nada (24/10/2026). Ver `operaciones/simulacion_del_dia.py`.
 *
 * @param {{ cookies: any }} ctx
 * @param {string} [fecha]  'AAAA-MM-DD'; vacía = hoy en la hora de la empresa
 */
export async function leerSimulacionDelDia(ctx, fecha) {
  const q = fecha ? `?fecha=${encodeURIComponent(fecha)}` : '';
  return apiRequest(`/operaciones/dia/simulacion/${q}`, {}, ctx);
}
