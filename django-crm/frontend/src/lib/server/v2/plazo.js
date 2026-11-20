/**
 * ESPERAR CON PLAZO  --  07/11/2026
 *
 * Una lectura que no contesta no puede retener una pantalla. Esto vivía
 * copiado en tres lugares (el hub de Configuración, el menú de la app y la
 * conversación), cada copia con su variante, y la próxima corrección iba a
 * llegar a una sola. Ahora hay uno. No depende de ninguna pantalla, así que
 * cualquiera lo puede importar.
 *
 * Las dos funciones NUNCA rechazan: devuelven `null` cuando la lectura falla
 * o vence. Eso es lo que permite devolver su promesa desde un `load` para que
 * llegue después (SvelteKit la manda en la misma respuesta cuando resuelve):
 * una promesa rechazada viajando al navegador rompe la pantalla.
 *
 * Con `nombre`, la lectura que queda sin valor lo deja dicho en el log: cuál,
 * y si fue el plazo o un error (su estado HTTP o su tipo). Texto fijo, nunca
 * el mensaje del error ni la URL --que lleva el identificador de la
 * conversación--: un null que no deja rastro se ve igual que una llamada mal
 * escrita, y uno que deja datos de un cliente en el log es peor.
 */

/**
 * @param {string | undefined} nombre @param {string} motivo
 * @returns {null}
 */
function avisar(nombre, motivo) {
  if (nombre) console.warn(`[plazo] ${nombre} sin valor: ${motivo}`);
  return null;
}

/**
 * `promesa`, o `null` si falla o tarda más de `ms`. Para lo que no acepta una
 * señal de abortar (las llamadas al CRM): el plazo corta la ESPERA de la
 * página, no el pedido, que sigue del otro lado hasta contestar.
 *
 * @template T
 * @param {Promise<T>} promesa
 * @param {number} ms
 * @param {string} [nombre]
 * @returns {Promise<T | null>}
 */
export function conPlazo(promesa, ms, nombre) {
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let reloj;
  const vencido = new Promise((resolver) => {
    reloj = setTimeout(() => resolver(avisar(nombre, `plazo de ${ms} ms`)), ms);
  });
  return Promise.race([
    Promise.resolve(promesa).catch((/** @type {any} */ err) =>
      avisar(nombre, `error ${err?.status ?? err?.name ?? 'desconocido'}`)
    ),
    vencido
  ]).finally(() => clearTimeout(reloj));
}

/**
 * Un `fetch` con plazo que lee también el cuerpo: `{ ok, status, cuerpo }`,
 * o `null` si no contestó dentro de `ms` o falló la conexión. Acá sí se
 * aborta el pedido, no solo la espera.
 *
 * El plazo cubre la respuesta ENTERA, no solo la cabecera. Un AbortController
 * propio y no `AbortSignal.timeout`: este obedece al reloj del proceso --lo
 * que permite probarlo con temporizadores falsos-- y se limpia al terminar.
 *
 * Una respuesta que llegó con error (un 404, un 500) NO es null: vuelve con
 * su `status`, porque quien llama decide si eso es "no existe" o "falló".
 *
 * @param {typeof fetch} fetch
 * @param {string} url
 * @param {RequestInit} init
 * @param {number} ms
 * @param {string} [nombre]
 * @returns {Promise<{ ok: boolean, status: number, cuerpo: any } | null>}
 */
export async function leerConPlazo(fetch, url, init, ms, nombre) {
  const control = new AbortController();
  const reloj = setTimeout(() => control.abort(), ms);
  try {
    const r = await fetch(url, { ...init, signal: control.signal });
    const cuerpo = await r.json().catch(() => null);
    if (control.signal.aborted) return avisar(nombre, `plazo de ${ms} ms`);
    if (!r.ok) avisar(nombre, `error ${r.status}`);
    return { ok: r.ok, status: r.status, cuerpo };
  } catch (/** @type {any} */ err) {
    return avisar(nombre, control.signal.aborted ? `plazo de ${ms} ms` : `error ${err?.name ?? 'desconocido'}`);
  } finally {
    clearTimeout(reloj);
  }
}
