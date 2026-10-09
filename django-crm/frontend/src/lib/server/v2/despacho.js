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
 * @param {{ cookies: any }} ctx
 * @param {boolean} conFicha
 */
export async function leerCasosDespachables(ctx, conFicha = false) {
  try {
    const d = await apiRequest(
      `/campo/casos-despachables/${conFicha ? '?ficha=1' : ''}`, {}, ctx
    );
    return { casos: d?.casos ?? [], tope: d?.tope ?? 0, error: false };
  } catch {
    return { casos: [], tope: 0, error: true };
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
export async function despacharACampo(ctx, cuerpo, idempotencia) {
  return apiRequest('/campo/trabajos/crear/', {
    method: 'POST',
    body: cuerpo,
    headers: { 'Idempotency-Key': idempotencia }
  }, ctx);
}
