/**
 * Solicitudes de instalación: la bandeja donde se decide, y sus ajustes.
 *
 * Todo va contra Django y no contra el motor, aunque los ajustes terminen en
 * la config del tenant: la bandeja vive en Django (es una tabla nuestra), y
 * partir la pantalla entre dos backends por un par de variables sólo agrega
 * un lugar más donde algo puede fallar. Django hace ese salto por dentro.
 */
import { env } from '$env/dynamic/private';
import { env as publicEnv } from '$env/dynamic/public';

const API = `${env.PRIVATE_DJANGO_API_URL || publicEnv.PUBLIC_DJANGO_API_URL}/api`;

async function pedir(fetch, ruta, opciones = {}) {
  const res = await fetch(`${API}${ruta}`, {
    ...opciones,
    headers: { 'Content-Type': 'application/json', ...(opciones.headers || {}) }
  });
  if (!res.ok) {
    const cuerpo = await res.json().catch(() => ({}));
    throw new Error(cuerpo?.error || cuerpo?.detail || `El servidor respondió ${res.status}`);
  }
  return res.json();
}

/**
 * Las solicitudes que esperan una decisión. Nunca lanza: no poder listar es
 * una pantalla vacía con un aviso, no un error que tumba la navegación.
 */
export async function leerBandeja(fetch, estado = '') {
  try {
    const q = estado ? `?estado=${encodeURIComponent(estado)}` : '';
    return { solicitudes: (await pedir(fetch, `/solicitudes/bandeja/${q}`)).solicitudes ?? [] };
  } catch (/** @type {any} */ err) {
    return { solicitudes: [], error: err?.message || 'No se pudo leer la bandeja.' };
  }
}

/** Los dos equipos configurados hoy. */
export async function leerAjustes(fetch) {
  try {
    return await pedir(fetch, '/solicitudes/ajustes/');
  } catch (/** @type {any} */ err) {
    return { error: err?.message || 'No se pudo leer la configuración.' };
  }
}

/** El personal de WispHub, para elegir de una lista en vez de escribir un id. */
export async function leerTecnicos(fetch) {
  try {
    return (await pedir(fetch, '/solicitudes/tecnicos/')).tecnicos ?? [];
  } catch {
    // Sin lista, la pantalla cae a campos de texto: poder configurar aunque
    // WispHub no responda vale más que una lista perfecta.
    return [];
  }
}

export async function guardarAjustes(fetch, valores) {
  return pedir(fetch, '/solicitudes/ajustes/', {
    method: 'PUT',
    body: JSON.stringify(valores)
  });
}

/** Aprobar o rechazar. Aprobar mueve el ticket de WispHub al equipo que instala. */
export async function decidir(fetch, id, aprueba, nota) {
  return pedir(fetch, `/solicitudes/${id}/decidir/`, {
    method: 'POST',
    body: JSON.stringify({ aprueba, nota })
  });
}
